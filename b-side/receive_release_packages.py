"""Receive only explicitly pinned ZIP assets outside code; never build datasets.

Without --download this checks already supplied archives only. A future split
requires its own reviewed asset manifest; no release enumeration or auto-expansion.
Original/filled review files are never rewritten. No inference dependencies.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import urllib.request
import zipfile


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def verify_archive(path, asset):
    if path.stat().st_size != asset['size'] or sha(path) != asset['sha256']:
        raise ValueError('Archive size/SHA mismatch: ' + asset['name'])


def safe_members(z, max_expanded):
    seen = set(); total = 0; members = []
    for item in z.infolist():
        name = item.filename; parts = PurePosixPath(name).parts
        if (not parts or name.startswith('/') or '\\' in name or ':' in name
                or any(p in ['.', '..'] for p in name.rstrip('/').split('/'))
                or any(not p for p in name.rstrip('/').split('/'))):
            raise ValueError('Unsafe ZIP path')
        # Case-insensitive collision check also protects Windows/macOS receivers.
        key = name.rstrip('/').casefold()
        if key in seen:
            raise ValueError('Duplicate/colliding ZIP path')
        seen.add(key)
        mode = item.external_attr >> 16
        if stat.S_IFMT(mode) not in [0, stat.S_IFREG, stat.S_IFDIR] or item.flag_bits & 1:
            raise ValueError('Special/encrypted ZIP member')
        total += item.file_size
        if total > max_expanded:
            raise ValueError('ZIP expanded-size bound exceeded')
        members.append(item)
    # File-as-parent collisions must be rejected before writing anything.
    files = {x.filename.casefold() for x in members if not x.is_dir()}
    for item in members:
        if any(p.as_posix().casefold() in files for p in PurePosixPath(item.filename).parents if str(p) != '.'):
            raise ValueError('ZIP file/directory collision')
    return members, total


def receive(manifest, root, download=False):
    root = root.resolve(); code = Path(__file__).resolve().parent
    if root == code or code in root.parents:
        raise ValueError('External destination required, outside B code')
    assets = manifest['assets']; names = set(); packages = set()
    for asset in assets:
        if (not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*\.zip', asset['name'])
                or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', asset['package'])
                or asset['name'].casefold() in names or asset['package'].casefold() in packages
                or not re.fullmatch(r'[0-9a-f]{64}', asset['sha256'])
                or not isinstance(asset['size'], int) or asset['size'] <= 0
                or asset['max_expanded_bytes'] <= 0):
            raise ValueError('Invalid explicit asset pin')
        if not asset['url'].startswith('https://github.com/joyboy-type/EdgeCoRAG/releases/download/'):
            raise ValueError('Unexpected asset source; no arbitrary URL acquisition')
        names.add(asset['name'].casefold()); packages.add(asset['package'].casefold())
    if any((root/'packages'/a['package']).exists() for a in assets):
        raise ValueError('Extraction destination exists; never overwrite reviews/materials')
    root.mkdir(parents=True, exist_ok=True); (root/'archives').mkdir(exist_ok=True)
    records = []
    try:
        for asset in assets:
            path = root/'archives'/asset['name']
            if not path.exists():
                if not download:
                    raise FileNotFoundError('Supply archive or explicitly use --download: ' + asset['name'])
                part = path.with_suffix('.zip.part')
                request = urllib.request.Request(asset['url'], headers={'User-Agent': 'EdgeCoRAG-B-receipt-v1'})
                count = 0
                with urllib.request.urlopen(request, timeout=45) as response, part.open('xb') as out:
                    while block := response.read(1024 * 1024):
                        count += len(block)
                        if count > asset['size']:
                            raise ValueError('Download exceeds pinned size')
                        out.write(block)
                verify_archive(part, asset); part.rename(path)
            verify_archive(path, asset)
            destination = root/'packages'/asset['package']
            with zipfile.ZipFile(path) as z:
                members, expanded = safe_members(z, asset['max_expanded_bytes'])
                destination.mkdir(parents=True)
                for item in members:
                    target = destination/item.filename
                    if item.is_dir():
                        target.mkdir(parents=True, exist_ok=True)
                    else:
                        target.parent.mkdir(parents=True, exist_ok=True)
                        with z.open(item) as src, target.open('xb') as out:
                            shutil.copyfileobj(src, out)
            records.append({**asset, 'ZIP_verified': True, 'safe_extraction': True,
                            'file_entries': len(members), 'expanded_bytes': expanded})
        result = {'status': 'received_not_semantically_accepted',
                  'assets': records, 'GPU_verified': False}
        (root/'reception.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        return result
    except Exception as e:
        (root/'reception.failure.json').write_text(json.dumps({'status': 'receipt_failed',
            'completed_assets': records, 'error': type(e).__name__+': '+str(e)}, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        raise  # Keep partial files/failure receipt for diagnosis; never delete a review.


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest', type=Path, required=True)
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--download', action='store_true')
    a = p.parse_args()
    result = receive(json.loads(a.manifest.read_text(encoding='utf-8')), a.root, a.download)
    print(json.dumps({'status': result['status'], 'assets': len(result['assets'])}))
