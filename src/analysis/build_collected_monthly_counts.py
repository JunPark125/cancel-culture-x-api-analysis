"""Build monthly collected-row reports from the raw X master CSV files."""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from src.config import HASHTAG_CONFIG, REPORTS_DIR, START_TIME, END_TIME


OUTPUT_COLUMNS = [
    "hashtag_type",
    "month",
    "collected_rows",
    "unique_post_count",
]


def parse_x_timestamp(value: str) -> datetime | None:
    """Parse an X timestamp into UTC, returning None for invalid values."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def output_path_for(hashtag_type: str) -> Path:
    return REPORTS_DIR / f"x_2022_{hashtag_type}_collected_monthly_counts.csv"


def build_collected_monthly_counts(hashtag_type: str) -> Path:
    """Group one raw master file by created_at month and unique post ID."""
    config = HASHTAG_CONFIG[hashtag_type]
    raw_path = config["raw_master_path"]
    if not raw_path.exists():
        raise FileNotFoundError(f"Raw master file not found: {raw_path}")

    period_start = parse_x_timestamp(START_TIME)
    period_end = parse_x_timestamp(END_TIME)
    if period_start is None or period_end is None:
        raise RuntimeError("Invalid START_TIME or END_TIME in config.py")

    row_counts: dict[str, int] = defaultdict(int)
    post_ids_by_month: dict[str, set[str]] = defaultdict(set)

    with raw_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            created_at = parse_x_timestamp(row.get("created_at", ""))
            if created_at is None:
                continue
            if created_at < period_start or created_at >= period_end:
                continue

            month = created_at.strftime("%Y-%m")
            row_counts[month] += 1
            post_id = (row.get("post_id") or "").strip()
            if post_id:
                post_ids_by_month[month].add(post_id)

    output_path = output_path_for(hashtag_type)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        for month in sorted(row_counts):
            writer.writerow(
                {
                    "hashtag_type": hashtag_type,
                    "month": month,
                    "collected_rows": row_counts[month],
                    "unique_post_count": len(post_ids_by_month[month]),
                }
            )

    return output_path


def build_all_collected_monthly_counts(
    hashtags: list[str] | None = None,
) -> list[Path]:
    selected = hashtags or sorted(HASHTAG_CONFIG.keys())
    return [build_collected_monthly_counts(hashtag_type) for hashtag_type in selected]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build monthly collected-count reports from raw X master CSVs."
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
    paths = build_all_collected_monthly_counts(args.hashtags)
    for path in paths:
        print(f"Wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
