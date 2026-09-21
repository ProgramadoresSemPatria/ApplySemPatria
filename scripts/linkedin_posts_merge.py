"""Backward-compatible module alias for retrieval.sources.linkedin.posts_merge."""

import sys

import retrieval.sources.linkedin.posts_merge as _impl

sys.modules[__name__] = _impl
