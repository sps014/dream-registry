"""Create tiny, synthetic registry archives for development; no network or Git checkout."""
import hashlib
import io
import json
import tarfile
from pathlib import Path

FIXTURE = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "packages.json"


def create_demo_registry(destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "index").mkdir(exist_ok=True)
    (destination / ".demo").touch()
    for package in json.loads(FIXTURE.read_text(encoding="utf-8")):
        records = []
        for version in package["versions"]:
            name = package["name"]
            metadata = {key: package[key] for key in ("name", "description", "targets", "type", "keywords")}
            metadata.update(version=version, authors=["Dream demo author"], license="MIT", edition="2026")
            manifest = "[package]\n" + "\n".join(f"{key} = {json.dumps(value)}" for key, value in metadata.items())
            readme = (f"# {name}\n\n{package['description']}\n\n"
                      "This is a small development fixture, not the published package.\n\n"
                      f"## Install\n\n```bash\ndreamer add {name} --version {version}\n```\n\n"
                      "## Usage\n\n```dream\nimport system;\nfun main(): void {\n    System.println(\"Hello, Dream\");\n}\n```\n\n"
                      "| Feature | Status |\n| --- | --- |\n| Markdown | Available |\n")
            relative = f"dl/{name}/{name}-{version}.tar.gz"
            archive_path = destination / relative
            archive_path.parent.mkdir(parents=True, exist_ok=True)
            # Stable metadata makes identical fixtures reproducible.
            import gzip
            with archive_path.open("wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", filename="", mtime=0) as zipped:
                with tarfile.open(fileobj=zipped, mode="w") as archive:
                    for filename, text in {"dream.toml": manifest, "README.md": readme}.items():
                        content = text.encode("utf-8")
                        info = tarfile.TarInfo(filename)
                        info.size = len(content)
                        archive.addfile(info, io.BytesIO(content))
            records.append({**metadata, "vers": version, "tarball": relative,
                "cksum": "sha256:" + hashlib.sha256(archive_path.read_bytes()).hexdigest(),
                "readme": "README.md", "deps": package.get("deps", [])})
        (destination / "index" / name).write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
