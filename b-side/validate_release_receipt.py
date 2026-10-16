"""One small artificial ZIP safety check; no real samples or network."""
import hashlib
import io
from pathlib import Path
import stat
import tempfile
import zipfile
from receive_release_packages import receive, safe_members


def rejects(call):
    try:
        call()
    except (ValueError, FileNotFoundError):
        return
    raise AssertionError('Expected rejection')


def zip_bytes(items):
    b = io.BytesIO()
    with zipfile.ZipFile(b, 'w') as z:
        for name, value in items:
            z.writestr(name, value)
    return b.getvalue()


def main():
    with tempfile.TemporaryDirectory(prefix='B-zip-fixture-') as tmp:
        root = Path(tmp); archive = root/'archives/fixture.zip'
        archive.parent.mkdir(); data = zip_bytes([('metadata.txt', '人工夹具'), ('images/a.txt', 'fixture only')])
        archive.write_bytes(data)
        asset = {'name': 'fixture.zip', 'package': 'fixture', 'size': len(data),
                 'sha256': hashlib.sha256(data).hexdigest(), 'max_expanded_bytes': 10000,
                 'url': 'https://github.com/joyboy-type/EdgeCoRAG/releases/download/artificial/fixture.zip'}
        result = receive({'assets': [asset]}, root)
        assert result['assets'][0]['ZIP_verified']
        assert (root/'packages/fixture/metadata.txt').read_text(encoding='utf-8') == '人工夹具'
        rejects(lambda: receive({'assets': [asset]}, root))
        rejects(lambda: receive({'assets': [{**asset, 'sha256': '0'*64}]}, root/'bad'))
        for entries in [[('../escape', 'x')], [('/absolute', 'x')], [('a\\b', 'x')],
                        [('A.txt', 'x'), ('a.txt', 'y')], [('a', 'x'), ('a/b', 'y')]]:
            with zipfile.ZipFile(io.BytesIO(zip_bytes(entries))) as z:
                rejects(lambda: safe_members(z, 10000))
        b = io.BytesIO()
        with zipfile.ZipFile(b, 'w') as z:
            symlink = zipfile.ZipInfo('link'); symlink.external_attr = (stat.S_IFLNK | 0o777) << 16
            z.writestr(symlink, 'elsewhere')
        with zipfile.ZipFile(io.BytesIO(b.getvalue())) as z:
            rejects(lambda: safe_members(z, 10000))
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            rejects(lambda: safe_members(z, 1))
        bad = root/'bad/archives'; bad.mkdir(parents=True, exist_ok=True)
        (bad/'fixture.zip').write_bytes(data)
        rejects(lambda: receive({'assets': [{**asset, 'sha256': '0'*64}]}, root/'bad'))
    print('PASS: artificial ZIP hash/UTF-8 receipt, no overwrite, traversal/collision/symlink/size rejection; no network.')


if __name__ == '__main__':
    main()
