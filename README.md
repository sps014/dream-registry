# Dream package registry

Public sparse-index registry for [Dream](https://github.com/sps014/Dream) packages.

## Layout

```text
index/<name>                         # newline-delimited JSON (one version per line)
dl/<name>/<name>-<version>.tar.gz    # package tarballs (dream.toml + src/ + README)
catalog.json                         # compact search catalog (no full readme)
```

Indexes and tarballs are kept in separate trees so resolve/search never download blobs.

## Index fields

Each index line includes resolve fields (`name`, `vers`, `deps`, `cksum`, `tarball`) plus package
metadata from `dream.toml` / README at publish time:

- `description`, `authors`, `license`, `edition`, `type` (`bin`/`lib`), `targets`
- `readme` (archive-relative path link, e.g. `README.md` — not file contents)

## Use

```toml
[registries]
default = "https://raw.githubusercontent.com/sps014/dream-registry/main"
```

```bash
dreamer add <package>
dreamer search <query>
```

## Publish

```bash
export DREAM_REGISTRY_TOKEN=ghp_...   # contents:write on this repo
dreamer publish
```

**Limits:** max tarball **10 MiB**; duplicate `name@version` rejected.

## Protocol

See [Dream package manager docs](https://sps014.github.io/Dream/tooling/package-manager/).
