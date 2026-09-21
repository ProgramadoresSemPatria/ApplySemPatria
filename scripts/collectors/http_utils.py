"""Backward-compatible alias for retrieval.sources.boards.collectors.http_utils."""
import sys
import retrieval.sources.boards.collectors.http_utils as _impl
sys.modules[__name__] = _impl
