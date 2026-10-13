#!/usr/bin/env python3
"""Write a redacted debug report JSON under runs/ (for email / GitHub issues)."""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

from retrieval.shared.support_bundle import build_debug_report  # noqa: E402

TZ = ZoneInfo("America/Sao_Paulo")


def main() -> int:
    bundle = build_debug_report()
    out_dir = ROOT / "runs"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(TZ).strftime("%Y%m%d-%H%M%S")
    path = out_dir / f"debug-report-{stamp}.json"
    path.write_text(json.dumps(bundle, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
