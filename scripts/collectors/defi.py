"""Backward-compatible alias for retrieval.sources.boards.collectors.defi."""
import sys
import retrieval.sources.boards.collectors.defi as _impl
sys.modules[__name__] = _impl
