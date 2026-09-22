"""Backward-compatible module alias for retrieval.apply.pipelines.dm_followup."""

import sys

import retrieval.apply.pipelines.dm_followup as _impl

sys.modules[__name__] = _impl

if __name__ == "__main__":
    raise SystemExit(_impl.main())

