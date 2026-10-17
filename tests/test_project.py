import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
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
