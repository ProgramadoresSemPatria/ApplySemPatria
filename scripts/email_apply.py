"""Backward-compatible module alias for retrieval.apply.pipelines.email_apply."""

import sys

import retrieval.apply.pipelines.email_apply as _impl

sys.modules[__name__] = _impl

if __name__ == "__main__":
    raise SystemExit(_impl.main())

