"""Backward-compatible CLI entry point.

Copyright and license: GNU GPL-3.0, based on
EinzbernLi/Glados-Railgun-checkin.
"""

from src.main import main


if __name__ == "__main__":
    raise SystemExit(main())
