"""Backward-compatible module alias for retrieval.apply.pipelines.dm_apply."""

import sys

import retrieval.apply.pipelines.dm_apply as _impl

sys.modules[__name__] = _impl

if __name__ == "__main__":
    raise SystemExit(_impl.main())

