"""Backward-compatible module alias for retrieval.sources.linkedin.jobs_merge."""

import sys

import retrieval.sources.linkedin.jobs_merge as _impl

sys.modules[__name__] = _impl
