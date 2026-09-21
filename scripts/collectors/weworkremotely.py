"""Backward-compatible alias for retrieval.sources.boards.collectors.weworkremotely."""
import sys
import retrieval.sources.boards.collectors.weworkremotely as _impl
sys.modules[__name__] = _impl
