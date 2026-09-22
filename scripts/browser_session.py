"""Backward-compatible module alias for retrieval.shared.browser.session."""

import sys

import retrieval.shared.browser.session as _impl

sys.modules[__name__] = _impl

