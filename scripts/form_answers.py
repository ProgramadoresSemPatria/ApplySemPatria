"""Backward-compatible module alias for retrieval.apply.domain.form_answers."""

import sys

import retrieval.apply.domain.form_answers as _impl

sys.modules[__name__] = _impl

