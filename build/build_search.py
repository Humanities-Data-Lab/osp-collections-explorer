"""Run staticSearch (Project Endings) over the item pages in site/items.

Needs Java and Apache Ant (everything else ships inside the staticSearch checkout).
The checkout is pinned to a release tag AND a commit hash: the build stops if they disagree.
Usage: python3 build/build_search.py [--require]   (--require fails instead of skipping when Java/Ant are missing)
"""
import os
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


def have_java():
    if not shutil.which("java"):
        return False
    return subprocess.run(["java", "-version"], capture_output=True).returncode == 0


def main():
    require = "--require" in sys.argv
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
    print(f"staticSearch {TAG}: {n} index files written")


if __name__ == "__main__":
    main()
