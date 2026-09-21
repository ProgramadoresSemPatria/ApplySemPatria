"""Backward-compatible module alias for retrieval.sources.linkedin.copy_link."""

import sys

import retrieval.sources.linkedin.copy_link as _impl

sys.modules[__name__] = _impl
