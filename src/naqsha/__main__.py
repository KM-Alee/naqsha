"""Allow ``python -m naqsha`` as an alias for the ``naqsha`` console script."""

from __future__ import annotations

from naqsha.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
