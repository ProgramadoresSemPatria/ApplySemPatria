# ApplySemPatria — common tasks (run `make` or `make help`)
# Requires: Python 3.11+, make, git clone of this repo

.DEFAULT_GOAL := help

TRACK ?= ai-engineer
SINCE ?= 7d
PORT ?= 8765
VENV := .venv
PYTHON := $(VENV)/bin/python3
JOBSEARCH := $(VENV)/bin/jobsearch
COMPOSE := docker compose -f dev/docker-compose.yml

# reset-data: set CONFIRM=1 (see script). Optional: BACKUP=0 RESET_LINKEDIN=0 RESET_BROWSER=1
BACKUP ?= 1
RESET_LINKEDIN ?= 1
RESET_BROWSER ?= 0

.PHONY: help
help: ## Show targets (default)
	@echo "ApplySemPatria — common commands (TRACK=$(TRACK))"
	@echo ""
	@grep -E '^[a-zA-Z0-9_.-]+:.*##' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "Examples:"
	@echo "  make quickstart && make onboarding && make ui"
	@echo "  make discover SINCE=14d"
	@echo "  make ui PORT=8765"
	@echo "  make reset-data CONFIRM=1   # wipe local data (backup first)"
	@echo "  make fresh-start CONFIRM=1  # reset + bootstrap track template"

.PHONY: venv clean-venv
venv: ## Create or repair .venv (recreates if pip is missing)
	@if [ -x '$(PYTHON)' ] && '$(PYTHON)' -m pip --version >/dev/null 2>&1; then \
	  exit 0; \
	fi; \
	if [ -d '$(VENV)' ]; then \
	  echo "⚠ $(VENV) exists but has no pip — recreating…"; \
	  rm -rf '$(VENV)'; \
	fi; \
	python3 -m venv '$(VENV)'; \
	'$(PYTHON)' -m ensurepip --upgrade 2>/dev/null || true; \
	'$(PYTHON)' -m pip install -U pip wheel

clean-venv: ## Remove .venv (run before make install if install keeps failing)
	rm -rf '$(VENV)'

.PHONY: install
install: venv ## Editable install + browser + Gmail extras
	$(PYTHON) -m pip install -U pip
	$(PYTHON) -m pip install -e ".[browser,gmail]"
	@echo ""
	@echo "✓ Installed. Optional: make browser"
	@echo "  Next: make bootstrap && make onboarding"

.PHONY: upgrade
upgrade: venv ## Re-run pip install after git pull
	$(PYTHON) -m pip install -e ".[browser,gmail]"

.PHONY: browser
browser: install ## Install Patchright Chromium (LinkedIn / forms)
	$(VENV)/bin/patchright install chromium

.PHONY: bootstrap
bootstrap: ## Copy examples/tracks/$(TRACK) → tracks/$(TRACK) (skips existing)
	bash scripts/bootstrap_local.sh $(TRACK)

.PHONY: first-run quickstart
first-run: install bootstrap ## Install + copy track template; then run onboarding yourself
	@echo ""
	@echo "Track template ready under tracks/$(TRACK)/"
	@echo "Run: make onboarding"

quickstart: first-run ## Same as first-run — use after clone (install + bootstrap)

.PHONY: require-install
require-install:
	@test -x '$(JOBSEARCH)' || { echo "✗ Run \`make install\` first."; exit 1; }

.PHONY: onboarding doctor discover table ui tracks
onboarding: require-install ## Interactive first-run wizard (TRACK=)
	$(JOBSEARCH) onboarding --track $(TRACK)

doctor: require-install ## Readiness report (profile, Gmail, LinkedIn, deps)
	$(JOBSEARCH) doctor

discover: require-install ## Discover board jobs (TRACK=, SINCE=)
	$(JOBSEARCH) discover --track $(TRACK) --since $(SINCE)

table: require-install ## Refresh applications table + UI snapshot
	$(JOBSEARCH) table

ui: require-install ## Applications dashboard (PORT=8765 default)
	$(JOBSEARCH) ui --port $(PORT)

tracks: require-install ## List tracks and readiness
	$(JOBSEARCH) tracks list

.PHONY: install-cli
install-cli: require-install ## jobsearch install --browser (deps + Chromium via CLI)
	$(JOBSEARCH) install --browser

.PHONY: test test-unit test-coverage test-stable
test: ## Full test suite (unit + browser)
	bash scripts/run_tests.sh all

test-unit: ## Unit tests only
	bash scripts/run_tests.sh unit

test-coverage: ## Unit tests + coverage report
	bash scripts/run_tests.sh coverage

test-stable: ## Repeated unit + browser (flake check)
	bash scripts/run_tests.sh stable

.PHONY: docker-build docker-e2e docker-smoke docker-ui docker-onboard
docker-build: ## Build dev Docker image
	$(COMPOSE) build

docker-e2e: ## CI-style install → onboarding → UI checks in container
	$(COMPOSE) run --rm e2e

docker-smoke: ## Onboarding smoke from mounted working tree
	$(COMPOSE) run --rm onboarding-smoke

docker-ui: ## Dashboard on http://127.0.0.1:8765/ (isolated volumes)
	$(COMPOSE) up ui

docker-onboard: ## Interactive onboarding inside Docker
	$(COMPOSE) run --rm onboard

.PHONY: reset-data fresh-start
reset-data: ## Delete local data; backup first (CONFIRM=1 required)
	CONFIRM=$(CONFIRM) BACKUP=$(BACKUP) RESET_LINKEDIN=$(RESET_LINKEDIN) \
		RESET_BROWSER=$(RESET_BROWSER) BACKUP_DIR="$(BACKUP_DIR)" \
		bash scripts/reset_local_data.sh

collect-visible: require-install ## jobsearch.settings.yaml with visible Chrome for LinkedIn ingest
	@$(PYTHON) -c "from pathlib import Path; s=Path('examples/jobsearch.settings.yaml').read_text(); d=Path('jobsearch.settings.yaml'); d.write_text(s.replace('linkedin_collect_visible: false','linkedin_collect_visible: true')); print('Wrote', d.resolve(), '(browser.linkedin_collect_visible: true)')"

audit-ingestion: ## Snapshot research status + registry (see logs/ingestion-watch.log)
	bash scripts/ingestion_audit.sh

fresh-start: reset-data bootstrap ## Wipe data + copy track template (CONFIRM=1)
	@echo ""
	@echo "Fresh track template under tracks/$(TRACK)/"
	@echo "Run: make onboarding"
