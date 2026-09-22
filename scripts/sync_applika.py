"""Backward-compatible module alias for retrieval.apply.integrations.applika.sync."""

import sys

import retrieval.apply.integrations.applika.sync as _impl

sys.modules[__name__] = _impl

if __name__ == "__main__":
    raise SystemExit(_impl.main())

