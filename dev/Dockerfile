# Isolated jobsearch environment: editable install + smoke/e2e (no host tracks/registry).
FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    JOBSEARCH_SKIP_LINKEDIN=1 \
    JOBSEARCH_NO_REEXEC=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bash \
        ca-certificates \
        curl \
        git \
        rsync \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install first (layer cache), then copy source
COPY pyproject.toml jobsearch_cli_entry.py requirements.txt README.md tracks.json domain-blacklist.json ./
COPY scripts ./scripts
COPY flows ./flows
COPY ui ./ui
COPY examples ./examples
COPY playbooks ./playbooks
COPY dev ./dev
COPY templates ./templates
COPY tests ./tests
COPY docs ./docs

RUN pip install --no-cache-dir -e ".[gmail]" \
    && mkdir -p registry state runs tracks logs \
    && echo '{"jobs":[]}' > registry/jobs.json

# Default: run full docker e2e (install + onboarding + UI HTTP checks)
CMD ["bash", "dev/docker-e2e.sh"]
