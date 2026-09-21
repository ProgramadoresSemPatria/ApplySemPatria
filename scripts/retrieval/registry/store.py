"""Job registry and run output management."""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from retrieval._paths import ROOT

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


PLACEHOLDER_KEY_RE = re.compile(r"^linkedin-post:[0-9a-f]+$", re.IGNORECASE)


def is_placeholder_job_key(key: str) -> bool:
    bare = (key or "").split("|")[-1].strip()
    return bool(PLACEHOLDER_KEY_RE.match(bare))


def remember_legacy_job_key(job: dict[str, Any], old_url: str) -> None:
    """Preserve linkedin-post:… keys after URL repair so stale UI snapshots still resolve."""
    old = (old_url or "").strip()
    if not old or not PLACEHOLDER_KEY_RE.match(old.split("|")[-1].strip()):
        return
    legacy = normalize_url(old)
    if legacy and not job.get("legacy_job_key"):
        job["legacy_job_key"] = legacy


def find_job_by_key(jobs: list[dict[str, Any]], key: str) -> dict[str, Any] | None:
    """Resolve a registry row by current or legacy (placeholder) job_key."""
    target = (key or "").strip().lower()
    if not target:
        return None
    track_prefix = ""
    bare = target
    if "|" in target:
        track_prefix, bare = target.split("|", 1)

    for job in jobs:
        if job_key(job) == target:
            return job
        legacy = (job.get("legacy_job_key") or "").strip().lower()
        if legacy and (legacy == target or legacy == bare):
            return job

    if not is_placeholder_job_key(bare):
        return None

    mapping = _placeholder_collect_mapping()
    meta = mapping.get(bare)
    if not meta:
        return None

    best: dict[str, Any] | None = None
    best_score = -1
    for job in jobs:
        if (job.get("company") or "").strip() != meta.get("company"):
            continue
        if (job.get("role") or "").casefold() != (meta.get("role") or "").casefold():
            continue
        score = 0
        if meta.get("search_query") and job.get("search_query") == meta["search_query"]:
            score += 4
        if meta.get("discovery_index") is not None and job.get("discovery_index") == meta["discovery_index"]:
            score += 8
        if meta.get("region_tag") and job.get("region_tag") == meta["region_tag"]:
            score += 2
        if score > best_score:
            best_score = score
            best = job
    if best and not best.get("legacy_job_key"):
        best["legacy_job_key"] = bare
    return best


def _placeholder_collect_mapping() -> dict[str, dict[str, Any]]:
    cached = getattr(find_job_by_key, "_placeholder_map", None)
    if cached is not None:
        return cached

    from linkedin_posts_merge import is_placeholder_post_url  # noqa: WPS433

    mapping: dict[str, dict[str, Any]] = {}
    for path in sorted(RUNS_DIR.glob("browser-collect*/**/*.json")):
        if not path.exists():
            continue
        try:
            with path.open(encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        for job in data.get("jobs") or []:
            if not isinstance(job, dict):
                continue
            url = (job.get("url") or "").strip()
            if not is_placeholder_post_url(url):
                continue
            pid = normalize_url(url)
            mapping[pid] = {
                "company": (job.get("company") or "").strip(),
                "role": (job.get("role") or "Ai Engineer").strip(),
                "search_query": job.get("search_query"),
                "discovery_index": job.get("discovery_index"),
                "region_tag": job.get("region_tag"),
            }
    find_job_by_key._placeholder_map = mapping  # type: ignore[attr-defined]
    return mapping


def backfill_legacy_job_keys(registry: dict[str, Any] | None = None) -> int:
    """Attach legacy_job_key from browser-collect placeholders to repaired registry rows."""
    data = registry if registry is not None else load_registry()
    jobs = data.get("jobs") or []
    mapping = _placeholder_collect_mapping()
    updated = 0
    for pid, meta in mapping.items():
        matches = [
            j
            for j in jobs
            if (j.get("company") or "").strip() == meta.get("company")
            and (j.get("role") or "").casefold() == (meta.get("role") or "").casefold()
        ]
        if not matches:
            continue
        target = matches[0]
        if len(matches) > 1:
            for j in matches:
                if j.get("discovery_index") == meta.get("discovery_index"):
                    target = j
                    break
                if meta.get("search_query") and j.get("search_query") == meta["search_query"]:
                    target = j
        if target.get("legacy_job_key") != pid:
            target["legacy_job_key"] = pid
            updated += 1
    if registry is None and updated:
        save_registry(data)
    return updated


def load_registry() -> dict[str, Any]:
    data = load_json(REGISTRY_PATH, {"jobs": []})
    if "jobs" not in data:
        data["jobs"] = []
    return data


def save_registry(data: dict[str, Any]) -> None:
    save_json(REGISTRY_PATH, data)


def index_registry(registry: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {job_key(j): j for j in registry.get("jobs", [])}


def infer_period_days_from_since(value: str | None, *, now: datetime | None = None) -> int:
    """Map ingestion ``since`` to LinkedIn date-posted filter (1–7 days)."""
    since = parse_since(value, None)
    min_dt = datetime.min.replace(tzinfo=timezone.utc)
    if since <= min_dt:
        return 7
    now = now or datetime.now(timezone.utc)
    hours = max(0.0, (now - since.astimezone(timezone.utc)).total_seconds() / 3600)
    # Allow next-morning research after an afternoon run (~36h).
    if hours <= 36:
        return 1
    days = int(hours / 24) + (1 if hours % 24 > 0 else 0)
    return min(7, max(1, days))


def job_posted_on_or_after(job: dict[str, Any], since: datetime) -> bool:
    """True when ``posted_at`` (or ``discovered_at`` fallback) is on/after ``since``."""
    since_utc = since.astimezone(timezone.utc) if since.tzinfo else since.replace(tzinfo=timezone.utc)
    posted = parse_posted_at(job.get("posted_at"))
    if posted is not None:
        return posted >= since_utc
    discovered = parse_posted_at(job.get("discovered_at"))
    if discovered is not None:
        return discovered >= since_utc
    return True


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
