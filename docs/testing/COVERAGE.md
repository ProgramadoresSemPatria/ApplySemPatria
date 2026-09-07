# Coverage — assertive thresholds

We treat coverage as a **regression gate**, not a vanity metric. CI fails if measured line rates drop below committed floors.

## What gets measured

| Command | Scope | Used in CI |
|---------|-------|------------|
| `./scripts/run_tests.sh coverage` | Unit tier only → `scripts/` | **Yes** (unit job) |
| `./scripts/run_tests.sh coverage-all` | Unit + browser (HAR, HTML, UI e2e) | Local only |

Reports:

- Terminal summary (uncovered lines)
- `htmlcov/index.html` — browse by file
- `coverage.xml` — machine-readable; uploaded logic + threshold check

Configuration: `pyproject.toml` → `[tool.coverage.*]`

## How CI enforces floors

After pytest-cov runs, two checks apply:

1. **Global floor** — `[tool.coverage.report] fail_under` in `pyproject.toml` (currently **20%** on all `scripts/`).
2. **Module floors** — `scripts/check_coverage_thresholds.py` reads `coverage-thresholds.json` and fails if any listed file regresses.

Both run automatically inside `./scripts/run_tests.sh coverage`.

```bash
# Manual check after any pytest-cov run
python scripts/check_coverage_thresholds.py coverage.xml
```

If CI fails on coverage:

```text
Coverage thresholds FAILED:
  - scripts/ui_server.py: 38.2% < 40.0%
```

Fix by adding tests (preferred) or, if the drop is intentional, update the floor in `coverage-thresholds.json` in the **same PR** as the code change.

## Module floors (UI-relevant)

Defined in `coverage-thresholds.json` at repo root. Current baselines reflect **unit tier** (what CI measures):

| Module | Min line rate | Tied to scenarios |
|--------|---------------|-------------------|
| `scripts/ui_server.py` | 40% | UI-01, UI-03..07, CLI-01..07 |
| `scripts/applications_ui_data.py` | 40% | UI-02, UI-04, UI-08, UI-09, FE-01..05 |
| `scripts/position_disposition.py` | 80% | UI-07, UI-08, FE-09/10 |
| `scripts/dm_state.py` | 60% | FE-01..04 |
| `scripts/application_channel.py` | 70% | FE-05 |
| `scripts/table_format.py` | 75% | FE-08 |
| `scripts/filters.py` | 80% | discovery filter scenarios |
| **Total `scripts/`** | **20%** | whole suite |

Browser e2e (`coverage-all`) typically adds ~2 pp overall and ~10 pp on `ui_server.py`, but **CI gates unit tier only** so PRs stay fast and deterministic.

## Local workflow

```bash
pip install -r requirements-dev.txt
PY=.venv-test/bin/python ./scripts/run_tests.sh coverage
open htmlcov/index.html
```

Before raising a floor:

1. Run coverage locally.
2. Set the new minimum **slightly below** the measured rate (leave ~1–2 pp buffer).
3. Document which scenario IDs the new tests cover in `docs/testing/UI_E2E_SCENARIOS.md`.

## Raising floors over time

Suggested ladder:

| Milestone | Total | `ui_server.py` | Action |
|-----------|-------|----------------|--------|
| Now | 20% | 40% | baseline |
| + UI-05..07 e2e | 21% | 50% | add Playwright tests |
| + UI-09, UI-10 | 22% | 55% | filter + stale banner |
| Discovery refactor | 25% | 55% | unit tests on collectors |

Do **not** set `fail_under` to a target you have not measured yet — that blocks every PR until tests land.

## What coverage does not prove

- **Frontend JS** in `ui/applications/index.html` — use Playwright scenarios in [UI_E2E_SCENARIOS.md](./UI_E2E_SCENARIOS.md).
- **Live LinkedIn / job boards** — excluded (`@pytest.mark.integration`).
- **Flaky e2e** — a passing coverage gate does not replace stable browser tests.

## CI artifacts

The unit job uploads `coverage-html` ( browsable `htmlcov/` ) and writes a Step Summary line like:

```text
Coverage (unit tier): 21.7% line coverage (1543/7119 lines)
```

Download the artifact from the Actions run → **Artifacts** → `coverage-html`.
