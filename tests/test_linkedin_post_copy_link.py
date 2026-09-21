"""Tests for LinkedIn post permalink extraction (article cards + copy link menu)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
FIXTURES = ROOT / "tests" / "fixtures" / "linkedin"
sys.path.insert(0, str(SCRIPTS))

from linkedin_post_copy_link import (  # noqa: E402
    extract_ordered_article_post_cards,
    find_copy_link_menu_labels,
    find_post_overflow_labels,
    normalize_copied_post_url,
    post_url_from_article_html,
)
from linkedin_posts_merge import pick_post_url_for_new_chunk  # noqa: E402

MELISSA_URN = "7503481913303584769"
MELISSA_FEED = f"https://www.linkedin.com/feed/update/urn:li:activity:{MELISSA_URN}/"


def test_post_url_from_article_html_uses_data_urn():
    html = FIXTURES.joinpath("content_search_melissa_card.html").read_text(encoding="utf-8")
    article = html.split("<article")[1]
    url = post_url_from_article_html(f"<article{article}")
    assert url == MELISSA_FEED


def test_extract_ordered_article_post_cards_matches_author():
    html = FIXTURES.joinpath("content_search_melissa_card.html").read_text(encoding="utf-8")
    cards = extract_ordered_article_post_cards(html)
    assert len(cards) == 1
    assert cards[0]["url"] == MELISSA_FEED
    assert "melissa" in cards[0]["author"].casefold()


def test_copy_link_menu_fixture_has_expected_labels():
    html = FIXTURES.joinpath("content_search_melissa_card.html").read_text(encoding="utf-8")
    assert find_copy_link_menu_labels(html) == ["Copy link to post"]
    assert any("control menu" in label.casefold() for label in find_post_overflow_labels(html))


def test_extract_sdui_listitem_finds_melissa_author():
    html = FIXTURES.joinpath("content_search_melissa_sdui.html").read_text(encoding="utf-8")
    cards = extract_ordered_article_post_cards(html)
    assert len(cards) == 1
    assert cards[0]["author"] == "Melissa Oliveira"


def test_normalize_copied_post_url_resolves_lnkd_shortlink(monkeypatch):
    def fake_run(cmd, **kwargs):
        class R:
            stdout = "location: https://www.linkedin.com/posts/melissa-oliveira-in_test-activity-7505822950961414145-4opL/\n"
            stderr = ""
            returncode = 0

        return R()

    monkeypatch.setattr("subprocess.run", fake_run)
    url = normalize_copied_post_url("https://lnkd.in/p/dKzmHrG9")
    assert "/posts/melissa-oliveira-in_" in url


def test_pick_post_url_for_new_chunk_uses_article_card():
    html = FIXTURES.joinpath("content_search_melissa_card.html").read_text(encoding="utf-8")
    cards = extract_ordered_article_post_cards(html)
    url, source = pick_post_url_for_new_chunk(
        "Melissa Oliveira",
        article_cards=cards,
        used_urls=set(),
    )
    assert url == MELISSA_FEED
    assert source == "article_card_author"
