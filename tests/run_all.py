#!/usr/bin/env python3
"""Run every test: the Python suite (with line and branch coverage when `coverage` is installed) and the JavaScript suite.
Usage: python3 tests/run_all.py [--no-js] [--no-python]
CI runs this before anything is built or deployed; it exits non-zero if any test fails or coverage falls below the floors below."""
import glob
import os
import shutil
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY_FLOOR = 95        # percent of lines and branches in build/*.py
JS_FLOOR = 90        # percent of lines in build/templates/*.js


def python_suite():
    try:
        import coverage  # noqa: F401
        have = True
    except ImportError:
        have = False
    if not have:
        print("coverage is not installed; running the Python tests without a coverage check")
        return subprocess.call([sys.executable, "-m", "unittest", "discover", "-s", "tests"], cwd=REPO)
    steps = [
        [sys.executable, "-m", "coverage", "run", "-m", "unittest", "discover", "-s", "tests"],
        [sys.executable, "-m", "coverage", "report", "-m", f"--fail-under={PY_FLOOR}"],
    ]
    for cmd in steps:
        code = subprocess.call(cmd, cwd=REPO)
        if code:
            return code
    return 0


def js_suite():
    node = shutil.which("node")
    if not node:
        print("node is not installed; the JavaScript tests cannot run")
        return 1
    files = sorted(glob.glob(os.path.join(REPO, "tests", "js", "*.test.js")))     # a directory argument is not accepted by every Node release
    return subprocess.call([node, "--test", "--experimental-test-coverage", f"--test-coverage-lines={JS_FLOOR}",
                            "--test-coverage-exclude=tests/**"] + files, cwd=REPO)


def main(argv):
    code = 0
    if "--no-python" not in argv:
        code = python_suite() or code
    if "--no-js" not in argv:
        code = js_suite() or code
    print("\nALL TESTS PASSED" if code == 0 else "\nTESTS FAILED")
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
