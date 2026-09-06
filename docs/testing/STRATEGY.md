# Test strategy & CI

## Tiers

| Tier | Marker | Runs in CI | Tools | Stability |
|------|--------|------------|-------|-----------|
| **Unit** | default | Always | pytest, unittest.mock | High — no network/browser |
| **Flow fixtures** | `@pytest.mark.playwright` | `ci/tests` branch | Patchright + static HTML | High — no LinkedIn network |
| **UI e2e** | `@pytest.mark.playwright` | `ci/tests` branch | Patchright + mock API server | High — no real apply subprocess |
| **Integration** | `@pytest.mark.integration` | Manual / nightly only | Live job boards | Low — excluded from PR CI |

## Local commands

```bash
pip install -r requirements-dev.txt
patchright install chromium

# Unit only (fast, run 3× for stability)
./scripts/run_tests.sh unit

# Flow + UI Playwright
./scripts/run_tests.sh playwright

# Everything except integration
./scripts/run_tests.sh all

# Stability loop (5× full non-integration suite)
./scripts/run_tests.sh stable
```

## CI workflows

| Workflow | Branch | Purpose |
|----------|--------|---------|
| `.github/workflows/ci.yml` | `main` | Scaffold — always green |
| `.github/workflows/tests.yml` | `ci/tests`, PRs → `ci/tests` | Unit + Playwright |

Develop test changes on `ci/tests`; merge to `main` when stable.

## Mock strategy (LinkedIn)

1. **HTML fixtures** (`tests/fixtures/linkedin/*.html`) — minimal `<main>` DOM for Connect / Message / Pending.
2. **Dry-run flow** — `flow_runner.run_recipe(..., send=False)` asserts `commit_kind` without clicks.
3. **HAR** (future) — record once with `record_har_path`; replay in CI with `route_from_har`.
4. **UI API** — patch `ui_server.run_action` / `refresh_live_snapshot` in test server; never spawn real browser apply in CI.

## LLM-as-judge

CI uses **rule-based judge only** (`expect_action`, `expect_step_states`).

Optional local check:

```bash
JOBSEARCH_LLM_JUDGE=1 OPENAI_API_KEY=... pytest tests/test_judge_llm.py -v
```

Skipped automatically when env vars unset.
