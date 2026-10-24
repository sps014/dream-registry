import hashlib
import io
import json
import shutil
import tarfile
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

from scripts.build_site import ROOT, archive_path, build, excerpt, find_readme, read_archive, render_readme
from scripts.demo_registry import create_demo_registry


class Links(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.links = []
        self.ids = set()
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if 'id' in attrs:
            self.ids.add(attrs['id'])
        for key in ('href', 'src'):
            if attrs.get(key):
                self.links.append(attrs[key])


class SiteTests(unittest.TestCase):
    def test_fixture_registry_routes_and_links(self):
        for base in ('', '/dream-registry'):
            with self.subTest(base=base), tempfile.TemporaryDirectory() as temp:
                output = Path(temp) / 'site'
                registry = Path(temp) / 'registry'
                create_demo_registry(registry)
                self.assertEqual(build(ROOT, output, base, registry=registry), {'packages': 4, 'versions': 6})
                for page in output.rglob('*.html'):
                    parsed = Links(page.read_text(encoding='utf-8'))
                    for value in parsed.links:
                        url = urlsplit(value)
                        if url.scheme or url.netloc:
                            continue
                        if url.path:
                            self.assertTrue(url.path.startswith(base + '/'), value)
                            relative = unquote(url.path[len(base):]).lstrip('/')
                            target = output / relative
                            if url.path.endswith('/'):
                                target /= 'index.html'
                        else:
                            target = page
                        self.assertTrue(target.is_file(), f'{page}: {value}')
                        if url.fragment and target.suffix == '.html':
                            self.assertIn(url.fragment, Links(target.read_text(encoding='utf-8')).ids)
                home = (output / 'index.html').read_text(encoding='utf-8')
                self.assertIn('Refine your search', home)
                self.assertIn('Platforms not specified', home)
                semver = (output / 'packages/semver/index.html').read_text(encoding='utf-8')
                self.assertIn('dreamer add semver --version 0.1.2', semver)
                self.assertIn('<h2 id="readme-usage">Usage</h2>', semver)
                self.assertIn('language-dream', semver)
                self.assertLess(semver.index('>0.1.2</a>'), semver.index('>0.1.1</a>'))

    def test_readme_selection_and_sanitization(self):
        files = {'README.md': b'default', 'docs/guide.md': b'guide', 'docs/image.png': b'image',
                 'docs/active.svg': b'<svg/>'}
        self.assertEqual(find_readme(files, 'docs/guide.md'), 'docs/guide.md')
        self.assertEqual(find_readme(files, None), 'README.md')
        self.assertEqual(find_readme(files, 'missing.md'), 'README.md')
        self.assertIsNone(find_readme({}, None))
        html = render_readme('# Guide\n\n<script>alert(1)</script>\n\n'
            '[bad](javascript:alert%281%29)\n\n![Image](image.png)\n\n'
            '[bad relative](../../secret)\n\n![active](active.svg)\n\n[Top](#guide)\n\n'
            '| A | B |\n|---|---|\n| 1 | 2 |', 'docs/guide.md', files, '/files/pkg/1.0.0')
        self.assertNotIn('<script>', html)
        self.assertNotIn('href="javascript:', html)
        self.assertIn('src="/files/pkg/1.0.0/docs/image.png"', html)
        self.assertNotIn('src="/files/pkg/1.0.0/docs/active.svg"', html)
        self.assertIn('<table>', html)
        self.assertIn('href="#readme-guide"', html)
        self.assertIn('<pre>&lt;b&gt;plain&lt;/b&gt;</pre>', render_readme('<b>plain</b>', 'README', {}, '/files'))
        self.assertEqual(excerpt('# Name\n\nFirst **prose** paragraph.\nContinued here.'), 'First prose paragraph. Continued here.')

    def test_unsafe_archive_members(self):
        for name in ('../escape', '/absolute', 'C:/absolute', 'dir\\escape', '.', ''):
            with self.subTest(name=name), self.assertRaises(ValueError):
                archive_path(name)
        with tempfile.TemporaryDirectory() as temp:
            for kind in (tarfile.SYMTYPE, tarfile.LNKTYPE):
                archive_file = Path(temp) / 'unsafe.tar.gz'
                with tarfile.open(archive_file, 'w:gz') as archive:
                    info = tarfile.TarInfo('README.md')
                    info.type = kind
                    info.linkname = '../secret'
                    archive.addfile(info)
                with self.assertRaises(ValueError):
                    read_archive(archive_file)

    def test_version_specific_data_and_missing_readme(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / 'source'
            shutil.copytree(ROOT / 'docs', source / 'docs')
            (source / 'index').mkdir()
            records = []
            releases = [('1.0.0', ['native'], '# Sample\n\nOriginal description.'),
                        ('1.1.0', ['web', 'node'], None),
                        ('2.0.0-beta.1', ['web'], '# Future\n\nFuture description.')]
            for version, targets, readme in releases:
                name = 'sample'
                archive_path = source / f'dl/{name}/{name}-{version}.tar.gz'
                archive_path.parent.mkdir(parents=True, exist_ok=True)
                manifest = f'[package]\nname="{name}"\nversion="{version}"\ntargets={json.dumps(targets)}\n'
                with tarfile.open(archive_path, 'w:gz') as archive:
                    files = {'dream.toml': manifest}
                    if readme:
                        files['README.md'] = readme
                    for filename, content in files.items():
                        content = content.encode()
                        info = tarfile.TarInfo(filename)
                        info.size = len(content)
                        archive.addfile(info, io.BytesIO(content))
                records.append({'name': name, 'vers': version, 'deps': [{'name': 'external', 'req': '^1'}],
                    'tarball': archive_path.relative_to(source).as_posix(),
                    'cksum': 'sha256:' + hashlib.sha256(archive_path.read_bytes()).hexdigest()})
            (source / 'index/sample').write_text('\n'.join(json.dumps(r) for r in records), encoding='utf-8')
            output = Path(temp) / 'site'
            build(source, output)
            latest = (output / 'packages/sample/index.html').read_text(encoding='utf-8')
            self.assertIn('dreamer add sample --version 1.1.0', latest)
            self.assertIn('This package does not include a README.', latest)
            self.assertIn('Node.js', latest)
            original = (output / 'packages/sample/1.0.0/index.html').read_text(encoding='utf-8')
            self.assertIn('Original description.', original)
            self.assertIn('>Native<', original)
            self.assertNotIn('>Node.js<', original)
            search = json.loads((output / 'search.json').read_text(encoding='utf-8'))
            self.assertEqual(search[0]['vers'], '2.0.0-beta.1')
            self.assertTrue(search[0]['prerelease'])
            # A registry containing only prereleases still gets an unversioned page.
            (source / 'index/sample').write_text(json.dumps(records[-1]), encoding='utf-8')
            build(source, Path(temp) / 'prerelease-site')
            prerelease = (Path(temp) / 'prerelease-site/packages/sample/index.html').read_text(encoding='utf-8')
            self.assertIn('dreamer add sample --version 2.0.0-beta.1', prerelease)

    def test_build_rejects_input_directories(self):
        for output in (ROOT, ROOT / 'docs', ROOT / 'index/generated', ROOT.parent):
            with self.subTest(output=output), self.assertRaises(ValueError):
                build(ROOT, output)


if __name__ == '__main__':
    unittest.main()
