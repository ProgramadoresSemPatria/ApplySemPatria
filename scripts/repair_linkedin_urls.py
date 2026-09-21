#!/usr/bin/env python3
"""Backward-compatible module alias for retrieval.sources.linkedin.repair_urls."""

import sys

import retrieval.sources.linkedin.repair_urls as _impl

sys.modules[__name__] = _impl

if __name__ == "__main__":
    raise SystemExit(_impl.main())
