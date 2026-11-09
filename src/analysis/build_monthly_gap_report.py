"""Compare collected 2022 monthly counts with X Counts API monthly totals."""

from __future__ import annotations

import argparse
import csv
from calendar import monthrange
from pathlib import Path

from src.config import DATA_DIR, REPORTS_DIR


YEAR = 2022
BIG_GAP_THRESHOLD = 2000
OPTIONAL_GAP_THRESHOLD = 1000

TREND_COUNTS_DIR = DATA_DIR / "counts"

INPUTS = {
    "boycott": {
        "collected_path": REPORTS_DIR / "x_2022_boycott_collected_monthly_counts.csv",
        "expected_path": TREND_COUNTS_DIR / "x_boycott_monthly_counts_2015_2025.csv",
    },
    "cancel": {
        "collected_path": REPORTS_DIR / "x_2022_cancel_collected_monthly_counts.csv",
        "expected_path": TREND_COUNTS_DIR / "x_cancel_monthly_counts_2015_2025.csv",
    },
}

OUTPUT_COLUMNS = [
    "hashtag_type",
    "month",
    "expected_count",
    "collected_rows",
    "collected_unique_posts",
    "missing_count",
    "collection_rate",
    "gap_severity",
    "recommended_action",
    "backfill_window_granularity",
    "backfill_start_time",
    "backfill_end_time",
]


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    """Read a CSV with UTF-8 BOM tolerance."""
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def month_start_end(month: str) -> tuple[str, str]:
    """Return UTC start/end timestamps for a YYYY-MM month."""
    year, month_number = [int(part) for part in month.split("-")]
    if month_number == 12:
        next_year, next_month = year + 1, 1
    else:
        next_year, next_month = year, month_number + 1
    _last_day = monthrange(year, month_number)[1]
    start_time = f"{year:04d}-{month_number:02d}-01T00:00:00Z"
    end_time = f"{next_year:04d}-{next_month:02d}-01T00:00:00Z"
    return start_time, end_time


def read_expected_counts(path: Path) -> dict[str, int]:
    """Read Counts API monthly totals and keep only the target year."""
    expected: dict[str, int] = {}
    for row in read_csv_rows(path):
        month = row["month"]
        if not month.startswith(f"{YEAR}-"):
            continue
        expected[month] = int(row["monthly_count"])
    return expected


def read_collected_counts(path: Path) -> dict[str, dict[str, int]]:
    """Read collected monthly counts from raw master-derived report."""
    collected: dict[str, dict[str, int]] = {}
    for row in read_csv_rows(path):
        month = row["month"]
        collected[month] = {
            "collected_rows": int(row["collected_rows"]),
            "collected_unique_posts": int(row["unique_post_count"]),
        }
    return collected


def classify_gap(missing_count: int, collection_rate: float) -> tuple[str, str, str]:
    """Return severity, action, and suggested backfill granularity."""
    if missing_count >= BIG_GAP_THRESHOLD:
        return (
            "large_gap",
            "daily_backfill_recommended",
            "day",
        )
    if missing_count >= OPTIONAL_GAP_THRESHOLD:
        return (
            "medium_gap",
            "optional_monthly_backfill",
            "month",
        )
    if missing_count > 0:
        return (
            "small_gap",
            "document_gap_no_immediate_backfill",
            "none",
        )
    if missing_count == 0:
        return (
            "no_gap",
            "no_action_needed",
            "none",
        )
    return (
        "over_collected",
        "inspect_query_or_duplicates",
        "none",
    )


def build_rows() -> list[dict[str, object]]:
    """Build one comparison row per hashtag/month."""
    output_rows: list[dict[str, object]] = []

    for hashtag_type, paths in INPUTS.items():
        expected_counts = read_expected_counts(paths["expected_path"])
        collected_counts = read_collected_counts(paths["collected_path"])

        for month in sorted(expected_counts):
            expected_count = expected_counts[month]
            collected = collected_counts.get(
                month,
                {"collected_rows": 0, "collected_unique_posts": 0},
            )
            unique_posts = collected["collected_unique_posts"]
            missing_count = expected_count - unique_posts
            collection_rate_value = unique_posts / expected_count if expected_count else 0
            severity, action, granularity = classify_gap(
                missing_count, collection_rate_value
            )
            start_time, end_time = month_start_end(month)

            output_rows.append(
                {
                    "hashtag_type": hashtag_type,
                    "month": month,
                    "expected_count": expected_count,
                    "collected_rows": collected["collected_rows"],
                    "collected_unique_posts": unique_posts,
                    "missing_count": missing_count,
                    "collection_rate": f"{collection_rate_value:.4f}",
                    "gap_severity": severity,
                    "recommended_action": action,
                    "backfill_window_granularity": granularity,
                    "backfill_start_time": start_time,
                    "backfill_end_time": end_time,
                }
            )

    return output_rows


def write_gap_report(output_path: Path) -> Path:
    """Write the monthly comparison report."""
    rows = build_rows()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a 2022 monthly gap report comparing Counts API and collected rows."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPORTS_DIR / "x_2022_monthly_collection_gap_report.csv",
        help="Output path for the monthly gap report.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_path = write_gap_report(args.output)
    print(f"Wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
