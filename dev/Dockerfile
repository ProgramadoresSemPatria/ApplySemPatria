# Dev-only: simulate first-run onboarding from a clean copy (does not touch your live ~/job-search).
FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1
ENV JOBSEARCH_SKIP_LINKEDIN=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates git rsync \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace
