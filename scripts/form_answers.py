#!/usr/bin/env python3
"""Reusable form-fill resolver (token-saver).

Loads form-answers.json (the knowledge base of Q->A rules) and resolves a form
field to a concrete value using, in priority order:
  1. explicit per-run answers (passed in)
  2. the knowledge-base rules (label/name/id regex -> profile_key | literal)

The knowledge base is deterministic, so once a question is in it, no LLM tokens
are spent to answer it again. url_apply.py only surfaces the *unresolved* fields
for the agent, and any new answer gets appended to the bank via add_rule().
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from track_store import load_form_answers, track_path  # noqa: E402


def bank_path(track_id: str | None = None) -> Path:
    if track_id:
        return track_path(track_id, "form_answers_path")
    return ROOT / "form-answers.json"


def load_bank(track_id: str | None = None) -> list[dict[str, Any]]:
    path = bank_path(track_id)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("rules", [])
    except (OSError, json.JSONDecodeError):
        return []


def _haystack(field: dict[str, Any]) -> str:
    return " ".join(
        str(field.get(k, "")) for k in ("label", "name", "id", "placeholder")
    ).lower()


def resolve(
    field: dict[str, Any],
    profile: dict[str, Any],
    answers: dict[str, str] | None = None,
    rules: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return a resolution dict:
    {status: 'ok'|'empty'|'none', value, source, option_regex, reason}
      - ok    -> value ready to fill
      - empty -> matched a profile_key but the profile value is blank (need input)
      - none  -> no rule matched (need the agent to decide)
    """
    answers = answers or {}
    rules = rules if rules is not None else load_bank()

    key = field.get("name") or field.get("id") or field.get("label")
    if key and key in answers:
        return {"status": "ok", "value": str(answers[key]), "source": "answers",
                "option_regex": None, "reason": ""}

    hay = _haystack(field)
    if not hay.strip():
        return {"status": "none", "value": None, "source": None,
                "option_regex": None, "reason": "no label/name/id"}

    for rule in rules:
        pat = rule.get("q")
        if not pat:
            continue
        try:
            if not re.search(pat, hay, re.I):
                continue
        except re.error:
            continue
        option_regex = rule.get("option_regex")
        if "profile_key" in rule:
            pk = rule["profile_key"]
            val = str(profile.get(pk, "") or "").strip()
            if not val:
                return {"status": "empty", "value": None, "source": f"profile:{pk}",
                        "option_regex": option_regex, "reason": f"profile.{pk} is blank"}
            return {"status": "ok", "value": val, "source": f"profile:{pk}",
                    "option_regex": option_regex, "reason": ""}
        if "value" in rule:
            val = str(rule["value"])
            if not val:
                return {"status": "empty", "value": None, "source": "rule:literal",
                        "option_regex": option_regex, "reason": "rule value blank"}
            return {"status": "ok", "value": val, "source": "rule:literal",
                    "option_regex": option_regex, "reason": ""}

    return {"status": "none", "value": None, "source": None,
            "option_regex": None, "reason": "no rule matched"}


def add_rule(
    q: str,
    *,
    value: str | None = None,
    profile_key: str | None = None,
    option_regex: str | None = None,
    prepend: bool = True,
    track_id: str | None = None,
) -> None:
    """Append/prepend a new rule to the knowledge base (so next form is free)."""
    path = bank_path(track_id)
    data = json.loads(path.read_text(encoding="utf-8"))
    rule: dict[str, Any] = {"q": q}
    if profile_key is not None:
        rule["profile_key"] = profile_key
    if value is not None:
        rule["value"] = value
    if option_regex is not None:
        rule["option_regex"] = option_regex
    rules = data.setdefault("rules", [])
    if prepend:
        rules.insert(0, rule)
    else:
        rules.append(rule)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    # Quick self-test with sample fields.
    prof = json.loads((ROOT / "applicant-profile.json").read_text(encoding="utf-8"))
    samples = [
        {"label": "First Name", "type": "text", "required": True},
        {"label": "Are you legally authorized to work?", "type": "select",
         "options": ["Yes", "No"], "required": True},
        {"label": "Desired salary", "type": "text", "required": True},
        {"label": "Portfolio of secret projects", "type": "text", "required": False},
    ]
    for s in samples:
        print(s["label"], "->", resolve(s, prof))
