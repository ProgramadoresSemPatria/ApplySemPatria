"""Backward-compatible alias for retrieval.sources.boards.collectors.wellfound."""
import sys
import retrieval.sources.boards.collectors.wellfound as _impl
sys.modules[__name__] = _impl
