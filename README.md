# Dream package registry

Public sparse-index registry for [Dream](https://github.com/sps014/Dream) packages.

## Layout

```text
index/<name>                         # newline-delimited JSON (one version per line)
dl/<name>/<name>-<version>.tar.gz    # package tarballs (dream.toml + src/)
catalog.json                         # compact search catalog
```

Indexes and tarballs are kept in separate trees so resolve/search never download blobs.

## Use

In `dream.toml`:

```toml
[registries]
default = "https://raw.githubusercontent.com/sps014/dream-registry/main"
```

Or rely on dreamer's built-in default (same URL).

```bash
dreamer add <package>
dreamer search <query>
```

## Publish

Requires a GitHub token with `contents: write` on this repo:

```bash
export DREAM_REGISTRY_TOKEN=ghp_...   # or pass --token
dreamer publish
```

**Limits**

- Max tarball size: **10 MiB**
- Duplicate `name@version` is rejected

## Protocol

See [Dream package manager docs](https://sps014.github.io/Dream/tooling/package-manager/).
