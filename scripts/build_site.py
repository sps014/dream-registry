"""Build the registry website without changing the sparse registry protocol."""
from __future__ import annotations

import argparse
import hashlib
import json
import posixpath
import re
import shutil
import tarfile
import tomllib
from pathlib import Path, PurePosixPath
from urllib.parse import quote, unquote, urlsplit, urlunsplit

import bleach
from jinja2 import Environment, FileSystemLoader, select_autoescape
from markdown_it import MarkdownIt
from semantic_version import Version

ROOT = Path(__file__).resolve().parents[1]
README_NAMES = ("README.md", "README", "Readme.md", "readme.md")
PLATFORMS = {"native": "Native", "web": "Web", "node": "Node.js"}
ACTIVE_SUFFIXES = {".html", ".htm", ".svg", ".xml", ".js", ".mjs", ".css"}
MARKDOWN = MarkdownIt("commonmark", {"html": False, "linkify": False}).enable("table")
SAFE_TAGS = set(bleach.sanitizer.ALLOWED_TAGS) | {
    "p", "pre", "code", "h1", "h2", "h3", "h4", "h5", "h6", "hr", "br",
    "img", "table", "thead", "tbody", "tr", "th", "td", "del",
}


def archive_path(value: str) -> str:
    """Only accept relative POSIX paths; never follow archive links."""
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise ValueError(f"Unsafe archive path: {value!r}")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or ":" in value:
        raise ValueError(f"Unsafe archive path: {value!r}")
    normalized = str(path)
    if normalized == ".":
        raise ValueError(f"Unsafe archive path: {value!r}")
    return normalized


def read_archive(path: Path, expected_checksum: str | None = None) -> dict[str, bytes]:
    if path.stat().st_size > 10 * 1024 * 1024:
        raise ValueError(f"Archive exceeds registry limit: {path}")
    if expected_checksum:
        actual = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected_checksum:
            raise ValueError(f"Checksum mismatch: {path}")
    files = {}
    total = 0
    with tarfile.open(path, "r:gz") as archive:
        for member in archive:
            name = archive_path(member.name)
            if member.isdir():
                continue
            if not member.isfile():
                raise ValueError(f"Archive contains a link or special file: {name}")
            total += member.size
            if total > 64 * 1024 * 1024:
                raise ValueError(f"Archive expands beyond 64 MiB: {path}")
            if name in files:
                raise ValueError(f"Duplicate archive member: {name}")
            with archive.extractfile(member) as stream:
                files[name] = stream.read()
    return files


def find_readme(files: dict[str, bytes], declared: str | None) -> str | None:
    if declared:
        name = archive_path(declared)
        if name in files:
            return name
    return next((name for name in README_NAMES if name in files), None)


def excerpt(source: str) -> str:
    """Use the first prose paragraph, excluding headings and fenced examples."""
    previous = None
    for token in MARKDOWN.parse(source):
        if token.type == "inline" and previous == "paragraph_open":
            text = "".join(" " if t.type == "softbreak" else t.content for t in (token.children or [])
                           if t.type in {"text", "code_inline", "softbreak"})
            text = " ".join(text.split())
            if text:
                return text[:240] + ("…" if len(text) > 240 else "")
        previous = token.type
    return ""


def render_readme(source: str, name: str, files: dict[str, bytes], asset_url: str) -> str:
    if not name.lower().endswith((".md", ".markdown")):
        from html import escape
        return "<pre>" + escape(source) + "</pre>"
    tokens = MARKDOWN.parse(source)
    anchors = {}
    used_ids = set()
    for i, token in enumerate(tokens):
        if token.type != "heading_open":
            continue
        heading = tokens[i + 1]
        text = "".join(t.content for t in heading.children or [] if t.type in {"text", "code_inline"})
        slug = re.sub(r"[^\w\- ]", "", text.lower()).replace(" ", "-") or "section"
        unique = slug
        count = 1
        while unique in used_ids:
            unique = f"{slug}-{count}"
            count += 1
        used_ids.add(unique)
        anchors[unique] = "readme-" + unique
        token.attrSet("id", anchors[unique])

    def rewrite(value: str) -> str:
        parts = urlsplit(value)
        if parts.scheme or parts.netloc:
            return value
        if not parts.path:
            if parts.fragment in anchors:
                return "#" + anchors[parts.fragment]
            return value
        target = posixpath.normpath(posixpath.join(posixpath.dirname(name), unquote(parts.path)))
        try:
            target = archive_path(target)
        except ValueError:
            return "#"
        if target == name and parts.fragment in anchors:
            return "#" + anchors[parts.fragment]
        if target not in files or PurePosixPath(target).suffix.lower() in ACTIVE_SUFFIXES:
            return "#"
        return urlunsplit(("", "", asset_url + "/" + quote(target, safe="/"), parts.query, parts.fragment))

    for token in tokens:
        for child in token.children or []:
            attr = "src" if child.type == "image" else "href" if child.type == "link_open" else None
            if attr:
                child.attrSet(attr, rewrite(child.attrGet(attr) or ""))
    html = MARKDOWN.renderer.render(tokens, MARKDOWN.options, {})
    return bleach.clean(html, tags=SAFE_TAGS, attributes={
        "a": ["href", "title"], "img": ["src", "alt", "title"], "code": ["class"],
        "th": ["align"], "td": ["align"], "ol": ["start"],
        **{f"h{i}": ["id"] for i in range(1, 7)},
    }, protocols={"http", "https", "mailto"}, strip=True)


def build(source: Path, output: Path, base_path: str = "", registry: Path | None = None) -> dict:
    base = "/" + base_path.strip("/") if base_path.strip("/") else ""
    output = output.resolve()
    source = source.resolve()
    registry = (registry or source).resolve()
    # Refuse output directories that could overwrite inputs or the checkout.
    if output == source or output in source.parents or any(
        output == source / part or source / part in output.parents
        for part in ("docs", "index", "dl", "scripts", ".git", "tests")
    ):
        raise ValueError("Output must be a separate build directory")
    if output == registry or output in registry.parents or registry in output.parents:
        # A build under the checkout is allowed when the checkout itself is the registry.
        if registry != source or output == registry or output in registry.parents:
            raise ValueError("Output must not overwrite registry data")
    output.mkdir(parents=True, exist_ok=True)
    env = Environment(loader=FileSystemLoader([source / "docs", source / "docs" / "templates"]),
                      autoescape=select_autoescape(("html",)))
    env.globals.update(base=base, platforms=PLATFORMS, demo=(registry / ".demo").is_file())
    env.filters["urlpart"] = lambda value: quote(str(value), safe="")

    packages = []
    all_versions = {}
    for index_file in sorted((registry / "index").iterdir()):
        if not index_file.is_file() or index_file.name.startswith("."):
            continue
        versions = []
        for line in index_file.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            name, version = record["name"], record["vers"]
            if name != index_file.name or not re.fullmatch(r"[A-Za-z0-9_-]+", name):
                raise ValueError(f"Invalid package name: {name}")
            parsed = Version(version)
            tarball = archive_path(record["tarball"])
            if not tarball.startswith("dl/"):
                raise ValueError(f"Tarball must be under dl/: {tarball}")
            archive_file = (registry / tarball).resolve()
            if not archive_file.is_relative_to((registry / "dl").resolve()):
                raise ValueError(f"Tarball escapes dl/: {tarball}")
            files = read_archive(archive_file, record.get("cksum"))
            manifest = tomllib.loads(files["dream.toml"].decode("utf-8"))["package"]
            if manifest.get("name") != name or manifest.get("version") != version:
                raise ValueError(f"Manifest identity mismatch: {name}@{version}")
            targets = manifest.get("targets", [])
            if not isinstance(targets, list) or not all(isinstance(t, str) for t in targets):
                raise ValueError(f"Invalid package.targets: {name}@{version}")
            readme_name = find_readme(files, record.get("readme"))
            readme_source = files[readme_name].decode("utf-8", errors="replace") if readme_name else ""
            pkg = dict(record)
            pkg.update(targets=list(dict.fromkeys(targets)), prerelease=bool(parsed.prerelease),
                       description=record.get("description") or excerpt(readme_source),
                       authors=record.get("authors") or manifest.get("authors", []),
                       type=record.get("type") or manifest.get("type", "lib"),
                       keywords=record.get("keywords") or manifest.get("keywords", []),
                       license=record.get("license") or manifest.get("license"),
                       edition=record.get("edition") or manifest.get("edition"),
                       deps=record.get("deps", []), tarball_url=base + "/" + quote(tarball, safe="/"),
                       size=f"{archive_file.stat().st_size / 1024:.1f} KB")
            asset_url = f"{base}/package-files/{name}/{quote(version, safe='')}"
            pkg["readme_html"] = render_readme(readme_source, readme_name, files, asset_url) if readme_name else ""
            pkg["url"] = f"{base}/packages/{name}/{quote(version, safe='')}/"
            # Copy regular files as downloads; never serve package HTML/SVG as active content.
            asset_dest = output / "package-files" / name / version
            for filename, content in files.items():
                dest = asset_dest / filename
                dest.parent.mkdir(parents=True, exist_ok=True)
                if dest.suffix.lower() in ACTIVE_SUFFIXES:
                    # These files remain available inside the original archive.
                    continue
                dest.write_bytes(content)
            archive_dest = output / tarball
            archive_dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(archive_file, archive_dest)
            versions.append(pkg)
        versions.sort(key=lambda p: Version(p["vers"]), reverse=True)
        if not versions:
            continue
        if len({p["vers"] for p in versions}) != len(versions):
            raise ValueError(f"Duplicate package version: {index_file.name}")
        latest = next((p for p in versions if not p["prerelease"]), versions[0])
        packages.append(latest)
        all_versions[latest["name"]] = versions

    known_names = set(all_versions)
    for name, versions in all_versions.items():
        latest = next(p for p in packages if p["name"] == name)
        for pkg in versions:
            page = env.get_template("package.html").render(pkg=pkg, versions=versions,
                latest=latest, known_names=known_names, title=f"{name} {pkg['vers']} · Dream Registry")
            dest = output / "packages" / name / pkg["vers"] / "index.html"
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(page, encoding="utf-8")
            if pkg is latest:
                (output / "packages" / name / "index.html").write_text(page, encoding="utf-8")

    # Search includes every release so prerelease selection remains accurate.
    search = [{key: pkg.get(key) for key in (
        "name", "vers", "description", "authors", "type", "keywords", "targets", "prerelease", "url"
    )} for versions in all_versions.values() for pkg in versions]
    (output / "search.json").write_text(json.dumps(search, ensure_ascii=False), encoding="utf-8")
    (output / "index.html").write_text(env.get_template("index.html").render(
        title="Packages · Dream Registry", packages=packages), encoding="utf-8")
    (output / "404.html").write_text(env.get_template("404.html").render(
        title="Page not found · Dream Registry"), encoding="utf-8")
    for filename in ("site.css", "site.js"):
        shutil.copyfile(source / "docs" / filename, output / filename)
    (output / ".nojekyll").touch()
    return {"packages": len(packages), "versions": len(search)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "_site")
    parser.add_argument("--base-path", default="", help="Deployment prefix, e.g. /dream-registry")
    parser.add_argument("--registry", type=Path, help="Registry data directory containing index/ and dl/; defaults to demo fixtures")
    args = parser.parse_args()
    if args.registry is None:
        from demo_registry import create_demo_registry
        args.registry = ROOT / ".demo-registry"
        create_demo_registry(args.registry)
        print("Using small demo fixtures (not published packages). Pass --registry for production data.")
    result = build(ROOT, args.output, args.base_path, registry=args.registry)
    print(f"Built {result['packages']} packages / {result['versions']} versions in {args.output}")
