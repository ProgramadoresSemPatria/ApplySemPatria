#!/usr/bin/env python3
"""Audit board discovery: Python urllib collectors vs Patchright HTTP fetch.

Uses the *same* collector code for both paths. Python calls urllib; Patchright
patches collectors.http_utils to route through browser APIRequestContext.

Non-LinkedIn enabled sources only.

Usage:
  python3 benchmark_board_sources.py
  python3 benchmark_board_sources.py --samples 3 --interval 10
  python3 benchmark_board_sources.py --source remoteok --json
"""

from __future__ import annotations

import argparse
import asyncio
import concurrent.futures
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

from collectors import COLLECTORS  # noqa: E402
from discover import load_config  # noqa: E402
from registry import job_key  # noqa: E402

TZ = ZoneInfo("America/Sao_Paulo")
HISTORY_PATH = ROOT / "runs" / "board-audit-history.jsonl"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _identity_key(job: dict[str, Any]) -> str:
    source = (job.get("source") or "").strip().lower()
    company = (job.get("company") or "").strip().lower()
    role = (job.get("role") or "").strip().lower()
    return f"{source}|{company}|{role}"


def _keys(jobs: list[dict[str, Any]], *, by: str) -> set[str]:
    fn = _identity_key if by == "identity" else job_key
    return {fn(j) for j in jobs if fn(j)}


class BrowserFetchBridge:
    """Sync fetch_* compatible with collectors.http_utils, backed by Patchright."""

    def __init__(self, request, loop: asyncio.AbstractEventLoop) -> None:
        self._request = request
        self._loop = loop

    def fetch_text(self, url: str, timeout: int = 30) -> str:
        future = asyncio.run_coroutine_threadsafe(self._fetch_text(url, timeout), self._loop)
        return future.result(timeout=timeout + 15)

    def fetch_json(self, url: str, timeout: int = 30) -> Any:
        return json.loads(self.fetch_text(url, timeout=timeout))

    async def _fetch_text(self, url: str, timeout: int) -> str:
        resp = await self._request.get(
            url,
            timeout=timeout * 1000,
            headers={"User-Agent": USER_AGENT, "Accept": "*/*"},
        )
        if not resp.ok:
            body = await resp.text()
            raise RuntimeError(f"HTTP {resp.status} for {url}: {body[:200]}")
        return await resp.text()


def run_python_collectors(config: dict[str, Any], sources: list[str]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for name in sources:
        collector = COLLECTORS.get(name)
        if not collector:
            continue
        try:
            out[name] = collector(config)
        except Exception as exc:  # noqa: BLE001
            out[name] = []
            print(f"  python {name}: ERROR {exc}")
    return out


async def run_patchright_collectors(
    config: dict[str, Any],
    sources: list[str],
    *,
    headless: bool,
) -> dict[str, list[dict[str, Any]]]:
    from browser_session import close_session, launch_context  # noqa: E402

    import collectors.http_utils as hu  # noqa: E402

    orig_text = hu.fetch_text
    orig_json = hu.fetch_json
    loop = asyncio.get_running_loop()
    out: dict[str, list[dict[str, Any]]] = {}

    pw, browser, ctx = await launch_context(headless=headless, use_cookies=False)
    try:
        bridge = BrowserFetchBridge(ctx.request, loop)
        hu.fetch_text = bridge.fetch_text
        hu.fetch_json = bridge.fetch_json

        def _collect(name: str) -> tuple[str, list[dict[str, Any]] | Exception]:
            collector = COLLECTORS.get(name)
            if not collector:
                return name, []
            try:
                return name, collector(config)
            except Exception as exc:  # noqa: BLE001
                return name, exc

        with concurrent.futures.ThreadPoolExecutor(max_workers=len(sources) or 1) as pool:
            futures = [loop.run_in_executor(pool, _collect, name) for name in sources]
            for coro in asyncio.as_completed(futures):
                name, result = await coro
                if isinstance(result, Exception):
                    out[name] = []
                    print(f"  patchright {name}: ERROR {result}")
                else:
                    out[name] = result
    finally:
        hu.fetch_text = orig_text
        hu.fetch_json = orig_json
        await close_session(pw=pw, browser=browser, context=ctx)

    return out


def compare_source(name: str, py_jobs: list[dict], pr_jobs: list[dict]) -> dict[str, Any]:
    url_py, url_pr = _keys(py_jobs, by="url"), _keys(pr_jobs, by="url")
    id_py, id_pr = _keys(py_jobs, by="identity"), _keys(pr_jobs, by="identity")

    def _parity(a: set[str], b: set[str]) -> dict[str, Any]:
        both = a & b
        py_only = a - b
        pr_only = b - a
        union = a | b
        pct = (len(both) / len(union) * 100) if union else 100.0
        return {
            "overlap": len(both),
            "python_only": len(py_only),
            "patchright_only": len(pr_only),
            "parity_pct": round(pct, 1),
            "python_only_sample": sorted(py_only)[:3],
            "patchright_only_sample": sorted(pr_only)[:3],
        }

    url_cmp = _parity(url_py, url_pr)
    id_cmp = _parity(id_py, id_pr)
    match = url_cmp["python_only"] == 0 and url_cmp["patchright_only"] == 0

    return {
        "source": name,
        "python_count": len(py_jobs),
        "patchright_count": len(pr_jobs),
        "url": url_cmp,
        "identity": id_cmp,
        "match": match,
    }


def run_single_audit(
    config: dict[str, Any],
    sources: list[str],
    *,
    headless: bool,
) -> dict[str, Any]:
    py_all = run_python_collectors(config, sources)
    pr_all = asyncio.run(run_patchright_collectors(config, sources, headless=headless))
    results = [compare_source(n, py_all.get(n, []), pr_all.get(n, [])) for n in sources]
    all_match = all(r["match"] for r in results)
    return {
        "generated_at": datetime.now(TZ).isoformat(),
        "sources": results,
        "summary": {
            "all_match": all_match,
            "avg_url_parity_pct": round(
                sum(r["url"]["parity_pct"] for r in results) / len(results), 1
            )
            if results
            else 100.0,
            "sources_checked": len(results),
        },
    }


def append_history(report: dict[str, Any]) -> None:
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with HISTORY_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(report, ensure_ascii=False) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit Python vs Patchright board discovery")
    parser.add_argument("--source", action="append", default=[], help="Limit to source(s)")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--samples", type=int, default=1, help="Repeated runs (default 1)")
    parser.add_argument("--interval", type=int, default=0, help="Seconds between samples")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    config = load_config()
    enabled = [
        n
        for n, cfg in config.get("sources", {}).items()
        if cfg.get("enabled") and n in COLLECTORS and n != "linkedin"
    ]
    if args.source:
        enabled = [s for s in enabled if s in args.source]

    print("Board audit — Python urllib vs Patchright HTTP (same collectors)")
    print(f"Sources: {', '.join(enabled) or '(none)'}")
    print(f"Samples: {args.samples}\n")

    sample_reports: list[dict[str, Any]] = []
    for i in range(args.samples):
        if i > 0 and args.interval > 0:
            print(f"Waiting {args.interval}s before sample {i + 1}…")
            time.sleep(args.interval)
        if args.samples > 1:
            print(f"--- Sample {i + 1}/{args.samples} ---")
        print("Running Python collectors…")
        t0 = time.monotonic()
        report = run_single_audit(config, enabled, headless=args.headless)
        report["sample"] = i + 1
        report["elapsed_sec"] = round(time.monotonic() - t0, 1)
        sample_reports.append(report)
        append_history(report)

        if not args.json:
            for r in report["sources"]:
                flag = "✓" if r["match"] else "≠"
                u = r["url"]
                print(
                    f"{flag} {r['source']:<18} py={r['python_count']:>3} "
                    f"pr={r['patchright_count']:>3} url_parity={u['parity_pct']:>5}%"
                )

    final = {
        "generated_at": datetime.now(TZ).isoformat(),
        "samples": args.samples,
        "interval_sec": args.interval,
        "sources": enabled,
        "sample_reports": sample_reports,
        "summary": {
            "all_samples_match": all(s["summary"]["all_match"] for s in sample_reports),
            "all_sources_match_every_sample": all(
                all(r["match"] for r in s["sources"]) for s in sample_reports
            ),
        },
    }

    out_path = ROOT / "runs" / f"board-audit-{datetime.now(TZ).strftime('%Y-%m-%d')}.json"
    out_path.write_text(json.dumps(final, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(final, indent=2))
        return 0

    print(f"\nHistory: {HISTORY_PATH}")
    print(f"Report:  {out_path}")
    if final["summary"]["all_samples_match"]:
        print("Result: FULL parity — Python and Patchright return identical URL sets.")
    else:
        print("Result: MISMATCH — see samples above and report JSON.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
