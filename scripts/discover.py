#!/usr/bin/env python3
"""Backward-compatible module alias for retrieval.sources.boards.discover."""

import sys

import retrieval.sources.boards.discover as _impl

sys.modules[__name__] = _impl

if __name__ == "__main__":
    raise SystemExit(_impl.main())
