"""Run the copied research transformations on synthetic data, entirely offline."""
import csv
import json
import os
import socket
import tempfile
from pathlib import Path


def main():
    # This process never reads research data or a token file and cannot open sockets.
    def no_network(*args, **kwargs):
        raise RuntimeError("Network disabled in the synthetic demo")
    socket.socket.connect = no_network
    socket.socket.connect_ex = no_network
    socket.create_connection = no_network
    destination = Path(tempfile.mkdtemp(prefix="x-api-synthetic-demo-"))
    os.environ["X_DATA_DIR"] = str(destination)
    os.environ["X_CANCEL_EXPECTED_COUNT"] = "4"
    os.environ["X_BOYCOTT_EXPECTED_COUNT"] = "4"
    from src.api_collection.collect_x_posts_2022 import tweet_to_raw_row, append_unique_raw_rows
    from src.config import HASHTAG_CONFIG
    from src.analysis.build_collected_monthly_counts import build_all_collected_monthly_counts
    from src.analysis.build_monthly_gap_report import write_gap_report
    from src.analysis.quality_check import build_quality_report
    from src.preprocessing.build_professor_submission import build_all_professor_submissions

    fixture = Path(__file__).resolve().parents[1] / "data/sample/synthetic_posts.json"
    posts = json.loads(fixture.read_text())["data"]
    for hashtag, config in HASHTAG_CONFIG.items():
        rows = [tweet_to_raw_row(post, hashtag_type=hashtag, query=config["query"],
                                window_start="2022-01-01T00:00:00Z",
                                window_end="2023-01-01T00:00:00Z") for post in posts]
        written = append_unique_raw_rows(config["raw_master_path"], rows + [rows[0]], set())
        assert written == 3, "Duplicate suppression failed"
        count_path = destination / "counts" / f"x_{hashtag}_monthly_counts_2015_2025.csv"
        count_path.parent.mkdir(exist_ok=True)
        with count_path.open("w", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["month", "monthly_count"])
            for month in range(1, 13):
                writer.writerow([f"2022-{month:02}", 3 if month == 1 else 1 if month == 2 else 0])
    build_all_collected_monthly_counts()
    write_gap_report(destination / "reports/synthetic_gap_report.csv")
    build_all_professor_submissions()
    build_quality_report()
    print("SYNTHETIC ONLY: per hashtag, 4 attempted rows → 3 unique rows; one duplicate suppressed.")
    print("Synthetic baseline: 4 counts; 3 posts; gap: 1. These are not research results.")
    print(f"Generated local files: {destination}")


if __name__ == "__main__":
    main()
