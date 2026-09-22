"""Backward-compatible module alias for retrieval.apply.integrations.browser.dm_chat."""

import sys

import retrieval.apply.integrations.browser.dm_chat as _impl

sys.modules[__name__] = _impl

if __name__ == "__main__":
    raise SystemExit(_impl.main())

