"""Backward-compatible module alias for retrieval.apply.tools.dm_recheck."""

import sys

import retrieval.apply.tools.dm_recheck as _impl

sys.modules[__name__] = _impl

if __name__ == "__main__":
    raise SystemExit(_impl.main())

