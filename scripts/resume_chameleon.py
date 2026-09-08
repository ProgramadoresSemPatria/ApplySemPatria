"""ResumeChameleon — tailor CV headline per role from master documents."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from registry import job_key as registry_job_key  # noqa: E402
from registry import load_registry  # noqa: E402
from resume_keywords import (  # noqa: E402
    extract_role_keywords_for_job,
    join_headline_paragraph,
    merge_headline_skill_list,
    normalize_keyword,
    parse_pipe_skills,
    split_headline_paragraph,
)
from resume_pdf import (  # noqa: E402
    DEFAULT_PDF_FONT_PATH,
    distribute_skills_to_lines,
    extract_pdf_headline,
    generate_pdf_from_master,
    skills_from_pdf_headline,
    _resolve_font_path,
)
from track_store import (  # noqa: E402
    infer_track,
    load_chameleon_config,
    resolve_track,
    save_chameleon_config,
    track_label,
)

TZ = ZoneInfo("America/Sao_Paulo")

DEFAULT_CHAMELEON_CONFIG: dict[str, Any] = {
    "enabled": True,
    "output_format": "pdf",
    "download_dir": "~/Downloads",
    "cache_dir": "state/chameleon",
    "headline_separator": " | ",
    "headline_max_chars": 280,
    "headline_max_chars_per_line": 95,
    "headline_max_lines": 2,
    "headline_max_skills": 18,
    "headline_paragraph_index": 1,
    "pdf_skills_y_min": 65.0,
    "pdf_skills_y_max": 95.0,
    "pdf_headline_font_size": 11.5,
    "pdf_font_path": "/System/Library/Fonts/Supplemental/Tahoma.ttf",
    "pdf_headline_min_font_size": 8.0,
    "compact_trailing_pages": True,
    "pdf_sparse_tail_max_y": 220.0,
    "pdf_tail_merge_gap": 16.0,
    "pdf_bottom_margin": 36.0,
    "pdf_prev_page_min_fill_ratio": 0.55,
    "tech_lexicon": [],
    "masters": [],
}


def _expand(path: str | Path) -> Path:
    return Path(str(path).replace("~/", f"{Path.home()}/")).expanduser().resolve()


def _pdf_font_path(cfg: dict[str, Any]) -> Path:
    try:
        return _resolve_font_path(cfg)
    except FileNotFoundError:
        return Path(DEFAULT_PDF_FONT_PATH)


def _slug(text: str, *, max_len: int = 40) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return slug[:max_len] or "role"


def default_chameleon_config(track_id: str | None = None) -> dict[str, Any]:
    cfg = dict(DEFAULT_CHAMELEON_CONFIG)
    tid = resolve_track(track_id)
    try:
        from track_store import load_profile  # noqa: WPS433

        profile = load_profile(tid)
        from track_store import load_email_config  # noqa: WPS433

        email_cfg = load_email_config(tid)
        resume = (email_cfg.get("resume_path") or profile.get("resume_path") or "").strip()
        if resume:
            pdf_path = _expand(resume)
            docx_path = pdf_path.with_suffix(".docx")
            if pdf_path.suffix.lower() != ".pdf":
                docx_path = pdf_path if pdf_path.suffix.lower() == ".docx" else pdf_path.with_suffix(".docx")
                pdf_path = pdf_path if pdf_path.suffix.lower() == ".pdf" else pdf_path.parent / f"{pdf_path.stem}.pdf"
            if not pdf_path.is_file() and docx_path.is_file():
                pdf_guess = docx_path.parent / f"{docx_path.stem}.pdf"
                if pdf_guess.is_file():
                    pdf_path = pdf_guess
            cfg["masters"] = [
                {
                    "id": tid.replace("_", "-"),
                    "label": track_label(tid),
                    "pdf_path": str(pdf_path) if pdf_path.is_file() else "",
                    "docx_path": str(docx_path) if docx_path.is_file() else "",
                    "path": str(pdf_path if pdf_path.is_file() else docx_path),
                    "default": True,
                    "keywords": [],
                }
            ]
    except Exception:  # noqa: BLE001
        pass
    return cfg


def chameleon_config_path(track_id: str | None = None) -> Path:
    from track_store import track_path  # noqa: WPS433

    return track_path(track_id, "chameleon_config_path")


def master_pdf_path(master: dict[str, Any]) -> Path | None:
    for key in ("pdf_path", "path"):
        raw = (master.get(key) or "").strip()
        if not raw:
            continue
        path = _expand(raw)
        if path.suffix.lower() == ".pdf" and path.is_file():
            return path
    return None


def master_docx_path(master: dict[str, Any]) -> Path | None:
    for key in ("docx_path", "path"):
        raw = (master.get(key) or "").strip()
        if not raw:
            continue
        path = _expand(raw)
        if path.suffix.lower() == ".docx" and path.is_file():
            return path
    return None


def master_is_ready(master: dict[str, Any]) -> bool:
    return master_pdf_path(master) is not None or master_docx_path(master) is not None


def chameleon_is_configured(cfg: dict[str, Any] | None = None, *, track_id: str | None = None) -> bool:
    data = cfg if cfg is not None else load_chameleon_config(track_id)
    if not data.get("enabled", True):
        return False
    masters = data.get("masters") or []
    return any(master_is_ready(m) for m in masters)


def chameleon_status(track_id: str | None = None) -> dict[str, Any]:
    tid = resolve_track(track_id)
    cfg = load_chameleon_config(tid)
    masters = cfg.get("masters") or []
    valid = [m for m in masters if master_is_ready(m)]
    ready = chameleon_is_configured(cfg)
    if ready:
        message = f"{len(valid)} master CV(s) ready."
    elif not masters:
        message = "Add at least one master CV in Settings → CV Chameleon or run `jobsearch chameleon setup`."
    else:
        message = "Master CV path(s) missing — update CV Chameleon settings."
    return {
        "ready": ready,
        "message": message,
        "masters_count": len(valid),
        "track_id": tid,
    }


def _master_format(master: dict[str, Any], path: Path) -> str:
    explicit = (master.get("format") or "").strip().lower()
    if explicit:
        return explicit
    return path.suffix.lstrip(".").lower() or "pdf"


def _read_docx_paragraph(path: Path, index: int) -> str:
    from docx import Document  # noqa: WPS433

    doc = Document(str(path))
    if index < 0 or index >= len(doc.paragraphs):
        raise IndexError(f"Paragraph index {index} out of range for {path.name}")
    return doc.paragraphs[index].text or ""


def _write_docx_paragraph(path: Path, index: int, text: str, dest: Path) -> None:
    from docx import Document  # noqa: WPS433

    doc = Document(str(path))
    if index < 0 or index >= len(doc.paragraphs):
        raise IndexError(f"Paragraph index {index} out of range for {path.name}")
    doc.paragraphs[index].text = text
    dest.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(dest))


def headline_skills_from_master(master: dict[str, Any], cfg: dict[str, Any]) -> list[str]:
    keywords = list(master.get("keywords") or [])
    sep = cfg.get("headline_separator") or " | "
    pdf_path = master_pdf_path(master)
    if pdf_path:
        try:
            headline = extract_pdf_headline(
                pdf_path,
                skills_y_min=float(cfg.get("pdf_skills_y_min", 65.0)),
                skills_y_max=float(cfg.get("pdf_skills_y_max", 95.0)),
            )
            parsed = skills_from_pdf_headline(headline, sep)
            if parsed:
                return parsed
        except Exception:  # noqa: BLE001
            pass
    docx_path = master_docx_path(master)
    if docx_path:
        try:
            paragraph = _read_docx_paragraph(docx_path, int(cfg.get("headline_paragraph_index", 1)))
            _, skills_line = split_headline_paragraph(paragraph)
            parsed = parse_pipe_skills(skills_line, sep)
            if parsed:
                return parsed
        except Exception:  # noqa: BLE001
            pass
    return [k for k in keywords if k]


def score_master(master: dict[str, Any], role_keywords: list[str], cfg: dict[str, Any]) -> int:
    role_set = {normalize_keyword(k) for k in role_keywords if k}
    master_terms = {normalize_keyword(k) for k in headline_skills_from_master(master, cfg) if k}
    master_terms.update(normalize_keyword(k) for k in master.get("keywords") or [] if k)
    score = len(master_terms & role_set)
    if master.get("default"):
        score += 1
    return score


def pick_best_master(cfg: dict[str, Any], role_keywords: list[str]) -> dict[str, Any] | None:
    candidates = [m for m in cfg.get("masters") or [] if master_is_ready(m)]
    if not candidates:
        return None
    scored = sorted(
        ((score_master(m, role_keywords, cfg), m) for m in candidates),
        key=lambda item: (item[0], bool(item[1].get("default"))),
        reverse=True,
    )
    return scored[0][1]


def sync_master_keywords(track_id: str | None = None, *, save: bool = True) -> dict[str, Any]:
    """Re-read headline skills from master PDF/DOCX into config keywords."""
    tid = resolve_track(track_id)
    cfg = load_chameleon_config(tid)
    updated: list[dict[str, Any]] = []
    sep = cfg.get("headline_separator") or " | "
    for master in cfg.get("masters") or []:
        master = dict(master)
        skills = headline_skills_from_master(master, cfg)
        if skills:
            master["keywords"] = skills
        updated.append(master)
    cfg["masters"] = updated
    if save:
        save_chameleon_config(tid, cfg)
    return cfg


def cache_dir_for(cfg: dict[str, Any], track_id: str) -> Path:
    rel = cfg.get("cache_dir") or "state/chameleon"
    base = _expand(rel)
    if not base.is_absolute():
        base = (ROOT / rel).resolve()
    return (base / track_id).resolve()


def artifact_paths(cfg: dict[str, Any], track_id: str, jk: str) -> tuple[Path, Path]:
    cache = cache_dir_for(cfg, track_id)
    safe = re.sub(r"[^a-zA-Z0-9._-]+", "_", jk)[:180]
    ext = "pdf" if (cfg.get("output_format") or "pdf").lower() == "pdf" else "docx"
    return cache / f"{safe}.json", cache / f"{safe}.{ext}"


def output_filename(master_path: Path, job: dict[str, Any], ext: str) -> str:
    stem = master_path.stem
    company = _slug(job.get("company") or "company")
    role = _slug(job.get("role") or "role")
    return f"{stem}-{company}-{role}.{ext.lstrip('.')}"


def generate_for_job(
    job: dict[str, Any],
    *,
    track_id: str | None = None,
    master_id: str | None = None,
    download: bool = True,
) -> dict[str, Any]:
    tid = resolve_track(track_id or infer_track(job))
    cfg = load_chameleon_config(tid)
    if not chameleon_is_configured(cfg):
        raise RuntimeError(chameleon_status(tid)["message"])

    role_keywords = extract_role_keywords_for_job(job, cfg)
    master = None
    if master_id:
        for item in cfg.get("masters") or []:
            if item.get("id") == master_id:
                master = item
                break
        if not master:
            raise ValueError(f"Unknown master id: {master_id}")
    else:
        master = pick_best_master(cfg, role_keywords)
    if not master:
        raise RuntimeError("No usable master CV found.")

    pdf_path = master_pdf_path(master)
    docx_path = master_docx_path(master)
    output_format = (cfg.get("output_format") or "pdf").lower()
    jk = registry_job_key(job)
    meta_path, cache_out = artifact_paths(cfg, tid, jk)
    download_dir = _expand(cfg.get("download_dir") or "~/Downloads")
    download_dir.mkdir(parents=True, exist_ok=True)
    sep = cfg.get("headline_separator") or " | "

    existing_skills = headline_skills_from_master(master, cfg)
    merged_list = merge_headline_skill_list(
        role_keywords,
        existing_skills,
        max_skills=int(cfg.get("headline_max_skills") or 18),
    )
    skill_lines = distribute_skills_to_lines(
        merged_list,
        separator=sep,
        max_lines=int(cfg.get("headline_max_lines") or 2),
        max_chars_per_line=int(cfg.get("headline_max_chars_per_line") or 95),
        font_path=_pdf_font_path(cfg) if pdf_path else None,
        font_size=float(cfg.get("pdf_headline_font_size") or 11.5),
    )

    result: dict[str, Any] = {
        "job_key": jk,
        "track_id": tid,
        "master_id": master.get("id"),
        "master_label": master.get("label"),
        "master_pdf_path": str(pdf_path) if pdf_path else "",
        "master_docx_path": str(docx_path) if docx_path else "",
        "role_keywords": role_keywords,
        "existing_skills": existing_skills,
        "merged_skills": merged_list,
        "skill_lines": skill_lines,
        "headline_edited": False,
        "generated_at": datetime.now(TZ).isoformat(),
        "output_format": output_format,
    }

    if output_format == "pdf" and pdf_path:
        before = extract_pdf_headline(
            pdf_path,
            skills_y_min=float(cfg.get("pdf_skills_y_min", 65.0)),
            skills_y_max=float(cfg.get("pdf_skills_y_max", 95.0)),
        )
        result["headline_before"] = [row.get("text") for row in before.get("skill_lines") or []]
        result["headline_after"] = skill_lines
        result["headline_edited"] = result["headline_before"] != skill_lines
        layout = generate_pdf_from_master(pdf_path, cache_out, skill_lines, cfg=cfg)
        result["pdf_layout"] = layout
        out_name = output_filename(pdf_path, job, "pdf")
        download_path = download_dir / out_name
        shutil.copy2(cache_out, download_path)
        result["output_path"] = str(download_path)
        result["cache_path"] = str(cache_out)
        result["format"] = "pdf"
    elif docx_path:
        paragraph_index = int(cfg.get("headline_paragraph_index", 1))
        original = _read_docx_paragraph(docx_path, paragraph_index)
        title_block, _ = split_headline_paragraph(original)
        new_paragraph = join_headline_paragraph(title_block, sep.join(skill_lines))
        result["headline_edited"] = normalize_keyword(original) != normalize_keyword(new_paragraph)
        result["headline_before"] = original
        result["headline_after"] = new_paragraph
        _write_docx_paragraph(docx_path, paragraph_index, new_paragraph, cache_out)
        out_name = output_filename(docx_path, job, "docx")
        download_path = download_dir / out_name
        shutil.copy2(cache_out, download_path)
        result["output_path"] = str(download_path)
        result["cache_path"] = str(cache_out)
        result["format"] = "docx"
    elif pdf_path:
        out_name = output_filename(pdf_path, job, "pdf")
        download_path = download_dir / out_name
        shutil.copy2(pdf_path, download_path)
        result["output_path"] = str(download_path)
        result["cache_path"] = str(download_path)
        result["format"] = "pdf"
        result["note"] = "PDF copied without headline edits (missing PyMuPDF or skill lines)."
    else:
        raise FileNotFoundError("No master PDF or DOCX found for this track.")

    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if download:
        result["download_path"] = str(download_path)
    return result


def find_job_by_key(job_key_value: str) -> dict[str, Any] | None:
    for job in load_registry()["jobs"]:
        if registry_job_key(job) == job_key_value:
            return job
    return None


def resolve_output_for_job(job_key_value: str, *, track_id: str | None = None) -> Path | None:
    job = find_job_by_key(job_key_value)
    if not job:
        return None
    tid = resolve_track(track_id or infer_track(job))
    cfg = load_chameleon_config(tid)
    meta_path, cache_out = artifact_paths(cfg, tid, job_key_value)
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        out = Path(meta.get("output_path") or "")
        if out.is_file():
            return out
    if cache_out.is_file():
        return cache_out
    return None


def cmd_generate(args: argparse.Namespace) -> int:
    job = find_job_by_key(args.job_key)
    if not job:
        print(f"ERROR: Job not found: {args.job_key}")
        return 1
    try:
        result = generate_for_job(
            job,
            track_id=args.track,
            master_id=args.master,
            download=not args.no_download,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 1

    print(f"Master: {result.get('master_label')} ({result.get('master_id')})")
    print(f"Role keywords ({len(result.get('role_keywords') or [])}): {', '.join(result.get('role_keywords') or [])}")
    merged = result.get("merged_skills") or []
    print(f"Headline skills ({len(merged)}): {' | '.join(merged)}")
    for idx, line in enumerate(result.get("skill_lines") or [], start=1):
        print(f"  line {idx}: {line}")
    if result.get("headline_edited"):
        print("\nHeadline updated.")
    elif result.get("note"):
        print(f"\n{result['note']}")
    print(f"\nSaved → {result.get('output_path')}")
    return 0


def cmd_keywords(args: argparse.Namespace) -> int:
    job = find_job_by_key(args.job_key)
    if not job:
        print(f"ERROR: Job not found: {args.job_key}")
        return 1
    cfg = load_chameleon_config(args.track)
    keywords = extract_role_keywords_for_job(job, cfg)
    if args.json:
        print(json.dumps({"job_key": args.job_key, "keywords": keywords}, indent=2))
    else:
        print(f"Keywords for {job.get('role')} @ {job.get('company')}:")
        for kw in keywords:
            print(f"  - {kw}")
    return 0


def cmd_masters(args: argparse.Namespace) -> int:
    cfg = load_chameleon_config(args.track)
    masters = cfg.get("masters") or []
    if not masters:
        print("No masters configured.")
        return 0
    print(f"Masters for {track_label(args.track)}:\n")
    for master in masters:
        pdf = master_pdf_path(master)
        docx = master_docx_path(master)
        ok = "✓" if master_is_ready(master) else "✗"
        default = " (default)" if master.get("default") else ""
        print(f"  [{ok}] {master.get('id')}: {master.get('label')}{default}")
        if pdf:
            print(f"      pdf:  {pdf}")
        if docx:
            print(f"      docx: {docx}")
        kws = master.get("keywords") or []
        if kws:
            print(f"      keywords: {', '.join(kws[:12])}{'…' if len(kws) > 12 else ''}")
    return 0


def cmd_sync(args: argparse.Namespace) -> int:
    cfg = sync_master_keywords(args.track, save=not args.dry_run)
    print(f"Synced masters for {track_label(args.track)}:")
    for master in cfg.get("masters") or []:
        kws = master.get("keywords") or []
        print(f"  {master.get('id')}: {len(kws)} keyword(s)")
    if args.dry_run:
        print("(dry run — not saved)")
    return 0


def cmd_setup(args: argparse.Namespace) -> int:
    tid = resolve_track(args.track)
    path = chameleon_config_path(tid)
    if path.exists() and not args.force:
        print(f"Config already exists: {path}")
        print("Use --force to recreate from profile resume.")
        return 0
    cfg = default_chameleon_config(tid)
    if args.master:
        cfg["masters"] = [
            {
                "id": args.master_id or tid.replace("_", "-"),
                "label": args.master_label or track_label(tid),
                "path": str(_expand(args.master)),
                "format": Path(args.master).suffix.lstrip(".").lower() or "docx",
                "default": True,
                "keywords": [],
            }
        ]
    save_chameleon_config(tid, cfg)
    sync_master_keywords(tid)
    print(f"Created CV Chameleon config → {path}")
    print(chameleon_status(tid)["message"])
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    status = chameleon_status(args.track)
    if args.json:
        print(json.dumps(status, indent=2))
    else:
        flag = "ready" if status["ready"] else "not ready"
        print(f"CV Chameleon ({status['track_id']}): {flag}")
        print(status["message"])
    return 0


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--track", default=None, help="Career track (default from tracks.json)")

    parser = argparse.ArgumentParser(description="ResumeChameleon — tailor CV per role")
    sub = parser.add_subparsers(dest="command", required=True)

    gen = sub.add_parser("generate", parents=[common], help="Generate tailored CV for a job")
    gen.add_argument("--job-key", required=True)
    gen.add_argument("--master", default=None, help="Force a master id")
    gen.add_argument("--no-download", action="store_true", help="Only write cache, skip ~/Downloads copy")
    gen.set_defaults(func=cmd_generate)

    kw = sub.add_parser("keywords", parents=[common], help="Show extracted role keywords")
    kw.add_argument("--job-key", required=True)
    kw.add_argument("--json", action="store_true")
    kw.set_defaults(func=cmd_keywords)

    masters = sub.add_parser("masters", parents=[common], help="List configured master CVs")
    masters.set_defaults(func=cmd_masters)

    sync = sub.add_parser("sync", parents=[common], help="Re-read headline keywords from master DOCX files")
    sync.add_argument("--dry-run", action="store_true")
    sync.set_defaults(func=cmd_sync)

    setup = sub.add_parser("setup", parents=[common], help="Create chameleon config from profile resume")
    setup.add_argument("--master", help="Master DOCX/PDF path")
    setup.add_argument("--master-id", default=None)
    setup.add_argument("--master-label", default=None)
    setup.add_argument("--force", action="store_true")
    setup.set_defaults(func=cmd_setup)

    status = sub.add_parser("status", parents=[common], help="Show setup readiness")
    status.add_argument("--json", action="store_true")
    status.set_defaults(func=cmd_status)

    return parser


def main() -> int:
    args = build_parser().parse_args()
    if getattr(args, "track", None):
        resolve_track(args.track)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
