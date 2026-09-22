"""Backward-compatible module alias for retrieval.shared.browser.human_pacing."""

import sys

import retrieval.shared.browser.human_pacing as _impl

sys.modules[__name__] = _impl

