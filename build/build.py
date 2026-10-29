"""Build the site. Usage: python3 build/build.py [--refresh] [--accept-anomalies] [--require-search]

--refresh re-fetches the wiki text (network); the default uses the committed
build/raw/pages.json so a release can be rebuilt identically.
The build stops if the parser reports anomalies not listed in
build/known_anomalies.json (Endings 3.1: relentless validation).
"""
import glob
import importlib
import json
import os
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:  # pragma: no cover  (explicit, so the build also works under python3 -I; the script-mode test covers it)
    sys.path.insert(0, HERE)


def sig(a):
    return "|".join([a["type"], str(a.get("volume", a.get("page", ""))), str(a.get("text", ""))[:60]])


def check_xhtml():
    """staticSearch reads the item pages as XML, so every page it indexes must be well-formed."""
    bad = []
    for path in sorted(glob.glob(os.path.join(HERE, "..", "site", "items", "*.html"))):
        try:
            ET.parse(path)
        except ET.ParseError as e:
            bad.append((os.path.basename(path), str(e)))
    if bad:
        sys.exit("Build stopped: pages that are not well-formed XHTML: " + repr(bad[:5]))


def step(name):
    """Import a pipeline module afresh, so that it reads the files the previous step has just written."""
    mod = sys.modules.get(name)
    return importlib.reload(mod) if mod else importlib.import_module(name)


def check_anomalies(accept):
    with open(os.path.join(HERE, "validation.json"), encoding="utf-8") as f:
        found = {sig(a) for a in json.load(f)["anomalies"]}
    known_path = os.path.join(HERE, "known_anomalies.json")
    known = set()
    if os.path.exists(known_path):
        with open(known_path, encoding="utf-8") as f:
            known = set(json.load(f))
    new = sorted(found - known)
    if new and not accept:
        print("Build stopped: new anomalies need review (then add to known_anomalies.json or rerun with --accept-anomalies):")
        for n in new:
            print("  ", n)
        sys.exit(1)
    if accept:
        with open(known_path, "w", encoding="utf-8") as f:
            json.dump(sorted(found), f, ensure_ascii=False, indent=1)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if "--refresh" in argv:
        step("fetch").main()
    step("parse").main()
    check_anomalies("--accept-anomalies" in argv)
    step("render").main()
    check_xhtml()
    step("build_search").main(["--require"] if "--require-search" in argv else [])


if __name__ == "__main__":
    main()
