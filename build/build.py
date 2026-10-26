"""Build the site. Usage: python3 build/build.py [--refresh]

--refresh re-fetches the wiki text (network); the default uses the committed
build/raw/pages.json so a release can be rebuilt identically.
The build stops if the parser reports anomalies not listed in
build/known_anomalies.json (Endings 3.1: relentless validation).
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def sig(a):
    return "|".join([a["type"], str(a.get("volume", a.get("page", ""))), str(a.get("text", ""))[:60]])


def run(script):
    subprocess.run([sys.executable, os.path.join(HERE, script)], check=True)


if "--refresh" in sys.argv:
    run("fetch.py")
run("parse.py")
with open(os.path.join(HERE, "validation.json"), encoding="utf-8") as f:
    found = {sig(a) for a in json.load(f)["anomalies"]}
known_path = os.path.join(HERE, "known_anomalies.json")
known = set(json.load(open(known_path, encoding="utf-8"))) if os.path.exists(known_path) else set()
new = sorted(found - known)
if new and "--accept-anomalies" not in sys.argv:
    print("Build stopped: new anomalies need review (then add to known_anomalies.json or rerun with --accept-anomalies):")
    for n in new:
        print("  ", n)
    sys.exit(1)
if "--accept-anomalies" in sys.argv:
    json.dump(sorted(found), open(known_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
run("render.py")
