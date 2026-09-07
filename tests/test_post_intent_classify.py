"""Tests for optional LLM post intent classifier."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from post_intent_classify import (  # noqa: E402
    _normalize_intent,
    classify_post_llm,
    classify_with_openai,
    load_cache,
    make_llm_classify_fn,
    save_cache,
)


def test_normalize_intent_aliases():
    assert _normalize_intent(" hiring ") == "hiring"
    assert _normalize_intent("job-seeker") == "job_seeker"
    assert _normalize_intent("recruiter") == "hiring"


def test_cache_roundtrip(tmp_path, monkeypatch):
    cache_file = tmp_path / "cache.json"
    monkeypatch.setattr("post_intent_classify.CACHE_PATH", cache_file)
    save_cache({"abc": "hiring"})
    assert load_cache()["abc"] == "hiring"


def test_classify_post_llm_disabled():
    assert classify_post_llm("some text", cfg={"llm_intent_classify_enabled": False}) is None


def test_classify_with_openai_no_api_key():
    assert classify_with_openai("text", api_key="") is None


@patch("post_intent_classify.classify_with_openai")
def test_make_llm_classify_fn_delegates(mock_openai, tmp_path, monkeypatch):
    cache_file = tmp_path / "cache.json"
    monkeypatch.setattr("post_intent_classify.CACHE_PATH", cache_file)
    mock_openai.return_value = "hiring"
    fn = make_llm_classify_fn({"llm_intent_classify_enabled": True, "llm_intent_model": "gpt-4o-mini"})
    assert fn("borderline post about AI engineer", "Headline") == "hiring"
    mock_openai.assert_called_once()


@patch("post_intent_classify.classify_with_openai")
def test_classify_post_llm_uses_cache(mock_openai, tmp_path, monkeypatch):
    cache_file = tmp_path / "cache.json"
    monkeypatch.setattr("post_intent_classify.CACHE_PATH", cache_file)
    text = "Unique post text for cache key test xyz"
    mock_openai.return_value = "hiring"

    cfg = {"llm_intent_classify_enabled": True, "llm_intent_model": "gpt-4o-mini"}
    first = classify_post_llm(text, cfg=cfg)
    second = classify_post_llm(text, cfg=cfg)

    assert first == "hiring"
    assert second == "hiring"
    mock_openai.assert_called_once()
