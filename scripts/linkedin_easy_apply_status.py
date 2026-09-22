"""Backward-compatible module alias for retrieval.apply.pipelines.linkedin_easy_apply_status."""

import sys

import retrieval.apply.pipelines.linkedin_easy_apply_status as _impl

sys.modules[__name__] = _impl

if __name__ == "__main__":
    raise SystemExit(_impl.main())

