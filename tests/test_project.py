import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
import warnings
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('edgegame', ROOT / 'tools/edgegame.py')
edgegame = importlib.util.module_from_spec(spec)
spec.loader.exec_module(edgegame)
check_spec = importlib.util.spec_from_file_location('check_project', ROOT / 'tools/check_project.py')
checks = importlib.util.module_from_spec(check_spec)
check_spec.loader.exec_module(checks)


class LauncherIconTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workspace = tempfile.TemporaryDirectory()
        cls.sdk = Path(cls.workspace.name) / 'sdk'
        edgegame.extract(ROOT / 'sdk/sdk.zip', cls.sdk)
        sys.path.insert(0, str(cls.sdk))

    @classmethod
    def tearDownClass(cls):
        sys.path[:] = [entry for entry in sys.path if entry != str(cls.sdk)]
        cls.workspace.cleanup()

    def test_icon_preparation_outputs_only_80_square_icon(self):
        from PIL import Image
        from compiler.bitmaps import unpack
        from compiler.authoring.schema import GameSpec
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / 'spec.json'
            source.write_text('{}')
            icon = root / 'icon.png'
            Image.new('RGB', (80, 80), '#ff0000').save(icon)
            output = root / 'prepared.json'
            edgegame.prepare(SimpleNamespace(sdk=self.sdk, spec=source, icon=icon,
                                            bindings=None, title_art=None, output=output))
            prepared = json.loads(output.read_text())
            self.assertNotIn('launcher_card', prepared)
            self.assertEqual(set(prepared), {'launcher_icon', 'bitmap_compression'})
            image = prepared['launcher_icon']
            self.assertEqual((image['width'], image['height']), (80, 80))
            decoded = unpack(image)
            pixels = bytes.fromhex(decoded['pixels'])
            self.assertEqual(len(pixels), 6400)
            self.assertTrue(all(decoded['palette'][index*4:index*4+4] == 'f800'
                                and decoded['alpha'][index] == 'f' for index in pixels))
            self.assertEqual(list(root.rglob('icon-pack.json')), [])
            spec = json.loads((ROOT / 'templates/spec.json').read_text())
            spec.update(json.loads((ROOT / 'tests/fixtures/portable/rules.json').read_text()))
            spec.update(prepared, code=(ROOT / 'tests/fixtures/portable/game.lua').read_text())
            GameSpec.model_validate(spec)

    def test_icon_source_rejects_rectangular_and_transparent_art(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / 'spec.json'
            source.write_text('{}')
            for size, alpha in (((128, 96), 255), ((80, 80), 254)):
                with self.subTest(size=size, alpha=alpha):
                    icon = root / 'icon.png'
                    Image.new('RGBA', size, (255, 0, 0, alpha)).save(icon)
                    output = root / 'prepared.json'
                    with self.assertRaisesRegex(ValueError, 'square'):
                        edgegame.prepare(SimpleNamespace(sdk=self.sdk, spec=source, icon=icon,
                                                        bindings=None, title_art=None, output=output))
                    self.assertFalse(output.exists())

    def test_encoded_icon_requires_80_square_opaque_pixels(self):
        from PIL import Image
        from compiler.bitmaps import pack
        from compiler.packages import validate_launcher_icon
        from scripts.bitmap_pack import encode_v2
        for size in ((128, 96), (32, 24)):
            with self.subTest(size=size):
                icon = pack(encode_v2(Image.new('RGB', size, 'red'), size, transparent=False))
                with self.assertRaisesRegex(ValueError, '80×80'):
                    validate_launcher_icon(icon)
        transparent = pack(encode_v2(Image.new('RGBA', (80, 80)), (80, 80)))
        with self.assertRaisesRegex(ValueError, '不透明'):
            validate_launcher_icon(transparent)


class ProjectTests(unittest.TestCase):
    def test_archive_inventory_rejects_extra_source_archives_and_hidden_files(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'sdk.zip'
            for extra in ('engine.ts', 'source.zip', '.DS_Store', '__pycache__/engine.pyc'):
                with zipfile.ZipFile(path, 'w') as archive:
                    archive.writestr('runtime.wasm', b'\0asm')
                    archive.writestr(extra, 'unexpected')
                with zipfile.ZipFile(path) as archive:
                    with self.assertRaisesRegex(ValueError, 'inventory differs'):
                        checks.check_zip_inventory(archive, {'runtime.wasm'})

    def test_archive_inventory_rejects_duplicate_names(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'sdk.zip'
            with warnings.catch_warnings():
                warnings.simplefilter('ignore', UserWarning)
                with zipfile.ZipFile(path, 'w') as archive:
                    archive.writestr('runtime.wasm', b'\0asm')
                    archive.writestr('runtime.wasm', 'source hidden by duplicate name')
            with zipfile.ZipFile(path) as archive:
                with self.assertRaisesRegex(ValueError, 'Duplicate'):
                    checks.check_zip_inventory(archive, {'runtime.wasm'})

    def test_new_games_have_independent_consistent_records_identity(self):
        with tempfile.TemporaryDirectory() as temp:
            identities, keys = set(), set()
            for index in range(2):
                folder = Path(temp) / str(index)
                subprocess.run([sys.executable, str(ROOT / 'tools/game.py'), 'new',
                                str(folder), '--name', 'New Game'], check=True, capture_output=True)
                spec = json.loads((folder / 'spec.json').read_text())
                code = (folder / 'game.lua').read_text()
                key = re.search(r'^-- @records-key ([0-9a-f]{64})$', code, re.M).group(1)
                self.assertEqual(spec['code'], code)
                self.assertEqual(spec['name'], 'New Game')
                self.assertEqual(spec['rules'], [])
                self.assertEqual(spec['tests'], [])
                self.assertIn('-- @manba-template', code)
                self.assertEqual(key, hashlib.sha256((spec['records_id'] + ':rules-v1').encode()).hexdigest())
                identities.add(spec['records_id'])
                keys.add(key)
            self.assertEqual(len(identities), 2)
            self.assertEqual(len(keys), 2)

    def test_new_game_does_not_overwrite_existing_work(self):
        with tempfile.TemporaryDirectory() as temp:
            game = Path(temp) / 'game'
            command = [sys.executable, str(ROOT / 'tools/game.py'), 'new', str(game)]
            first = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            (game / 'game.lua').write_text('user work')
            second = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(second.returncode, 0)
            self.assertEqual((game / 'game.lua').read_text(), 'user work')

    def test_sdk_archive_traversal_rejected_before_writing(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / 'sdk.zip'
            with zipfile.ZipFile(archive, 'w') as z:
                z.writestr('../outside.txt', 'no')
            with self.assertRaisesRegex(ValueError, 'Unsafe archive path'):
                edgegame.extract(archive, root / 'sdk')
            self.assertFalse((root / 'outside.txt').exists())


if __name__ == '__main__':
    unittest.main()
