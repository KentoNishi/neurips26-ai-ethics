# NeurIPS 2026 Ethics Flags

Code for tracing ethics-flagged ICLR submissions to later public versions. The pipeline collects submissions and reviews from OpenReview and ranks candidate matches in OpenAlex using titles, authors, abstracts, and publication dates.

## Layout

- `src/neurips26_ethics/`: data collection, paper matching, and file utilities.
- `scripts/run_pipeline.py`: collect submissions and reviews, identify ethics-flagged submissions, and search for candidate matches.
- `scripts/run_targeted_rematch.py`: repeat the search for submissions with missing or low-scoring matches, or matches marked invalid or uncertain.

## Usage

```bash
python -m pip install -e .
python scripts/run_pipeline.py --data-dir data/papers --years 2021 2022 2023 2024 2025 2026
```

To rerun matching for selected submissions (through 2024 by default):

```bash
python scripts/run_targeted_rematch.py --data-dir data/papers
```

Results are written to `data/papers/`. Optional environment variables can be supplied in a local `.env` file.
