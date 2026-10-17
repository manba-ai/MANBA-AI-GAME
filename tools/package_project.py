#!/usr/bin/env python3
"""Deterministic, explicit-scope portable project ZIP; excludes local work/tools."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile
from check_project import check, PROJECT_FILES

ROOT = Path(__file__).resolve().parents[1]
def package(output):
    check()
    files = {name: (ROOT / name).read_bytes() for name in PROJECT_FILES}
    manifest = {'format': 'manba.project-package/1',
                'files': {name: hashlib.sha256(raw).hexdigest() for name, raw in sorted(files.items())}}
    files['MANIFEST.json'] = (json.dumps(manifest, indent=2) + '\n').encode()
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, raw in sorted(files.items()):
            info = zipfile.ZipInfo('manba-ai-game/' + name, (2026, 10, 17, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, raw)
    result = {'archive': output.name, 'bytes': output.stat().st_size,
              'sha256': hashlib.sha256(output.read_bytes()).hexdigest(), 'files': len(files)}
    output.with_suffix('.sha256').write_text(result['sha256'] + '  ' + output.name + '\n')
    print(json.dumps(result, indent=2))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'dist/manba-ai-game.zip')
    package(parser.parse_args().output.resolve())
