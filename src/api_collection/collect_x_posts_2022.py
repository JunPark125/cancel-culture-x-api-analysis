"""Collect 2022 English, non-retweet X posts for #cancel and #boycott.

The script uses the X API v2 full-archive search endpoint and writes one raw
master CSV per hashtag. It is designed to be restarted safely: completed month
windows are skipped, in-progress pagination tokens are reused, and existing
post IDs in the raw CSV are not appended twice.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from src.config import (
    BACKOFF_BASE_SECONDS,
    BACKOFF_MAX_SECONDS,
    BEARER_TOKEN_ENV,
    CHECKPOINT_STATE_PATH,
    COLLECTION_LOG_COLUMNS,
    COLLECTION_LOG_PATH,
    ENV_FILE_PATH,
    FAILED_REQUESTS_COLUMNS,
    FAILED_REQUESTS_LOG_PATH,
    FULL_ARCHIVE_SEARCH_URL,
    HASHTAG_CONFIG,
    MAX_RESULTS,
    MAX_RETRIES,
    RATE_LIMIT_BUFFER_SECONDS,
    RAW_MASTER_COLUMNS,
    REQUEST_TIMEOUT_SECONDS,
    SOURCE_ENDPOINT_LABEL,
    START_TIME,
    END_TIME,
    TWEET_FIELDS,
    VISIBLE_TOKEN_FILE_PATH,
)


class ApiRequestError(RuntimeError):
    """Raised when the X API request fails after retries or is not retryable."""


def utc_now_iso() -> str:
    """Return a compact UTC timestamp for logs and collected_at."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_local_env_file(path: Path) -> None:
    """Load simple KEY=VALUE pairs from a local token file."""
    if not path.exists():
        return

    with path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def load_local_token_files() -> None:
    """Load token files without overriding variables already set in the shell."""
    load_local_env_file(VISIBLE_TOKEN_FILE_PATH)
    load_local_env_file(ENV_FILE_PATH)


def parse_utc_datetime(value: str) -> datetime:
    """Parse an X API timestamp string into a timezone-aware UTC datetime."""
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def format_x_time(value: datetime) -> str:
    """Format a datetime as the UTC timestamp format expected by the X API."""
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def next_month_start(value: datetime) -> datetime:
    """Return the first instant of the month after value."""
    if value.month == 12:
        return datetime(value.year + 1, 1, 1, tzinfo=timezone.utc)
    return datetime(value.year, value.month + 1, 1, tzinfo=timezone.utc)


def monthly_windows(start_time: str, end_time: str) -> list[tuple[str, str]]:
    """Split the inclusive/exclusive collection interval into month windows."""
    start = parse_utc_datetime(start_time)
    end = parse_utc_datetime(end_time)
    current = datetime(start.year, start.month, 1, tzinfo=timezone.utc)

    windows: list[tuple[str, str]] = []
    while current < end:
        following_month = next_month_start(current)
        window_start = max(current, start)
        window_end = min(following_month, end)
        if window_start < window_end:
            windows.append((format_x_time(window_start), format_x_time(window_end)))
        current = following_month
    return windows


def month_key(window_start: str) -> str:
    """Return a stable checkpoint key such as 2022-01 for a month window."""
    return window_start[:7]


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def ensure_csv_header(path: Path, columns: list[str]) -> None:
    """Create an empty CSV with a header if needed."""
    ensure_parent(path)
    if path.exists() and path.stat().st_size > 0:
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()


def write_csv_row(path: Path, columns: list[str], row: dict[str, Any]) -> None:
    """Append a single row to a CSV, creating the header when necessary."""
    ensure_csv_header(path, columns)
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writerow({column: row.get(column, "") for column in columns})


def write_collection_log(
    *,
    level: str,
    event: str,
    hashtag_type: str = "",
    query: str = "",
    month_window_start: str = "",
    month_window_end: str = "",
    next_token: str = "",
    status_code: str | int = "",
    rows_returned: str | int = "",
    rows_written: str | int = "",
    message: str = "",
) -> None:
    """Record high-level collection progress."""
    write_csv_row(
        COLLECTION_LOG_PATH,
        COLLECTION_LOG_COLUMNS,
        {
            "timestamp": utc_now_iso(),
            "level": level,
            "event": event,
            "hashtag_type": hashtag_type,
            "query": query,
            "month_window_start": month_window_start,
            "month_window_end": month_window_end,
            "next_token": next_token,
            "status_code": status_code,
            "rows_returned": rows_returned,
            "rows_written": rows_written,
            "message": message,
        },
    )


def write_failed_request(
    *,
    context: dict[str, Any],
    attempt: int,
    status_code: str | int,
    error_type: str,
    will_retry: bool,
    message: str,
    response_text: str = "",
) -> None:
    """Record every failed request attempt, including retryable attempts."""
    write_csv_row(
        FAILED_REQUESTS_LOG_PATH,
        FAILED_REQUESTS_COLUMNS,
        {
            "timestamp": utc_now_iso(),
            "hashtag_type": context.get("hashtag_type", ""),
            "query": context.get("query", ""),
            "month_window_start": context.get("month_window_start", ""),
            "month_window_end": context.get("month_window_end", ""),
            "next_token": context.get("next_token", ""),
            "attempt": attempt,
            "status_code": status_code,
            "error_type": error_type,
            "will_retry": will_retry,
            "message": message,
            "response_text": response_text[:5000],
        },
    )


def progress_percent(collected: int, expected: int) -> str:
    """Format collection progress against the Counts API expected total."""
    if expected <= 0:
        return "n/a"
    return f"{(collected / expected) * 100:.1f}%"


def print_progress(message: str, *, quiet: bool = False) -> None:
    """Print a timestamped progress message for long-running collection."""
    if quiet:
        return
    print(f"[{utc_now_iso()}] {message}", flush=True)


def default_checkpoint() -> dict[str, Any]:
    return {
        "created_at": utc_now_iso(),
        "updated_at": utc_now_iso(),
        "endpoint": FULL_ARCHIVE_SEARCH_URL,
        "hashtags": {},
    }


def load_checkpoint(path: Path = CHECKPOINT_STATE_PATH) -> dict[str, Any]:
    """Load the checkpoint state, or create an empty one in memory."""
    if not path.exists() or path.stat().st_size == 0:
        return default_checkpoint()
    with path.open("r", encoding="utf-8") as handle:
        state = json.load(handle)
    state.setdefault("hashtags", {})
    return state


def save_checkpoint(state: dict[str, Any], path: Path = CHECKPOINT_STATE_PATH) -> None:
    """Atomically save checkpoint state so interruption is less likely to corrupt it."""
    ensure_parent(path)
    state["updated_at"] = utc_now_iso()
    temporary_path = path.with_suffix(".tmp")
    with temporary_path.open("w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2, sort_keys=True)
        handle.write("\n")
    temporary_path.replace(path)


def checkpoint_entry(
    state: dict[str, Any],
    hashtag_type: str,
    key: str,
    window_start: str,
    window_end: str,
) -> dict[str, Any]:
    """Get or initialize a checkpoint entry for one hashtag/month pair."""
    hashtag_state = state.setdefault("hashtags", {}).setdefault(hashtag_type, {})
    return hashtag_state.setdefault(
        key,
        {
            "status": "not_started",
            "window_start": window_start,
            "window_end": window_end,
            "next_token": None,
            "rows_written": 0,
        },
    )


def mark_window_progress(
    state: dict[str, Any],
    hashtag_type: str,
    key: str,
    *,
    next_token: str | None,
    rows_written_increment: int,
) -> None:
    """Update a checkpoint after each successfully written response page."""
    entry = state["hashtags"][hashtag_type][key]
    entry["status"] = "in_progress"
    entry["next_token"] = next_token
    entry["rows_written"] = int(entry.get("rows_written") or 0) + rows_written_increment
    entry["last_page_at"] = utc_now_iso()
    save_checkpoint(state)


def mark_window_completed(state: dict[str, Any], hashtag_type: str, key: str) -> None:
    """Mark one month window complete after the final page has been processed."""
    entry = state["hashtags"][hashtag_type][key]
    entry["status"] = "completed"
    entry["next_token"] = None
    entry["completed_at"] = utc_now_iso()
    save_checkpoint(state)


def load_existing_post_ids(raw_path: Path) -> set[str]:
    """Read post IDs already present in a raw master CSV."""
    existing_ids: set[str] = set()
    if not raw_path.exists() or raw_path.stat().st_size == 0:
        return existing_ids

    with raw_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            post_id = (row.get("post_id") or "").strip()
            if post_id:
                existing_ids.add(post_id)
    return existing_ids


def create_session(bearer_token: str) -> requests.Session:
    """Create a requests session authenticated with the bearer token."""
    session = requests.Session()
    session.headers.update(
        {
            "Authorization": f"Bearer {bearer_token}",
            "User-Agent": "x-2022-cancel-boycott-research/1.0",
        }
    )
    return session


def retry_backoff_seconds(attempt: int) -> int:
    """Exponential backoff for temporary failures."""
    return min(BACKOFF_BASE_SECONDS ** attempt, BACKOFF_MAX_SECONDS)


def rate_limit_wait_seconds(response: requests.Response) -> int:
    """Use X rate-limit headers when available; fall back to one minute."""
    wait_options: list[float] = []

    retry_after = response.headers.get("retry-after")
    if retry_after:
        try:
            wait_options.append(float(retry_after))
        except ValueError:
            pass

    reset_at = response.headers.get("x-rate-limit-reset")
    if reset_at:
        try:
            wait_options.append(max(float(reset_at) - time.time(), 0))
        except ValueError:
            pass

    wait_seconds = max(wait_options) if wait_options else 60
    return int(wait_seconds + RATE_LIMIT_BUFFER_SECONDS)


def is_retryable_status(status_code: int) -> bool:
    return status_code in {408, 425, 429, 500, 502, 503, 504}


def get_json_with_retries(
    session: requests.Session,
    params: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    """GET a JSON response from X, handling temporary failures and rate limits."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = session.get(
                FULL_ARCHIVE_SEARCH_URL,
                params=params,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
        except requests.RequestException as exc:
            will_retry = attempt < MAX_RETRIES
            write_failed_request(
                context=context,
                attempt=attempt,
                status_code="",
                error_type=exc.__class__.__name__,
                will_retry=will_retry,
                message=str(exc),
            )
            if not will_retry:
                raise ApiRequestError(f"Request failed after retries: {exc}") from exc
            sleep_seconds = retry_backoff_seconds(attempt)
            write_collection_log(
                level="warning",
                event="request_exception_retry",
                status_code="",
                message=f"Sleeping {sleep_seconds}s after {exc.__class__.__name__}.",
                **context,
            )
            time.sleep(sleep_seconds)
            continue

        if response.status_code == 200:
            try:
                return response.json()
            except ValueError as exc:
                write_failed_request(
                    context=context,
                    attempt=attempt,
                    status_code=response.status_code,
                    error_type="InvalidJSON",
                    will_retry=False,
                    message=str(exc),
                    response_text=response.text,
                )
                raise ApiRequestError("X API returned invalid JSON.") from exc

        will_retry = attempt < MAX_RETRIES and is_retryable_status(response.status_code)
        write_failed_request(
            context=context,
            attempt=attempt,
            status_code=response.status_code,
            error_type="HTTPError",
            will_retry=will_retry,
            message=response.reason,
            response_text=response.text,
        )

        if response.status_code == 429 and will_retry:
            sleep_seconds = rate_limit_wait_seconds(response)
            write_collection_log(
                level="warning",
                event="rate_limited",
                status_code=response.status_code,
                message=f"Sleeping {sleep_seconds}s until rate-limit reset.",
                **context,
            )
            time.sleep(sleep_seconds)
            continue

        if will_retry:
            sleep_seconds = retry_backoff_seconds(attempt)
            write_collection_log(
                level="warning",
                event="http_retry",
                status_code=response.status_code,
                message=f"Sleeping {sleep_seconds}s after HTTP {response.status_code}.",
                **context,
            )
            time.sleep(sleep_seconds)
            continue

        raise ApiRequestError(
            "X API request failed with "
            f"HTTP {response.status_code}: {response.text[:1000]}"
        )

    raise ApiRequestError("X API request failed after all retry attempts.")


def note_tweet_text(tweet: dict[str, Any]) -> str:
    """Return long-form note_tweet text when present, otherwise normal text."""
    note_tweet = tweet.get("note_tweet")
    if isinstance(note_tweet, dict):
        full_text = note_tweet.get("text")
        if isinstance(full_text, str) and full_text.strip():
            return full_text
    text = tweet.get("text")
    return text if isinstance(text, str) else ""


def tweet_to_raw_row(
    tweet: dict[str, Any],
    *,
    hashtag_type: str,
    query: str,
    window_start: str,
    window_end: str,
) -> dict[str, Any]:
    """Flatten the requested X post fields into the raw master CSV schema."""
    public_metrics = tweet.get("public_metrics") or {}
    collected_at = utc_now_iso()
    return {
        "post_id": tweet.get("id", ""),
        "created_at": tweet.get("created_at", ""),
        "author_id": tweet.get("author_id", ""),
        "text": tweet.get("text", ""),
        "post_text_full": note_tweet_text(tweet),
        "like_count": public_metrics.get("like_count", ""),
        "repost_count": public_metrics.get("retweet_count", ""),
        "reply_count": public_metrics.get("reply_count", ""),
        "quote_count": public_metrics.get("quote_count", ""),
        "bookmark_count": public_metrics.get("bookmark_count", ""),
        "impression_count": public_metrics.get("impression_count", ""),
        "lang": tweet.get("lang", ""),
        "hashtag_type": hashtag_type,
        "query": query,
        "month_window_start": window_start,
        "month_window_end": window_end,
        "collected_at": collected_at,
        "source_endpoint": SOURCE_ENDPOINT_LABEL,
        "raw_json": json.dumps(tweet, ensure_ascii=False, sort_keys=True),
    }


def append_unique_raw_rows(
    raw_path: Path,
    rows: list[dict[str, Any]],
    existing_post_ids: set[str],
) -> int:
    """Append rows whose post_id is not already in the raw master file."""
    ensure_csv_header(raw_path, RAW_MASTER_COLUMNS)
    rows_to_write: list[dict[str, Any]] = []

    for row in rows:
        post_id = str(row.get("post_id") or "").strip()
        if not post_id or post_id in existing_post_ids:
            continue
        rows_to_write.append(row)
        existing_post_ids.add(post_id)

    if not rows_to_write:
        return 0

    with raw_path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=RAW_MASTER_COLUMNS)
        for row in rows_to_write:
            writer.writerow({column: row.get(column, "") for column in RAW_MASTER_COLUMNS})

    return len(rows_to_write)


def build_request_params(
    *,
    query: str,
    window_start: str,
    window_end: str,
    max_results: int,
    next_token: str | None,
) -> dict[str, Any]:
    """Build full-archive search query parameters for one page."""
    params: dict[str, Any] = {
        "query": query,
        "start_time": window_start,
        "end_time": window_end,
        "max_results": max_results,
        "tweet.fields": ",".join(TWEET_FIELDS),
    }
    if next_token:
        params["next_token"] = next_token
    return params


def collect_month_window(
    *,
    session: requests.Session,
    state: dict[str, Any],
    hashtag_type: str,
    query: str,
    raw_path: Path,
    window_start: str,
    window_end: str,
    max_results: int,
    existing_post_ids: set[str],
    expected_count: int,
    quiet: bool,
) -> None:
    """Collect one hashtag/month window until pagination is exhausted."""
    key = month_key(window_start)
    entry = checkpoint_entry(state, hashtag_type, key, window_start, window_end)

    if entry.get("status") == "completed":
        write_collection_log(
            level="info",
            event="month_skipped_completed",
            hashtag_type=hashtag_type,
            query=query,
            month_window_start=window_start,
            month_window_end=window_end,
            message="Month window already completed in checkpoint.",
        )
        print_progress(
            f"{hashtag_type} {key}: already completed; "
            f"current unique rows={len(existing_post_ids):,}/{expected_count:,} "
            f"({progress_percent(len(existing_post_ids), expected_count)}).",
            quiet=quiet,
        )
        return

    next_token = entry.get("next_token")
    print_progress(
        f"{hashtag_type} {key}: starting window "
        f"({window_start} to {window_end}); "
        f"current unique rows={len(existing_post_ids):,}/{expected_count:,} "
        f"({progress_percent(len(existing_post_ids), expected_count)}).",
        quiet=quiet,
    )
    write_collection_log(
        level="info",
        event="month_started",
        hashtag_type=hashtag_type,
        query=query,
        month_window_start=window_start,
        month_window_end=window_end,
        next_token=next_token or "",
    )

    while True:
        context = {
            "hashtag_type": hashtag_type,
            "query": query,
            "month_window_start": window_start,
            "month_window_end": window_end,
            "next_token": next_token or "",
        }
        params = build_request_params(
            query=query,
            window_start=window_start,
            window_end=window_end,
            max_results=max_results,
            next_token=next_token,
        )

        response_json = get_json_with_retries(session, params, context)
        tweets = response_json.get("data") or []
        meta = response_json.get("meta") or {}

        raw_rows = [
            tweet_to_raw_row(
                tweet,
                hashtag_type=hashtag_type,
                query=query,
                window_start=window_start,
                window_end=window_end,
            )
            for tweet in tweets
        ]
        rows_written = append_unique_raw_rows(raw_path, raw_rows, existing_post_ids)

        next_token = meta.get("next_token")
        mark_window_progress(
            state,
            hashtag_type,
            key,
            next_token=next_token,
            rows_written_increment=rows_written,
        )

        write_collection_log(
            level="info",
            event="page_collected",
            hashtag_type=hashtag_type,
            query=query,
            month_window_start=window_start,
            month_window_end=window_end,
            next_token=next_token or "",
            status_code=200,
            rows_returned=len(tweets),
            rows_written=rows_written,
            message=f"API result_count={meta.get('result_count', '')}",
        )

        month_rows_written = int(
            state["hashtags"][hashtag_type][key].get("rows_written") or 0
        )
        page_state = "more pages remain" if next_token else "last page for month"
        print_progress(
            f"{hashtag_type} {key}: returned={len(tweets):,}, "
            f"new_rows_written={rows_written:,}, "
            f"month_new_rows={month_rows_written:,}, "
            f"total_unique_rows={len(existing_post_ids):,}/{expected_count:,} "
            f"({progress_percent(len(existing_post_ids), expected_count)}); "
            f"{page_state}.",
            quiet=quiet,
        )

        if not next_token:
            mark_window_completed(state, hashtag_type, key)
            write_collection_log(
                level="info",
                event="month_completed",
                hashtag_type=hashtag_type,
                query=query,
                month_window_start=window_start,
                month_window_end=window_end,
                rows_written=state["hashtags"][hashtag_type][key].get("rows_written", 0),
            )
            print_progress(
                f"{hashtag_type} {key}: completed. "
                f"Total unique rows for {hashtag_type} so far: "
                f"{len(existing_post_ids):,}/{expected_count:,} "
                f"({progress_percent(len(existing_post_ids), expected_count)}).",
                quiet=quiet,
            )
            return


def all_selected_windows_completed(
    state: dict[str, Any],
    selected_hashtags: list[str],
    windows: list[tuple[str, str]],
) -> bool:
    """Return True only if every selected hashtag/month is marked completed."""
    for hashtag_type in selected_hashtags:
        hashtag_state = state.get("hashtags", {}).get(hashtag_type, {})
        for window_start, _window_end in windows:
            entry = hashtag_state.get(month_key(window_start), {})
            if entry.get("status") != "completed":
                return False
    return True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect 2022 #cancel and #boycott posts from X full-archive search."
    )
    parser.add_argument(
        "--hashtags",
        nargs="+",
        choices=sorted(HASHTAG_CONFIG.keys()),
        default=sorted(HASHTAG_CONFIG.keys()),
        help="One or more hashtag datasets to collect.",
    )
    parser.add_argument(
        "--start-time",
        default=START_TIME,
        help="Collection start_time, inclusive, in UTC ISO format.",
    )
    parser.add_argument(
        "--end-time",
        default=END_TIME,
        help="Collection end_time, exclusive, in UTC ISO format.",
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=MAX_RESULTS,
        help="Results per request. X full-archive search allows up to 500.",
    )
    parser.add_argument(
        "--build-derived",
        action="store_true",
        help="After collection, build professor CSVs and the quality report if complete.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Do not print page-by-page progress messages to the terminal.",
    )
    parser.add_argument("--allow-live-api", action="store_true",
                        help="Explicitly enable potentially paid X API requests.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.allow_live_api:
        raise RuntimeError("Live API access is disabled. Review access and costs before using --allow-live-api.")
    if args.max_results < 10 or args.max_results > MAX_RESULTS:
        raise ValueError(f"--max-results must be between 10 and {MAX_RESULTS}.")

    load_local_token_files()
    bearer_token = os.environ.get(BEARER_TOKEN_ENV)
    if not bearer_token:
        raise RuntimeError(
            f"Missing bearer token. Set {BEARER_TOKEN_ENV} in your shell, "
            "x_api_token.env, or .env."
        )
    if bearer_token == "PASTE_YOUR_X_BEARER_TOKEN_HERE":
        raise RuntimeError(
            "The token file still contains the placeholder token. "
            "Paste your real X API Bearer Token into x_api_token.env first."
        )

    windows = monthly_windows(args.start_time, args.end_time)
    state = load_checkpoint()
    save_checkpoint(state)

    session = create_session(bearer_token)
    print_progress(
        f"Collection started for {', '.join(args.hashtags)} across "
        f"{len(windows)} monthly windows.",
        quiet=args.quiet,
    )
    write_collection_log(
        level="info",
        event="collection_started",
        message=(
            f"Collecting {', '.join(args.hashtags)} across {len(windows)} "
            f"monthly windows."
        ),
    )

    for hashtag_type in args.hashtags:
        config = HASHTAG_CONFIG[hashtag_type]
        query = config["query"]
        raw_path = config["raw_master_path"]
        expected_count = int(config["expected_count"])
        ensure_csv_header(raw_path, RAW_MASTER_COLUMNS)
        existing_post_ids = load_existing_post_ids(raw_path)
        print_progress(
            f"{hashtag_type}: raw file currently has "
            f"{len(existing_post_ids):,}/{expected_count:,} unique post IDs "
            f"({progress_percent(len(existing_post_ids), expected_count)}).",
            quiet=args.quiet,
        )

        for window_start, window_end in windows:
            collect_month_window(
                session=session,
                state=state,
                hashtag_type=hashtag_type,
                query=query,
                raw_path=raw_path,
                window_start=window_start,
                window_end=window_end,
                max_results=args.max_results,
                existing_post_ids=existing_post_ids,
                expected_count=expected_count,
                quiet=args.quiet,
            )

    write_collection_log(level="info", event="collection_finished")
    print_progress("Collection finished.", quiet=args.quiet)

    if args.build_derived:
        if all_selected_windows_completed(state, args.hashtags, windows):
            from src.preprocessing.build_professor_submission import build_all_professor_submissions
            from src.analysis.quality_check import build_quality_report

            build_all_professor_submissions(args.hashtags)
            build_quality_report(args.hashtags)
            write_collection_log(level="info", event="derived_files_built")
        else:
            write_collection_log(
                level="warning",
                event="derived_files_skipped",
                message="Not all selected windows are complete.",
            )

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("Interrupted. Progress already written to checkpoint/log files.", file=sys.stderr)
        raise SystemExit(130)
    except Exception as exc:
        write_collection_log(level="error", event="collection_failed", message=str(exc))
        print(f"Collection failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
