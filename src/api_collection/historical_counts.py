"""Counts API workflow extracted from the original trend notebook.

The original pagination, fixed 60-second 429 wait, and aggregation are retained.
No API request runs on import. CLI requests require --allow-live-api.
"""
import argparse
import os
import time
from pathlib import Path
import requests
import pandas as pd
from src.config import DATA_DIR
from src.analysis.historical_counts import aggregate_counts

COUNTS_ALL_URL = "https://api.x.com/2/tweets/counts/all"

def fetch_counts_all(query, start_time, end_time, bearer_token, granularity="day"):
    all_rows = []
    next_token = None
    request_count = 0

    while True:
        params = {
            "query": query,
            "start_time": start_time,
            "end_time": end_time,
            "granularity": granularity
        }

        if next_token:
            params["next_token"] = next_token

        response = requests.get(
            COUNTS_ALL_URL,
            headers={"Authorization": f"Bearer {bearer_token}", "User-Agent": "CancelCultureResearch/1.0"},
            params=params,
            timeout=30
        )

        if response.status_code == 429:
            print("Rate limit reached. Rest for 60 seconds")
            time.sleep(60)
            continue

        if response.status_code >= 400:
            print("Error status:", response.status_code)
            print(response.text)
            response.raise_for_status()

        payload = response.json()
        request_count += 1

        rows = payload.get("data", [])
        all_rows.extend(rows)

        meta = payload.get("meta", {})
        print(
            f"Request {request_count}: "
            f"rows={len(rows)}, "
            f"page_total={meta.get('total_tweet_count')}, "
            f"total_rows_so_far={len(all_rows)}"
        )

        next_token = meta.get("next_token")

        if not next_token:
            break

        time.sleep(1)

    return pd.DataFrame(all_rows), request_count

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hashtag", choices=["cancel", "boycott"], required=True)
    parser.add_argument("--start-time", default="2015-01-01T00:00:00Z")
    parser.add_argument("--end-time", default="2026-01-01T00:00:00Z")
    parser.add_argument("--output-dir", type=Path, default=DATA_DIR / "counts")
    parser.add_argument("--allow-live-api", action="store_true")
    args = parser.parse_args()
    if not args.allow_live_api:
        parser.error("Live API access is disabled; explicit --allow-live-api is required.")
    token = os.environ.get("X_BEARER_TOKEN", "")
    if not token:
        parser.error("Set X_BEARER_TOKEN in the environment.")
    frame, requests_used = fetch_counts_all(
        f"#{args.hashtag} -is:retweet lang:en", args.start_time, args.end_time, token)
    if frame.empty:
        print("No count data returned.")
        return
    daily, monthly, yearly = aggregate_counts(frame)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for interval, table in [("daily", daily), ("monthly", monthly), ("yearly", yearly)]:
        first = args.start_time[:4]
        last = (pd.Timestamp(args.end_time) - pd.Timedelta(seconds=1)).year
        table.to_csv(args.output_dir / f"x_{args.hashtag}_{interval}_counts_{first}_{last}.csv",
                     index=False, encoding="utf-8-sig")
    print(f"Successful response pages: {requests_used}. No cost estimate is provided.")

if __name__ == "__main__":
    main()
