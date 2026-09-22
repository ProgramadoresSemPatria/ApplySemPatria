"""Backward-compatible module alias for retrieval.apply.domain.apply_email."""

import sys

import retrieval.apply.domain.apply_email as _impl

sys.modules[__name__] = _impl

