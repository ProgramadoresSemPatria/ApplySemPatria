"""Backward-compatible alias for retrieval.sources.boards.collectors.f6s."""
import sys
import retrieval.sources.boards.collectors.f6s as _impl
sys.modules[__name__] = _impl
