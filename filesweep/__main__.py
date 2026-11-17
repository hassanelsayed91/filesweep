"""Entry point so ``python -m filesweep`` works without installing anything."""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
