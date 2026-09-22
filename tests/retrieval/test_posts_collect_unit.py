"""Unit coverage for posts_collect helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from linkedin_content_collect import (  # noqa: E402
    _chunk_key,
    _extract_author,
    parse_feed_text,
)


def test_chunk_key_and_author():
    chunk = "Jane Doe\n• 3rd+\nHiring AI Engineer"
    assert _chunk_key(chunk, "Jane Doe")
    assert _extract_author(chunk)


def test_parse_feed_text():
    raw = "Feed post\nAcme AI\nHiring AI Engineer remote $120k USD apply"
    posts = parse_feed_text(raw)
    assert isinstance(posts, list)


@pytest.mark.asyncio
async def test_collect_feed_text_mocked():
    from linkedin_content_collect import collect_feed_text

    feed_text = "Feed post\nAcme\nAI Engineer role $120k"
    fake_html = f"<html>{feed_text}</html>"
    with patch("patchright.async_api.async_playwright") as pw:
        main_loc = AsyncMock()
        main_loc.inner_text = AsyncMock(return_value=feed_text)
        page = AsyncMock()
        page.content = AsyncMock(return_value=fake_html)
        page.locator = MagicMock(return_value=main_loc)
        page.viewport_size = {"width": 1280, "height": 900}
        page.mouse.move = AsyncMock()
        page.mouse.wheel = AsyncMock()
        page.goto = AsyncMock()
        page.wait_for_selector = AsyncMock()
        page.on = MagicMock()
        ctx = AsyncMock()
        ctx.new_page = AsyncMock(return_value=page)
        ctx.pages = []
        ctx.close = AsyncMock()
        ctx.grant_permissions = AsyncMock()
        browser = AsyncMock()
        browser.new_context = AsyncMock(return_value=ctx)
        p = MagicMock()
        p.chromium.launch = AsyncMock(return_value=browser)
        pw.return_value.__aenter__ = AsyncMock(return_value=p)
        pw.return_value.__aexit__ = AsyncMock(return_value=False)
        with patch("linkedin_content_collect.load_cookies", return_value=[]):
            with patch("linkedin_content_collect.install_copy_link_hook", AsyncMock()):
                with patch("linkedin_content_collect.browser_launch_kwargs", return_value={}):
                    with patch(
                        "linkedin_content_collect.resolve_chunk_post_url_via_copy_link",
                        AsyncMock(return_value=None),
                    ):
                        raw, refs, stats = await collect_feed_text(
                            "https://linkedin.com/search/content/",
                            max_scrolls=1,
                            max_stale=1,
                        )
        assert isinstance(stats, dict)
        assert "Feed post" in raw or isinstance(refs, list)


def test_posts_to_jobs_respects_max(monkeypatch):
    from linkedin_content_collect import posts_to_jobs

    posts = [{"author": f"Co{i}", "text": f"Hiring AI Engineer role {i}"} for i in range(5)]
    job = {"url": "https://example.com", "role": "AI Engineer", "source": "linkedin_posts"}
    monkeypatch.setattr("linkedin_content_collect.load_linkedin_config", lambda: {})
    monkeypatch.setattr("linkedin_content_collect.load_json", lambda *a, **k: {})
    def fake_post_to_job(post, meta, cfg, job_cfg):
        j = dict(job)
        j["url"] = f"https://example.com/{post['author']}"
        return j

    monkeypatch.setattr("linkedin_content_collect.post_to_job", fake_post_to_job)
    monkeypatch.setattr("linkedin_content_collect.job_key", lambda j: j["url"])
    jobs = posts_to_jobs(posts, {"query": "ai"}, max_roles=2)
    assert len(jobs) == 2


@pytest.mark.asyncio
async def test_run_query_mocked(monkeypatch, tmp_path):
    from linkedin_content_collect import run_query

    monkeypatch.setattr("linkedin_content_collect.RUNS", tmp_path)
    monkeypatch.setattr("linkedin_content_collect.load_linkedin_config", lambda: {})
    monkeypatch.setattr(
        "linkedin_content_collect.collect_feed_text",
        AsyncMock(return_value=("Feed post\nAcme\nAI Engineer", [], {"scrolls": 1})),
    )
    monkeypatch.setattr(
        "linkedin_content_collect.parse_feed_text",
        lambda raw, refs: [{"author": "Acme", "text": "AI Engineer"}],
    )
    monkeypatch.setattr(
        "linkedin_content_collect.posts_to_jobs",
        lambda posts, meta, max_roles: [{"role": "AI Engineer", "url": "https://x"}],
    )
    result = await run_query("ai engineer", "AI Engineer", "worldwide", period_days=7, max_roles=5, max_scrolls=1, merge=False, since="7d")
    assert result["posts_found"] == 1
    assert result["roles_kept"] == 1
