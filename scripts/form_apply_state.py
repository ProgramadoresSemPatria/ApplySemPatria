"""Backward-compatible module alias for retrieval.apply.state.form_apply_state."""

import sys

import retrieval.apply.state.form_apply_state as _impl

sys.modules[__name__] = _impl

