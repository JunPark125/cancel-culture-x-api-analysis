"""Build professor-facing simplified CSV files from raw master files."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from src.config import (
    HASHTAG_CONFIG,
    PROFESSOR_SUBMISSION_COLUMNS,
)


def load_pandas() -> Any:
    """Import pandas lazily so --help works before dependencies are installed."""
    try:
        import pandas as pd
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "pandas is required. Install dependencies with: pip install -r requirements.txt"
        ) from exc
    return pd


def usable_text(raw: Any, pd: Any) -> Any:
    """Prefer post_text_full, falling back to text for older/non-note posts."""
    post_text_full = raw.get("post_text_full", pd.Series("", index=raw.index)).fillna("")
    text = raw.get("text", pd.Series("", index=raw.index)).fillna("")
    return post_text_full.where(post_text_full.astype(str).str.strip() != "", text)


def build_professor_submission(hashtag_type: str) -> Path:
    """Create one simplified CSV for a professor from the raw master file."""
    config = HASHTAG_CONFIG[hashtag_type]
    raw_path = config["raw_master_path"]
    output_path = config["professor_submission_path"]

    if not raw_path.exists():
        raise FileNotFoundError(f"Raw master file not found: {raw_path}")

    pd = load_pandas()
    raw = pd.read_csv(raw_path, dtype="string", keep_default_na=False)
    created_at = raw.get(
        "created_at", pd.Series("", index=raw.index, dtype="string")
    )
    timestamp_sort = pd.to_datetime(created_at, errors="coerce", utc=True)

    invalid_timestamps = created_at.astype(str).str.strip().ne("") & timestamp_sort.isna()
    if invalid_timestamps.any():
        raise ValueError(
            f"Invalid created_at value(s) in {raw_path}: "
            f"{int(invalid_timestamps.sum())} row(s)"
        )

    professor = pd.DataFrame(
        {
            # Display only the calendar date in the professor-facing file.
            "timestamp": timestamp_sort.dt.strftime("%Y-%m-%d"),
            "user_id": raw.get("author_id", ""),
            "post_text": usable_text(raw, pd),
            "like_count": pd.to_numeric(raw.get("like_count", ""), errors="coerce").astype(
                "Int64"
            ),
            "repost_count": pd.to_numeric(
                raw.get("repost_count", ""), errors="coerce"
            ).astype("Int64"),
            # Keep the full timestamp temporarily so rows within the same date
            # are also ordered by their original posting time.
            "_timestamp_sort": timestamp_sort,
        }
    )
    professor = professor.sort_values(
        "_timestamp_sort", kind="stable", na_position="last"
    ).drop(columns="_timestamp_sort")
    professor = professor.reset_index(drop=True)
    professor = professor[PROFESSOR_SUBMISSION_COLUMNS]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    professor.to_csv(output_path, index=False)
    return output_path


def build_all_professor_submissions(hashtags: list[str] | None = None) -> list[Path]:
    """Build professor-facing files for the selected hashtags."""
    selected = hashtags or sorted(HASHTAG_CONFIG.keys())
    return [build_professor_submission(hashtag_type) for hashtag_type in selected]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build professor-facing CSVs from raw X hashtag master files."
    )
    parser.add_argument(
        "--hashtags",
        nargs="+",
        choices=sorted(HASHTAG_CONFIG.keys()),
        default=sorted(HASHTAG_CONFIG.keys()),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    paths = build_all_professor_submissions(args.hashtags)
    for path in paths:
        print(f"Wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
