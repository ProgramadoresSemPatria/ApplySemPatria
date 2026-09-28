# ApplySemPatria (jobsearch CLI)

[![CI](https://github.com/ProgramadoresSemPatria/ApplySemPatria/actions/workflows/ci.yml/badge.svg)](https://github.com/ProgramadoresSemPatria/ApplySemPatria/actions/workflows/ci.yml)

Local-first job discovery and application tooling (boards, LinkedIn posts, email/DM/form apply channels, applications UI).

**Stable install model:** clone this repo once, use a project venv, run the `jobsearch` command from that folder. Your data (`tracks/`, `registry/`, `state/`) stays on your machine and is not uploaded.

## Requirements

- **Python 3.11+**
- **macOS or Linux** (Windows may work; browser apply is tested on macOS)
- **Git** (full clone — the CLI expects `flows/`, `ui/`, `examples/` next to `scripts/`)

## Quick start (recommended)

```bash
git clone https://github.com/ProgramadoresSemPatria/ApplySemPatria.git job-search
cd job-search

python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# Installs core deps + puts `jobsearch` on PATH (editable = same layout as development)
pip install -e ".[browser,gmail]"
patchright install chromium

# Copy track templates (profile + configs — not in git per user)
TRACK=ai-engineer
mkdir -p "tracks/$TRACK"
cp -R "examples/tracks/$TRACK/." "tracks/$TRACK/"

# Edit tracks/$TRACK/applicant-profile.json (email, resume path, etc.)
jobsearch onboarding --track "$TRACK"
jobsearch doctor
jobsearch discover --track "$TRACK"
jobsearch table
jobsearch ui
```

### Without `pip install -e` (legacy)

```bash
pip install -r requirements.txt
python scripts/jobsearch.py doctor
```

## Keeping your install stable (match a maintainer machine)

| Step | Why |
|------|-----|
| Use **one clone directory** and always `cd` there before commands | Paths, `flows/`, and `state/` are relative to the repo root |
| Stay on **`main`** or a **release tag** (`git checkout v0.1.0`) | Tags are the supported snapshots for others |
| Run **`jobsearch install --browser`** after pulling if deps changed | Aligns Patchright + Python packages with `requirements.txt` |
| Run **`jobsearch doctor`** before discover/apply | Surfaces missing profile, cookies, Gmail, browser |
| Never commit **`tracks/`**, **`secrets/`**, **`state/`**, **`registry/`** | Already gitignored; keeps your data local |

Upgrade after `git pull`:

```bash
source .venv/bin/activate
pip install -e ".[browser,gmail]"
jobsearch doctor
```

Optional: pin a release when we tag them:

```bash
git fetch --tags
git checkout v0.1.0
pip install -e ".[browser,gmail]"
```

## What's in git vs local

| In git | Local only (`.gitignore`) |
|--------|---------------------------|
| `scripts/`, `tests/`, `ui/`, `flows/`, `playbooks/` | `tracks/` — your profile & preferences |
| `examples/tracks/` — sanitized templates | `registry/` — discovered jobs |
| `tracks.json` — track manifest | `runs/` — generated tables & audit output |
| `domain-blacklist.json` — shared scam domains | `state/` — apply progress, Gmail token |
| | `secrets/` — credentials |

## Commands

```bash
jobsearch discover          # fetch new roles into registry
jobsearch table             # build applications markdown + UI snapshot
jobsearch ui                # dashboard at http://127.0.0.1:8765
jobsearch apply dm --list   # preview DM/connect queue
jobsearch onboarding        # first-run setup wizard
jobsearch install --browser # Patchright + Chromium (LinkedIn DM / forms)
```

See `playbooks/` for channel-specific setup (Gmail, LinkedIn session, Himalayas, etc.).

## Cursor / agent-assisted apply (optional)

The CLI runs **deterministic** steps (discover, table, Playwright connect flows, email).  
**Form apply** and fuzzy judgment are designed to work with an **IDE agent** (e.g. Cursor + skills) or optional **`OPENAI_API_KEY`** for LinkedIn post intent (`llm_intent_classify_enabled` in track config). No agent is bundled in the pip package.

## Publishing releases (maintainers)

1. Bump `version` in `pyproject.toml`, commit, tag: `git tag v0.1.0 && git push origin v0.1.0`
2. CI on `main` should stay green (`./scripts/run_tests.sh unit`)
3. Users install with **`git clone` + `pip install -e ".[browser,gmail]"`** at that tag

PyPI-only `pip install jobsearch-cli` without a clone is **not** supported yet (data files and `tracks/` layout require the full repo).

## Docker (isolated install + e2e)

Use Docker to verify the same install flow as the README **without your local `tracks/`, `registry/`, or secrets**. Data lives only inside the container.

```bash
# Build
docker compose -f dev/docker-compose.yml build

# CI-style e2e: pip install → onboarding → table → UI HTTP checks
docker compose -f dev/docker-compose.yml run --rm e2e

# Extra smoke: rsync a fresh copy from your working tree (read-only mount)
docker compose -f dev/docker-compose.yml run --rm onboarding-smoke

# Browse the dashboard (empty registry until you run discover inside the container)
docker compose -f dev/docker-compose.yml up ui
# → http://127.0.0.1:8765/
```

GitHub Actions runs **`docker-e2e.yml`** on every push to `main` (see `.github/workflows/docker-e2e.yml`).

## Testing

```bash
pip install -r requirements-dev.txt
patchright install chromium
./scripts/run_tests.sh all            # unit + browser
./scripts/run_tests.sh coverage         # unit tests + terminal/html/xml report
./scripts/run_tests.sh coverage-all     # unit + browser combined coverage
./scripts/run_tests.sh stable           # 5× unit + 3× browser
python scripts/generate_linkedin_hars.py  # after editing linkedin HTML fixtures
```

Scenario catalog: `docs/testing/SCENARIOS.md`  
CI strategy: `docs/testing/STRATEGY.md`  

GitHub Actions: `ci.yml` on `main` (scaffold); full suite on **`ci/tests`** branch via `tests.yml`.
