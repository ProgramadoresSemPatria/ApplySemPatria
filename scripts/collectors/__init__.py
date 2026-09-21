"""Backward-compatible module alias for retrieval.sources.boards.collectors."""

import sys

import retrieval.sources.boards.collectors as _impl

sys.modules[__name__] = _impl
