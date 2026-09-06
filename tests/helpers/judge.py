"""Rule-based test judge — stable CI expectations without an LLM."""

from __future__ import annotations

from typing import Any


class JudgeVerdict:
    def __init__(self, *, ok: bool, reason: str = "") -> None:
        self.ok = ok
        self.reason = reason

    def __bool__(self) -> bool:
        return self.ok


def expect_action(cmd: list[str], *, must_include: list[str] | None = None, must_exclude: list[str] | None = None) -> JudgeVerdict:
    text = " ".join(cmd)
    for needle in must_include or []:
        if needle not in cmd and needle not in text:
            return JudgeVerdict(ok=False, reason=f"missing {needle!r} in {cmd!r}")
    for bad in must_exclude or []:
        if bad in cmd:
            return JudgeVerdict(ok=False, reason=f"unexpected {bad!r} in {cmd!r}")
    return JudgeVerdict(ok=True)


def expect_ui_approval_env(env: dict[str, str]) -> JudgeVerdict:
    if env.get("JOBSEARCH_UI_APPROVED") != "1":
        return JudgeVerdict(ok=False, reason="JOBSEARCH_UI_APPROVED not set")
    return JudgeVerdict(ok=True)


def expect_step_states(actions: dict[str, dict[str, Any]], expected: dict[str, dict[str, bool]]) -> JudgeVerdict:
    for key, want in expected.items():
        state = actions.get(key)
        if not state:
            return JudgeVerdict(ok=False, reason=f"missing action key {key!r}")
        for field in ("available", "done", "in_progress"):
            if field in want and bool(state.get(field)) != want[field]:
                return JudgeVerdict(
                    ok=False,
                    reason=f"{key}.{field}: got {state.get(field)!r}, want {want[field]!r}",
                )
    return JudgeVerdict(ok=True)


def expect_api_action(body: dict[str, Any], action: str, job_key: str) -> JudgeVerdict:
    if body.get("action") != action:
        return JudgeVerdict(ok=False, reason=f"action {body.get('action')!r} != {action!r}")
    if body.get("job_key") != job_key:
        return JudgeVerdict(ok=False, reason="job_key mismatch")
    return JudgeVerdict(ok=True)


def expect_flow_commit(result: dict[str, Any], kind: str) -> JudgeVerdict:
    log = result.get("steps") or []
    if result.get("commit_kind") == kind or any(e.get("commit_kind") == kind for e in log if e.get("committed")):
        return JudgeVerdict(ok=True)
    return JudgeVerdict(ok=False, reason=f"expected commit_kind={kind!r}, got {result!r}")


def expect_classify(kind: str, expected: str) -> JudgeVerdict:
    if kind == expected:
        return JudgeVerdict(ok=True)
    return JudgeVerdict(ok=False, reason=f"classify {kind!r} != {expected!r}")


def optional_llm_judge(prompt: str, *, criteria: str) -> JudgeVerdict | None:
    """Optional LLM judge — returns None when skipped (no API key)."""
    import os

    if os.environ.get("JOBSEARCH_LLM_JUDGE") != "1":
        return None
    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    return JudgeVerdict(ok=True, reason="llm judge skipped (stub)")
