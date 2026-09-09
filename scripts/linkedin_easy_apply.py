#!/usr/bin/env python3
"""LinkedIn Easy Apply — deterministic Patchright flow (no LLM).

Opens a /jobs/view/ URL, clicks Easy Apply, walks the modal wizard (contact,
resume, questions), and optionally submits.

Development: use --visual (default) to watch the headed browser.

Usage:
  linkedin_easy_apply.py apply --url URL [--visual] [--submit] [--hold 180]
  linkedin_easy_apply.py dry-run --url URL [--visual]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path
from typing import Any, Literal

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

import form_answers  # noqa: E402
from browser_session import close_session, launch_context  # noqa: E402
from flow_runner import resolve_recipe, run_recipe  # noqa: E402
from track_store import load_linkedin_jobs_config, load_profile as load_track_profile  # noqa: E402
from url_apply import (  # noqa: E402
    autofill,
    extract_fields,
    log_submission,
    notify_form_change,
)

MODAL_SELECTORS = (
    ".jobs-easy-apply-modal",
    ".jobs-easy-apply-content",
    "[data-test-modal-id='easy-apply-modal']",
)

WizardButton = Literal["next", "review", "submit", "none"]

NEXT_PATTERNS = (
    r"^Next$",
    r"Continue to next step",
    r"^Continue$",
)
REVIEW_PATTERNS = (r"Review your application", r"^Review$")
SUBMIT_PATTERNS = (r"Submit application", r"^Submit$")


def is_linkedin_job_url(url: str) -> bool:
    return "/jobs/view/" in (url or "").lower()


def load_profile(track_id: str | None = None) -> dict[str, Any]:
    return load_track_profile(track_id)


async def modal_locator(page):
    for sel in MODAL_SELECTORS:
        loc = page.locator(sel)
        if await loc.count() > 0:
            candidate = loc.first
            try:
                if await candidate.is_visible():
                    return candidate
            except Exception:  # noqa: BLE001
                continue
    dialog = page.locator("div[role='dialog']").filter(
        has=page.locator(".jobs-easy-apply-content, .jobs-easy-apply-modal, [data-test-modal-id='easy-apply-modal']")
    )
    if await dialog.count() > 0:
        try:
            if await dialog.first.is_visible():
                return dialog.first
        except Exception:  # noqa: BLE001
            pass
    return None


async def modal_visible(page) -> bool:
    loc = await modal_locator(page)
    if loc is None:
        return False
    try:
        return await loc.is_visible()
    except Exception:  # noqa: BLE001
        return False


async def detect_wizard_button(page) -> WizardButton:
    """Pick the primary footer action in the Easy Apply modal."""
    root = await modal_locator(page)
    scope = root if root is not None else page

    for pattern in SUBMIT_PATTERNS:
        btn = scope.get_by_role("button", name=re.compile(pattern, re.I))
        if await btn.count() > 0 and await btn.first.is_visible():
            return "submit"

    for pattern in REVIEW_PATTERNS:
        btn = scope.get_by_role("button", name=re.compile(pattern, re.I))
        if await btn.count() > 0 and await btn.first.is_visible():
            return "review"

    for pattern in NEXT_PATTERNS:
        btn = scope.get_by_role("button", name=re.compile(pattern, re.I))
        if await btn.count() > 0 and await btn.first.is_visible():
            return "next"

    btn = scope.locator("button[data-easy-apply-next-button]")
    if await btn.count() > 0 and await btn.first.is_visible():
        return "next"

    primary = scope.locator("footer button.artdeco-button--primary, .jobs-easy-apply-footer button.artdeco-button--primary")
    if await primary.count() > 0 and await primary.first.is_visible():
        label = (await primary.first.inner_text()).strip().lower()
        if "submit" in label:
            return "submit"
        if "review" in label:
            return "review"
        return "next"

    return "none"


async def click_wizard_button(page, kind: WizardButton, *, send: bool) -> dict[str, Any]:
    root = await modal_locator(page)
    scope = root if root is not None else page
    rec: dict[str, Any] = {"kind": kind, "clicked": False, "dry_run": False}

    patterns = {
        "submit": SUBMIT_PATTERNS,
        "review": REVIEW_PATTERNS,
        "next": NEXT_PATTERNS,
    }.get(kind, ())

    btn = None
    for pattern in patterns:
        loc = scope.get_by_role("button", name=re.compile(pattern, re.I))
        if await loc.count() > 0:
            btn = loc.first
            break
    if btn is None and kind == "next":
        loc = scope.locator("button[data-easy-apply-next-button]")
        if await loc.count() > 0:
            btn = loc.first
    if btn is None and kind in ("next", "review", "submit"):
        primary = scope.locator(
            "footer button.artdeco-button--primary, .jobs-easy-apply-footer button.artdeco-button--primary"
        )
        if await primary.count() > 0:
            btn = primary.first

    if btn is None:
        rec["error"] = f"{kind} button not found"
        return rec

    if kind == "submit" and not send:
        rec["dry_run"] = True
        rec["note"] = "DRY: would submit application"
        return rec

    try:
        await btn.wait_for(state="visible", timeout=8000)
        for _ in range(12):
            if await btn.is_enabled():
                break
            await asyncio.sleep(0.35)
        await btn.click(timeout=15000)
        rec["clicked"] = True
        await asyncio.sleep(2.0 if kind == "submit" else 1.2)
    except Exception as exc:  # noqa: BLE001
        rec["error"] = str(exc)[:160]
    return rec


async def fill_current_step(
    page,
    profile: dict[str, Any],
    answers: dict[str, str],
    *,
    track_id: str | None,
) -> dict[str, Any]:
    fields = await extract_fields(page)
    visible = [f for f in fields if f.get("type") != "hidden"]
    report = await autofill(page, visible, profile, answers, track_id=track_id)
    await notify_form_change(page)
    return report


async def open_easy_apply_modal(page, job_url: str, profile: dict[str, Any], *, send: bool) -> dict[str, Any]:
    from linkedin_ui import click_easy_apply_button  # noqa: WPS433

    recipe = resolve_recipe(job_url, name="linkedin-easy-apply-open")
    if recipe is None:
        recipe = resolve_recipe(job_url)
    if recipe is None or recipe.get("name") != "linkedin-easy-apply-open":
        raise RuntimeError("linkedin-easy-apply-open flow recipe missing under flows/")

    result = await run_recipe(
        page,
        recipe,
        variables={"job_url": job_url},
        profile=profile,
        send=send,
    )
    if not await modal_visible(page):
        click = await click_easy_apply_button(page)
        result = {**result, "fallback_click": click}
    if not await modal_visible(page):
        raise RuntimeError(
            "Easy Apply modal did not open — check that the job still has Easy Apply and you are signed in."
        )
    return result


async def run_wizard(
    page,
    profile: dict[str, Any],
    answers: dict[str, str],
    *,
    track_id: str | None,
    send: bool,
    max_steps: int = 10,
) -> dict[str, Any]:
    log: list[dict[str, Any]] = []
    submitted = False
    confirmed = False

    for step_idx in range(max_steps):
        if not await modal_visible(page):
            if submitted:
                break
            log.append({"step": step_idx, "note": "modal closed"})
            break

        report = await fill_current_step(page, profile, answers, track_id=track_id)
        gaps = [f for f in report.get("needs_input", []) + report.get("unmapped", []) if f.get("required")]
        log.append(
            {
                "step": step_idx,
                "filled": len(report.get("filled", [])),
                "gaps": len(gaps),
                "resume": report.get("resume_uploaded"),
            }
        )
        if gaps and send:
            return {
                "ok": False,
                "message": f"{len(gaps)} required field(s) unresolved — not submitting",
                "log": log,
                "submitted": False,
            }

        kind = await detect_wizard_button(page)
        if kind == "none":
            log.append({"step": step_idx, "note": "no wizard button"})
            break

        click = await click_wizard_button(page, kind, send=send)
        log.append({"step": step_idx, "button": kind, **click})

        if kind == "submit":
            submitted = click.get("clicked") or click.get("dry_run")
            if click.get("clicked"):
                body = ""
                try:
                    body = (await page.inner_text("body"))[:4000].lower()
                except Exception:  # noqa: BLE001
                    pass
                cues = (
                    "application sent",
                    "your application was sent",
                    "application submitted",
                    "thanks for applying",
                    "done",
                )
                confirmed = any(c in body for c in cues) or not await modal_visible(page)
            break

        if not click.get("clicked") and not click.get("dry_run"):
            break

    return {
        "ok": True,
        "submitted": submitted,
        "confirmed": confirmed,
        "log": log,
    }


async def run_apply(
    job_url: str,
    *,
    answers: dict[str, str],
    hold: int,
    hold_on_error: int,
    submit: bool,
    visual: bool,
    company: str = "",
    role: str = "",
    track_id: str | None = None,
    job_key: str = "",
) -> dict[str, Any]:
    if not is_linkedin_job_url(job_url):
        raise ValueError("URL must be a linkedin.com/jobs/view/ listing")

    profile = load_profile(track_id)
    jobs_cfg = load_linkedin_jobs_config(track_id)
    visual = visual if visual is not None else bool(jobs_cfg.get("easy_apply_visual", True))

    pw, browser, ctx = await launch_context(headless=not visual)
    summary: dict[str, Any] = {"url": job_url, "visual": visual, "submit": submit}

    try:
        page = await ctx.new_page()
        print(f"{'[visual]' if visual else '[headless]'} LinkedIn Easy Apply → {job_url}")
        open_result = await open_easy_apply_modal(page, job_url, profile, send=submit)
        summary["open"] = open_result

        wizard = await run_wizard(
            page,
            profile,
            answers,
            track_id=track_id,
            send=submit,
        )
        summary.update(wizard)

        if wizard.get("log"):
            last_fill = wizard["log"][0] if wizard["log"] else {}
            if "filled" in last_fill:
                print(f"wizard steps: {len(wizard['log'])} · submitted={wizard.get('submitted')}")

        if submit and wizard.get("submitted") and wizard.get("confirmed"):
            log_submission(
                job_url,
                page.url,
                company=company,
                role=role,
                confirmed=True,
                job_key=job_key,
            )
            print("✓ Easy Apply submitted + logged")
            from table_refresh import refresh_applications_table  # noqa: E402

            refresh_applications_table()
        elif submit and wizard.get("submitted"):
            log_submission(
                job_url,
                page.url,
                company=company,
                role=role,
                confirmed=False,
                job_key=job_key,
            )
            print("⚠ Submit clicked — verify confirmation in the browser")
            from table_refresh import refresh_applications_table  # noqa: E402

            refresh_applications_table()
        elif not submit:
            print("DRY-RUN: filled wizard steps; pass --submit to send application")

        print(f"\nholding browser open {hold}s…")
        await asyncio.sleep(hold)
    except Exception as exc:  # noqa: BLE001
        summary["ok"] = False
        summary["message"] = str(exc)[:240]
        print(f"ERROR: {summary['message']}")
        if visual and hold_on_error > 0:
            print(f"\nholding browser open {hold_on_error}s for review…")
            await asyncio.sleep(hold_on_error)
        raise
    finally:
        await close_session(pw=pw, browser=browser, context=ctx)

    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="LinkedIn Easy Apply (deterministic flow)")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--url", required=True, help="linkedin.com/jobs/view/… URL")
        p.add_argument("--answers", type=Path, help="JSON map for extra field answers")
        p.add_argument("--hold", type=int, default=120, help="Seconds to keep browser open")
        p.add_argument("--company", default="")
        p.add_argument("--role", default="")
        p.add_argument("--track", default=None)
        p.add_argument(
            "--visual",
            action=argparse.BooleanOptionalAction,
            default=True,
            help="Headed browser so you can watch (default: on)",
        )

    p_apply = sub.add_parser("apply", help="Open Easy Apply and walk the wizard")
    add_common(p_apply)
    p_apply.add_argument("--submit", action="store_true", help="Click Submit application on final step")
    p_apply.add_argument("--job-key", default="", help="Registry job key for UI status tracking")
    p_apply.add_argument("--hold-on-error", type=int, default=15, help="Seconds to keep browser open after failure")

    p_dry = sub.add_parser("dry-run", help="Fill steps without submitting")
    add_common(p_dry)

    args = parser.parse_args()
    answers: dict[str, str] = {}
    if getattr(args, "answers", None) and args.answers.exists():
        answers = json.loads(args.answers.read_text(encoding="utf-8"))

    submit = args.command == "apply" and bool(getattr(args, "submit", False))
    if args.command == "dry-run":
        submit = False

    result = asyncio.run(
        run_apply(
            args.url,
            answers=answers,
            hold=args.hold,
            hold_on_error=getattr(args, "hold_on_error", 15),
            submit=submit,
            visual=args.visual,
            company=args.company,
            role=args.role,
            track_id=args.track,
            job_key=getattr(args, "job_key", "") or "",
        )
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result.get("ok", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
