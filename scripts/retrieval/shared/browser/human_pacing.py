"""Human-like delays and mouse/keyboard behavior for LinkedIn browser actions.

Each user-visible pause is capped at MAX_HUMAN_PAUSE (default 3s). Short poll
intervals are only used while waiting for DOM state, not between social actions.
"""

from __future__ import annotations

import asyncio
import os
import random
from typing import Any

MIN_HUMAN_PAUSE = 0.5
MAX_HUMAN_PAUSE = 3.0


def human_pacing_enabled() -> bool:
    return os.environ.get("JOBSEARCH_HUMAN_PACING", "1").strip().lower() not in {"0", "false", "off", "no"}


def cap_pause(seconds: float) -> float:
    """Clamp a pause to [MIN_HUMAN_PAUSE, MAX_HUMAN_PAUSE] when pacing is on."""
    return min(max(seconds, MIN_HUMAN_PAUSE), MAX_HUMAN_PAUSE)


def jitter_seconds(base: float, *, spread: float = 0.35, minimum: float | None = None) -> float:
    value = base * random.uniform(1.0 - spread, 1.0 + spread)
    floor = minimum if minimum is not None else 0.0
    return cap_pause(max(floor, value))


async def pause(base: float, *, spread: float = 0.35, minimum: float | None = None) -> None:
    if not human_pacing_enabled():
        await asyncio.sleep(0.05)
        return
    await asyncio.sleep(jitter_seconds(base, spread=spread, minimum=minimum))


async def pause_poll(*, base: float = 0.35) -> None:
    """DOM polling / spinner wait — not a simulated human pause."""
    if not human_pacing_enabled():
        await asyncio.sleep(min(base, 0.15))
        return
    await asyncio.sleep(min(jitter_seconds(base, spread=0.25, minimum=0.12), 1.0))


async def pause_human(*, base: float | None = None, low: float | None = None, high: float | None = None) -> None:
    """User-visible idle — capped at MAX_HUMAN_PAUSE seconds."""
    if not human_pacing_enabled():
        await asyncio.sleep(0.05)
        return
    if low is not None and high is not None:
        sec = cap_pause(random.uniform(low, high))
    elif base is not None:
        sec = jitter_seconds(base, spread=0.35, minimum=MIN_HUMAN_PAUSE)
    else:
        sec = cap_pause(random.uniform(MIN_HUMAN_PAUSE, MAX_HUMAN_PAUSE))
    await asyncio.sleep(sec)


async def pause_page_settle(*, base: float = 2.5) -> None:
    """After navigation — brief skim before acting."""
    await pause_human(base=base)


async def pause_before_click(*, base: float = 2.0) -> None:
    await pause_human(base=base)


async def pause_after_click(*, base: float = 2.0) -> None:
    await pause_human(base=base)


async def pause_between_actions(*, low: float = 2.0, high: float = 3.0) -> None:
    """Gap between connect/DM sends on different profiles."""
    await pause_human(low=low, high=high)


async def pause_between_reads(*, low: float = 1.5, high: float = 3.0) -> None:
    """Scan / inspect loops."""
    await pause_human(low=low, high=high)


async def maybe_session_break(action_index: int) -> None:
    if not human_pacing_enabled() or action_index <= 0:
        return
    if action_index % random.randint(3, 5) != 0:
        return
    await pause_human(low=2.0, high=MAX_HUMAN_PAUSE)


async def drift_mouse(page: Any, *, moves: int | None = None) -> None:
    if not human_pacing_enabled():
        return
    viewport = page.viewport_size or {"width": 1360, "height": 940}
    w, h = int(viewport["width"]), int(viewport["height"])
    count = moves if moves is not None else random.randint(1, 3)
    cx = random.randint(int(w * 0.25), int(w * 0.75))
    cy = random.randint(int(h * 0.2), int(h * 0.75))
    for _ in range(count):
        tx = cx + random.randint(-120, 120)
        ty = cy + random.randint(-90, 90)
        tx = max(int(w * 0.08), min(int(w * 0.92), tx))
        ty = max(int(h * 0.1), min(int(h * 0.92), ty))
        steps = random.randint(8, 16)
        await page.mouse.move(tx, ty, steps=steps)
        cx, cy = tx, ty
        await pause_poll(base=random.uniform(0.12, 0.35))


async def human_scroll(page: Any, *, direction: int = 1) -> None:
    """Small irregular scroll — reading the page."""
    if not human_pacing_enabled():
        return
    delta = direction * random.randint(180, 520)
    await page.mouse.wheel(0, delta)
    await pause_poll(base=random.uniform(0.2, 0.45))
    if random.random() < 0.35:
        await page.mouse.wheel(0, -direction * random.randint(40, 140))


async def _element_center(locator: Any) -> tuple[float, float] | None:
    try:
        box = await locator.bounding_box()
    except Exception:
        return None
    if not box:
        return None
    ox = random.uniform(-box["width"] * 0.15, box["width"] * 0.15)
    oy = random.uniform(-box["height"] * 0.15, box["height"] * 0.15)
    return box["x"] + box["width"] / 2 + ox, box["y"] + box["height"] / 2 + oy


async def human_click(
    page: Any,
    locator: Any,
    *,
    index: int = 0,
    timeout: float = 15000,
    force: bool = False,
) -> None:
    """Move cursor naturally, pause, then click."""
    target = locator.nth(index)
    await target.scroll_into_view_if_needed(timeout=int(timeout))
    await human_scroll(page, direction=random.choice([-1, 1]))
    await drift_mouse(page, moves=1)
    center = await _element_center(target)
    if center is not None:
        await page.mouse.move(center[0], center[1], steps=random.randint(10, 18))
    await pause_before_click(base=random.uniform(1.0, 2.5))
    if force:
        await target.click(force=True, timeout=int(timeout))
    else:
        await target.click(timeout=int(timeout))
    await pause_after_click(base=random.uniform(1.0, 2.5))


async def human_fill(page: Any, locator: Any, text: str, *, index: int = 0) -> None:
    """Click composer and type with irregular keystroke timing."""
    target = locator.nth(index)
    await target.scroll_into_view_if_needed(timeout=8000)
    center = await _element_center(target)
    if center is not None:
        await page.mouse.move(center[0], center[1], steps=random.randint(8, 14))
    await pause_before_click(base=random.uniform(1.0, 2.0))
    await target.click(timeout=10000)
    if not human_pacing_enabled():
        await target.fill(text)
        return
    await target.fill("")
    delay_ms = random.randint(35, 90)
    await target.press_sequentially(text, delay=delay_ms)
    await pause_human(base=random.uniform(1.0, 2.5))
