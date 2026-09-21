"""Backward-compatible alias for retrieval.sources.boards.collectors.himalayas."""
import sys
import retrieval.sources.boards.collectors.himalayas as _impl
sys.modules[__name__] = _impl
