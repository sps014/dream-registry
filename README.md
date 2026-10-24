# Dream Registry website

Website source lives on the independent, orphan **`feat/site`** branch. Published package
indexes, catalog, and archives remain on **`main`**. The branches are not merged into each
other. This branch contains no published package archives or registry history.

## Develop without downloading packages

Clone only the website branch (a normal clone fetches all branches):

```bash
git clone --single-branch --branch feat/site --depth 1 https://github.com/sps014/dream-registry.git dream-registry-site
cd dream-registry-site
python -m venv .venv
# Activate: .venv\Scripts\Activate.ps1 on Windows,
# or source .venv/bin/activate on macOS/Linux.
python -m pip install -r requirements.txt
python scripts/build_site.py
python -m http.server 8000 --directory _site
```

Open [the local preview](http://localhost:8000). The default build generates tiny, synthetic
archives from `tests/fixtures/packages.json` in ignored `.demo-registry/`. It needs no registry
checkout or network access, and shows a development banner. These fixtures are not real
package documentation. All tests run against fixtures and temporary directories.

```bash
python -m unittest discover -s tests -v
node --check docs/site.js
```

To inspect real published data, supply a directory containing `index/` and `dl/` explicitly:

```bash
python scripts/build_site.py --registry /path/to/registry --output _site
```

The deployment workflow fetches current `main` into ignored `.registry-data/`, using a
shallow checkout limited to `index/` and `dl/`. Real archives are needed only for production
builds or when you explicitly choose a real-data preview. No registry data is changed.
Use a fresh output directory when switching data sources or deleting package versions to
avoid retaining obsolete generated files. `_site/` and `_demo-site/` are ignored build output.

## Pages and metadata

- `/packages/<name>/`: latest stable release, or latest prerelease if no stable release exists.
- `/packages/<name>/<version>/`: documentation and metadata for that specific version.
- README, Platforms, Dependencies, and Versions tabs use URL fragments.
- Search, any-match platform filters, package type, prerelease option, and sorting use query
  parameters. Browser back/forward restores those selections.

`docs/index.html` is a Jinja template, not deployable HTML. The generator renders it and the
package templates into a standalone static website. There is no runtime backend.

Badges come from `[package].targets` in the version's archived `dream.toml`. Missing or empty
targets display Native, Web, and Node.js badges and match every platform filter: Dream treats an empty list
as no host preference and permits Native, Web, or Node.js. This describes host selection,
not a claim that every platform-specific API in a package has been tested on every host. README discovery
uses the index's `readme` path, then `README.md`, `README`, `Readme.md`, and `readme.md`.
Markdown is sanitized during generation. Relative links resolve to safe regular archive
files; missing or unsafe links are disabled. Active HTML/SVG/XML/JavaScript/CSS files remain
available only inside the original archive download.

## Deployment and branch setup

- Pushes and pull requests targeting `feat/site` run tests using only demo fixtures.
- Pushes to `feat/site` also build real data and deploy through GitHub Pages.
- A small workflow on `main` calls the reusable website workflow on `feat/site` whenever
  package indexes or archives change. Publishing packages therefore refreshes the site
  without adding site source to the registry branch. No additional token or secret is needed.
- The workflow on `main` also supports manual dispatch for an explicit rebuild.

In repository **Settings → Pages → Build and deployment**, set **Source** to **GitHub Actions**.
The workflow uses `--base-path /dream-registry`; omit it for root hosting or change it for a
different prefix. The Pages environment must allow deployments from **both `main` and
`feat/site`**, since either branch can trigger a production build.

For the initial remote setup, push **`feat/site` first**, then push the `main` workflow commit,
so its referenced reusable workflow already exists. Afterwards, publish packages on `main`
as usual and make website changes on `feat/site`. Do not merge the unrelated branch histories.
