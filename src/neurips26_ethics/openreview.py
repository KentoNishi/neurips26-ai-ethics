"""OpenReview harvesting and normalization."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional
from urllib.parse import urljoin

import requests

from .text_utils import collapse_whitespace


@dataclass(frozen=True)
class YearConfig:
    year: int
    api_base: str
    invitation: str
    supports_public_ethics_flags: bool


YEAR_CONFIGS: dict[int, YearConfig] = {
    2021: YearConfig(
        year=2021,
        api_base="https://api.openreview.net/notes",
        invitation="ICLR.cc/2021/Conference/-/Blind_Submission",
        supports_public_ethics_flags=False,
    ),
    2022: YearConfig(
        year=2022,
        api_base="https://api.openreview.net/notes",
        invitation="ICLR.cc/2022/Conference/-/Blind_Submission",
        supports_public_ethics_flags=True,
    ),
    2023: YearConfig(
        year=2023,
        api_base="https://api.openreview.net/notes",
        invitation="ICLR.cc/2023/Conference/-/Blind_Submission",
        supports_public_ethics_flags=True,
    ),
    2024: YearConfig(
        year=2024,
        api_base="https://api2.openreview.net/notes",
        invitation="ICLR.cc/2024/Conference/-/Submission",
        supports_public_ethics_flags=True,
    ),
    2025: YearConfig(
        year=2025,
        api_base="https://api2.openreview.net/notes",
        invitation="ICLR.cc/2025/Conference/-/Submission",
        supports_public_ethics_flags=True,
    ),
    2026: YearConfig(
        year=2026,
        api_base="https://api2.openreview.net/notes",
        invitation="ICLR.cc/2026/Conference/-/Submission",
        supports_public_ethics_flags=True,
    ),
}

ETHICS_NEGATIVE_VALUES = {"no", "no.", "no ethics review needed."}
ETHICS_KEYWORDS = {
    "ethic",
    "bias",
    "fairness",
    "privacy",
    "safety",
    "security",
    "harm",
    "legal",
    "copyright",
    "gdpr",
    "human subject",
    "irb",
    "plagiarism",
    "dual submission",
    "responsible research",
    "discrimination",
    "unprofessional",
}

REVIEW_TEXT_FIELDS = [
    "review",
    "summary",
    "main_review",
    "summary_of_the_paper",
    "summary_of_the_review",
    "strength_and_weaknesses",
    "strengths",
    "weaknesses",
    "questions",
]

DECISION_TEXT_FIELDS = [
    "decision",
    "comment",
    "metareview:_summary,_strengths_and_weaknesses",
    "justification_for_why_not_higher_score",
    "justification_for_why_not_lower_score",
    "note_from_PC",
]


class OpenReviewClient:
    """Fetches ICLR submissions and public replies from OpenReview."""

    web_base = "https://openreview.net"

    def __init__(
        self,
        *,
        session: Optional[requests.Session] = None,
        user_agent: str = (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"
        ),
        timeout: float = 60.0,
        min_request_interval: float = 2.5,
        max_retries: int = 8,
    ) -> None:
        self.session = session or requests.Session()
        self.session.headers["User-Agent"] = user_agent
        self.session.headers["Accept"] = "application/json,text/plain,*/*"
        self.session.headers["Referer"] = "https://openreview.net/"
        self.timeout = timeout
        self.min_request_interval = min_request_interval
        self.max_retries = max_retries
        self._last_request_ts = 0.0

    def iter_submissions(self, year: int, *, page_size: int = 200) -> Iterator[dict]:
        config = YEAR_CONFIGS[year]
        offset = 0
        while True:
            response = self._get(
                config.api_base,
                params={
                    "invitation": config.invitation,
                    "limit": page_size,
                    "offset": offset,
                    "details": "replies",
                },
            )
            notes = response.json().get("notes", [])
            if not notes:
                return
            for note in notes:
                yield note
            offset += page_size

    def harvest_year(self, year: int) -> tuple[list[dict], list[dict], list[dict], dict]:
        config = YEAR_CONFIGS[year]
        submission_rows: list[dict] = []
        review_rows: list[dict] = []
        raw_notes: list[dict] = []
        summary = {
            "year": year,
            "supports_public_ethics_flags": config.supports_public_ethics_flags,
            "submission_count": 0,
            "flagged_paper_count": 0,
            "flagged_reject_count": 0,
            "flagged_accept_count": 0,
            "flagged_withdrawn_count": 0,
            "flagged_unknown_decision_count": 0,
        }

        for note in self.iter_submissions(year):
            raw_notes.append(note)
            submission, reviews = normalize_submission(note, year=year, supports_public_ethics_flags=config.supports_public_ethics_flags)
            submission_rows.append(submission)
            review_rows.extend(reviews)

        summary["submission_count"] = len(submission_rows)
        for row in submission_rows:
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

        return submission_rows, review_rows, raw_notes, summary

    def download_pdf(self, pdf_url: str, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with self.session.get(pdf_url, timeout=self.timeout, stream=True) as response:
            response.raise_for_status()
            with destination.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=65536):
                    if chunk:
                        handle.write(chunk)
        return destination

    def _get(self, url: str, *, params: dict) -> requests.Response:
        delay = self.min_request_interval
        for attempt in range(self.max_retries):
            elapsed = time.monotonic() - self._last_request_ts
            wait_time = self.min_request_interval - elapsed
            if wait_time > 0:
                time.sleep(wait_time)

            response = self.session.get(url, params=params, timeout=self.timeout)
            self._last_request_ts = time.monotonic()
            if response.status_code not in {429, 500, 502, 503, 504}:
                response.raise_for_status()
                return response

            retry_after = response.headers.get("Retry-After")
            if retry_after and retry_after.isdigit():
                delay = max(delay, float(retry_after))
            time.sleep(delay)
            delay = min(delay * 2, 60.0)

        response.raise_for_status()
        return response


def normalize_submission(note: dict, *, year: int, supports_public_ethics_flags: bool) -> tuple[dict, list[dict]]:
    content = normalize_content(note.get("content", {}))
    replies = note.get("details", {}).get("replies", [])
    submission_id = note.get("id")
    forum_id = note.get("forum") or submission_id
    paper_number = note.get("number")
    authors = ensure_list(content.get("authors"))
    author_ids = ensure_list(content.get("authorids"))
    keywords = ensure_list(content.get("keywords"))
    pdf_url = absolute_openreview_url(content.get("pdf"))

    decision = None
    decision_text = ""
    meta_review_text = ""
    withdrawn = False
    reviews: list[dict] = []

    all_ethics_values: list[str] = []
    ethics_flagged = False
    ethics_flagged_review_count = 0
    ethics_categories: list[str] = []
    review_texts: list[str] = []

    for reply in replies:
        invitation = extract_invitation(reply)
        reply_content = normalize_content(reply.get("content", {}))

        if "Official_Review" in invitation:
            ethics_values = normalize_ethics_values(reply_content.get("flag_for_ethics_review"))
            is_flagged = has_positive_ethics_flag(ethics_values)
            if is_flagged:
                ethics_flagged = True
                ethics_flagged_review_count += 1
                for value in ethics_values:
                    if value not in ethics_categories and not is_negative_ethics_value(value):
                        ethics_categories.append(value)
            all_ethics_values.extend(ethics_values)

            review_text = collect_text(reply_content, REVIEW_TEXT_FIELDS)
            if review_text:
                review_texts.append(review_text)
            reviews.append(
                {
                    "year": year,
                    "submission_id": submission_id,
                    "forum_id": forum_id,
                    "paper_number": paper_number,
                    "review_id": reply.get("id"),
                    "review_invitation": invitation,
                    "rating": extract_scalar(reply_content, ["rating", "recommendation"]),
                    "confidence": extract_scalar(reply_content, ["confidence"]),
                    "ethics_flag_values": ethics_values,
                    "ethics_flagged": is_flagged,
                    "review_text": review_text,
                }
            )
        elif "Decision" in invitation:
            decision = extract_scalar(reply_content, ["decision"])
            decision_text = collect_text(reply_content, DECISION_TEXT_FIELDS)
        elif "Meta_Review" in invitation:
            meta_review_text = collect_text(reply_content, DECISION_TEXT_FIELDS)
        elif "Withdrawal" in invitation:
            withdrawn = True

    combined_text = " ".join(part for part in [decision_text, meta_review_text, " ".join(review_texts)] if part).lower()
    ethics_linked_rejection = (
        bool(decision)
        and decision.lower().startswith("reject")
        and ethics_flagged
        and any(keyword in combined_text for keyword in ETHICS_KEYWORDS)
    )

    submission = {
        "year": year,
        "submission_id": submission_id,
        "forum_id": forum_id,
        "paper_number": paper_number,
        "title": content.get("title", ""),
        "abstract": content.get("abstract", ""),
        "authors": authors,
        "author_ids": author_ids,
        "keywords": keywords,
        "pdf_url": pdf_url,
        "decision": decision or "",
        "decision_text": decision_text,
        "meta_review_text": meta_review_text,
        "withdrawn": withdrawn,
        "supports_public_ethics_flags": supports_public_ethics_flags,
        "ethics_flagged": ethics_flagged,
        "ethics_flagged_review_count": ethics_flagged_review_count,
        "ethics_flag_values": all_ethics_values,
        "ethics_categories": ethics_categories,
        "review_count": len(reviews),
        "ethics_linked_rejection": ethics_linked_rejection,
    }
    return submission, reviews


def normalize_content(content: dict) -> dict:
    normalized = {}
    for key, value in content.items():
        normalized[key] = unwrap_value(value)
    return normalized


def unwrap_value(value):
    if isinstance(value, dict):
        if "value" in value:
            return unwrap_value(value["value"])
        return {key: unwrap_value(inner) for key, inner in value.items()}
    if isinstance(value, list):
        return [unwrap_value(item) for item in value]
    if isinstance(value, str):
        return collapse_whitespace(value)
    return value


def ensure_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def extract_invitation(reply: dict) -> str:
    if reply.get("invitation"):
        return str(reply["invitation"])
    invitations = reply.get("invitations") or []
    if invitations:
        return str(invitations[0])
    return ""


def extract_scalar(content: dict, keys: list[str]) -> str:
    for key in keys:
        value = content.get(key)
        if value is None:
            continue
        if isinstance(value, list):
            return collapse_whitespace(", ".join(str(item) for item in value))
        return collapse_whitespace(str(value))
    return ""


def collect_text(content: dict, keys: list[str]) -> str:
    values: list[str] = []
    for key in keys:
        value = content.get(key)
        if value is None:
            continue
        if isinstance(value, list):
            value = " ".join(str(item) for item in value)
        else:
            value = str(value)
        value = collapse_whitespace(value)
        if value:
            values.append(value)
    return "\n".join(values)


def normalize_ethics_values(value) -> list[str]:
    if value is None:
        return []
    value = unwrap_value(value)
    if isinstance(value, list):
        values = [collapse_whitespace(str(item)) for item in value if str(item).strip()]
        return values
    return [collapse_whitespace(str(value))]


def is_negative_ethics_value(value: str) -> bool:
    return value.strip().lower() in ETHICS_NEGATIVE_VALUES


def has_positive_ethics_flag(values: list[str]) -> bool:
    if not values:
        return False
    return any(not is_negative_ethics_value(value) for value in values)


def absolute_openreview_url(url: Optional[str]) -> str:
    if not url:
        return ""
    return urljoin("https://openreview.net", str(url))


def write_harvest_cache(path: Path, notes: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for note in notes:
            handle.write(json.dumps(note, ensure_ascii=True))
            handle.write("\n")


def load_harvest_cache(path: Path) -> list[dict]:
    if not path.exists():
        return []
    notes: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                notes.append(json.loads(line))
    return notes
