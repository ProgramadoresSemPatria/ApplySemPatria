#!/usr/bin/env python3
"""Deterministic Playwright flow runner.

Executes saved step recipes (JSON) so repeated apply flows run WITHOUT any LLM
reasoning. The LLM only needs to discover a flow once; save it under flows/ and
replay it forever.

Recipe schema (flows/*.json):
{
  "name": "linkedin-connect-or-message",
  "description": "...",
  "match": {"url_contains": ["linkedin.com/in/"], "domains": ["greenhouse.io"]},
  "vars_required": ["profile_url"],
  "branches": [                      # optional; first branch whose `when` matches runs
    {"name": "already_connected",
     "when": {"exists": {"role": "button", "name_regex": "^Message"}},
     "steps": [...]},
    {"name": "fallback", "when": {"always": true}, "steps": [...]}
  ],
  "steps": [...]                     # used when no branches
}

Step actions:
  goto     {"target": "{profile_url}", "wait_until": "domcontentloaded", "timeout": 60000}
  sleep    {"seconds": 2.5}
  click    {"role": "button", "name_regex": "^Connect$"} | {"selector": "..."}
           optional flags: "optional": true, "destructive": true
  fill     {"selector": "#email", "profile_key": "email"} |
           {"role": "textbox", "value_template": "{message}", "index": 0}
  upload   {"selector": "input[type=file]", "profile_key": "resume_path"}
  select   {"selector": "#country", "profile_key": "country" | "value": "Brazil"}
  check    {"selector": "#remote", "when_value": "yes"}
  screenshot {"path": "runs/shot.png"}
  assert_visible {"role": "button", "name_regex": "..."}  (records pass/fail)

Steps marked "destructive": true (click that submits/connects/sends, fill of a
message, upload, submit) are SKIPPED in dry-run — logged as "would …".
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
FLOWS_DIR = ROOT / "flows"
LEARNED_DIR = FLOWS_DIR / "learned"


def load_recipes() -> list[dict[str, Any]]:
    recipes: list[dict[str, Any]] = []
    for d in (FLOWS_DIR, LEARNED_DIR):
        if not d.exists():
            continue
        for path in sorted(d.glob("*.json")):
            try:
                recipes.append(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                continue
    return recipes


def resolve_recipe(url: str, *, name: str | None = None) -> dict[str, Any] | None:
    url_l = (url or "").lower()
    if name:
        for recipe in load_recipes():
            if recipe.get("name") == name:
                return recipe
        return None
    for recipe in load_recipes():
        match = recipe.get("match", {})
        if any(s.lower() in url_l for s in match.get("url_contains", [])):
            return recipe
        if any(d.lower() in url_l for d in match.get("domains", [])):
            return recipe
    return None


def _subst(text: str, variables: dict[str, str]) -> str:
    if not isinstance(text, str):
        return text
    for k, v in variables.items():
        text = text.replace("{" + k + "}", str(v))
    return text


def _locator(page, step: dict[str, Any], variables: dict[str, str]):
    # Optional CSS scope (e.g. "main") to disambiguate controls that appear
    # multiple times on a page (LinkedIn has many "More" buttons).
    scope = step.get("scope")
    base = page.locator(scope).first if scope else page
    if "selector" in step:
        return base.locator(_subst(step["selector"], variables))
    role = step.get("role")
    name_regex = step.get("name_regex")
    if role and name_regex:
        return base.get_by_role(role, name=re.compile(name_regex, re.I))
    if role:
        return base.get_by_role(role)
    raise ValueError(f"step needs selector or role: {step}")


async def _exists(page, cond: dict[str, Any], variables: dict[str, str]) -> bool:
    if cond.get("always"):
        return True
    spec = cond.get("exists")
    if not spec:
        return False
    try:
        loc = _locator(page, spec, variables)
        return await loc.count() > 0
    except Exception:  # noqa: BLE001
        return False


async def _run_steps(
    page,
    steps: list[dict[str, Any]],
    *,
    variables: dict[str, str],
    profile: dict[str, Any],
    send: bool,
    log: list[dict[str, Any]],
) -> None:
    import asyncio

    for step in steps:
        action = step.get("action")
        destructive = bool(step.get("destructive"))
        optional = bool(step.get("optional"))
        rec: dict[str, Any] = {"action": action, "ok": True, "note": ""}

        try:
            if action == "goto":
                await page.goto(
                    _subst(step["target"], variables),
                    wait_until=step.get("wait_until", "domcontentloaded"),
                    timeout=step.get("timeout", 60000),
                )
                if send:
                    from human_pacing import drift_mouse, pause_page_settle  # noqa: WPS433

                    await pause_page_settle()
                    await drift_mouse(page)
            elif action == "sleep":
                from human_pacing import MIN_HUMAN_PAUSE, pause_human  # noqa: WPS433

                sec = max(float(step.get("seconds", MIN_HUMAN_PAUSE)), MIN_HUMAN_PAUSE)
                await pause_human(base=sec)
            elif action == "press":
                await page.keyboard.press(step.get("key", "Escape"))
                rec["note"] = step.get("key", "Escape")
            elif action == "click":
                loc = _locator(page, step, variables)
                if await loc.count() == 0:
                    rec["ok"] = optional
                    rec["note"] = "not found" + ("" if optional else " (required)")
                elif destructive and not send:
                    rec["note"] = "DRY: would click"
                    if step.get("commit"):
                        rec["committed"] = True  # dry: target exists -> would commit
                        rec["commit_kind"] = step.get("commit_kind")
                else:
                    idx = step.get("index", 0)
                    if send:
                        from human_pacing import human_click  # noqa: WPS433

                        await human_click(
                            page,
                            loc,
                            index=idx,
                            timeout=float(step.get("timeout", 15000)),
                            force=bool(step.get("force")),
                        )
                    else:
                        await loc.nth(idx).click(timeout=step.get("timeout", 15000))
                    if step.get("commit"):
                        rec["committed"] = True
                        rec["commit_kind"] = step.get("commit_kind")
            elif action == "fill":
                loc = _locator(page, step, variables)
                value = None
                if "profile_key" in step:
                    value = str(profile.get(step["profile_key"], "") or "")
                elif "value_template" in step:
                    value = _subst(step["value_template"], variables)
                elif "value" in step:
                    value = str(step["value"])
                if not value:
                    rec["ok"] = optional
                    rec["note"] = f"no value for {step.get('profile_key')}"
                elif await loc.count() == 0:
                    rec["ok"] = optional
                    rec["note"] = "field not found"
                elif destructive and not send:
                    rec["note"] = f"DRY: would fill '{value[:40]}'"
                else:
                    if send:
                        from human_pacing import human_fill  # noqa: WPS433

                        await human_fill(page, loc, value, index=step.get("index", 0))
                    else:
                        await loc.nth(step.get("index", 0)).fill(value)
                    rec["note"] = f"filled '{value[:40]}'"
            elif action == "upload":
                loc = _locator(page, step, variables)
                path = Path(str(profile.get(step.get("profile_key", "resume_path"), ""))).expanduser()
                if not path.exists():
                    rec["ok"] = optional
                    rec["note"] = "file missing"
                elif await loc.count() == 0:
                    rec["ok"] = optional
                    rec["note"] = "file input not found"
                elif destructive and not send:
                    rec["note"] = f"DRY: would upload {path.name}"
                else:
                    await loc.first.set_input_files(str(path))
                    rec["note"] = f"uploaded {path.name}"
            elif action == "select":
                loc = _locator(page, step, variables)
                value = str(profile.get(step["profile_key"], "")) if "profile_key" in step else step.get("value", "")
                if value and await loc.count() > 0:
                    if not (destructive and not send):
                        await loc.first.select_option(label=value)
                    rec["note"] = f"select {value}"
                else:
                    rec["ok"] = optional
                    rec["note"] = "select skipped"
            elif action == "check":
                loc = _locator(page, step, variables)
                if await loc.count() > 0 and not (destructive and not send):
                    await loc.first.check()
            elif action == "assert_visible":
                loc = _locator(page, step, variables)
                rec["ok"] = await loc.count() > 0
                rec["note"] = "visible" if rec["ok"] else "missing"
            elif action == "screenshot":
                path = ROOT / _subst(step.get("path", "runs/flow-shot.png"), variables)
                path.parent.mkdir(parents=True, exist_ok=True)
                await page.screenshot(path=str(path))
                rec["note"] = str(path)
            elif action == "dismiss_premium":
                from linkedin_ui import dismiss_premium_modal  # noqa: E402

                if await dismiss_premium_modal(page):
                    rec["note"] = "closed premium modal"
                else:
                    rec["note"] = "not shown"
            elif action == "close_chat":
                from linkedin_ui import close_message_thread  # noqa: E402

                if await close_message_thread(page):
                    rec["note"] = "chat closed"
                else:
                    rec["note"] = "chat not open"
            elif action == "cleanup_chat":
                from linkedin_ui import cleanup_after_message  # noqa: E402

                closed = await cleanup_after_message(page)
                rec["note"] = ", ".join(closed) if closed else "nothing to close"
            elif action == "wait_job_detail":
                from linkedin_ui import wait_for_job_detail_ready  # noqa: E402

                rec["ok"] = await wait_for_job_detail_ready(page, timeout_ms=int(step.get("timeout_ms", 30000)))
                rec["note"] = "job detail ready" if rec["ok"] else "job detail not ready"
            elif action == "click_easy_apply":
                from linkedin_ui import click_easy_apply_button  # noqa: E402

                click = await click_easy_apply_button(page)
                rec["ok"] = bool(click.get("clicked"))
                rec["note"] = click.get("strategy") or click.get("error") or "click failed"
            else:
                rec["ok"] = False
                rec["note"] = f"unknown action {action}"
        except Exception as exc:  # noqa: BLE001
            rec["ok"] = optional
            rec["note"] = f"error: {str(exc)[:120]}"

        log.append(rec)
        if rec.get("committed"):
            if rec.get("commit_kind") == "message" and send:
                from linkedin_ui import cleanup_after_message  # noqa: E402

                closed = await cleanup_after_message(page)
                log.append(
                    {
                        "action": "cleanup_chat",
                        "ok": True,
                        "note": ", ".join(closed) if closed else "nothing to close",
                    }
                )
            break  # a real (or would-be) action succeeded; don't fall through to fallbacks
        if not rec["ok"] and not optional and action in ("click", "goto", "click_easy_apply", "wait_job_detail"):
            break


async def run_recipe(
    page,
    recipe: dict[str, Any],
    *,
    variables: dict[str, str],
    profile: dict[str, Any],
    send: bool,
) -> dict[str, Any]:
    """Execute a recipe. Returns {branch, steps:[...]}. Deterministic (no LLM)."""
    log: list[dict[str, Any]] = []
    branch_name = "steps"

    branches = recipe.get("branches")
    if branches:
        chosen = None
        for br in branches:
            if await _exists(page, br.get("when", {}), variables):
                chosen = br
                break
        if chosen is None:
            return {"branch": None, "steps": [{"action": "none", "ok": False, "note": "no branch matched"}]}
        branch_name = chosen.get("name", "branch")
        await _run_steps(page, chosen.get("steps", []), variables=variables, profile=profile, send=send, log=log)
    else:
        await _run_steps(page, recipe.get("steps", []), variables=variables, profile=profile, send=send, log=log)

    committed = any(s.get("committed") for s in log)
    commit_kind = next((s.get("commit_kind") for s in log if s.get("committed")), None)
    return {"branch": branch_name, "steps": log, "committed": committed, "commit_kind": commit_kind}


def save_learned_flow(recipe: dict[str, Any]) -> Path:
    """Persist a newly-discovered flow so future runs are deterministic."""
    LEARNED_DIR.mkdir(parents=True, exist_ok=True)
    name = re.sub(r"[^a-z0-9-]+", "-", recipe.get("name", "flow").lower()).strip("-")
    path = LEARNED_DIR / f"{name}.json"
    path.write_text(json.dumps(recipe, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path
