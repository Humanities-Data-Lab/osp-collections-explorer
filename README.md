# Open Scholarship Press Collections Explorer

A static, dependency-free single-page explorer for the annotated bibliographies of the
[Open Scholarship Press Collections](https://en.wikibooks.org/wiki/Open_Scholarship_Press_Collections),
built to the [Endings Principles](https://endings.uvic.ca/principles.html).

Metadata and annotations are read from the public wiki text. The cited articles are linked, never downloaded.

## Build

    python3 build/build.py             # rebuild from the committed snapshot (build/raw/pages.json)
    python3 build/build.py --refresh   # re-fetch Wikibooks first, then rebuild

Requires Python 3.9+. The full-text Search page also needs Java and Apache Ant (the build skips it with a notice when they are missing; CI requires it). Output goes to `site/`; open `site/index.html` directly or serve the folder.
The build stops on parser anomalies not listed in `build/known_anomalies.json`; review them, then rerun with `--accept-anomalies`.

## Deploy (GitHub Pages)

Settings, Pages, Source: "GitHub Actions". The workflow in `.github/workflows/pages.yml` builds and deploys on push to `main`
or on manual dispatch. All links are relative, so the site works at a project subpath (`user.github.io/repo/`) or any other address.

## Layout

- `build/fetch.py`, `parse.py`, `render.py`, `build_search.py`, `build.py`: pipeline
- `build/staticSearch_config.xml`: configuration for [staticSearch](https://endings.uvic.ca/staticSearch/) (checkout pinned to v2.0.3 by tag and commit)
- `build/corrections.json`: named corrections of source typing errors, each with its reason
- `build/templates/`: hand-written CSS and JavaScript, inlined into every page
- `build/raw/pages.json`: snapshot of the wiki text with revision ids (commit this)

Data licence: CC BY-SA 4.0 (inherited from Wikibooks). Software licence: to be chosen by the maintainers.
