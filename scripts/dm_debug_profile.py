"""Backward-compatible module alias for retrieval.apply.tools.dm_debug_profile."""

import sys

import retrieval.apply.tools.dm_debug_profile as _impl

sys.modules[__name__] = _impl

if __name__ == "__main__":
    raise SystemExit(_impl.main())

