"""Cold-import laziness invariant.

`from barflow import track` must load only the C core — the decoration
submodules (style, columns, themes, bar_styles, spinners, _progress) are
resolved lazily via PEP 562 `__getattr__` on first access. This is the
~1 ms cold-import headline feature; if a future edit hoists one of those
imports to module level (e.g. moving a cached `from . import X` out of a
function), this test fails before the benchmark silently regresses.

Run in a fresh subprocess: the in-process test interpreter has already
imported the whole package, so sys.modules here is useless for the check.
"""

import os
import subprocess
import sys
from pathlib import Path

SRC = str(Path(__file__).resolve().parent.parent / "src")

LAZY = [
    "barflow.style",
    "barflow.columns",
    "barflow.themes",
    "barflow.bar_styles",
    "barflow.spinners",
    "barflow._progress",
    "barflow.hooks",
    "barflow.aio",
]


def _modules_after(import_stmt: str) -> set[str]:
    code = (
        f"import sys\n{import_stmt}\n"
        "import json\n"
        f"print(json.dumps([m for m in {LAZY!r} if m in sys.modules]))\n"
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = SRC + os.pathsep + env.get("PYTHONPATH", "")
    r = subprocess.run([sys.executable, "-c", code],
                       capture_output=True, text=True, env=env)
    assert r.returncode == 0, f"subprocess failed:\n{r.stdout}\n{r.stderr}"
    import json
    return set(json.loads(r.stdout.strip().splitlines()[-1]))


def test_import_track_stays_lazy():
    leaked = _modules_after("from barflow import track")
    assert not leaked, f"cold import eagerly loaded lazy submodules: {sorted(leaked)}"


def test_import_barflow_stays_lazy():
    leaked = _modules_after("import barflow")
    assert not leaked, f"import barflow eagerly loaded lazy submodules: {sorted(leaked)}"
