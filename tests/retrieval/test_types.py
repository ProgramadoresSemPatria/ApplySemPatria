"""Coverage for retrieval.types."""

from __future__ import annotations

from retrieval.types import CollectResult, JobRecord, MergeResult, as_job_record


def test_as_job_record_returns_same_dict():
    raw: JobRecord = {
        "source": "google",
        "url": "https://example.com/jobs/1",
        "role": "AI Engineer",
        "company": "Acme",
    }
    out = as_job_record(raw)
    assert out is raw
    assert out["source"] == "google"


def test_typed_dict_shapes_are_usable():
    merge: MergeResult = {"new_total": 3, "eligible": 2}
    collect: CollectResult = {"query": "ai engineer", "posts_found": 10, "merge": merge}
    assert collect["merge"]["eligible"] == 2
