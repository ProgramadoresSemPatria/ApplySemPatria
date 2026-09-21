"""Backward-compatible module alias for retrieval.pipeline.daily."""

import sys

import retrieval.pipeline.daily as _impl

sys.modules[__name__] = _impl

if __name__ == "__main__":
    raise SystemExit(_impl.main())
