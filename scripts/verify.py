"""Verify every distributed file against the release manifest."""
from pathlib import Path
import ast
import hashlib
import json


def main():
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / 'MANIFEST.json').read_text(encoding='utf-8'))
    errors = []
    for item in manifest['files']:
        path = root / item['path']
        if not path.is_file():
            errors.append(f'Missing: {item["path"]}')
        elif hashlib.sha256(path.read_bytes()).hexdigest() != item['sha256']:
            errors.append(f'Changed: {item["path"]}')
        elif path.suffix == '.py':
            ast.parse(path.read_text(encoding='utf-8-sig'), filename=item['path'])
    if errors:
        raise SystemExit('\n'.join(errors))
    print(f'Verified {len(manifest["files"])} file hashes and Python syntax.')


if __name__ == '__main__':
    main()
