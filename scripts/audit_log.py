"""Backward-compatible module alias for retrieval.shared.audit_log."""

import sys

import retrieval.shared.audit_log as _impl

sys.modules[__name__] = _impl

if __name__ == "__main__":
    raise SystemExit(_impl.main())

