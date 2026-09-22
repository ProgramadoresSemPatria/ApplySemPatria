"""Backward-compatible module alias for retrieval.apply.state.dm_state."""

import sys

import retrieval.apply.state.dm_state as _impl

sys.modules[__name__] = _impl

