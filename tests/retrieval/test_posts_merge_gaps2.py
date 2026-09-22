"""Additional branch coverage for posts_merge — HTML extraction, URL resolution, merge helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

from linkedin_posts_merge import (
    LOGIN_SCRIPT,
    _chunk_url_for_index,
    _guess_apply_channel,
    _guess_company,
    build_queries,
    check_linkedin_session,
    enrich_job_recruiter_profile,
    extract_activity_refs_from_html,
    extract_ordered_feed_update_urls,
    extract_profile_refs_from_html,
    linkedin_content_search_url,
    parse_feed_search_posts,
    patch_recruiter_profiles_on_known,
    post_to_job,
    register_author_post_urls,
    resolve_author_post_url,
    resolve_feed_update_to_posts_permalink,
    resolve_post_urls,
    sort_jobs_by_recency,
    write_linkedin_run_markdown,
)
from registry import job_key
from tests.helpers.example_configs import load_example_linkedin_config

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "linkedin"


# --- extract_activity_refs_from_html ---


def test_extract_activity_refs_from_html_person_and_posts_permalink():
    html = (FIXTURES / "content_search_monika_card.html").read_text(encoding="utf-8")
    html += (
        '<a href="https://www.linkedin.com/posts/monikakuqi_hiring-activity-7503481913303584769-abcd/">'
        "permalink</a>"
    )
    refs = extract_activity_refs_from_html(html)
    assert len(refs) >= 1
    monika = next(r for r in refs if r["activity_id"] == "7503481913303584769")
    assert monika["author_kind"] == "person"
    assert monika["author_slug"] == "monikakuqi"
    assert "/posts/monikakuqi" in monika["url"]


def test_extract_activity_refs_from_html_company_and_feed_url():
    html = """
    <div urn%3Ali%3Aactivity%3A999888777>marker</div>
    <a href="https://www.linkedin.com/company/acme-ai/">Acme AI</a>
    """
    refs = extract_activity_refs_from_html(html)
    assert len(refs) == 1
    assert refs[0]["author_kind"] == "company"
    assert refs[0]["author_slug"] == "acme-ai"
    assert refs[0]["url"].endswith("urn:li:activity:999888777/")


def test_extract_activity_refs_dedupes_same_activity_id():
    html = (
        'data-urn="urn:li:activity:111" '
        'data-urn="urn:li:activity:111" '
        'href="https://www.linkedin.com/in/jane-doe/"'
    )
    refs = extract_activity_refs_from_html(html)
    assert len(refs) == 1
    assert refs[0]["activity_id"] == "111"


# --- extract_profile_refs_from_html ---


def test_extract_profile_refs_from_html_person_and_company():
    # Keep links far apart so label windows do not bleed across cards.
    html = (
        '<a href="https://www.linkedin.com/company/acme-corp/" aria-label="Acme Corp">Acme</a>'
        + ("<!-- pad -->" * 80)
        + '<a href="https://www.linkedin.com/in/jane-doe/"><strong>Jane Doe</strong></a>'
    )
    refs = extract_profile_refs_from_html(html)
    kinds = {r["kind"] for r in refs}
    assert kinds == {"person", "company"}
    person = next(r for r in refs if r["kind"] == "person")
    assert person["text"] == "Jane Doe"
    company = next(r for r in refs if r["kind"] == "company")
    assert company["text"] == "Acme Corp"


def test_extract_profile_refs_dedupes_urls():
    html = (
        '<a href="https://www.linkedin.com/in/jane-doe/?trk=foo">Jane</a>'
        '<a href="https://www.linkedin.com/in/jane-doe/">Jane again</a>'
    )
    refs = extract_profile_refs_from_html(html)
    assert len(refs) == 1


# --- extract_ordered_feed_update_urls ---


def test_extract_ordered_feed_update_urls_mixed_sources_in_dom_order():
    html = (
        'href="https://www.linkedin.com/posts/user_slug-activity-100/" '
        'href="https://www.linkedin.com/feed/update/urn:li:activity:200/" '
        '"activityUrn":"urn:li:activity:300" '
        'data-urn="urn:li:activity:400"'
    )
    urls = extract_ordered_feed_update_urls(html)
    assert len(urls) == 4
    assert "/posts/" in urls[0]
    assert "200" in urls[1]
    assert "300" in urls[2]
    assert "400" in urls[3]


def test_extract_ordered_feed_update_urls_dedupes_preserving_first_position():
    html = (
        FIXTURES / "content_search_two_posts.html"
    ).read_text(encoding="utf-8")
    urls = extract_ordered_feed_update_urls(html)
    assert len(urls) == 2
    assert "7503481913303584769" in urls[0]
    assert "7503200610150973442" in urls[1]


# --- register_author_post_urls / resolve_author_post_url ---


def test_register_author_post_urls_maps_author_and_slug():
    author_map: dict[str, str] = {}
    feed_url = "https://www.linkedin.com/feed/update/urn:li:activity:123/"
    register_author_post_urls(
        author_map,
        [
            {
                "author": "Monika Kuqi",
                "author_slug": "monikakuqi",
                "url": feed_url,
            }
        ],
    )
    assert author_map["monika kuqi"] == feed_url
    assert author_map["slug:monikakuqi"] == feed_url


def test_resolve_author_post_url_branches():
    feed_url = "https://www.linkedin.com/feed/update/urn:li:activity:555/"
    author_map = {"jane doe": feed_url, "slug:jane-doe": feed_url}
    profile_refs = [
        {"kind": "person", "url": "https://www.linkedin.com/in/jane-doe/", "text": "Jane Doe"},
    ]
    html_posts = [
        {
            "author": "Jane Doe",
            "author_slug": "jane-doe",
            "url": feed_url,
        }
    ]
    activity_refs = [
        {
            "kind": "feed_post",
            "author_slug": "jane-doe",
            "url": feed_url,
            "activity_id": "555",
            "urn_kind": "activity",
        }
    ]

    url, source = resolve_author_post_url("Jane Doe", author_url_map=author_map)
    assert url == feed_url
    assert source == "author_map"

    url2, source2 = resolve_author_post_url(
        "Jane Doe",
        author_url_map={"slug:jane-doe": feed_url},
        profile_refs=profile_refs,
    )
    assert url2 == feed_url
    assert source2 == "author_map_slug"

    url3, source3 = resolve_author_post_url("Jane Doe", html_posts=html_posts)
    assert url3 == feed_url
    assert source3 == "html_card_author"

    url4, source4 = resolve_author_post_url(
        "Jane Doe",
        activity_refs=activity_refs,
        profile_refs=profile_refs,
    )
    assert url4 == feed_url
    assert source4 in {"feed_post_slug", "activity_ref_slug", "activity_ref_urn"}


# --- resolve_post_urls ---


def test_resolve_post_urls_text_feed_update():
    chunk = "Jane Doe\nHiring AI Engineer\nhttps://www.linkedin.com/feed/update/urn:li:activity:42/"
    post_url, apply_url, source, feed_idx, job_idx = resolve_post_urls(
        chunk,
        "Jane Doe",
        refs=[],
        feed_post_urls=[],
        feed_post_by_title={},
        feed_idx=0,
        job_urls=[],
        job_idx=0,
    )
    assert "42" in post_url
    assert source == "text_feed_update"
    assert feed_idx == 0
    assert job_idx == 0
    assert apply_url == "" or "lnkd.in" in apply_url or "http" in apply_url


def test_resolve_post_urls_collect_chunk_url_and_feed_index():
    chunk = "Bob Recruiter\nHiring AI Engineer remote"
    feed_urls = ["https://www.linkedin.com/feed/update/urn:li:activity:100/"]
    post_url, _, source, feed_idx, _ = resolve_post_urls(
        chunk,
        "Bob Recruiter",
        refs=[],
        feed_post_urls=feed_urls,
        feed_post_by_title={},
        feed_idx=0,
        job_urls=[],
        job_idx=0,
        chunk_url="https://www.linkedin.com/feed/update/urn:li:activity:999/",
    )
    assert "999" in post_url
    assert source == "collect_chunk_url"
    assert feed_idx == 1


def test_resolve_post_urls_view_job_and_lnkd_apply():
    chunk = "Recruiter\nHiring AI Engineer\nView job\nApply at https://lnkd.in/apply123"
    refs = [
        {
            "kind": "feed_post",
            "url": "https://www.linkedin.com/feed/update/urn:li:activity:1/",
            "author_slug": "recruiter",
            "text": "Recruiter",
        }
    ]
    post_url, apply_url, source, _, job_idx = resolve_post_urls(
        chunk,
        "Recruiter",
        refs=refs,
        feed_post_urls=[],
        feed_post_by_title={},
        feed_idx=0,
        job_urls=["https://www.linkedin.com/jobs/view/777/"],
        job_idx=0,
    )
    assert post_url
    assert "lnkd.in/apply123" in apply_url or "jobs/view/777" in apply_url
    assert source in {"feed_post_slug", "activity_ref_slug", "activity_ref_urn", "text_feed_update"}
    assert job_idx in (0, 1)


def test_resolve_post_urls_none_when_no_match():
    post_url, apply_url, source, _, _ = resolve_post_urls(
        "Unknown Author\nHiring",
        "Unknown Author",
        refs=[],
        feed_post_urls=[],
        feed_post_by_title={},
        feed_idx=0,
        job_urls=[],
        job_idx=0,
    )
    assert post_url == ""
    assert apply_url == ""
    assert source == "none"


# --- enrich_job_recruiter_profile / patch_recruiter_profiles_on_known ---


def test_enrich_job_recruiter_profile_skips_when_already_set():
    job = {
        "source": "linkedin_posts",
        "company": "Jane Doe",
        "url": "https://www.linkedin.com/feed/update/urn:li:activity:1/",
        "recruiter_profile_url": "https://www.linkedin.com/in/jane-doe/",
    }
    assert enrich_job_recruiter_profile(job, []) is False


def test_enrich_job_recruiter_profile_skips_wrong_source_and_job_seeker():
    job_wrong_source = {"source": "google", "company": "Jane", "url": "https://example.com/"}
    assert enrich_job_recruiter_profile(job_wrong_source, []) is False

    job_seeker = {
        "source": "linkedin_posts",
        "post_intent": "job_seeker",
        "company": "Jane",
        "url": "https://www.linkedin.com/feed/update/urn:li:activity:1/",
    }
    assert enrich_job_recruiter_profile(job_seeker, []) is False


def test_enrich_job_recruiter_profile_from_refs():
    job = {
        "source": "linkedin_posts",
        "company": "Monika Kuqi",
        "url": "https://www.linkedin.com/feed/update/urn:li:activity:7503481913303584769/",
    }
    refs = [
        {
            "kind": "feed_post",
            "url": "https://www.linkedin.com/feed/update/urn:li:activity:7503481913303584769/",
            "author_slug": "monikakuqi",
            "activity_id": "7503481913303584769",
        }
    ]
    assert enrich_job_recruiter_profile(job, refs) is True
    assert job["recruiter_profile_url"] == "https://www.linkedin.com/in/monikakuqi/"


def test_enrich_job_recruiter_profile_resolve_posts_mock(monkeypatch):
    job = {
        "source": "linkedin_posts",
        "company": "Monika Kuqi",
        "url": "https://www.linkedin.com/feed/update/urn:li:activity:7503481913303584769/",
    }
    permalink = "https://www.linkedin.com/posts/monikakuqi_hiring-activity-7503481913303584769-abcd/"

    def fake_resolve(url, **kwargs):
        return permalink

    monkeypatch.setattr("linkedin_posts_merge.resolve_feed_update_to_posts_permalink", fake_resolve)
    assert enrich_job_recruiter_profile(job, [], resolve_posts=True) is True
    assert job["url"] == permalink
    assert job["recruiter_profile_url"] == "https://www.linkedin.com/in/monikakuqi/"


def test_patch_recruiter_profiles_on_known():
    existing_job = {
        "source": "linkedin_posts",
        "company": "Acme",
        "role": "AI Engineer",
        "url": "https://www.linkedin.com/feed/update/urn:li:activity:100/",
    }
    registry = {"jobs": [dict(existing_job)]}
    incoming = [
        {
            **existing_job,
            "recruiter_profile_url": "https://www.linkedin.com/in/recruiter/",
        }
    ]
    patched = patch_recruiter_profiles_on_known(registry, incoming)
    assert patched == 1
    assert registry["jobs"][0]["recruiter_profile_url"] == "https://www.linkedin.com/in/recruiter/"

    registry2 = {
        "jobs": [
            {
                **existing_job,
                "recruiter_profile_url": "https://www.linkedin.com/in/already/",
            }
        ]
    }
    assert patch_recruiter_profiles_on_known(registry2, incoming) == 0


# --- _guess_company / _guess_apply_channel / _chunk_url_for_index ---


def test_guess_company_branches():
    assert _guess_company({"company_header": "  Acme AI  "}, "") == "Acme AI"
    assert _guess_company({"author": {"name": "Jane Recruiter"}}, "") == "Jane Recruiter"
    assert _guess_company({"author": "Bob Smith"}, "") == "Bob Smith"
    assert _guess_company({"company": "Globex"}, "text") == "Globex"
    assert _guess_company({}, "") == "Unknown"


def test_guess_apply_channel_branches():
    assert _guess_apply_channel("Apply jobs@acme.com") == "email"
    assert _guess_apply_channel("DM me to apply") == "chat"
    assert _guess_apply_channel("Apply https://example.com/jobs/1") == "external_url"
    assert _guess_apply_channel("We're hiring — comment below") == "linkedin_post"


def test_chunk_url_for_index_prefers_chunk_urls():
    chunk_urls = ["https://www.linkedin.com/feed/update/urn:li:activity:111/"]
    ordered = ["https://www.linkedin.com/feed/update/urn:li:activity:222/"]
    assert _chunk_url_for_index(0, chunk_urls=chunk_urls, ordered_activity_urls=ordered).endswith("111/")
    assert _chunk_url_for_index(0, chunk_urls=[""], ordered_activity_urls=ordered).endswith("222/")
    assert _chunk_url_for_index(5, chunk_urls=[], ordered_activity_urls=[]) == ""


# --- linkedin_content_search_url / build_queries ---


def test_linkedin_content_search_url_recency():
    url_week = linkedin_content_search_url('"ai engineer" + "latam"', recency="past-week")
    assert "datePosted" in url_week
    assert "past-week" in url_week
    url_day = linkedin_content_search_url("query", recency="past-24h")
    assert "past-24h" in url_day
    url_month = linkedin_content_search_url("query", recency="past-month")
    assert "past-month" in url_month
    url_default = linkedin_content_search_url("query", recency="unknown")
    assert "past-week" in url_default


def test_build_queries_combinations():
    cfg = {
        "roles": ["ai engineer", "agent engineer"],
        "region_suffixes": ["latam"],
        "default_period_days": 1,
        "query_template": '"{role}" + "{region}"',
    }
    queries = build_queries(cfg)
    assert len(queries) == 2
    assert queries[0]["region"] == "latam"
    assert "linkedin.com/search/results/content" in queries[0]["linkedin_url"]


# --- sort_jobs_by_recency ---


def test_sort_jobs_by_recency_posted_then_index():
    jobs = [
        {"role": "Old", "posted_at": "2026-01-01T00:00:00+00:00", "discovery_index": 0},
        {"role": "New", "posted_at": "2026-06-01T00:00:00+00:00", "discovery_index": 5},
        {"role": "IndexOnly", "discovery_index": 1},
        {"role": "NoDate"},
    ]
    ranked = sort_jobs_by_recency(jobs)
    assert ranked[0]["role"] == "New"
    assert ranked[1]["role"] == "Old"
    assert ranked[2]["role"] == "IndexOnly"


# --- post_to_job branches ---


def test_post_to_job_returns_none_for_empty_and_blacklisted():
    cfg = load_example_linkedin_config()
    meta = {"query": "q", "role_keyword": "ai engineer", "region": "latam"}
    assert post_to_job({}, meta, cfg, {}) is None
    blocked_url = post_to_job(
        {"text": "Hiring AI Engineer", "url": "https://66ghz.com/fake-job/1"},
        meta,
        cfg,
        {},
    )
    assert blocked_url is None
    blocked_text = post_to_job(
        {
            "text": "Hiring AI Engineer apply https://66ghz.com/fake-job/2",
            "url": "https://www.linkedin.com/feed/update/urn:li:activity:1/",
        },
        meta,
        cfg,
        {},
    )
    assert blocked_text is None


def test_post_to_job_hiring_with_salary_and_worldwide():
    cfg = load_example_linkedin_config()
    post = {
        "text": "We're hiring an AI Engineer remote worldwide. USD 130k. jobs@hire.co",
        "url": "https://www.linkedin.com/feed/update/urn:li:activity:123/",
        "author": {"name": "Recruiter Co"},
        "discovery_index": 3,
    }
    meta = {"query": "q", "role_keyword": "ai engineer", "region": "worldwide"}
    job = post_to_job(post, meta, cfg, {})
    assert job is not None
    assert job["filter_result"] == "eligible"
    assert job["location_note"] == "Worldwide"
    assert job["apply_channel"] == "email"
    assert job["discovery_index"] == 3
    assert job["apply_email"] == "jobs@hire.co"


def test_post_to_job_placeholder_when_no_url():
    cfg = load_example_linkedin_config()
    post = {
        "text": "We're hiring an AI Engineer remote LATAM. DM me.",
        "author": "Recruiter",
    }
    meta = {"query": "q", "role_keyword": "ai engineer", "region": "latam"}
    job = post_to_job(post, meta, cfg, {})
    assert job is not None
    assert job["url"].startswith("linkedin-post:")
    assert job["url_source"] == "placeholder"


def test_post_to_job_require_usd_salary_path():
    cfg = {**load_example_linkedin_config(), "require_usd_salary": True}
    post = {
        "text": "Hiring AI Engineer $150k USD remote",
        "url": "https://www.linkedin.com/feed/update/urn:li:activity:1/",
        "author": "Co",
    }
    meta = {"query": "q", "role_keyword": "ai engineer", "region": "latam"}
    job = post_to_job(post, meta, cfg, {})
    assert job is not None
    assert job.get("post_intent") == "hiring"


# --- parse_feed_search_posts edge cases ---


def test_parse_feed_search_posts_strips_did_you_mean():
    raw = (
        "Did you mean ai engineer?\n\n"
        "Feed post\n\nJane Doe\n\n1h • \n\nFollow\n\nHiring AI Engineer LATAM\n"
    )
    posts = parse_feed_search_posts(
        {"sections": {"search_results": raw}, "references": {"search_results": []}}
    )
    assert len(posts) == 1
    assert posts[0]["author"] == "Jane Doe"


def test_parse_feed_search_posts_skips_helpful_prompt_and_empty():
    raw = (
        "Are these results helpful?\n\n"
        "Feed post\n\n\n\n"
        "Feed post\n\nBob Lee\n\n2h • \n\nFollow\n\nHiring AI Engineer\n"
    )
    posts = parse_feed_search_posts(
        {"sections": {"search_results": raw}, "references": {"search_results": []}}
    )
    assert len(posts) == 1
    assert posts[0]["author"] == "Bob Lee"


def test_parse_feed_search_posts_uses_author_post_urls_when_refs_empty():
    raw = "Feed post\n\nMonika Kuqi\n\n1h • \n\nFollow\n\nHiring AI Engineer\n"
    activity = "https://www.linkedin.com/feed/update/urn:li:activity:7503481913303584769/"
    posts = parse_feed_search_posts(
        {
            "sections": {"search_results": raw},
            "references": {"search_results": []},
            "author_post_urls": {"monika kuqi": activity},
        }
    )
    assert len(posts) == 1
    assert activity in posts[0]["url"]
    assert posts[0]["url_source"] == "author_map"


# --- write_linkedin_run_markdown ---


def test_write_linkedin_run_markdown(tmp_path):
    cfg = load_example_linkedin_config()
    since = datetime(2026, 1, 1, tzinfo=timezone.utc)
    all_jobs = [
        {
            "role": "New Role",
            "company": "Acme",
            "posted_at": "2026-09-01T00:00:00+00:00",
            "posted_label": "2h",
            "filter_result": "eligible",
            "location_note": "LATAM",
            "url": "https://www.linkedin.com/posts/acme_hiring/",
            "source": "linkedin_posts",
            "salary_usd": "$120k",
        },
        {
            "role": "Old Role",
            "company": "Beta",
            "posted_at": "2025-06-01T00:00:00+00:00",
            "filter_result": "skipped",
            "location_note": "Worldwide",
            "url": "https://www.linkedin.com/posts/beta/",
            "source": "linkedin_posts",
        },
    ]
    new_jobs = [all_jobs[0]]
    run_path = tmp_path / "runs" / "linkedin-posts-test.md"
    write_linkedin_run_markdown(
        run_path,
        since,
        all_jobs,
        new_jobs,
        period_days=7,
        recency="past-week",
        queries_run=6,
        cfg=cfg,
    )
    text = run_path.read_text(encoding="utf-8")
    assert "LinkedIn posts run" in text
    assert "New to registry: **1**" in text
    assert "New Role" in text
    assert job_key(all_jobs[0]) in {job_key(j) for j in new_jobs}
    assert "yes" in text
    assert run_path.exists()


# --- check_linkedin_session ---


def test_check_linkedin_session_valid(monkeypatch):
    mock_result = MagicMock(returncode=0, stdout="Session valid ✅", stderr="")

    def fake_run(cmd, **kwargs):
        assert str(LOGIN_SCRIPT) in cmd[0] or cmd[0] == str(LOGIN_SCRIPT)
        return mock_result

    monkeypatch.setattr("subprocess.run", fake_run)
    ok, msg = check_linkedin_session()
    assert ok is True
    assert "valid" in msg.lower() or "✅" in msg


def test_check_linkedin_session_invalid_and_timeout(monkeypatch):
    monkeypatch.setattr(
        "subprocess.run",
        lambda *a, **k: MagicMock(returncode=1, stdout="", stderr="expired"),
    )
    ok, msg = check_linkedin_session()
    assert ok is False

    import subprocess

    def raise_timeout(*a, **k):
        raise subprocess.TimeoutExpired(cmd="status", timeout=120)

    monkeypatch.setattr("subprocess.run", raise_timeout)
    ok2, msg2 = check_linkedin_session()
    assert ok2 is False
    assert "timed out" in msg2.lower()


def test_check_linkedin_session_missing_script(monkeypatch, tmp_path):
    fake_script = tmp_path / "missing-login.sh"
    monkeypatch.setattr("linkedin_posts_merge.LOGIN_SCRIPT", fake_script)
    ok, msg = check_linkedin_session()
    assert ok is False
    assert "missing" in msg.lower()


# --- resolve_feed_update_to_posts_permalink (mock subprocess) ---


def test_resolve_feed_update_to_posts_permalink_og_url(monkeypatch):
    html = '<meta property="og:url" content="https://www.linkedin.com/posts/jane-doe_hiring-activity-123-abcd/" />'

    def fake_run(cmd, **kwargs):
        return MagicMock(returncode=0, stdout=html, stderr="")

    monkeypatch.setattr("subprocess.run", fake_run)
    out = resolve_feed_update_to_posts_permalink(
        "https://www.linkedin.com/feed/update/urn:li:activity:123/"
    )
    assert "/posts/jane-doe" in out
    assert out.endswith("/")
