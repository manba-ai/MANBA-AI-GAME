#!/usr/bin/env python3
"""SDK initialization and game package build helpers for tools/game.py."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def extract(archive, target):
    with zipfile.ZipFile(archive) as source:
        for item in source.infolist():
            dest = (target/item.filename).resolve()
            if not dest.is_relative_to(target.resolve()):
                raise ValueError('Unsafe archive path')
        source.extractall(target)


def use_sdk(path):
    root = path.resolve()
    if not (root/'SDK-MANIFEST.json').is_file():
        raise ValueError('Run init into a writable workspace first')
    sys.path.insert(0, str(root))
    return root


def init(args):
    dest = args.sdk.resolve()
    if dest.exists():
        raise ValueError('SDK destination exists; select a new empty path')
    if sys.version_info < (3, 11, 8):
        raise ValueError('Python 3.11.8+ required')
    if not shutil.which('node'):
        raise ValueError('Node.js 20+ required')
    version = subprocess.run(['node', '--version'], capture_output=True, text=True, check=True).stdout.strip()
    if int(version.lstrip('v').split('.')[0]) < 20:
        raise ValueError('Node.js 20+ required')
    system, machine = platform.system().lower(), platform.machine().lower()
    machine = {'amd64': 'x86_64', 'arm64': 'aarch64'}.get(machine, machine)
    if system == 'darwin' and machine == 'aarch64':
        machine = 'arm64'
    target = system + '-' + machine
    if target not in ('darwin-arm64', 'darwin-x86_64', 'linux-x86_64', 'linux-aarch64'):
        raise ValueError('Supported development systems: macOS 11+ and Linux, x86_64/arm64; use WSL2 on Windows')
    import pydantic
    import PIL
    if int(pydantic.__version__.split('.')[0]) != 2:
        raise ValueError('Pydantic 2 required')
    extract(ROOT/'sdk/sdk.zip', dest)
    manifest = json.loads((dest/'SDK-MANIFEST.json').read_text())
    for name, expected in manifest['files'].items():
        if sha((dest/name).read_bytes()) != expected:
            raise ValueError(f'SDK checksum mismatch: {name}')
    binaries = dest/'.tools/bin'
    binaries.mkdir(parents=True)
    for name in ('luac', 'game-runner', 'package-json-probe'):
        executable = binaries/name
        shutil.copyfile(dest/'runtime/bin'/target/name, executable)
        executable.chmod(0o755)
    subprocess.run([str(binaries/'luac'), '-v'], check=True, capture_output=True)
    print(json.dumps({'sdk': str(dest), 'platform': target, 'checksums_verified': len(manifest['files']),
                      'pydantic': pydantic.__version__, 'pillow': PIL.__version__}))


def prepare(args):
    use_sdk(args.sdk)
    from PIL import Image
    from scripts.bitmap_pack import compile_pack, encode_v2
    from compiler.bitmaps import pack
    from compiler.packages import validate_launcher_icon
    spec = json.loads(args.spec.read_text())
    if args.bindings:
        bindings = json.loads(args.bindings.read_text())
        if bindings.get('runtime_profile', 'legacy') != spec.get('runtime_profile', 'legacy'):
            raise ValueError('Asset and GameSpec runtime_profile differ; choose the same explicit resource budget')
        spec.update(bitmaps=bindings['bitmaps'], sprite_manifest=bindings['sprite_manifest'])
        data = dict(spec.get('data') or {})
        for key, value in bindings['data'].items():
            if key in data and data[key] != value:
                raise ValueError(f'Conflicting data.{key}; explicitly update stale art bindings')
            data[key] = value
        spec['data'] = data
    output = args.output.resolve()
    artdir = output.parent/(output.stem+'-compiled')
    artdir.mkdir(parents=True, exist_ok=True)
    with Image.open(args.icon) as source:
        if source.width != source.height or source.convert('RGBA').getextrema()[3] != (255, 255):
            raise ValueError('Icon source must be opaque square art; compiled size is 80x80')
        spec['launcher_icon'] = validate_launcher_icon(pack(encode_v2(source, (80, 80), transparent=False)))
    if args.title_art:
        with Image.open(args.title_art) as source:
            if abs(source.width/source.height-4/3) > .01:
                raise ValueError('Title illustration must have a 4:3 composition')
            source.convert('RGB').resize((320, 240), Image.Resampling.LANCZOS).save(artdir/'title.png')
        entries = [{'name': f'title{i}', 'file': 'title.png', 'rect': [x, y, w, h],
                    'size': [w, h], 'encoding': 'indexed8-alpha4', 'transparent': False,
                    'trim': False, 'resample': 'nearest', 'role': 'cover'}
                   for i, (x, y, w, h) in enumerate((x, y, min(128, 320-x), min(128, 240-y))
                                                  for y in (0, 128) for x in (0, 128, 256))]
        write_json(artdir/'title-pack.json', {'format': 'bitmap-pack/1', 'sprites': entries})
        result = compile_pack(artdir/'title-pack.json', artdir/'title')
        spec['cover'] = {'version': 4, 'title': spec['name'].upper(),
                         'description': spec['description'][:120],
                         'bitmaps': json.loads(Path(result['atlas']).read_text())}
    spec['bitmap_compression'] = 'zlib'
    write_json(output, spec)
    print(json.dumps({'prepared_spec': str(output)}))


def compile_game(root, source, frozen, output):
    from compiler.authoring.schema import build, GameSpec
    from compiler.authoring.runtime import validate_runtime
    from compiler.packages import encode
    from compiler.bitmaps import pack, unpack
    if not re.search(r'^-- @records-key [0-9a-f]{64}$', source['code'], re.M):
        raise ValueError('Portable custom path requires @records-key and authored records callbacks; see docs/GAME_API.md')
    if '-- @manba-template' in source['code']:
        raise ValueError('Implement the game callbacks and remove @manba-template before building')
    normalized = GameSpec.model_validate(source).model_dump(mode='json', exclude_none=True)
    if normalized['tests'] != frozen:
        raise ValueError('Frozen acceptance differs: restore tests or perform a separately documented rule revision')
    package, normalized = build(source)
    raw = encode(package)
    output.mkdir(parents=True, exist_ok=True)
    failed = output/('candidate-'+sha(raw)[:12]+'.edgegame')
    failed.write_bytes(raw)
    checks = validate_runtime(package, normalized['tests'])
    # Check package parsing with the bounded C++ JSON parser as well.
    parsed = subprocess.run([str(root/'.tools/bin/package-json-probe')], input=raw,
                            capture_output=True, check=True)
    # Compare every authored bitmap, including title tiles, to its stored form.
    baseline = list(source.get('bitmaps') or [])
    if (source.get('cover') or {}).get('version') == 4:
        baseline += source['cover']['bitmaps']
    bits = package.get('assets', {}).get('bitmaps', [])
    exact = len(baseline) == len(bits) and all(unpack(b) == unpack(a) for a, b in zip(baseline, bits))
    for b in bits:
        if unpack(pack(unpack(b))) != unpack(b):
            raise ValueError('Bitmap compression round-trip differs')
    if baseline and not exact:
        raise ValueError('Final bitmap atlas differs from authored baseline')
    target = output/'game.edgegame'
    failed.replace(target)
    report = {'package_sha256': sha(raw), 'package_bytes': len(raw),
              'code_bytes': len(package['code'].encode()), 'bitmap_count': len(bits),
              'source_pixels': sum(b['width']*b['height'] for b in bits),
              'frozen_cases': len(frozen), 'authored_bitmap_equality': exact,
              'compression_roundtrip': True, 'arduinojson': parsed.stdout.decode().strip(),
              'native': checks}
    write_json(output/'validation.json', report)
    return report


def build(args):
    root = use_sdk(args.sdk)
    source = json.loads(args.spec.read_text())
    frozen = json.loads(args.frozen_tests.read_text())
    report = compile_game(root, source, frozen, args.output.resolve())
    print(json.dumps(report, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest='command', required=True)
    for name, func in [('init', init), ('prepare', prepare), ('build', build)]:
        sub = subs.add_parser(name)
        sub.add_argument('--sdk', required=True, type=Path)
        sub.set_defaults(func=func)
        if name in ('prepare', 'build'):
            sub.add_argument('--spec', required=True, type=Path)
        if name != 'init':
            sub.add_argument('--output', required=True, type=Path)
        if name == 'prepare':
            sub.add_argument('--bindings', type=Path)
            sub.add_argument('--icon', required=True, type=Path)
            sub.add_argument('--title-art', type=Path)
        if name == 'build':
            sub.add_argument('--frozen-tests', required=True, type=Path)
    args = parser.parse_args()
    args.func(args)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        raise SystemExit(1)
