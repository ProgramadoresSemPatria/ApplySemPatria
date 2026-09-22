# Data / retrieval layer

All **external I/O** lives under `scripts/retrieval/`: job ingestion, apply pipelines, browser automation, Gmail, Applika, and shared audit logging. Presentation (tables, UI server) stays at `scripts/` top level.

## Layout

```
scripts/retrieval/
  _paths.py                     # ROOT, SCRIPTS
  types.py                      # JobRecord, MergeResult, CollectResult

  registry/
    store.py                    # jobs.json load/save/merge/dedupe

  sources/                      # INGEST
    linkedin/                   # posts + jobs collect/merge/repair
    boards/                     # discover + collectors (RemoteOK, …)
    google/                     # Google CSE discover

  apply/                        # APPLY + external integrations
    pipelines/
      dm_apply.py               # LinkedIn connect / message
      dm_followup.py            # Bulk DM follow-up
      email_apply.py              # Gmail API / SMTP
      url_apply.py                # ATS / form autofill
      linkedin_easy_apply.py    # Easy Apply wizard
      linkedin_easy_apply_status.py
      flow_runner.py              # flows/*.json recipes
    state/
      dm_state.py                 # dm-applications.json
      applied_state.py            # applied-applications.json
      form_apply_state.py         # url-applications.json
    integrations/
      applika/                    # applika CLI sync
      gmail/                      # OAuth / app-password setup
      browser/dm_chat.py          # LinkedIn messaging helpers
    domain/
      application_channel.py      # email / DM / URL classification
      apply_email.py
      form_answers.py
      position_disposition.py
    tools/                        # dm_recheck, dm_debug_profile

  shared/                       # used by ingest + apply
    audit_log.py
    browser/
      session.py                  # Patchright / cookies / profile
      human_pacing.py
      linkedin_ui.py

  pipeline/
    daily.py                      # daily research orchestration
```

## Backward compatibility

Legacy paths (`dm_apply`, `email_apply`, `browser_session`, `applika_apply`, `registry`, …) are **module aliases** (`sys.modules[__name__] = _impl`). Subprocess CLIs and existing imports keep working unchanged.

## Data flow

| Phase | Modules | Output |
|-------|---------|--------|
| Ingest | `sources/*` → `registry.store` | `registry/jobs.json` |
| Apply | `apply/pipelines/*` → `apply/state/*` | `state/*-applications.json` |
| Present | `generate_applications.py` (outside layer) | applications table + UI snapshot |

## Tests

| Suite | Path |
|-------|------|
| Layer + shim parity | `tests/test_retrieval_layer.py` |
| Ingest e2e (fixtures) | `tests/e2e/test_retrieval_pipeline_e2e.py` |
| Post URL pipeline | `tests/e2e/test_post_url_pipeline.py` |
| HAR replay (connect/message) | `tests/test_flow_linkedin_har.py` |
| Apply unit | `tests/test_dm_apply.py`, `tests/test_email_apply.py`, … |
