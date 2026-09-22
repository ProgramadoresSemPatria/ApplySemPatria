"""Backward-compatible module alias for retrieval.shared.browser.linkedin_ui."""

import sys

import retrieval.shared.browser.linkedin_ui as _impl

sys.modules[__name__] = _impl

