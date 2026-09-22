"""Retrieval layer structure, imports, and behavior parity with v1 shims."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))


RETRIEVAL_MODULES = [
    "retrieval",
    "retrieval.registry.store",
    "retrieval.sources.linkedin.copy_link",
    "retrieval.sources.linkedin.posts_merge",
    "retrieval.sources.linkedin.posts_collect",
    "retrieval.sources.linkedin.jobs_merge",
    "retrieval.sources.linkedin.jobs_collect",
    "retrieval.sources.linkedin.repair_urls",
    "retrieval.sources.linkedin.repair_fields",
    "retrieval.sources.boards.discover",
    "retrieval.sources.boards.collectors",
    "retrieval.sources.google.discover",
    "retrieval.pipeline.daily",
    "retrieval.shared.audit_log",
    "retrieval.shared.browser.session",
    "retrieval.apply.pipelines.dm_apply",
    "retrieval.apply.pipelines.email_apply",
    "retrieval.apply.pipelines.url_apply",
    "retrieval.apply.pipelines.flow_runner",
    "retrieval.apply.state.dm_state",
    "retrieval.apply.integrations.applika.apply",
    "retrieval.apply.integrations.gmail.configure",
    "retrieval.apply.domain.application_channel",
]

APPLY_SHIM_PAIRS = [
    ("browser_session", "retrieval.shared.browser.session"),
    ("audit_log", "retrieval.shared.audit_log"),
    ("dm_apply", "retrieval.apply.pipelines.dm_apply"),
    ("dm_followup", "retrieval.apply.pipelines.dm_followup"),
    ("email_apply", "retrieval.apply.pipelines.email_apply"),
    ("url_apply", "retrieval.apply.pipelines.url_apply"),
    ("flow_runner", "retrieval.apply.pipelines.flow_runner"),
    ("dm_state", "retrieval.apply.state.dm_state"),
    ("applied_state", "retrieval.apply.state.applied_state"),
    ("form_apply_state", "retrieval.apply.state.form_apply_state"),
    ("applika_apply", "retrieval.apply.integrations.applika.apply"),
    ("sync_applika", "retrieval.apply.integrations.applika.sync"),
    ("gmail_configure", "retrieval.apply.integrations.gmail.configure"),
    ("application_channel", "retrieval.apply.domain.application_channel"),
    ("apply_email", "retrieval.apply.domain.apply_email"),
    ("position_disposition", "retrieval.apply.domain.position_disposition"),
]

SHIM_PAIRS = [
    ("registry", "retrieval.registry.store"),
    ("linkedin_posts_merge", "retrieval.sources.linkedin.posts_merge"),
    ("linkedin_jobs_merge", "retrieval.sources.linkedin.jobs_merge"),
    ("linkedin_content_collect", "retrieval.sources.linkedin.posts_collect"),
    ("linkedin_jobs_collect", "retrieval.sources.linkedin.jobs_collect"),
    ("linkedin_post_copy_link", "retrieval.sources.linkedin.copy_link"),
    ("daily_research", "retrieval.pipeline.daily"),
    ("discover", "retrieval.sources.boards.discover"),
    ("google_jobs_discover", "retrieval.sources.google.discover"),
    ("repair_linkedin_urls", "retrieval.sources.linkedin.repair_urls"),
    ("repair_registry_fields", "retrieval.sources.linkedin.repair_fields"),
    ("collectors", "retrieval.sources.boards.collectors"),
    *APPLY_SHIM_PAIRS,
]


@pytest.mark.parametrize("module_name", RETRIEVAL_MODULES)
def test_retrieval_module_imports(module_name: str) -> None:
    mod = importlib.import_module(module_name)
    assert mod is not None


@pytest.mark.parametrize("shim,canonical", SHIM_PAIRS)
def test_shim_is_same_module_object(shim: str, canonical: str) -> None:
    shim_mod = importlib.import_module(shim)
    canon_mod = importlib.import_module(canonical)
    assert shim_mod is canon_mod


def test_retrieval_paths_point_at_repo_root() -> None:
    from retrieval._paths import ROOT, SCRIPTS

    assert SCRIPTS.name == "scripts"
    assert (ROOT / "registry" / "jobs.json").parent.name == "registry"
    assert ROOT == Path(__file__).resolve().parent.parent


def test_infer_period_days_daily_after_prior_run() -> None:
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from registry import infer_period_days_from_since

    now = datetime(2026, 9, 21, 10, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
    since = "2026-09-20T16:46:13.006525-03:00"
    assert infer_period_days_from_since(since, now=now) == 1


def test_boards_discover_exports_run_discovery() -> None:
    from retrieval.sources.boards.discover import run_discovery

    assert callable(run_discovery)


def test_pipeline_exports_run_daily_research() -> None:
    from retrieval.pipeline import run_daily_research

    assert callable(run_daily_research)


def test_apply_exports_channel_classifier() -> None:
    from application_channel import classify_channel

    assert callable(classify_channel)


def test_apply_flow_runner_uses_repo_flows_dir() -> None:
    from flow_runner import FLOWS_DIR

    assert FLOWS_DIR.name == "flows"
    assert FLOWS_DIR.parent == Path(__file__).resolve().parent.parent


def test_collectors_registry_has_all_sources() -> None:
    from collectors import COLLECTORS

    expected = {
        "remoteok",
        "weworkremotely",
        "defi",
        "himalayas",
        "opentoworkremote",
        "wellfound",
        "f6s",
    }
    assert set(COLLECTORS) == expected
