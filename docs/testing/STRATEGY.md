# Test strategy & CI

## Tiers

| Tier | Marker / path | Runs in CI | Tools | Stability |
|------|---------------|------------|-------|-----------|
| **Unit** | default (excludes integration, playwright, har, browser) | Always | pytest, mocks | High |
| **HAR validate** | `tests/test_har_fixtures.py` | Always (before browser) | JSON parse only | High |
| **HAR replay** | `@pytest.mark.har`, `test_flow_linkedin_har.py` | Always | Patchright + committed `.har` | High — offline |
| **HTML baseline** | `test_flow_linkedin_fixtures.py` | Always | Patchright + `file://` HTML | High |
| **UI e2e** | `@pytest.mark.playwright`, `tests/e2e/` | Always | Mock HTTP server + Patchright | High |
| **Integration** | `@pytest.mark.integration` | Never in CI | Live job boards | Low |

## Local commands

```bash
pip install -r requirements-dev.txt
patchright install chromium

./scripts/run_tests.sh verify-hars   # HAR JSON integrity only
./scripts/run_tests.sh unit          # ~85 tests
./scripts/run_tests.sh playwright    # verify-hars + HTML + HAR + UI e2e
./scripts/run_tests.sh all           # unit + playwright
./scripts/run_tests.sh stable        # 5× unit + 3× browser
```

Regenerate HAR after HTML fixture changes:

```bash
python scripts/generate_linkedin_hars.py
```

## CI workflows (GitHub Actions)

| Workflow | Trigger | Jobs |
|----------|---------|------|
| `.github/workflows/ci.yml` | `main`, `ci/tests` push/PR, manual | **unit** → **browser** → **ci gate** |

Badge: [![CI](https://github.com/ProgramadoresSemPatria/ApplySemPatria/actions/workflows/ci.yml/badge.svg)](https://github.com/ProgramadoresSemPatria/ApplySemPatria/actions/workflows/ci.yml)

Observe: `gh run list --workflow=ci.yml` · `gh run watch`

### CI audit checklist

- [x] No live LinkedIn / job board network in default path
- [x] HAR files committed (`tests/fixtures/har/*.har`)
- [x] Fixed mock port `18766` (HAR URL must match replay URL)
- [x] `not_found=abort` on HAR replay — stray requests fail loudly
- [x] Stability repeats: 3× unit, 3× browser on CI
- [x] Integration tests excluded via `-m "not integration …"`
- [x] Patchright `install-deps` on Ubuntu for headless Chromium

## Mock strategy (LinkedIn)

1. **HTML fixtures** — `tests/fixtures/linkedin/*.html` minimal DOM.
2. **HAR replay** — recorded from local mock server; tests use `run_with_har()`.
3. **Rule-based judge** — `expect_flow_commit`, `expect_classify`, `expect_action`.
4. **Real LinkedIn HAR** (optional future) — record once with auth; separate manual job only.

## LLM-as-judge

CI uses **rule-based judge only**. Optional local: `JOBSEARCH_LLM_JUDGE=1` + API key.
