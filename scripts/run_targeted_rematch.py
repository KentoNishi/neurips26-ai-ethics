#!/usr/bin/env python3
"""Repeat paper searches for missing, low-scoring, invalid, or uncertain matches."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from neurips26_ethics.env_utils import load_dotenv
from neurips26_ethics.rematch import TargetedRematcher


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Repeat OpenAlex searches for missing, low-scoring, invalid, or uncertain paper matches."
    )
    parser.add_argument("--data-dir", default="data/papers")
    parser.add_argument("--max-source-year", type=int, default=2024)
    parser.add_argument("--min-score", type=float, default=0.65)
    parser.add_argument("--top-k-matches", type=int, default=10)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--min-request-interval", type=float, default=1.0)
    parser.add_argument("--per-source-timeout", type=int, default=120)
    return parser


def main() -> int:
    load_dotenv(Path(".env"))
    args = build_parser().parse_args()

    rematcher = TargetedRematcher(
        data_dir=Path(args.data_dir),
        max_source_year=args.max_source_year,
        min_score=args.min_score,
        top_k_matches=args.top_k_matches,
        limit=args.limit,
        min_request_interval=args.min_request_interval,
        per_source_timeout=args.per_source_timeout,
    )
    summary = rematcher.run()
    print("Targeted rematch complete.")
    print(f"Selected targets: {summary['selected_targets']}")
    print(f"Added matches: {summary['added_matches']}")
    print(f"Improved matches: {summary['improved_matches']}")
    print(f"Final best-match rows: {summary['final_best_match_rows']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
