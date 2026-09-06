"""LinkedIn flow tests via HAR replay — LI-HAR-01..08."""

from __future__ import annotations

import asyncio

import pytest

from tests.helpers.judge import expect_classify, expect_flow_commit
from tests.helpers.linkedin_har import HAR_SLUGS, mock_profile_url, run_with_har

pytestmark = pytest.mark.har


async def _flow_dry_run(page, *, message: str = "Hi test"):
    from flow_runner import resolve_recipe, run_recipe

    recipe = resolve_recipe("https://www.linkedin.com/in/test/", name="linkedin-connect-or-message")
    assert recipe is not None
    return await run_recipe(
        page,
        recipe,
        variables={"profile_url": page.url, "message": message},
        profile={},
        send=False,
    )


async def _classify(page, url: str) -> str:
    from dm_apply import classify_affordance

    return await classify_affordance(page, url)


@pytest.mark.parametrize(
    "har_name,slug,commit_kind",
    [
        ("profile-connect", "test-connect", "connect"),
        ("profile-message", "test-message", "message"),
    ],
)
def test_har_flow_dry_run_commit(har_name: str, slug: str, commit_kind: str):
    url = mock_profile_url(slug)

    async def _run(page):
        return await _flow_dry_run(page)

    result = asyncio.run(run_with_har(har_name, url, _run))
    verdict = expect_flow_commit(result, commit_kind)
    assert verdict, verdict.reason


@pytest.mark.parametrize(
    "har_name,slug,expected",
    [
        ("profile-connect", "test-connect", "connect_top"),
        ("profile-message", "test-message", "message"),
        ("profile-pending", "test-pending", "follow_only"),
        ("profile-connect-more", "test-connect-more", "connect_more"),
        ("profile-connected", "test-connected", "message"),
        ("profile-connected-only", "test-connected-only", "connected"),
    ],
)
def test_har_classify_affordance(har_name: str, slug: str, expected: str):
    url = mock_profile_url(slug)

    async def _run(page):
        return await _classify(page, url)

    kind = asyncio.run(run_with_har(har_name, url, _run, fast_classify=True))
    verdict = expect_classify(kind, expected)
    assert verdict, verdict.reason


def test_har_replay_blocks_live_network():
    """Wrong URL must fail when HAR has no matching entry (not_found=abort)."""
    url = mock_profile_url("test-connect")
    bad = url.replace("test-connect", "does-not-exist")

    async def _noop(page):
        return None

    with pytest.raises(Exception):
        asyncio.run(run_with_har("profile-connect", bad, _noop))


def test_har_offline_no_mock_server():
    """HAR replay serves page without running LinkedInMockServer."""
    url = mock_profile_url("test-message")

    async def _run(page):
        title = await page.title()
        assert "Message" in title or "Fixture" in title
        return await _flow_dry_run(page, message="Hello")

    result = asyncio.run(run_with_har("profile-message", url, _run))
    assert expect_flow_commit(result, "message")
