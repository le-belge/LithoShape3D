"""Point d'entree headless. Ne depend que de `core` (pas de Qt, pas de PyVista)."""

from __future__ import annotations

import argparse

from lithoshape3d import __version__


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="lithoshape3d")
    parser.add_argument("--version", action="version", version=f"lithoshape3d {__version__}")
    try:
        parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or 0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
