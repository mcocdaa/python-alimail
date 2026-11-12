"""Allow ``python -m alimail`` to behave like the ``alimail`` console script."""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
