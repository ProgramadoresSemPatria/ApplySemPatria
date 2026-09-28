"""Console entry for ``pip install -e .`` — keeps ROOT at the repo clone."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parent
    scripts = root / "scripts"
    if not (scripts / "jobsearch.py").exists():
        print("jobsearch: missing scripts/ — install from a full git clone.", file=sys.stderr)
        return 1

    os.environ.setdefault("JOBSEARCH_ROOT", str(root))
    os.chdir(root)
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))

    import jobsearch  # noqa: WPS433 — scripts/jobsearch.py on sys.path

    return jobsearch.main()
