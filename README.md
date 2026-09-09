# ApplySemPatria

[![CI](https://github.com/ProgramadoresSemPatria/ApplySemPatria/actions/workflows/ci.yml/badge.svg)](https://github.com/ProgramadoresSemPatria/ApplySemPatria/actions/workflows/ci.yml)

Local-first job discovery and application tooling (boards, LinkedIn posts, email/DM/form apply channels, applications UI).

## Quick start

```bash
git clone https://github.com/ProgramadoresSemPatria/ApplySemPatria.git job-search
cd job-search
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Copy track templates (profile, configs) — not stored in git
TRACK=ai-engineer
mkdir -p "tracks/$TRACK"
cp -R "examples/tracks/$TRACK/." "tracks/$TRACK/"

# Edit tracks/$TRACK/applicant-profile.json (email, resume path, etc.)
python scripts/jobsearch.py onboarding --track "$TRACK"
python scripts/jobsearch.py doctor
python scripts/jobsearch.py discover --track "$TRACK"
python scripts/jobsearch.py table
python scripts/jobsearch.py ui
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
```

See `playbooks/` for channel-specific setup (Gmail, LinkedIn session, Himalayas, etc.).

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
