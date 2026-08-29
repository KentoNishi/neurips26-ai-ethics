"""Candidate paper matching using OpenAlex."""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Iterable, Optional

import requests

from .text_utils import collapse_whitespace, important_terms, jaccard, normalize_author, title_similarity


class OpenAlexMatcher:
    """Searches OpenAlex for likely successor papers and ranks candidates."""

    base_url = "https://api.openalex.org/works"

    def __init__(
        self,
        *,
        session: Optional[requests.Session] = None,
        timeout: float = 45.0,
        min_request_interval: float = 0.75,
        user_agent: str = "neurips26-ethics/0.1 (OpenAlex matcher)",
        mailto: str = "",
        api_key: str = "",
        cache_dir: Optional[Path] = None,
        max_retries: int = 4,
    ) -> None:
        self.session = session or requests.Session()
        self.user_agent = user_agent
        self.session.headers["User-Agent"] = self.user_agent
        self.session.headers["Connection"] = "close"
        self.timeout = timeout
        self.min_request_interval = min_request_interval
        self.mailto = mailto
        self.api_key = api_key
        self.cache_dir = cache_dir
        self.max_retries = max_retries
        self.offline = os.getenv("OPENALEX_OFFLINE", "").lower() in {"1", "true", "yes"}
        self._last_request_ts = 0.0

    def find_matches(self, paper: dict, *, top_k: int = 10, max_results_per_query: int = 12) -> list[dict]:
        queries = build_queries(
            paper["title"],
            paper.get("authors", []),
            abstract=paper.get("abstract", ""),
        )
        scored: dict[str, dict] = {}

        for query in queries:
            for candidate in self.search(query, year=paper["year"], per_page=max_results_per_query):
                match = score_candidate(paper, candidate, matched_query=query)
                current = scored.get(candidate["id"])
                if current is None or match["score"] > current["score"]:
                    scored[candidate["id"]] = match
            if should_stop_querying(scored.values()):
                break

        ranked = sorted(scored.values(), key=lambda row: row["score"], reverse=True)
        for rank, row in enumerate(ranked[:top_k], start=1):
            row["rank"] = rank
        return ranked[:top_k]

    def search(self, query: str, *, year: int, per_page: int) -> list[dict]:
        params = {
            "search": query,
            "per-page": per_page,
            "filter": f"from_publication_date:{year-1}-01-01,to_publication_date:{year+5}-12-31",
        }
        if self.mailto:
            params["mailto"] = self.mailto
        if self.api_key:
            params["api_key"] = self.api_key

        cache_path = self._cache_path(query, year)
        if cache_path and cache_path.exists():
            data = json.loads(cache_path.read_text(encoding="utf-8"))
        else:
            if self.offline:
                return []
            data = self._fetch(params)
            if cache_path:
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                cache_path.write_text(json.dumps(data, ensure_ascii=True), encoding="utf-8")
        return [normalize_openalex_work(work) for work in data.get("results", [])]

    def _cache_path(self, query: str, year: int) -> Optional[Path]:
        if not self.cache_dir:
            return None
        digest = hashlib.sha1(f"{year}:{query}".encode("utf-8")).hexdigest()
        return self.cache_dir / f"{digest}.json"

    def _fetch(self, params: dict) -> dict:
        delay = self.min_request_interval
        response = None
        for _ in range(self.max_retries):
            elapsed = time.monotonic() - self._last_request_ts
            wait_time = self.min_request_interval - elapsed
            if wait_time > 0:
                time.sleep(wait_time)
            try:
                response = self.session.get(self.base_url, params=params, timeout=self.timeout)
                self._last_request_ts = time.monotonic()
            except requests.RequestException:
                self._last_request_ts = time.monotonic()
                self._reset_session()
                time.sleep(delay)
                delay = min(delay * 2, 15.0)
                continue
            if response.status_code not in {429, 500, 502, 503, 504}:
                response.raise_for_status()
                return response.json()
            retry_after = response.headers.get("Retry-After")
            if retry_after and retry_after.isdigit():
                delay = max(delay, float(retry_after))
            time.sleep(delay)
            delay = min(delay * 2, 15.0)
        if response is None:
            return {"results": []}
        if response.status_code in {429, 500, 502, 503, 504}:
            return {"results": []}
        response.raise_for_status()
        return {"results": []}

    def _reset_session(self) -> None:
        self.session.close()
        self.session = requests.Session()
        self.session.headers["User-Agent"] = self.user_agent
        self.session.headers["Connection"] = "close"


def build_queries(title: str, authors: list[str], *, abstract: str = "") -> list[str]:
    important = important_terms(title, limit=10)
    abstract_terms = important_terms(abstract, limit=10)
    surnames = [normalize_author(author) for author in authors if normalize_author(author)]
    title_parts = split_title_variants(title)

    queries = [collapse_whitespace(title)]
    queries.extend(title_parts)

    if important:
        queries.append(" ".join(important[:6]))
        queries.append(" ".join(important[:4]))

    if surnames:
        queries.append(f"{title} {' '.join(surnames[:2])}")
        if important:
            queries.append(" ".join(important[:4] + surnames[:2]))
        queries.append(" ".join(surnames[:2]))
        if abstract_terms:
            queries.append(" ".join(abstract_terms[:5] + surnames[:2]))

    if len(surnames) >= 3 and important:
        queries.append(" ".join(important[:3] + surnames[:3]))

    if abstract_terms:
        queries.append(" ".join(abstract_terms[:6]))

    deduped: list[str] = []
    seen = set()
    for query in queries:
        query = collapse_whitespace(query)
        if len(query) < 3:
            continue
        key = query.lower()
        if key not in seen:
            deduped.append(query)
            seen.add(key)
    return deduped


def split_title_variants(title: str) -> list[str]:
    title = collapse_whitespace(title)
    variants: list[str] = []
    parts = [title]
    if ":" in title:
        parts = [collapse_whitespace(part) for part in re.split(r":\s+", title) if collapse_whitespace(part)]

    expanded_parts: list[str] = []
    for part in parts:
        expanded_parts.extend(
            collapse_whitespace(piece)
            for piece in re.split(r"\s[-–—]{1,2}\s", part)
            if collapse_whitespace(piece)
        )

    if len(expanded_parts) >= 2:
        variants.extend(expanded_parts)
        variants.append(" ".join(expanded_parts[:2]))
    return variants


def should_stop_querying(matches: Iterable[dict]) -> bool:
    ranked = sorted(matches, key=lambda row: row.get("score", 0.0), reverse=True)
    if not ranked:
        return False

    best = ranked[0]
    if best["score"] >= 0.92:
        return True
    if best["score"] >= 0.84 and best.get("shared_author_count", 0) >= 1:
        return True
    if len(ranked) >= 2:
        runner_up = ranked[1]
        if (
            best["score"] >= 0.78
            and best.get("shared_author_count", 0) >= 1
            and best["score"] - runner_up.get("score", 0.0) >= 0.12
        ):
            return True
    return False


def normalize_openalex_work(work: dict) -> dict:
    authors = [author.get("author", {}).get("display_name", "") for author in work.get("authorships", []) if author.get("author")]
    abstract_index = work.get("abstract_inverted_index") or {}
    return {
        "id": work.get("id", ""),
        "title": work.get("display_name", "") or "",
        "doi": work.get("doi", "") or "",
        "publication_year": work.get("publication_year"),
        "publication_date": work.get("publication_date", "") or "",
        "type": work.get("type", "") or "",
        "authors": [author for author in authors if author],
        "abstract": invert_abstract(abstract_index),
        "primary_location_source": (((work.get("primary_location") or {}).get("source") or {}).get("display_name")) or "",
        "pdf_url": extract_pdf_url(work),
    }


def extract_pdf_url(work: dict) -> str:
    best = work.get("best_oa_location") or {}
    if best.get("pdf_url"):
        return str(best["pdf_url"])
    primary = work.get("primary_location") or {}
    if primary.get("pdf_url"):
        return str(primary["pdf_url"])
    for location in work.get("locations") or []:
        if location.get("pdf_url"):
            return str(location["pdf_url"])
    return ""


def invert_abstract(index: dict) -> str:
    if not index:
        return ""
    positions: dict[int, str] = {}
    for token, indexes in index.items():
        for position in indexes:
            positions[int(position)] = token
    return " ".join(token for _, token in sorted(positions.items()))


def score_candidate(paper: dict, candidate: dict, *, matched_query: str) -> dict:
    paper_title_terms = set(important_terms(paper["title"], limit=16))
    candidate_title_terms = set(important_terms(candidate["title"], limit=16))
    paper_abstract_terms = set(important_terms(paper.get("abstract", ""), limit=20))
    candidate_abstract_terms = set(important_terms(candidate.get("abstract", ""), limit=20))
    paper_authors = {normalize_author(author) for author in paper.get("authors", []) if normalize_author(author)}
    candidate_authors = {normalize_author(author) for author in candidate.get("authors", []) if normalize_author(author)}

    sim_title = title_similarity(paper["title"], candidate["title"])
    overlap_title = jaccard(paper_title_terms, candidate_title_terms)
    overlap_abstract = jaccard(paper_abstract_terms, candidate_abstract_terms)
    overlap_authors = jaccard(paper_authors, candidate_authors)
    shared_author_count = len(paper_authors & candidate_authors)
    shared_title_terms = len(paper_title_terms & candidate_title_terms)

    year_bonus = 0.0
    candidate_year = candidate.get("publication_year")
    if candidate_year:
        if candidate_year in {paper["year"], paper["year"] + 1}:
            year_bonus = 0.05
        elif candidate_year < paper["year"] - 1:
            year_bonus = -0.10
        elif candidate_year > paper["year"] + 5:
            year_bonus = -0.05

    same_source_penalty = 0.0
    if candidate.get("primary_location_source", "").lower().startswith("iclr"):
        same_source_penalty = -0.05

    author_bonus = 0.0
    if shared_author_count >= 2:
        author_bonus += 0.08
    elif shared_author_count == 1:
        author_bonus += 0.03

    title_bonus = 0.0
    if shared_title_terms >= 5:
        title_bonus += 0.05
    elif shared_title_terms >= 3:
        title_bonus += 0.02

    mismatch_penalty = 0.0
    if shared_author_count == 0 and sim_title < 0.45 and overlap_abstract < 0.15:
        mismatch_penalty = -0.18

    score = (
        0.38 * sim_title
        + 0.14 * overlap_title
        + 0.24 * overlap_authors
        + 0.16 * overlap_abstract
        + year_bonus
        + author_bonus
        + title_bonus
        + same_source_penalty
        + mismatch_penalty
    )

    return {
        "source_submission_id": paper["submission_id"],
        "source_forum_id": paper["forum_id"],
        "source_year": paper["year"],
        "source_title": paper["title"],
        "source_decision": paper.get("decision", ""),
        "source_ethics_flagged": paper.get("ethics_flagged", False),
        "source_ethics_linked_rejection": paper.get("ethics_linked_rejection", False),
        "candidate_id": candidate["id"],
        "candidate_title": candidate["title"],
        "candidate_doi": candidate["doi"],
        "candidate_publication_year": candidate.get("publication_year"),
        "candidate_publication_date": candidate.get("publication_date", ""),
        "candidate_type": candidate.get("type", ""),
        "candidate_authors": candidate.get("authors", []),
        "candidate_source": candidate.get("primary_location_source", ""),
        "candidate_pdf_url": candidate.get("pdf_url", ""),
        "matched_query": matched_query,
        "score": round(score, 4),
        "title_similarity": round(sim_title, 4),
        "title_token_overlap": round(overlap_title, 4),
        "author_overlap": round(overlap_authors, 4),
        "abstract_overlap": round(overlap_abstract, 4),
        "year_bonus": round(year_bonus, 4),
        "shared_author_count": shared_author_count,
        "shared_title_terms": shared_title_terms,
        "author_bonus": round(author_bonus, 4),
        "title_bonus": round(title_bonus, 4),
        "mismatch_penalty": round(mismatch_penalty, 4),
    }
