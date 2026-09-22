"""Backward-compatible module alias for retrieval.apply.state.applied_state."""

import sys

import retrieval.apply.state.applied_state as _impl

sys.modules[__name__] = _impl

