# ApplySemPatria (jobsearch CLI)

[![CI](https://github.com/ProgramadoresSemPatria/ApplySemPatria/actions/workflows/ci.yml/badge.svg)](https://github.com/ProgramadoresSemPatria/ApplySemPatria/actions/workflows/ci.yml)

Local-first job discovery and application tooling (boards, LinkedIn posts, email/DM/form apply channels, applications UI).

**Install and run everything with `make`** from a single clone. Your data (`tracks/`, `registry/`, `state/`) stays on your machine and is not uploaded.

## Requirements

- **Python 3.11+**
- **Make** (macOS/Linux — `make` is preinstalled on most systems)
- **Git** (full clone — the CLI expects `flows/`, `ui/`, `examples/` next to `scripts/`)
- **macOS or Linux** recommended (browser apply is tested on macOS)

## Quick start

```bash
git clone https://github.com/ProgramadoresSemPatria/ApplySemPatria.git job-search
cd job-search

make quickstart
make onboarding
make ui
```

That’s it for setup — no `pip`, no `source .venv/bin/activate`. Run **`make help`** for everything else (`discover`, `doctor`, `reset-data`, Docker, tests).

When you need LinkedIn or form apply in the browser: **`make browser`** once.

## Daily commands

| Goal | Command |
|------|---------|
| Discover jobs | `make discover` or `make discover SINCE=14d TRACK=ai-engineer` |
| Open dashboard | `make ui` |
| Health check | `make doctor` |
| List tracks | `make tracks` |
| Reinstall deps after `git pull` | `make upgrade` then `make doctor` |
| Install Chromium via CLI | `make install-cli` or `make browser` |
| Broken `.venv` / install fails | `make clean-venv` then `make quickstart` |
| Ingestion health snapshot | `make audit-ingestion` |
| Download debug report (CLI) | `make support-bundle` — or **Download debug report** in the UI |

## Reset local data (bugs / first-run replay)

Backs up beside the repo by default, then wipes personal data:

```bash
make reset-data              # preview — no changes
make reset-data CONFIRM=1    # backup + wipe tracks/, registry/, state/, secrets/, runs/, logs/
make fresh-start CONFIRM=1   # reset + bootstrap
make onboarding
```

Options: `BACKUP=0`, `RESET_LINKEDIN=0` (keep LinkedIn cookies), `RESET_BROWSER=1` (remove `patchright-profile/`).

## Keeping your install stable

| Step | Why |
|------|-----|
| Use **one clone** and run **`make …` from that folder** | Paths, `flows/`, and `state/` are relative to the repo root |
| Stay on **`main`** or a **release tag** (`git checkout v0.1.0`) | Tags are supported snapshots |
| After **`git pull`**: **`make upgrade`** and **`make doctor`** | Aligns Python packages and surfaces missing setup |
| Never commit **`tracks/`**, **`secrets/`**, **`state/`**, **`registry/`** | Gitignored — data stays local |

Pin a release when we tag them:

```bash
git fetch --tags
git checkout v0.1.0
make install
make doctor
```

## What's in git vs local

| In git | Local only (`.gitignore`) |
|--------|---------------------------|
| `scripts/`, `tests/`, `ui/`, `flows/`, `playbooks/` | `tracks/` — your profile & preferences |
| `examples/tracks/` — sanitized templates | `registry/` — discovered jobs |
| `tracks.json` — track manifest | `runs/` — generated tables & audit output |
| `domain-blacklist.json` — shared scam domains | `state/` — apply progress, Gmail token |
| `Makefile`, `scripts/reset_local_data.sh` | `secrets/` — credentials |

## Cursor / agent-assisted apply (optional)

The CLI runs **deterministic** steps (discover, table, Playwright connect flows, email).  
**Form apply** and fuzzy judgment are designed to work with an **IDE agent** (e.g. Cursor + skills) or optional **`OPENAI_API_KEY`** for LinkedIn post intent (`llm_intent_classify_enabled` in track config). No agent is bundled in the pip package.

See `playbooks/` for channel-specific notes (Gmail OAuth, LinkedIn session, Himalayas, etc.).

## Docker (isolated install + e2e)

Same project, no local `tracks/` or secrets — data only inside the container:

```bash
make docker-build
make docker-e2e          # CI-style smoke
make docker-ui           # http://127.0.0.1:8765/
make docker-onboard      # interactive onboarding in container
```

GitHub Actions runs **`docker-e2e.yml`** on every push to `main`.

## Testing (contributors)

```bash
make test              # unit + browser
make test-unit
make test-coverage
make test-stable
```

Scenario catalog: `docs/testing/SCENARIOS.md`  
CI strategy: `docs/testing/STRATEGY.md`

## Publishing releases (maintainers)

1. Bump `version` in `pyproject.toml`, commit, tag: `git tag v0.1.0 && git push origin v0.1.0`
2. CI on `main` should stay green (`make test-unit`)
3. Users: **`git clone`** at that tag, then **`make install`**

PyPI-only `pip install jobsearch-cli` without a clone is **not** supported yet (data files and `tracks/` layout require the full repo).

<details>
<summary>Manual install (no Make)</summary>

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[browser,gmail]"
patchright install chromium
bash scripts/bootstrap_local.sh ai-engineer
jobsearch onboarding --track ai-engineer
```

Legacy: `pip install -r requirements.txt` and `python scripts/jobsearch.py doctor`.

</details>
