"""End-to-end OpenReview scraping and successor-paper matching pipeline."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

from .io_utils import ensure_dir, write_csv, write_json, write_jsonl
from .matching import OpenAlexMatcher
from .openreview import OpenReviewClient, YEAR_CONFIGS, load_harvest_cache, normalize_submission, write_harvest_cache


class EthicsPipeline:
    """Runs harvesting, normalization, and candidate matching."""

    def __init__(
        self,
        *,
        data_dir: Path,
        openreview_client: OpenReviewClient | None = None,
        matcher: OpenAlexMatcher | None = None,
    ) -> None:
        self.data_dir = data_dir
        self.raw_dir = ensure_dir(self.data_dir / "raw")
        self.processed_dir = ensure_dir(self.data_dir / "processed")
        self.reports_dir = ensure_dir(self.data_dir / "reports")
        self.pdf_dir = ensure_dir(self.data_dir / "pdfs" / "openreview")
        self.cache_dir = ensure_dir(self.data_dir / "cache")

        self.openreview_client = openreview_client or OpenReviewClient()
        self.matcher = matcher or OpenAlexMatcher(
            cache_dir=self.cache_dir / "openalex",
            mailto=os.getenv("OPENALEX_MAILTO", ""),
            api_key=os.getenv("OPENALEX_API_KEY", ""),
        )

    def run(
        self,
        *,
        years: Iterable[int],
        top_k_matches: int = 10,
        download_source_pdfs: bool = True,
        reuse_openreview_cache: bool = True,
    ) -> dict:
        all_submissions: list[dict] = []
        all_reviews: list[dict] = []
        yearly_summaries: list[dict] = []

        for year in years:
            raw_cache_path = self.raw_dir / "openreview" / f"{year}_submissions.jsonl"
            if reuse_openreview_cache and raw_cache_path.exists():
                raw_notes = load_harvest_cache(raw_cache_path)
                submissions = []
                reviews = []
                for note in raw_notes:
                    submission, normalized_reviews = normalize_submission(
                        note,
                        year=year,
                        supports_public_ethics_flags=YEAR_CONFIGS[year].supports_public_ethics_flags,
                    )
                    submissions.append(submission)
                    reviews.extend(normalized_reviews)
                summary = self._summarize_year(year, submissions)
            else:
                submissions, reviews, raw_notes, summary = self.openreview_client.harvest_year(year)
                write_harvest_cache(raw_cache_path, raw_notes)
            all_submissions.extend(submissions)
            all_reviews.extend(reviews)
            yearly_summaries.append(summary)

        ethics_flagged = [row for row in all_submissions if row["ethics_flagged"]]
        ethics_rejected_or_withdrawn = [
            row
            for row in ethics_flagged
            if row["withdrawn"] or row["decision"].lower().startswith("reject") or not row["decision"]
        ]

        if download_source_pdfs:
            self._download_source_pdfs(ethics_flagged)

        candidate_rows = self._match_papers(ethics_rejected_or_withdrawn, top_k=top_k_matches)
        best_matches = self._best_matches(candidate_rows)

        summary = {
            "years": list(years),
            "yearly": yearly_summaries,
            "total_submissions": len(all_submissions),
            "total_reviews": len(all_reviews),
            "ethics_flagged_papers": len(ethics_flagged),
            "ethics_rejected_or_withdrawn_papers": len(ethics_rejected_or_withdrawn),
            "matched_papers": len({row["source_submission_id"] for row in candidate_rows}),
            "candidate_match_rows": len(candidate_rows),
            "public_ethics_flag_supported_years": [
                year for year in years if YEAR_CONFIGS[year].supports_public_ethics_flags
            ],
            "public_ethics_flag_unsupported_years": [
                year for year in years if not YEAR_CONFIGS[year].supports_public_ethics_flags
            ],
        }

        write_json(self.reports_dir / "pipeline_summary.json", summary)
        write_json(self.reports_dir / "yearly_summary.json", yearly_summaries)
        write_csv(self.processed_dir / "iclr_submissions.csv", all_submissions)
        write_csv(self.processed_dir / "iclr_reviews.csv", all_reviews)
        write_csv(self.processed_dir / "ethics_flagged_papers.csv", ethics_flagged)
        write_csv(self.processed_dir / "ethics_rejected_or_withdrawn_papers.csv", ethics_rejected_or_withdrawn)
        write_csv(self.processed_dir / "paper_match_candidates.csv", candidate_rows)
        write_csv(self.processed_dir / "paper_best_matches.csv", best_matches)
        write_jsonl(self.processed_dir / "paper_best_matches.jsonl", best_matches)
        return summary

    def _summarize_year(self, year: int, submissions: list[dict]) -> dict:
        summary = {
            "year": year,
            "supports_public_ethics_flags": YEAR_CONFIGS[year].supports_public_ethics_flags,
            "submission_count": len(submissions),
            "flagged_paper_count": 0,
            "flagged_reject_count": 0,
            "flagged_accept_count": 0,
            "flagged_withdrawn_count": 0,
            "flagged_unknown_decision_count": 0,
        }
        for row in submissions:
            if row["ethics_flagged"]:
                summary["flagged_paper_count"] += 1
                if row["withdrawn"]:
                    summary["flagged_withdrawn_count"] += 1
                elif row["decision"] and row["decision"].lower().startswith("reject"):
                    summary["flagged_reject_count"] += 1
                elif row["decision"] and ("accept" in row["decision"].lower()):
                    summary["flagged_accept_count"] += 1
                else:
                    summary["flagged_unknown_decision_count"] += 1
        return summary

    def _download_source_pdfs(self, papers: list[dict]) -> None:
        for paper in papers:
            pdf_url = paper.get("pdf_url")
            if not pdf_url:
                continue
            destination = self.pdf_dir / str(paper["year"]) / f"{paper['paper_number']}.pdf"
            if destination.exists():
                continue
            try:
                self.openreview_client.download_pdf(pdf_url, destination)
            except Exception:
                continue

    def _match_papers(self, papers: list[dict], *, top_k: int) -> list[dict]:
        rows: list[dict] = []
        for paper in papers:
            try:
                matches = self.matcher.find_matches(paper, top_k=top_k)
            except Exception as exc:
                matches = []
                error_message = str(exc)
            else:
                error_message = ""
            if not matches:
                rows.append(
                    {
                        "source_submission_id": paper["submission_id"],
                        "source_forum_id": paper["forum_id"],
                        "source_year": paper["year"],
                        "source_title": paper["title"],
                        "source_decision": paper.get("decision", ""),
                        "source_ethics_flagged": paper.get("ethics_flagged", False),
                        "source_ethics_linked_rejection": paper.get("ethics_linked_rejection", False),
                        "candidate_id": "",
                        "candidate_title": "",
                        "candidate_doi": "",
                        "candidate_publication_year": "",
                        "candidate_publication_date": "",
                        "candidate_type": "",
                        "candidate_authors": [],
                        "candidate_source": "",
                        "candidate_pdf_url": "",
                        "matched_query": "",
                        "score": "",
                        "title_similarity": "",
                        "title_token_overlap": "",
                        "author_overlap": "",
                        "abstract_overlap": "",
                        "year_bonus": "",
                        "shared_author_count": "",
                        "shared_title_terms": "",
                        "author_bonus": "",
                        "title_bonus": "",
                        "mismatch_penalty": "",
                        "rank": "",
                        "match_error": error_message,
                    }
                )
                continue
            rows.extend(matches)
        return rows

    def _best_matches(self, candidate_rows: list[dict]) -> list[dict]:
        best_by_submission: dict[str, dict] = {}
        for row in candidate_rows:
            current = best_by_submission.get(row["source_submission_id"])
            score = row.get("score")
            if score == "":
                continue
            if current is None or row["score"] > current["score"]:
                best_by_submission[row["source_submission_id"]] = row
        return sorted(best_by_submission.values(), key=lambda row: (row["source_year"], -row["score"]))
