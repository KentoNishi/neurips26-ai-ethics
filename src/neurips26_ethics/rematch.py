"""Repeat OpenAlex searches for missing, low-scoring, invalid, or uncertain matches."""

from __future__ import annotations

import ast
import csv
import io
import json
import os
import signal
from pathlib import Path
from typing import Optional

from .io_utils import ensure_dir, write_csv, write_json, write_jsonl
from .matching import OpenAlexMatcher


class TargetedRematcher:
    """Searches again for selected submissions up to a specified year."""

    def __init__(
        self,
        *,
        data_dir: Path,
        max_source_year: int = 2024,
        min_score: float = 0.65,
        top_k_matches: int = 10,
        limit: Optional[int] = None,
        min_request_interval: float = 1.0,
        per_source_timeout: int = 120,
    ) -> None:
        self.data_dir = data_dir
        self.processed_dir = self.data_dir / "processed"
        self.reports_dir = ensure_dir(self.data_dir / "reports")
        self.cache_dir = ensure_dir(self.data_dir / "cache" / "openalex")
        self.state_path = self.reports_dir / "targeted_rematch_state.json"
        self.max_source_year = max_source_year
        self.min_score = min_score
        self.top_k_matches = top_k_matches
        self.limit = limit
        self.per_source_timeout = per_source_timeout
        self.matcher = OpenAlexMatcher(
            cache_dir=self.cache_dir,
            mailto=os.getenv("OPENALEX_MAILTO", ""),
            api_key=os.getenv("OPENALEX_API_KEY", ""),
            min_request_interval=min_request_interval,
            max_retries=6,
        )

    def run(self) -> dict:
        sources = self._load_csv(self.processed_dir / "ethics_rejected_or_withdrawn_papers.csv")
        candidate_rows = self._load_csv(self.processed_dir / "paper_match_candidates.csv")
        best_matches = self._load_csv(self.processed_dir / "paper_best_matches.csv")
        pair_codes = self._load_optional_csv(self.data_dir / "analysis" / "pair_codes.csv")

        best_by_submission = {row["source_submission_id"]: row for row in best_matches}
        pair_codes_by_submission = {row["source_submission_id"]: row for row in pair_codes}
        target_sources = self._select_targets(sources, best_by_submission, pair_codes_by_submission)

        existing_candidates_by_submission: dict[str, list[dict[str, str]]] = {}
        for row in candidate_rows:
            existing_candidates_by_submission.setdefault(row["source_submission_id"], []).append(row)

        replacement_rows: dict[str, list[dict]] = {}
        outcomes = {
            "selected_targets": len(target_sources),
            "attempted_targets": 0,
            "added_matches": 0,
            "improved_matches": 0,
            "same_match_refreshed": 0,
            "preserved_existing_matches": 0,
            "still_unmatched": 0,
            "errors": 0,
        }
        completed_ids: set[str] = set()
        saved_state = self._load_state()
        if saved_state:
            replacement_rows = saved_state.get("replacement_rows", {})
            outcomes.update(saved_state.get("outcomes", {}))
            completed_ids = set(saved_state.get("completed_ids", []))

        for index, source in enumerate(target_sources, start=1):
            submission_id = source["submission_id"]
            if submission_id in completed_ids:
                continue
            existing_best = best_by_submission.get(submission_id)
            try:
                matches = self._find_matches_with_timeout(self._paper_from_source(source))
            except Exception:
                outcomes["errors"] += 1
                self.matcher._reset_session()
                replacement_rows[submission_id] = existing_candidates_by_submission.get(submission_id, [])
                completed_ids.add(submission_id)
                self._write_state(replacement_rows, outcomes, completed_ids)
                continue

            outcomes["attempted_targets"] += 1
            chosen_rows = self._choose_rows(matches, existing_best, existing_candidates_by_submission.get(submission_id, []))
            replacement_rows[submission_id] = chosen_rows
            completed_ids.add(submission_id)

            if not chosen_rows or not chosen_rows[0].get("candidate_id"):
                outcomes["still_unmatched"] += 1
            elif not existing_best:
                outcomes["added_matches"] += 1
            elif chosen_rows[0]["candidate_id"] != existing_best["candidate_id"]:
                outcomes["improved_matches"] += 1
            elif chosen_rows[0]["candidate_id"] == existing_best["candidate_id"]:
                outcomes["same_match_refreshed"] += 1
            else:
                outcomes["preserved_existing_matches"] += 1

            self._write_state(replacement_rows, outcomes, completed_ids)
            if index % 25 == 0:
                print(
                    f"[rematch] {len(completed_ids)}/{len(target_sources)} targets processed "
                    f"(added={outcomes['added_matches']} improved={outcomes['improved_matches']})"
                )

        merged_candidates = self._merge_candidate_rows(candidate_rows, replacement_rows)
        merged_best_matches = self._best_matches(merged_candidates)

        report = {
            "max_source_year": self.max_source_year,
            "min_score": self.min_score,
            "top_k_matches": self.top_k_matches,
            **outcomes,
            "final_best_match_rows": len(merged_best_matches),
            "final_candidate_rows": len(merged_candidates),
        }

        write_csv(self.processed_dir / "paper_match_candidates.csv", merged_candidates)
        write_csv(self.processed_dir / "paper_best_matches.csv", merged_best_matches)
        write_jsonl(self.processed_dir / "paper_best_matches.jsonl", merged_best_matches)
        write_json(self.reports_dir / "targeted_rematch_summary.json", report)
        self._clear_state()
        return report

    def _find_matches_with_timeout(self, paper: dict) -> list[dict]:
        previous_handler = signal.getsignal(signal.SIGALRM)

        def _raise_timeout(_signum, _frame) -> None:
            raise TimeoutError(f"Timed out while rematching {paper['submission_id']}")

        signal.signal(signal.SIGALRM, _raise_timeout)
        signal.alarm(self.per_source_timeout)
        try:
            return self.matcher.find_matches(paper, top_k=self.top_k_matches)
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, previous_handler)

    def _select_targets(
        self,
        sources: list[dict[str, str]],
        best_by_submission: dict[str, dict[str, str]],
        pair_codes_by_submission: dict[str, dict[str, str]],
    ) -> list[dict[str, str]]:
        targets: list[tuple[tuple[int, int, str], dict[str, str]]] = []
        for source in sources:
            year = int(source["year"])
            if year > self.max_source_year:
                continue
            submission_id = source["submission_id"]
            best = best_by_submission.get(submission_id)
            pair_code = pair_codes_by_submission.get(submission_id)
            reason_rank = self._target_reason_rank(best, pair_code)
            if reason_rank is None:
                continue
            priority = (reason_rank, year, submission_id)
            targets.append((priority, source))

        targets.sort(key=lambda item: item[0])
        selected = [source for _priority, source in targets]
        if self.limit is not None:
            selected = selected[: self.limit]
        return selected

    def _target_reason_rank(
        self,
        best: Optional[dict[str, str]],
        pair_code: Optional[dict[str, str]],
    ) -> Optional[int]:
        if best is None:
            return 0
        score = float(best.get("score") or 0.0)
        if score < self.min_score:
            return 1
        if pair_code and pair_code.get("pair_validity") in {"invalid", "uncertain"}:
            return 2
        return None

    def _paper_from_source(self, source: dict[str, str]) -> dict:
        return {
            "submission_id": source["submission_id"],
            "forum_id": source["forum_id"],
            "year": int(source["year"]),
            "title": source["title"],
            "abstract": source.get("abstract", ""),
            "authors": self._parse_json_list(source.get("authors", "")),
            "decision": source.get("decision", ""),
            "ethics_flagged": source.get("ethics_flagged") in {"True", "true", True},
            "ethics_linked_rejection": source.get("ethics_linked_rejection") in {"True", "true", True},
        }

    def _choose_rows(
        self,
        matches: list[dict],
        existing_best: Optional[dict[str, str]],
        existing_rows: list[dict[str, str]],
    ) -> list[dict]:
        if not matches:
            if existing_rows:
                return existing_rows
            return []

        new_best = matches[0]
        if existing_best is None:
            return matches

        old_score = float(existing_best.get("score") or 0.0)
        if new_best["candidate_id"] == existing_best.get("candidate_id"):
            return matches
        if float(new_best["score"]) > old_score:
            return matches
        return existing_rows

    def _merge_candidate_rows(
        self,
        candidate_rows: list[dict[str, str]],
        replacement_rows: dict[str, list[dict]],
    ) -> list[dict]:
        merged: list[dict] = []
        replaced = set(replacement_rows)
        seen = set()
        for row in candidate_rows:
            submission_id = row["source_submission_id"]
            if submission_id in replaced:
                if submission_id not in seen:
                    merged.extend(replacement_rows[submission_id])
                    seen.add(submission_id)
                continue
            merged.append(row)
        for submission_id, rows in replacement_rows.items():
            if submission_id not in seen and rows:
                merged.extend(rows)
        return merged

    def _best_matches(self, candidate_rows: list[dict]) -> list[dict]:
        best_by_submission: dict[str, dict] = {}
        for row in candidate_rows:
            current = best_by_submission.get(row["source_submission_id"])
            score = row.get("score")
            if score in {"", None}:
                continue
            score_value = float(score)
            current_score = float(current["score"]) if current is not None else float("-inf")
            if current is None or score_value > current_score:
                best_by_submission[row["source_submission_id"]] = row
        return sorted(best_by_submission.values(), key=lambda row: (int(row["source_year"]), -float(row["score"])))

    def _load_optional_csv(self, path: Path) -> list[dict[str, str]]:
        if not path.exists():
            return []
        return self._load_csv(path)

    def _load_csv(self, path: Path) -> list[dict[str, str]]:
        text = path.read_text(encoding="utf-8", errors="replace").replace("\x00", "")
        return list(csv.DictReader(io.StringIO(text)))

    def _parse_json_list(self, raw: str) -> list[str]:
        if not raw:
            return []
        try:
            value = ast.literal_eval(raw)
        except (SyntaxError, ValueError):
            return []
        return value if isinstance(value, list) else []

    def _load_state(self) -> dict | None:
        if not self.state_path.exists():
            return None
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None

    def _write_state(self, replacement_rows: dict[str, list[dict]], outcomes: dict, completed_ids: set[str]) -> None:
        write_json(
            self.state_path,
            {
                "replacement_rows": replacement_rows,
                "outcomes": outcomes,
                "completed_ids": sorted(completed_ids),
            },
        )

    def _clear_state(self) -> None:
        try:
            self.state_path.unlink()
        except FileNotFoundError:
            return
