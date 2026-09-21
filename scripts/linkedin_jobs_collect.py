"""Backward-compatible module alias for retrieval.sources.linkedin.jobs_collect."""

import sys

import retrieval.sources.linkedin.jobs_collect as _impl

sys.modules[__name__] = _impl

if __name__ == "__main__":
    raise SystemExit(_impl.main())
