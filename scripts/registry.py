"""Backward-compatible module alias for retrieval.registry.store."""

import sys

import retrieval.registry.store as _impl

sys.modules[__name__] = _impl
