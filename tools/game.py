#!/usr/bin/env python3
"""Create, validate and build MANBA game packages."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / 'tools'
TEMPLATES = ROOT / 'templates'


def run(*args):
    subprocess.run([str(x) for x in args], check=True, cwd=ROOT)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=Path, default=ROOT / '.work/sdk')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('setup', help='Verify and install bundled SDK tools and runtime')
    new = sub.add_parser('new', help='Create an empty authoring template in a new directory')
    new.add_argument('directory', type=Path)
    new.add_argument('--name', default='My Game', help='New game name, 1–24 characters')
    freeze = sub.add_parser('freeze', help='Normalize acceptance tests; refuse existing frozen file')
    freeze.add_argument('directory', type=Path)
    build = sub.add_parser('build', help='Build against frozen rules, then compare native and Wasm')
    build.add_argument('directory', type=Path)
    build.add_argument('--output', type=Path, required=True)
    build.add_argument('--bindings', type=Path, help='Compiled bitmap bindings.json')
    build.add_argument('--icon', type=Path, help='Opaque 4:3 PNG for package icons')
    build.add_argument('--title-art', type=Path, help='Optional 4:3 title illustration')
    args = parser.parse_args()
    sdk = args.sdk.resolve()
    if args.command == 'setup':
        run(sys.executable, TOOLS / 'edgegame.py', 'init', '--sdk', sdk)
        return
    folder = args.directory.resolve()
    if args.command == 'new':
        if not 1 <= len(args.name.strip()) <= 24:
            raise ValueError('Game name must contain 1–24 characters')
        folder.mkdir(parents=True, exist_ok=False)
        source = json.loads((TEMPLATES / 'spec.json').read_text(encoding='utf-8'))
        identity = 'game-' + uuid.uuid4().hex
        source['name'] = args.name.strip()
        source['records_id'] = identity
        code = (TEMPLATES / 'game.lua').read_text(encoding='utf-8')
        code = re.sub(r'^-- @records-key [0-9a-f]{64}$',
                      '-- @records-key ' + hashlib.sha256((identity + ':rules-v1').encode()).hexdigest(),
                      code, flags=re.M)
        source['code'] = code
        (folder / 'spec.json').write_text(json.dumps(source, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        (folder / 'game.lua').write_text(code, encoding='utf-8')
        print(f'Created {folder}. Write rules/tests, freeze, then implement game.lua.')
        return
    if not (sdk / 'SDK-MANIFEST.json').is_file():
        raise ValueError('SDK missing: run tools/game.py setup first')
    sys.path.insert(0, str(sdk))
    from compiler.authoring.schema import GameSpec
    source = json.loads((folder / 'spec.json').read_text(encoding='utf-8'))
    if (folder / 'game.lua').is_file():
        source['code'] = (folder / 'game.lua').read_text(encoding='utf-8')
    normalized = GameSpec.model_validate(source).model_dump(mode='json', exclude_none=True)
    if args.command == 'freeze':
        with (folder / 'frozen-tests.json').open('x', encoding='utf-8') as output:
            json.dump(normalized['tests'], output, ensure_ascii=False, indent=2)
            output.write('\n')
        print('Acceptance frozen. Rule changes require a new reviewed version.')
        return
    output = args.output.resolve()
    if (args.bindings or args.title_art) and not args.icon:
        raise ValueError('Asset preparation needs --icon with an opaque 4:3 PNG')
    if not args.icon and not source.get('launcher_card'):
        raise ValueError('Provide --icon with an opaque 4:3 PNG for the game icon')
    # Fresh directory makes failed candidates and earlier successful builds
    # unambiguous. The underlying builder retains failed packages for diagnosis.
    if output.exists():
        raise ValueError('Build output exists; choose a fresh version directory')
    frozen = folder / 'frozen-tests.json'
    if not frozen.is_file():
        raise ValueError('Missing frozen-tests.json; confirm rules and run freeze first')
    output.mkdir(parents=True)
    spec = output / 'spec.json'
    spec.write_text(json.dumps(source, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    if args.icon:
        prepare = [sys.executable, TOOLS / 'edgegame.py', 'prepare', '--sdk', sdk,
                   '--spec', spec, '--icon', args.icon.resolve(), '--output', spec]
        for flag, path in (('--bindings', args.bindings), ('--title-art', args.title_art)):
            if path:
                prepare.extend((flag, path.resolve()))
        run(*prepare)
    run(sys.executable, TOOLS / 'edgegame.py', 'build', '--sdk', sdk,
        '--spec', spec, '--frozen-tests', frozen, '--output', output)
    run('node', TOOLS / 'compare_runtime.mjs', sdk,
        output / 'game.edgegame', spec, output / 'native-wasm.json')
    print(f'Built {output / "game.edgegame"}; open it with play.html.')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, FileExistsError, FileNotFoundError, subprocess.CalledProcessError) as error:
        raise SystemExit(str(error))
