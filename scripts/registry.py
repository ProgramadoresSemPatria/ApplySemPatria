"""Job registry and run output management."""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
REGISTRY_PATH = ROOT / "registry" / "jobs.json"
STATE_PATH = ROOT / "state" / "last-run.json"
RUNS_DIR = ROOT / "runs"
LOCAL_TZ = ZoneInfo("America/Sao_Paulo")


def load_json(path: Path, default: dict | list) -> dict | list:
    if not path.exists():
        return default
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def normalize_url(url: str) -> str:
    return url.strip().rstrip("/").lower()


def job_key(job: dict[str, Any]) -> str:
    track = (job.get("track") or "").strip().lower()
    prefix = f"{track}|" if track else ""
    url = job.get("url") or ""
    if url:
        return prefix + normalize_url(url)
    company = (job.get("company") or "").strip().lower()
    role = (job.get("role") or "").strip().lower()
    source = (job.get("source") or "").strip().lower()
    return prefix + f"{source}|{company}|{role}"


def load_registry() -> dict[str, Any]:
    data = load_json(REGISTRY_PATH, {"jobs": []})
    if "jobs" not in data:
        data["jobs"] = []
    return data


def save_registry(data: dict[str, Any]) -> None:
    save_json(REGISTRY_PATH, data)


def index_registry(registry: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {job_key(j): j for j in registry.get("jobs", [])}


def parse_since(value: str | None, last_run: str | None) -> datetime:
    if not value or value == "last-run":
        if last_run:
            return datetime.fromisoformat(last_run)
        return datetime.min.replace(tzinfo=timezone.utc)

    value = value.strip()
    relative = re.fullmatch(r"(\d+)([hdm])", value, re.IGNORECASE)
    if relative:
        amount = int(relative.group(1))
        unit = relative.group(2).lower()
        now = datetime.now(timezone.utc)
        if unit == "h":
            return now.replace(microsecond=0) - timedelta(hours=amount)
        if unit == "d":
            return now.replace(microsecond=0) - timedelta(days=amount)
        if unit == "m":
            return now.replace(microsecond=0) - timedelta(days=amount * 30)

    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=LOCAL_TZ)
    return dt.astimezone(timezone.utc)


def parse_posted_at(value: str | int | float | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    if text.isdigit():
        return datetime.fromtimestamp(int(text), tz=timezone.utc)
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def is_new_for_run(job: dict[str, Any], since: datetime, known: dict[str, dict[str, Any]]) -> bool:
    key = job_key(job)
    if key in known:
        return False
    posted = parse_posted_at(job.get("posted_at"))
    if posted and posted >= since.astimezone(timezone.utc):
        return True
    if since == datetime.min.replace(tzinfo=timezone.utc):
        return True
    return key not in known


def merge_jobs(
    registry: dict[str, Any],
    incoming: list[dict[str, Any]],
    since: datetime,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    known = index_registry(registry)
    new_for_run: list[dict[str, Any]] = []
    now_iso = datetime.now(LOCAL_TZ).isoformat()

    for job in incoming:
        key = job_key(job)
        job.setdefault("discovered_at", now_iso)
        posted = parse_posted_at(job.get("posted_at"))
        if key in known:
            continue
        if since != datetime.min.replace(tzinfo=timezone.utc):
            if posted is None:
                pass
            elif posted < since.astimezone(timezone.utc):
                continue
        registry["jobs"].append(job)
        known[key] = job
        new_for_run.append(job)

    return registry, new_for_run


def write_run_markdown(
    run_path: Path,
    since: datetime,
    new_jobs: list[dict[str, Any]],
    source_stats: dict[str, Any],
    errors: list[str],
) -> None:
    run_path.parent.mkdir(parents=True, exist_ok=True)
    eligible = [j for j in new_jobs if j.get("filter_result") == "eligible"]
    skipped = [j for j in new_jobs if j.get("filter_result") == "skipped"]
    review = [j for j in new_jobs if j.get("filter_result") == "needs_review"]
    now = datetime.now(LOCAL_TZ)

    lines = [
        f"# Job discovery run — {now.strftime('%Y-%m-%d %H:%M %Z')}",
        "",
        f"**Since:** {since.isoformat()}",
        "",
        "## Summary",
        "",
        f"- New jobs found: **{len(new_jobs)}**",
        f"- Eligible: **{len(eligible)}**",
        f"- Skipped: **{len(skipped)}**",
        f"- Needs review: **{len(review)}**",
        "",
        "## Source stats",
        "",
        "| Source | Fetched | New | Eligible | Error |",
        "|--------|---------|-----|----------|-------|",
    ]

    for source, stats in sorted(source_stats.items()):
        lines.append(
            f"| {source} | {stats.get('fetched', 0)} | {stats.get('new', 0)} | "
            f"{stats.get('eligible', 0)} | {stats.get('error') or '—'} |"
        )

    if errors:
        lines.extend(["", "## Errors", ""])
        for err in errors:
            lines.append(f"- {err}")

    lines.extend(["", "## Eligible jobs (apply manually)", ""])
    if eligible:
        lines.extend(
            [
                "| ☐ | Role | Company | Salary (USD) | Location | Source | URL |",
                "|---|------|---------|--------------|----------|--------|-----|",
            ]
        )
        for job in eligible:
            salary = job.get("salary_usd") or "—"
            location = job.get("location_note") or job.get("location") or "—"
            lines.append(
                f"| ☐ | {job.get('role', '—')} | {job.get('company', '—')} | "
                f"{salary} | {location} | {job.get('source', '—')} | {job.get('url', '—')} |"
            )
    else:
        lines.append("_No eligible jobs this run._")

    if review:
        lines.extend(["", "## Needs review", ""])
        lines.extend(["| Role | Company | Reason | URL |", "|------|---------|--------|-----|"])
        for job in review:
            lines.append(
                f"| {job.get('role', '—')} | {job.get('company', '—')} | "
                f"{job.get('skip_reason', '—')} | {job.get('url', '—')} |"
            )

    if skipped:
        lines.extend(["", "## Skipped", ""])
        lines.extend(["| Role | Company | Reason | URL |", "|------|---------|--------|-----|"])
        for job in skipped:
            lines.append(
                f"| {job.get('role', '—')} | {job.get('company', '—')} | "
                f"{job.get('skip_reason', '—')} | {job.get('url', '—')} |"
            )

    run_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def purge_discovered_on_days(days: list[str]) -> int:
    """Remove registry rows whose ``discovered_at`` date is in ``days`` (YYYY-MM-DD)."""
    drop = {d.strip() for d in days if d and d.strip()}
    if not drop:
        return 0
    registry = load_registry()
    kept: list[dict[str, Any]] = []
    removed = 0
    for job in registry.get("jobs", []):
        raw = str(job.get("discovered_at") or "")
        if raw[:10] in drop:
            removed += 1
        else:
            kept.append(job)
    if removed:
        registry["jobs"] = kept
        save_registry(registry)
    return removed
