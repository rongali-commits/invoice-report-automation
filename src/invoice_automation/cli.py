from __future__ import annotations

import argparse
from pathlib import Path

from .pipeline import run_automation


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate billing CSV data and generate invoice-ready outputs."
    )
    parser.add_argument("input", type=Path, help="Input CSV file")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("output"),
        help="New or empty output directory (default: output)",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        result = run_automation(args.input, args.output)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(
        f"Processed {result.rows_read} rows: {result.ready_rows} ready, "
        f"{result.flagged_rows} flagged, total {result.currency} {result.clean_total:,.2f}."
    )
    print(f"Outputs: {result.output_directory.resolve()}")


if __name__ == "__main__":
    main()

