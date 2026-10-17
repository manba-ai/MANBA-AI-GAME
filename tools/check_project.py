#!/usr/bin/env python3
"""Check game SDK contents, documentation links and Play runtime checksums."""
import argparse
import hashlib
import json
from pathlib import Path
import posixpath
import re
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]


PROJECT_FILES = frozenset("""
.gitignore
AGENTS.md
README.md
SOURCE.json
THIRD_PARTY.md
contracts/km013-st7789-i8080-v1.json
docs/ASSETS.md
docs/AUTHORING.md
docs/GAME_API.md
docs/GAME_LIMITS.md
docs/PLAY.md
docs/VALIDATION.md
licenses/ArduinoJson.txt
licenses/Lua.txt
licenses/Wasmoon.txt
licenses/Zig.txt
licenses/fflate.txt
licenses/font-source.txt
licenses/font.txt
licenses/libcxx.txt
licenses/libcxxabi.txt
licenses/libunwind.txt
licenses/miniz.txt
licenses/musl.txt
play.build.json
play.html
reports/VALIDATION.md
reports/independent-build.json
requirements.txt
sdk/sdk.zip
templates/game.lua
templates/spec.json
tests/fixtures/portable/game.lua
tests/fixtures/portable/rules.json
tests/offline-audio.test.mjs
tests/offline-worker-host.mjs
tests/play.test.mjs
tests/runtime-fixtures.mjs
tests/test_project.py
tools/check_project.py
tools/compare_runtime.mjs
tools/edgegame.py
tools/game.py
tools/package_project.py
tools/verify_portable.py
""".split())

SDK_FILES = frozenset("""
SDK-MANIFEST.json
THIRD_PARTY.md
compiler/__init__.py
compiler/assets.py
compiler/audio.py
compiler/authoring/__init__.py
compiler/authoring/runtime.py
compiler/authoring/schema.py
compiler/bitmaps.py
compiler/cover_art.py
compiler/diagnostics.py
compiler/game_contract.py
compiler/lua.py
compiler/packages.py
compiler/records.py
contracts/km013-st7789-i8080-v1.json
docs/AUDIO.md
docs/BITMAP_ASSETS.md
docs/ENGINE_V2.md
docs/GAME_PERFORMANCE_GUIDE.md
docs/SDK.md
games/audio-lifecycle-v2.lua
games/audio.lua
games/cover.lua
games/library/graphics-v2.lua
licenses/ArduinoJson.txt
licenses/Lua.txt
licenses/Wasmoon.txt
licenses/Zig.txt
licenses/fflate.txt
licenses/libcxx.txt
licenses/libcxxabi.txt
licenses/libunwind.txt
licenses/miniz.txt
licenses/musl.txt
runtime/bin/darwin-arm64/game-runner
runtime/bin/darwin-arm64/luac
runtime/bin/darwin-arm64/package-json-probe
runtime/bin/darwin-x86_64/game-runner
runtime/bin/darwin-x86_64/luac
runtime/bin/darwin-x86_64/package-json-probe
runtime/bin/linux-aarch64/game-runner
runtime/bin/linux-aarch64/luac
runtime/bin/linux-aarch64/package-json-probe
runtime/bin/linux-x86_64/game-runner
runtime/bin/linux-x86_64/luac
runtime/bin/linux-x86_64/package-json-probe
runtime/glue.wasm
runtime/play-runtime.cjs
scripts/__init__.py
scripts/bitmap_pack.py
scripts/build_bitmap_pack.py
scripts/profile_game_performance.py
""".split())

def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def check_zip_inventory(archive, allowed):
    names = archive.namelist()
    if len(names) != len(set(names)):
        raise ValueError('Duplicate archive entries')
    if set(names) != set(allowed):
        raise ValueError('Archive file inventory differs: ' + str(sorted(set(names) ^ set(allowed))))
    for item in archive.infolist():
        if item.is_dir() or (item.external_attr >> 16) & 0o170000 == 0o120000:
            raise ValueError('Archive entry must be a regular file: ' + item.filename)


def check_scope(names):
    for name in names:
        parts = Path(name).parts
        if any(re.search(r'^(?:firmware|hardware|flash|serial|partition)(?:[_.-]|s\b|$)', part, re.I) for part in parts) or name.endswith('.ino'):
            raise ValueError('Unexpected component in game development package: ' + name)
        if name.endswith('.edgegame'):
            raise ValueError('Generated package must stay in the game workspace: ' + name)
        if name.endswith(('.c', '.cc', '.cpp', '.h', '.hpp', '.map', '.tar.gz')) or 'web' in parts:
            raise ValueError('Unexpected runtime source file: ' + name)
        if Path(name).name in ('build_host_tools.py', 'sync_game_contract.py', 'build_play.py', 'player_bundle.py', 'render_frames.py'):
            raise ValueError('Unexpected runtime development tool: ' + name)


def check_archive_docs(archive):
    names = set(archive.namelist())
    check_scope(names)
    checked = 0
    for name in names:
        if not name.endswith('.md'):
            continue
        content = archive.read(name).decode('utf-8')
        if re.search(r'/(?:Users|Volumes)/|\.\./Game/', content):
            raise ValueError('Non-portable documentation path: ' + name)
        if re.search(r'requirements-tools|server[/\.]|编辑器|刷机|固件|串口|ai-passport', content, re.I):
            raise ValueError('Obsolete SDK documentation: ' + name)
        for target in re.findall(r'`((?:compiler|scripts|games|contracts)/[^`\s]+)`', content):
            if target not in names:
                raise ValueError(f'Missing SDK reference: {name}: {target}')
        for target in re.findall(r'\]\(([^)#]+)(?:#[^)]*)?\)', content):
            if '://' in target or target.startswith('#'):
                continue
            resolved = posixpath.normpath(posixpath.join(posixpath.dirname(name), target))
            if resolved not in names:
                raise ValueError(f'Broken SDK documentation link: {name}: {target}')
            checked += 1
    return checked


def check(root=ROOT):
    source = json.loads((root / 'SOURCE.json').read_text())
    for name, expected in source['archives'].items():
        if sha((root / name).read_bytes()) != expected:
            raise ValueError('Archive checksum changed: ' + name)
    contract = (root / 'contracts/km013-st7789-i8080-v1.json').read_bytes()
    if sha(contract) != source['contract_sha256']:
        raise ValueError('Contract checksum mismatch')
    with zipfile.ZipFile(root / 'sdk/sdk.zip') as archive:
        check_zip_inventory(archive, SDK_FILES)
        archive_links = check_archive_docs(archive)
        manifest = json.loads(archive.read('SDK-MANIFEST.json'))
        if set(archive.namelist()) != set(manifest['files']) | {'SDK-MANIFEST.json'}:
            raise ValueError('SDK manifest does not cover all files')
        for name, expected in manifest['files'].items():
            if sha(archive.read(name)) != expected:
                raise ValueError('SDK file checksum mismatch: ' + name)
        if archive.read('contracts/km013-st7789-i8080-v1.json') != contract:
            raise ValueError('Project and SDK contracts differ')
        runtime_hashes = {name: sha(archive.read('runtime/' + name)) for name in ('play-runtime.cjs', 'glue.wasm')}
        if not archive.read('runtime/glue.wasm').startswith(b'\0asm\x01\0\0\0'):
            raise ValueError('Invalid Wasm runtime')
        if any(token in archive.read('runtime/play-runtime.cjs') for token in (b'sourceMappingURL', b'sourcesContent')):
            raise ValueError('Runtime bundle includes source maps')
        for target in ('darwin-arm64', 'darwin-x86_64', 'linux-x86_64', 'linux-aarch64'):
            for tool in ('luac', 'game-runner', 'package-json-probe'):
                raw = archive.read(f'runtime/bin/{target}/{tool}')
                if not raw.startswith(b'\xcf\xfa\xed\xfe' if target.startswith('darwin') else b'\x7fELF'):
                    raise ValueError('Invalid bundled executable: ' + target + '/' + tool)
    report = json.loads((root / 'play.build.json').read_text())
    html = (root / 'play.html').read_bytes()
    if b'sourceMappingURL' in html or b'sourcesContent' in html:
        raise ValueError('Play includes source maps')
    if report['html_sha256'] != sha(html) or report['contract_sha256'] != sha(contract):
        raise ValueError('Play file or contract checksum mismatch')
    worker = re.search(r'const __workerSource=("(?:[^"\\]|\\.)*");', html.decode())
    if not worker or sha(json.loads(worker[1]).encode()) != report['worker_sha256']:
        raise ValueError('Embedded Play runtime checksum mismatch')
    if report.get('sdk_runtime') != runtime_hashes or sha(contract) not in json.loads(worker[1]):
        raise ValueError('Play and SDK runtime release mismatch')
    if report.get('bundled_games') != 0:
        raise ValueError('Unexpected bundled game in Play')
    names = [str(p.relative_to(root)) for p in root.rglob('*') if p.is_file() and p.relative_to(root).as_posix() != 'MANIFEST.json'
             and not any(part.startswith('.') or part in ('dist', '__pycache__') for part in p.relative_to(root).parts)]
    check_scope(names)
    if set(names) != PROJECT_FILES - {'.gitignore'}:
        raise ValueError('Project file inventory differs: ' + str(sorted(set(names) ^ (PROJECT_FILES - {'.gitignore'}))))
    if (root / 'MANIFEST.json').exists():
        release = json.loads((root / 'MANIFEST.json').read_text())['files']
        if set(release) != PROJECT_FILES:
            raise ValueError('Project manifest file inventory differs')
        for name, expected in release.items():
            if sha((root / name).read_bytes()) != expected:
                raise ValueError('Release file checksum mismatch: ' + name)
    links = 0
    docs = [root / 'README.md', root / 'AGENTS.md',
            *sorted((root / 'docs').glob('*.md')), *sorted((root / 'reports').glob('*.md'))]
    for doc in docs:
        for target in re.findall(r'\]\(([^)#]+)(?:#[^)]*)?\)', doc.read_text()):
            if '://' in target or target.startswith('#'):
                continue
            if not (doc.parent / target).exists():
                raise ValueError(f'Broken link in {doc.relative_to(root)}: {target}')
            links += 1
    return {'passed': True, 'sdk_files_verified': len(manifest['files']), 'links_verified': links,
            'sdk_document_links_verified': archive_links, 'contract_sha256': sha(contract), 'browser_tested': False}


def check_release(path):
    with zipfile.ZipFile(path) as archive, tempfile.TemporaryDirectory(prefix='manba-audit-') as work:
        check_zip_inventory(archive, {'manba-ai-game/' + name for name in PROJECT_FILES | {'MANIFEST.json'}})
        archive.extractall(work)
        return {**check(Path(work) / 'manba-ai-game'), 'archive_sha256': sha(path.read_bytes()),
                'project_files_verified': len(PROJECT_FILES), 'archive_inventory_verified': True}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, help='Check both archive layers and every distributed file')
    args = parser.parse_args()
    try:
        print(json.dumps(check_release(args.archive) if args.archive else check(), indent=2))
    except (ValueError, FileNotFoundError, KeyError, zipfile.BadZipFile) as error:
        raise SystemExit(str(error))
