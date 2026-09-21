# Retrieval layer (v2)

All job **ingestion** lives under `scripts/retrieval/`. Presentation (tables, UI) and apply pipelines stay outside.

## Layout

```
scripts/retrieval/
  _paths.py                 # ROOT, SCRIPTS
  types.py                  # JobRecord, MergeResult, CollectResult
  registry/
    store.py                # jobs.json load/save/merge/dedupe
  sources/
    linkedin/
      copy_link.py          # SDUI copy-link URL extraction
      posts_collect.py      # Browser scroll collect
      posts_merge.py        # Parse + merge posts
      jobs_collect.py       # Jobs search pagination
      jobs_merge.py         # Jobs merge
      repair_urls.py        # Placeholder URL repair
      repair_fields.py      # Salary/email/URL field repair
    boards/
      discover.py           # Board orchestrator
      collectors/           # RemoteOK, Himalayas, etc.
    google/
      discover.py           # Google CSE discovery
  pipeline/
    daily.py                # Daily research orchestration
```

## Backward compatibility

Legacy import paths (`registry`, `linkedin_posts_merge`, `daily_research`, `collectors`, …) are **module aliases** that point at the retrieval implementation. Existing scripts and tests keep working.

## Data flow

1. **Collect** — source modules fetch raw data (browser or HTTP).
2. **Merge** — normalize to `JobRecord`, filter, dedupe via `registry.store.merge_jobs`.
3. **Present** — `generate_applications.py` reads registry (outside retrieval).

## Tests

| Suite | Path |
|-------|------|
| Layer structure + shim parity | `tests/test_retrieval_layer.py` |
| Retrieval e2e (fixtures, no browser) | `tests/e2e/test_retrieval_pipeline_e2e.py` |
| Post URL pipeline | `tests/e2e/test_post_url_pipeline.py` |
| HAR replay (connect/message) | `tests/test_flow_linkedin_har.py` |
