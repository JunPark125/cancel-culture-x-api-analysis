"""Create a data quality report for the raw X hashtag master files."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from src.config import (
    END_TIME,
    HASHTAG_CONFIG,
    QUALITY_REPORT_COLUMNS,
    QUALITY_REPORT_PATH,
    START_TIME,
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


def missing_mask(series: Any) -> Any:
    """Treat NA and blank strings as missing."""
    as_string = series.astype("string")
    return as_string.isna() | as_string.str.strip().eq("")


def text_for_quality(raw: Any, pd: Any) -> Any:
    """Use the same text fallback as professor exports."""
    post_text_full = raw.get("post_text_full", pd.Series("", index=raw.index)).fillna("")
    text = raw.get("text", pd.Series("", index=raw.index)).fillna("")
    return post_text_full.where(post_text_full.astype(str).str.strip() != "", text)


def iso_or_blank(timestamp: Any, pd: Any) -> str:
    if timestamp is None or pd.isna(timestamp):
        return ""
    return timestamp.isoformat()


def quality_row(hashtag_type: str) -> dict[str, object]:
    """Calculate quality checks for one raw master file."""
    config = HASHTAG_CONFIG[hashtag_type]
    raw_path = config["raw_master_path"]
    expected_count = config["expected_count"]
    pd = load_pandas()

    if not raw_path.exists():
        return {
            "hashtag_type": hashtag_type,
            "expected_count": expected_count,
            "collected_rows": 0,
            "unique_post_ids": 0,
            "duplicate_post_ids": 0,
            "missing_created_at": 0,
            "missing_author_id": 0,
            "missing_text": 0,
            "missing_like_count": 0,
            "missing_repost_count": 0,
            "rows_outside_2022": 0,
            "first_timestamp": "",
            "last_timestamp": "",
        }

    raw = pd.read_csv(raw_path, dtype="string", keep_default_na=False)
    collected_rows = len(raw)

    post_ids = raw.get("post_id", pd.Series("", index=raw.index)).astype("string")
    non_missing_post_ids = post_ids[~missing_mask(post_ids)]
    unique_post_ids = non_missing_post_ids.nunique()
    duplicate_post_ids = int(non_missing_post_ids.duplicated().sum())

    created_at = raw.get("created_at", pd.Series("", index=raw.index))
    timestamps = pd.to_datetime(created_at, utc=True, errors="coerce")
    period_start = pd.Timestamp(START_TIME)
    period_end = pd.Timestamp(END_TIME)
    outside_2022 = timestamps.notna() & (
        (timestamps < period_start) | (timestamps >= period_end)
    )

    valid_timestamps = timestamps.dropna()
    first_timestamp = valid_timestamps.min() if not valid_timestamps.empty else None
    last_timestamp = valid_timestamps.max() if not valid_timestamps.empty else None

    author_id = raw.get("author_id", pd.Series("", index=raw.index))
    like_count = raw.get("like_count", pd.Series("", index=raw.index))
    repost_count = raw.get("repost_count", pd.Series("", index=raw.index))
    usable_post_text = text_for_quality(raw, pd)

    return {
        "hashtag_type": hashtag_type,
        "expected_count": expected_count,
        "collected_rows": collected_rows,
        "unique_post_ids": int(unique_post_ids),
        "duplicate_post_ids": duplicate_post_ids,
        "missing_created_at": int(timestamps.isna().sum()),
        "missing_author_id": int(missing_mask(author_id).sum()),
        "missing_text": int(missing_mask(usable_post_text).sum()),
        "missing_like_count": int(missing_mask(like_count).sum()),
        "missing_repost_count": int(missing_mask(repost_count).sum()),
        "rows_outside_2022": int(outside_2022.sum()),
        "first_timestamp": iso_or_blank(first_timestamp, pd),
        "last_timestamp": iso_or_blank(last_timestamp, pd),
    }


def build_quality_report(hashtags: list[str] | None = None) -> Path:
    """Write the quality report CSV for selected hashtags."""
    selected = hashtags or sorted(HASHTAG_CONFIG.keys())
    rows = [quality_row(hashtag_type) for hashtag_type in selected]
    pd = load_pandas()
    report = pd.DataFrame(rows, columns=QUALITY_REPORT_COLUMNS)

    QUALITY_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    report.to_csv(QUALITY_REPORT_PATH, index=False)
    return QUALITY_REPORT_PATH


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a quality report from raw X hashtag master files."
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
    path = build_quality_report(args.hashtags)
    print(f"Wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
