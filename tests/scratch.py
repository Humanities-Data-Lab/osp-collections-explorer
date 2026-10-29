"""Shared helpers for the tests that build the site: a scratch copy of the build folder, so the repository is never written to."""
import contextlib
import importlib
import io
import json
import os
import shutil
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD = os.path.join(REPO, "build")
if BUILD not in sys.path:
    sys.path.insert(0, BUILD)

KEEP_SUFFIX = (".py", ".json", ".xml")


def make_scratch(prefix="osp-test-"):
    """Copy the program, its configuration, templates and the committed wiki snapshot into a temp folder.
    Returns (root, build_dir). Generated files (dataset.json, validation.json, site/) are not copied."""
    root = tempfile.mkdtemp(prefix=prefix)
    dest = os.path.join(root, "build")
    os.makedirs(os.path.join(dest, "raw"))
    for name in os.listdir(BUILD):
        src = os.path.join(BUILD, name)
        if os.path.isfile(src) and name.endswith(KEEP_SUFFIX) and name not in ("dataset.json", "validation.json"):
            shutil.copy(src, dest)
    shutil.copytree(os.path.join(BUILD, "templates"), os.path.join(dest, "templates"))
    shutil.copy(os.path.join(BUILD, "raw", "pages.json"), os.path.join(dest, "raw", "pages.json"))
    return root, dest


def reload(name):
    mod = sys.modules.get(name)
    return importlib.reload(mod) if mod else importlib.import_module(name)


_PARSED = {}


def run_parse(build_dir):
    """Run the parser against a scratch build folder (once per process; later calls copy the result). Returns the parse module."""
    parse = reload("parse")
    if not _PARSED:
        old = parse.HERE
        parse.HERE = build_dir
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                parse.main()
        finally:
            parse.HERE = old
        for name in ("dataset.json", "validation.json"):
            with open(os.path.join(build_dir, name), "rb") as f:
                _PARSED[name] = f.read()
    else:
        for name, data in _PARSED.items():
            with open(os.path.join(build_dir, name), "wb") as f:
                f.write(data)
    return parse


def load_render(build_dir):
    """Import render.py so that it reads and writes inside the scratch folder."""
    os.environ["OSP_BUILD_DIR"] = build_dir
    return reload("render")


def unload_render():
    os.environ.pop("OSP_BUILD_DIR", None)


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
