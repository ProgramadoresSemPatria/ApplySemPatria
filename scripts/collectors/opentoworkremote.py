"""Backward-compatible alias for retrieval.sources.boards.collectors.opentoworkremote."""
import sys
import retrieval.sources.boards.collectors.opentoworkremote as _impl
sys.modules[__name__] = _impl
