"""Backward-compatible module alias for retrieval.apply.domain.application_channel."""

import sys

import retrieval.apply.domain.application_channel as _impl

sys.modules[__name__] = _impl

