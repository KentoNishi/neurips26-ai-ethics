# NeurIPS 2026 Ethics Flags

Research code for the NeurIPS 2026 ethics-flags resubmission study.

This repository contains the OpenReview harvesting, paper-matching, and targeted rematching code used to trace ethics-flagged ICLR submissions into later public versions. It is research code for internal project use, not a polished public package.

## Layout

- `src/neurips26_ethics/`: pipeline, OpenReview client, matching logic, and utilities.
- `scripts/run_pipeline.py`: full local pipeline entrypoint.
- `scripts/run_targeted_rematch.py`: targeted refresh for weak or missing successor matches.

Generated data, exports, PDFs, local environments, and credentials are intentionally ignored.

## Usage

```bash
python -m pip install -e .
python scripts/run_pipeline.py --data-dir data/papers --years 2021 2022 2023 2024 2025 2026
```

To rerun targeted matching for older source cohorts:

```bash
python scripts/run_targeted_rematch.py --data-dir data/papers
```

Optional environment variables may be placed in a local `.env` file.
