"""Backward-compatible alias for retrieval.sources.boards.collectors.remoteok."""
import sys
import retrieval.sources.boards.collectors.remoteok as _impl
sys.modules[__name__] = _impl
