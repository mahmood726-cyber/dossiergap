"""DossierGap CLI entry — `python -m dossiergap ...`."""
from __future__ import annotations

import argparse
import sys


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dossiergap",
        description="FDA/EMA dossier pivotal-trial extraction and audit.",
    )
    sub = parser.add_subparsers(dest="command")

    extract = sub.add_parser("extract", help="Extract trials from FDA/EMA dossiers (Task 12)")
    extract.add_argument("--corpus", required=True, help="Path to cardiology-nme-corpus.json")
    extract.add_argument("--out", required=True, help="Output CSV path")
    extract.add_argument("--limit", type=int, default=None, help="Smoke-test: first N NMEs")
    extract.add_argument("--continue-on-error", action="store_true")

    sub.add_parser("preflight", help="Run Task 0 prereq gate")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    if args.command == "preflight":
        from pathlib import Path
        scripts_dir = Path(__file__).resolve().parents[2] / "scripts"
        sys.path.insert(0, str(scripts_dir))
        import preflight
        return preflight.main()

    if args.command == "extract":
        print("extract: not yet implemented (Task 12)", file=sys.stderr)
        return 2

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
