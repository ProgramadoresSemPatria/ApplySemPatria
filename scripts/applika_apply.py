"""Backward-compatible module alias for retrieval.apply.integrations.applika.apply."""

import sys

import retrieval.apply.integrations.applika.apply as _impl

sys.modules[__name__] = _impl

