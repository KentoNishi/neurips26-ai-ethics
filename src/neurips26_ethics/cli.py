"""CLI for the NeurIPS 2026 ethics pipeline."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from .env_utils import load_dotenv
from .pipeline import EthicsPipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the ICLR ethics scraping and paper-matching pipeline.")
    parser.add_argument(
        "--data-dir",
        default="data/papers",
        help="Directory for raw and processed outputs.",
    )
    parser.add_argument(
        "--years",
        nargs="+",
        type=int,
        default=[2021, 2022, 2023, 2024, 2025, 2026],
        help="ICLR years to process.",
    )
    parser.add_argument(
        "--top-k-matches",
        type=int,
        default=10,
        help="Number of candidate successor papers to retain per source paper.",
    )
    parser.add_argument(
        "--skip-pdf-downloads",
        action="store_true",
        help="Do not download OpenReview PDFs for ethics-flagged papers.",
    )
    parser.add_argument(
        "--refresh-openreview",
        action="store_true",
        help="Ignore cached OpenReview harvest files and fetch again.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    load_dotenv(Path(".env"))
    parser = build_parser()
    args = parser.parse_args(argv)

    pipeline = EthicsPipeline(data_dir=Path(args.data_dir))
    summary = pipeline.run(
        years=args.years,
        top_k_matches=args.top_k_matches,
        download_source_pdfs=not args.skip_pdf_downloads,
        reuse_openreview_cache=not args.refresh_openreview,
    )
    print("Pipeline complete.")
    print(f"Data directory: {Path(args.data_dir).resolve()}")
    print(f"Submissions: {summary['total_submissions']}")
    print(f"Ethics-flagged papers: {summary['ethics_flagged_papers']}")
    print(f"Candidate match rows: {summary['candidate_match_rows']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
