#!/usr/bin/env python3
"""Extract a release and prove local authoring/build/Play without a browser.
Run with a fresh Python venv. --forbid-read/--network-denied assert an OS sandbox
configured by the caller; this program cannot grant itself isolation.
"""
import argparse
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import socket
import subprocess
import sys
import tempfile
import zipfile


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--forbid-read', type=Path, action='append', default=[])
    parser.add_argument('--network-denied', action='store_true')
    parser.add_argument('--wheelhouse', type=Path, help='Optional local Python wheels for offline installation')
    args = parser.parse_args()
    import pydantic
    import PIL
    if sys.prefix == sys.base_prefix:
        raise ValueError('Run in a fresh virtual environment with requirements.txt installed')
    prefix = Path(sys.prefix).resolve()
    for module in (pydantic, PIL):
        if not Path(module.__file__).resolve().is_relative_to(prefix):
            raise ValueError('Dependency is not from the current virtual environment')
    for path in args.forbid_read:
        try:
            list(path.iterdir())
        except PermissionError:
            continue
        raise ValueError('Expected OS read denial did not occur')
    if args.network_denied:
        with socket.socket() as sock:
            try:
                sock.connect(('127.0.0.1', 9))
            except OSError as error:
                if error.errno not in (errno.EPERM, errno.EACCES):
                    raise ValueError('Expected OS network denial did not occur') from error
            else:
                raise ValueError('Network sandbox is not active')
    work = Path(tempfile.mkdtemp(prefix='manba-release-')).resolve()
    unpack = work / '独立开发 空格路径'
    with zipfile.ZipFile(args.archive) as archive:
        for entry in archive.infolist():
            if not (unpack / entry.filename).resolve().is_relative_to(unpack.resolve()):
                raise ValueError('Unsafe release archive path')
        archive.extractall(unpack)
    root = unpack / 'manba-ai-game'
    sys.path.insert(0, str(root / 'tools'))
    from check_project import PROJECT_FILES, check_zip_inventory
    with zipfile.ZipFile(args.archive) as archive:
        check_zip_inventory(archive, {'manba-ai-game/' + name for name in PROJECT_FILES | {'MANIFEST.json'}})
    manifest = json.loads((root / 'MANIFEST.json').read_text())
    for name, expected in manifest['files'].items():
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != expected:
            raise ValueError('Release manifest mismatch: ' + name)
    env = dict(os.environ)
    for name in list(env):
        if name in ('PYTHONPATH', 'PYTHONHOME') or name.startswith('POCKET_ARCADE_'):
            env.pop(name)
    env['PYTHONNOUSERSITE'] = '1'
    env['PATH'] = str(prefix / 'bin') + ':/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin'
    if args.wheelhouse:
        env['PIP_NO_INDEX'] = '1'
        env['PIP_FIND_LINKS'] = str(args.wheelhouse.resolve())
    checks = []
    def run(name, *command, extra_env=None):
        print(name, flush=True)
        result = subprocess.run([str(x) for x in command], cwd=root,
                                env=dict(env, **(extra_env or {})), capture_output=True, text=True)
        (work / (name + '.log')).write_text(result.stdout + result.stderr)
        if result.returncode:
            print(result.stdout[-6000:] + result.stderr[-6000:])
            raise RuntimeError(f'{name} failed; logs retained at {work}')
        checks.append(name)
        return result.stdout + result.stderr
    # Execute the published commands, with no parallel copy of their arguments.
    guide = (root / 'docs/AUTHORING.md').read_text()
    commands = [shlex.split(line) for block in re.findall(r'```sh\n(.*?)```', guide, re.S)
                for line in block.replace('\\\n', ' ').splitlines() if line.strip()]
    executed_commands = []
    def documented(name):
        if not commands:
            raise ValueError('Missing documented command: ' + name)
        command = commands.pop(0)
        result = run(name, *command)
        executed_commands.append(command)
        return result
    for name in ('python', 'node'):
        documented('prerequisite-' + name)
    documented('create-project-venv')
    documented('install-project-dependencies')
    py = root / '.venv/bin/python'
    environment = json.loads(run('project-environment', py, '-c',
        "import json,sys,pydantic,PIL; from pathlib import Path; "
        "print(json.dumps({'python':sys.version.split()[0], 'pydantic':pydantic.__version__, "
        "'pillow':PIL.__version__, 'isolated':sys.prefix != sys.base_prefix, "
        "'local_dependencies':all(Path(m.__file__).resolve().is_relative_to(Path(sys.prefix).resolve()) for m in (pydantic,PIL))}))"))
    if not environment['isolated'] or not environment['local_dependencies']:
        raise ValueError('Project dependencies are not isolated')
    run('integrity', py, 'tools/check_project.py')
    python_tests = run('python-tests', py, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_*.py')
    documented('sdk-runtime-setup')
    source = root / '.work/my-game'
    documented('new-game')
    spec = json.loads((source / 'spec.json').read_text())
    records = re.search(r'^-- @records-key [0-9a-f]{64}$', spec['code'], re.M).group()
    fixture = root / 'tests/fixtures/portable'
    spec.update(json.loads((fixture / 'rules.json').read_text()))
    spec['name'] = 'Lane Courier'
    spec['ui']['controller']['hint'] = 'LEFT/RIGHT: lanes; collect 3, miss 3 and lose. A starts.'
    spec['code'] = 'function init() end\n'
    write(source / 'spec.json', spec)
    (source / 'game.lua').write_text(spec['code'])
    documented('freeze-rules-before-code')
    frozen_sha = hashlib.sha256((source / 'frozen-tests.json').read_bytes()).hexdigest()
    code = re.sub(r'^-- @records-key [0-9a-f]{64}$', records, (fixture / 'game.lua').read_text(), flags=re.M)
    (source / 'game.lua').write_text(code)
    # Deliberately leave spec.code stale: the documented flow edits game.lua only.
    source_spec = (source / 'spec.json').read_bytes()
    from PIL import Image, ImageDraw
    art = source / 'art'
    art.mkdir()
    # Procedural test images, each with its own composition and native size.
    parcel = Image.new('RGBA', (16, 16)); draw = ImageDraw.Draw(parcel)
    draw.rectangle((1, 2, 14, 14), fill=(235, 173, 66, 255)); draw.rectangle((6, 2, 9, 14), fill=(255, 235, 193, 255))
    parcel.save(art / 'parcel.png')
    icon = Image.new('RGB', (128, 96), '#102a34'); draw = ImageDraw.Draw(icon)
    draw.polygon([(15, 95), (48, 4), (80, 4), (113, 95)], fill='#365864'); draw.rectangle((43, 30, 85, 72), fill='#efb94e'); draw.rectangle((60, 30, 68, 72), fill='#ffebc0')
    icon.save(art / 'icon.png')
    write(art / 'pack.json', {'format': 'bitmap-pack/1', 'sprites': [{'name': 'parcel', 'file': 'parcel.png', 'size': [16, 16], 'encoding': 'indexed8-alpha4', 'transparent': True, 'trim': False, 'resample': 'nearest', 'pivot': [8, 8]}]})
    documented('compile-hd-art')
    build = root / '.work/my-game-v1'
    documented('build-new-game')
    built_spec = json.loads((build / 'spec.json').read_text())
    if built_spec['code'] != code or (source / 'spec.json').read_bytes() != source_spec:
        raise ValueError('Build did not use the latest Lua or changed source configuration')
    if not all(built_spec.get(name) for name in ('bitmaps', 'launcher_card', 'launcher_icon')):
        raise ValueError('Build did not include the authored assets')
    if hashlib.sha256((source / 'frozen-tests.json').read_bytes()).hexdigest() != frozen_sha:
        raise ValueError('Frozen rules changed')
    victory = spec['tests'][2]['actions']
    trace = [{'name': 'Repeated full victory and restart', 'actions': (victory + [{'kind': 'input', 'value': 'restart'}]) * 20, 'restart_on_over': False}]
    write(source / 'stress.json', trace)
    documented('performance')
    performance = json.loads((build / 'performance.json').read_text())
    if performance['scenarios'][0]['running_step_results'] < 1000:
        raise ValueError('Performance trace did not exercise active gameplay')
    if commands:
        raise ValueError('Unverified commands remain in the development guide')
    # Cover the documented alternatives as well as the primary PNG flow.
    variants = {}
    for name, flags, expected_bitmaps in (
            ('geometry', [], 0),
            ('title-art', ['--bindings', art / 'compiled/bindings.json', '--title-art', art / 'title.png'], 7)):
        if name == 'title-art':
            title = Image.new('RGB', (320, 240), '#102a34')
            ImageDraw.Draw(title).rectangle((80, 60, 240, 180), fill='#efb94e')
            title.save(art / 'title.png')
        variant = root / '.work' / name
        run('build-' + name, py, 'tools/game.py', 'build', source, '--icon', art / 'icon.png',
            '--output', variant, *flags)
        package = json.loads((variant / 'game.edgegame').read_text())
        count = len(package['assets'].get('bitmaps', []))
        if count != expected_bitmaps:
            raise ValueError('Unexpected atlas for ' + name)
        run('play-' + name, 'node', '--test', 'tests/play.test.mjs', extra_env={
            'MANBA_TEST_PACKAGE':str(variant / 'game.edgegame'), 'MANBA_TEST_SPEC':str(variant / 'spec.json')})
        variants[name] = {'passed': True, 'bitmap_count': count,
                          'wasm_observations': json.loads((variant / 'native-wasm.json').read_text())['observations']}
    node_tests = run('shipped-play-import-and-audio', 'node', '--test', 'tests/play.test.mjs', 'tests/offline-audio.test.mjs', extra_env={'MANBA_TEST_PLAY':str(root / 'play.html'), 'MANBA_TEST_PACKAGE':str(build / 'game.edgegame'), 'MANBA_TEST_SPEC':str(build / 'spec.json')})
    validation = json.loads((build / 'validation.json').read_text())
    wasm = json.loads((build / 'native-wasm.json').read_text())
    report = {'passed':True, 'archive_sha256':hashlib.sha256(args.archive.read_bytes()).hexdigest(),
              'manifest_files_verified':len(manifest['files']), 'python':environment['python'], 'pydantic':environment['pydantic'], 'pillow':environment['pillow'],
              'fresh_venv':True, 'dependency_locations_within_venv':True, 'os_denied_source_directories':len(args.forbid_read), 'os_network_denied':args.network_denied,
              'path_contains_spaces_and_unicode':True, 'checks':checks, 'frozen_rules_sha256':frozen_sha,
              'node_tests_passed':int(re.search(r'# pass (\d+)', node_tests).group(1)), 'python_tests_passed':int(re.search(r'Ran (\d+) tests', python_tests).group(1)), 'performance_running_step_results':performance['scenarios'][0]['running_step_results'],
              'new_game':{'name':spec['name'], 'package_sha256':validation['package_sha256'], 'frozen_cases':validation['frozen_cases'], 'bitmap_count':validation['bitmap_count'], 'wasm_observations':wasm['observations']},
              'guide':'docs/AUTHORING.md', 'documented_commands_executed':executed_commands,
              'latest_lua_used_with_assets':True, 'source_configuration_unchanged':True,
              'build_variants':variants, 'archive_inventory_verified':True,
              'browser_tested':False,
              'scope':'New authored rules/implementation, actual native and Wasm, release Play with Node Worker and DOM doubles; no browser UI claim'}
    write(args.output, report)
    print(json.dumps({'report':str(args.output), 'work':str(work), 'passed':True}), flush=True)


if __name__ == '__main__':
    main()
