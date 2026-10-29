"""Run staticSearch (Project Endings) over the item pages in site/items.

Needs Java and Apache Ant (everything else ships inside the staticSearch checkout).
The checkout is pinned to a release tag AND a commit hash: the build stops if they disagree.
Usage: python3 build/build_search.py [--require]   (--require fails instead of skipping when Java/Ant are missing)
"""
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
REPO = "https://github.com/projectEndings/staticSearch.git"
TAG = "v2.0.3"
COMMIT = "900d3b80c938d8b185acce8527f604ca108bc415"
DEST = os.path.join(HERE, "_staticsearch")
CONFIG = os.path.join(HERE, "staticSearch_config.xml")
PAGE = os.path.join(ROOT, "site", "items", "search.html")
OUT = os.path.join(ROOT, "site", "items", "staticSearch")
INDEX = os.path.join(ROOT, "site", "index.html")
SLOT = "<!--@STATICSEARCH@-->"


def generated_form():
    """The search form staticSearch generated into search.html: the div#staticSearch element, found by counting divs."""
    with open(PAGE, encoding="utf-8") as f:
        t = f.read()
    start = t.index('<div id="staticSearch"')
    depth, pos = 0, start
    for m in re.finditer(r"<(/?)div\b[^>]*?(/?)>", t[start:]):
        if m.group(2) == "/":
            continue  # self-closing
        depth += -1 if m.group(1) else 1
        if depth == 0:
            return t[start:start + m.end()]
    raise ValueError("unbalanced div#staticSearch in " + PAGE)


def fill_explore_slot(form_block):
    with open(INDEX, encoding="utf-8") as f:
        t = f.read()
    if SLOT not in t:
        sys.exit("Build stopped: the Explore page has no staticSearch slot.")
    with open(INDEX, "w", encoding="utf-8") as f:
        f.write(t.replace(SLOT, form_block))



def have_java():
    if not shutil.which("java"):
        return False
    return subprocess.run(["java", "-version"], capture_output=True).returncode == 0


def main(argv=None):
    require = "--require" in (sys.argv[1:] if argv is None else argv)
    if not (have_java() and shutil.which("ant")):
        msg = "Java and Apache Ant are needed for staticSearch."
        if require:
            sys.exit("Build stopped: " + msg)
        print("Skipping search index:", msg)
        with open(PAGE, encoding="utf-8") as f:
            t = f.read()
        t = t.replace('<div id="staticSearch"></div>', '<p><strong>The search index was not built in this copy of the site.</strong> '
                      'Use Explore or the volume pages instead.</p>')
        with open(PAGE, "w", encoding="utf-8") as f:
            f.write(t)
        fill_explore_slot("")
        return
    if not os.path.isdir(DEST):
        subprocess.run(["git", "clone", "--quiet", "--depth", "1", "--branch", TAG, REPO, DEST], check=True)
    head = subprocess.run(["git", "-C", DEST, "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    if head != COMMIT:
        sys.exit(f"Build stopped: staticSearch checkout is {head}, expected {COMMIT} ({TAG}). Delete build/_staticsearch and retry.")
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    subprocess.run(["ant", "-DssConfigFile=" + CONFIG], cwd=DEST, check=True)
    n = sum(len(f) for _, _, f in os.walk(OUT)) if os.path.isdir(OUT) else 0
    if n < 20:
        sys.exit(f"Build stopped: staticSearch produced only {n} files in {OUT}.")
    form = generated_form().replace('data-ssfolder="staticSearch"', 'data-ssfolder="items/staticSearch"')
    fill_explore_slot('<link rel="stylesheet" href="items/staticSearch/ssSearch.css" id="ssCss"/>' + form +
                      '<script src="items/staticSearch/ssSearch.js"></script>')
    print(f"staticSearch {TAG}: {n} index files written; form copied into Explore")


if __name__ == "__main__":
    main()
