"""Backward-compatible module alias for retrieval.apply.pipelines.flow_runner."""

import sys

import retrieval.apply.pipelines.flow_runner as _impl

sys.modules[__name__] = _impl

if __name__ == "__main__":
    raise SystemExit(_impl.main())

