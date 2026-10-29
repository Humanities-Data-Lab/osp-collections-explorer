# Open Scholarship Press Collections Explorer

A static, dependency-free explorer for the annotated bibliographies of the
[Open Scholarship Press Collections](https://en.wikibooks.org/wiki/Open_Scholarship_Press_Collections),
built to the [Endings Principles](https://endings.uvic.ca/principles.html).

Searching and filtering use [staticSearch](https://endings.uvic.ca/staticSearch/): the Explore page embeds its generated form and engine and draws cards and charts from the matches. The Co-authorship page draws a network of authors who share items; its filters (volume, topic, type, year, minimum shared items, minimum group size, author) recompute the network in the browser with no libraries. Metadata and annotations are read from the public wiki text. The cited articles are linked, never downloaded.

## Build

    python3 build/build.py             # rebuild from the committed snapshot (build/raw/pages.json)
    python3 build/build.py --refresh   # re-fetch Wikibooks first, then rebuild

Requires Python 3.9+. The full-text Search page also needs Java and Apache Ant (the build skips it with a notice when they are missing; CI requires it). Output goes to `site/`; open `site/index.html` directly or serve the folder.
The build stops on parser anomalies not listed in `build/known_anomalies.json`; review them, then rerun with `--accept-anomalies`.

## Test

    python3 tests/run_all.py           # Python suite with coverage floor (95%), then the JavaScript suite (90% lines)

Python tests use `unittest` and the JavaScript tests use Node's built-in `node:test`; neither suite needs a package install. The coverage tool (`pip install coverage`) is optional locally and installed in CI. Tests build into scratch folders and never write to `site/` or `build/`. The deployment workflow runs this command first, and the build and deploy jobs wait for it (`tests/test_repo.py` checks that wiring).

## Deploy (GitHub Pages)

Settings, Pages, Source: "GitHub Actions". The workflow in `.github/workflows/pages.yml` builds and deploys on push to `main`
or on manual dispatch. All links are relative, so the site works at a project subpath (`user.github.io/repo/`) or any other address.

## Layout

- `build/fetch.py`, `parse.py`, `render.py`, `build_search.py`, `build.py`: pipeline
- `build/staticSearch_config.xml`: configuration for [staticSearch](https://endings.uvic.ca/staticSearch/) (checkout pinned to v2.0.3 by tag and commit)
- `build/corrections.json`: named corrections of source typing errors, each with its reason
- `tests/`: `test_*.py` (parser, fetcher, renderer, build orchestration, search step, repository guards) and `js/*.test.js` (both page scripts, run against a hand-written DOM stub)
- `build/templates/`: hand-written CSS and JavaScript (`app.js` for Explore, `coauthor.js` for Co-authorship), inlined into every page
- `build/raw/pages.json`: snapshot of the wiki text with revision ids (commit this)

Data licence: CC BY-SA 4.0 (inherited from Wikibooks). Software licence: to be chosen by the maintainers.
