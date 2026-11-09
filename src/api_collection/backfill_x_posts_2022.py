"""Backfill missing 2022 #cancel and #boycott posts into existing raw CSVs.

This script reads the monthly gap report, re-searches selected month windows,
and appends only posts whose post_id is not already present in the raw master
CSV. It uses separate backfill logs and checkpoint state so it does not rely on
the original collection checkpoint.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from datetime import date, datetime, time as datetime_time, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

from src.api_collection.collect_x_posts_2022 import (
    ApiRequestError,
    append_unique_raw_rows,
    build_request_params,
    create_session,
    ensure_csv_header,
    is_retryable_status,
    load_existing_post_ids,
    load_local_token_files,
    progress_percent,
    rate_limit_wait_seconds,
    retry_backoff_seconds,
    tweet_to_raw_row,
    utc_now_iso,
)
from src.config import (
    BACKOFF_MAX_SECONDS,
    BEARER_TOKEN_ENV,
    FULL_ARCHIVE_SEARCH_URL,
    HASHTAG_CONFIG,
    LOGS_DIR,
    MAX_RESULTS,
    MAX_RETRIES,
    RAW_MASTER_COLUMNS,
    REPORTS_DIR,
    REQUEST_TIMEOUT_SECONDS,
)


DEFAULT_GAP_REPORT_PATH = REPORTS_DIR / "x_2022_monthly_collection_gap_report.csv"
BACKFILL_COLLECTION_LOG_PATH = LOGS_DIR / "backfill_collection_log.csv"
BACKFILL_FAILED_REQUESTS_LOG_PATH = LOGS_DIR / "backfill_failed_requests.csv"
BACKFILL_CHECKPOINT_STATE_PATH = LOGS_DIR / "backfill_checkpoint_state.json"

WINDOW_STEPS = {
    "day": timedelta(days=1),
    "hour": timedelta(hours=1),
    "minute15": timedelta(minutes=15),
    "minute5": timedelta(minutes=5),
}

BACKFILL_COLLECTION_LOG_COLUMNS = [
    "timestamp",
    "level",
    "event",
    "hashtag_type",
    "query",
    "target_month",
    "window_start",
    "window_end",
    "next_token",
    "status_code",
    "rows_returned",
    "rows_written",
    "existing_or_duplicate_rows",
    "total_unique_post_ids",
    "message",
]

BACKFILL_FAILED_REQUESTS_COLUMNS = [
    "timestamp",
    "hashtag_type",
    "query",
    "target_month",
    "window_start",
    "window_end",
    "next_token",
    "attempt",
    "status_code",
    "error_type",
    "will_retry",
    "message",
    "response_text",
]


def print_progress(message: str, *, quiet: bool = False) -> None:
    if not quiet:
        print(f"[{utc_now_iso()}] {message}", flush=True)


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def write_csv_row(path: Path, columns: list[str], row: dict[str, Any]) -> None:
    ensure_parent(path)
    file_exists = path.exists() and path.stat().st_size > 0
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        if not file_exists:
            writer.writeheader()
        writer.writerow({column: row.get(column, "") for column in columns})


def write_backfill_log(
    *,
    level: str,
    event: str,
    hashtag_type: str = "",
    query: str = "",
    target_month: str = "",
    window_start: str = "",
    window_end: str = "",
    next_token: str = "",
    status_code: str | int = "",
    rows_returned: str | int = "",
    rows_written: str | int = "",
    existing_or_duplicate_rows: str | int = "",
    total_unique_post_ids: str | int = "",
    message: str = "",
) -> None:
    write_csv_row(
        BACKFILL_COLLECTION_LOG_PATH,
        BACKFILL_COLLECTION_LOG_COLUMNS,
        {
            "timestamp": utc_now_iso(),
            "level": level,
            "event": event,
            "hashtag_type": hashtag_type,
            "query": query,
            "target_month": target_month,
            "window_start": window_start,
            "window_end": window_end,
            "next_token": next_token,
            "status_code": status_code,
            "rows_returned": rows_returned,
            "rows_written": rows_written,
            "existing_or_duplicate_rows": existing_or_duplicate_rows,
            "total_unique_post_ids": total_unique_post_ids,
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
    write_csv_row(
        BACKFILL_FAILED_REQUESTS_LOG_PATH,
        BACKFILL_FAILED_REQUESTS_COLUMNS,
        {
            "timestamp": utc_now_iso(),
            "hashtag_type": context.get("hashtag_type", ""),
            "query": context.get("query", ""),
            "target_month": context.get("target_month", ""),
            "window_start": context.get("window_start", ""),
            "window_end": context.get("window_end", ""),
            "next_token": context.get("next_token", ""),
            "attempt": attempt,
            "status_code": status_code,
            "error_type": error_type,
            "will_retry": will_retry,
            "message": message,
            "response_text": response_text[:5000],
        },
    )


def parse_utc_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def format_x_time(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def month_start_end(month: str) -> tuple[datetime, datetime]:
    year, month_number = [int(part) for part in month.split("-")]
    start = datetime(year, month_number, 1, tzinfo=timezone.utc)
    if month_number == 12:
        end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        end = datetime(year, month_number + 1, 1, tzinfo=timezone.utc)
    return start, end


def parse_day(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def split_range(
    start: datetime,
    end: datetime,
    step: timedelta,
) -> list[tuple[str, str]]:
    windows: list[tuple[str, str]] = []
    current = start
    while current < end:
        next_window = min(current + step, end)
        windows.append((format_x_time(current), format_x_time(next_window)))
        current = next_window
    return windows


def auto_granularity_for_count(tweet_count: int | None, max_window_count: int) -> str:
    if tweet_count is None or tweet_count <= max_window_count:
        return "day"
    if tweet_count <= max_window_count * 24:
        return "hour"
    if tweet_count <= max_window_count * 96:
        return "minute15"
    return "minute5"


def windows_for_month(
    month: str,
    granularity: str,
    *,
    selected_days: set[date] | None = None,
    daily_counts_by_day: dict[str, int] | None = None,
    auto_max_count: int = 400,
) -> list[tuple[str, str]]:
    start, end = month_start_end(month)
    if granularity == "month":
        if selected_days:
            return []
        return [(format_x_time(start), format_x_time(end))]

    windows: list[tuple[str, str]] = []
    current = start
    while current < end:
        next_day = min(current + timedelta(days=1), end)
        if selected_days and current.date() not in selected_days:
            current = next_day
            continue

        if granularity == "auto":
            day_count = (daily_counts_by_day or {}).get(current.date().isoformat())
            day_granularity = auto_granularity_for_count(day_count, auto_max_count)
            step = WINDOW_STEPS[day_granularity]
        else:
            step = WINDOW_STEPS[granularity]

        windows.extend(split_range(current, next_day, step))
        current = next_day
    return windows


def default_checkpoint() -> dict[str, Any]:
    return {
        "created_at": utc_now_iso(),
        "updated_at": utc_now_iso(),
        "endpoint": FULL_ARCHIVE_SEARCH_URL,
        "targets": {},
    }


def load_checkpoint(path: Path = BACKFILL_CHECKPOINT_STATE_PATH) -> dict[str, Any]:
    if not path.exists() or path.stat().st_size == 0:
        return default_checkpoint()
    with path.open("r", encoding="utf-8") as handle:
        state = json.load(handle)
    state.setdefault("targets", {})
    return state


def save_checkpoint(
    state: dict[str, Any],
    path: Path = BACKFILL_CHECKPOINT_STATE_PATH,
) -> None:
    ensure_parent(path)
    state["updated_at"] = utc_now_iso()
    temporary_path = path.with_suffix(".tmp")
    with temporary_path.open("w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2, sort_keys=True)
        handle.write("\n")
    temporary_path.replace(path)


def legacy_checkpoint_key(hashtag_type: str, target_month: str, window_start: str) -> str:
    return f"{hashtag_type}|{target_month}|{window_start}"


def checkpoint_key(
    hashtag_type: str,
    target_month: str,
    window_start: str,
    window_end: str,
) -> str:
    return f"{hashtag_type}|{target_month}|{window_start}|{window_end}"


def checkpoint_entry(
    state: dict[str, Any],
    *,
    hashtag_type: str,
    target_month: str,
    window_start: str,
    window_end: str,
) -> dict[str, Any]:
    key = checkpoint_key(hashtag_type, target_month, window_start, window_end)
    legacy_key = legacy_checkpoint_key(hashtag_type, target_month, window_start)
    if key not in state["targets"]:
        legacy_entry = state["targets"].get(legacy_key)
        if legacy_entry and legacy_entry.get("window_end") == window_end:
            state["targets"][key] = state["targets"].pop(legacy_key)

    return state["targets"].setdefault(
        key,
        {
            "status": "not_started",
            "hashtag_type": hashtag_type,
            "target_month": target_month,
            "window_start": window_start,
            "window_end": window_end,
            "next_token": None,
            "rows_returned": 0,
            "rows_written": 0,
        },
    )


def mark_progress(
    state: dict[str, Any],
    *,
    hashtag_type: str,
    target_month: str,
    window_start: str,
    window_end: str,
    next_token: str | None,
    rows_returned_increment: int,
    rows_written_increment: int,
) -> None:
    key = checkpoint_key(hashtag_type, target_month, window_start, window_end)
    entry = state["targets"][key]
    entry["status"] = "in_progress"
    entry["next_token"] = next_token
    entry["rows_returned"] = int(entry.get("rows_returned") or 0) + rows_returned_increment
    entry["rows_written"] = int(entry.get("rows_written") or 0) + rows_written_increment
    entry["last_page_at"] = utc_now_iso()
    save_checkpoint(state)


def mark_completed(
    state: dict[str, Any],
    *,
    hashtag_type: str,
    target_month: str,
    window_start: str,
    window_end: str,
    expected_window_count: int | None,
    rows_returned_last_run: int,
) -> None:
    key = checkpoint_key(hashtag_type, target_month, window_start, window_end)
    entry = state["targets"][key]
    entry["status"] = "completed"
    entry["next_token"] = None
    entry["completed_at"] = utc_now_iso()
    entry["expected_window_count"] = expected_window_count
    entry["rows_returned_last_run"] = rows_returned_last_run
    save_checkpoint(state)


def mark_underfilled(
    state: dict[str, Any],
    *,
    hashtag_type: str,
    target_month: str,
    window_start: str,
    window_end: str,
    expected_window_count: int,
    rows_returned_last_run: int,
    min_completion_ratio: float,
) -> None:
    key = checkpoint_key(hashtag_type, target_month, window_start, window_end)
    entry = state["targets"][key]
    entry["status"] = "underfilled"
    entry["next_token"] = None
    entry["underfilled_at"] = utc_now_iso()
    entry["expected_window_count"] = expected_window_count
    entry["rows_returned_last_run"] = rows_returned_last_run
    entry["min_completion_ratio"] = min_completion_ratio
    save_checkpoint(state)


def read_gap_targets(
    *,
    gap_report_path: Path,
    min_missing: int,
    hashtags: list[str] | None,
    months: list[str] | None,
) -> list[dict[str, Any]]:
    if not gap_report_path.exists():
        raise FileNotFoundError(f"Gap report not found: {gap_report_path}")

    selected_hashtags = set(hashtags or [])
    selected_months = set(months or [])
    targets: list[dict[str, Any]] = []

    with gap_report_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            hashtag_type = row["hashtag_type"]
            month = row["month"]
            missing_count = int(row["missing_count"])
            if selected_hashtags and hashtag_type not in selected_hashtags:
                continue
            if selected_months and month not in selected_months:
                continue
            if missing_count < min_missing:
                continue

            targets.append(
                {
                    "hashtag_type": hashtag_type,
                    "month": month,
                    "expected_count": int(row["expected_count"]),
                    "collected_unique_posts": int(row["collected_unique_posts"]),
                    "missing_count": missing_count,
                    "collection_rate": float(row["collection_rate"]),
                }
            )

    return sorted(targets, key=lambda target: target["missing_count"], reverse=True)


def load_daily_counts(path: Path) -> dict[str, int]:
    if not path.exists():
        raise FileNotFoundError(f"Daily Counts API CSV not found: {path}")

    counts_by_day: dict[str, int] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required_columns = {"start", "tweet_count"}
        missing_columns = required_columns - set(reader.fieldnames or [])
        if missing_columns:
            missing = ", ".join(sorted(missing_columns))
            raise ValueError(f"{path} is missing required column(s): {missing}")

        for row in reader:
            start_value = (row.get("start") or "").strip()
            count_value = (row.get("tweet_count") or "").strip()
            if not start_value or not count_value:
                continue
            day = parse_utc_datetime(start_value).date().isoformat()
            counts_by_day[day] = int(count_value)

    return counts_by_day


def load_daily_counts_by_hashtag(
    specs: list[str],
    selected_hashtags: list[str],
) -> dict[str, dict[str, int]]:
    counts_by_hashtag: dict[str, dict[str, int]] = {}
    for spec in specs:
        if "=" in spec:
            hashtag_type, raw_path = spec.split("=", 1)
            hashtag_type = hashtag_type.strip()
            path = Path(raw_path.strip()).expanduser()
        elif len(selected_hashtags) == 1:
            hashtag_type = selected_hashtags[0]
            path = Path(spec).expanduser()
        else:
            raise ValueError(
                "Use hashtag=path for --daily-counts-path when more than one "
                "hashtag target is selected."
            )

        if hashtag_type not in HASHTAG_CONFIG:
            raise ValueError(f"Unknown hashtag in --daily-counts-path: {hashtag_type}")
        counts_by_hashtag[hashtag_type] = load_daily_counts(path)

    return counts_by_hashtag


def expected_count_for_window(
    window_start: str,
    window_end: str,
    daily_counts_by_day: dict[str, int] | None,
) -> int | None:
    if not daily_counts_by_day:
        return None

    start = parse_utc_datetime(window_start)
    end = parse_utc_datetime(window_end)
    is_full_utc_day = (
        start.time() == datetime_time(0, 0)
        and end - start == timedelta(days=1)
    )
    if not is_full_utc_day:
        return None

    return daily_counts_by_day.get(start.date().isoformat())


def is_underfilled(
    rows_returned: int,
    expected_count: int | None,
    min_completion_ratio: float,
) -> bool:
    if expected_count is None or expected_count <= 0:
        return False
    return rows_returned < expected_count * min_completion_ratio


def reset_entry_for_rerun(entry: dict[str, Any]) -> None:
    entry["status"] = "not_started"
    entry["next_token"] = None
    entry["rows_returned"] = 0
    entry["rows_written"] = 0


def wait_for_request_slot(
    request_clock: dict[str, float | None],
    min_interval_seconds: float,
) -> None:
    if min_interval_seconds <= 0:
        request_clock["last_request_started_at"] = time.monotonic()
        return

    last_request_started_at = request_clock.get("last_request_started_at")
    if last_request_started_at is not None:
        elapsed = time.monotonic() - last_request_started_at
        wait_seconds = min_interval_seconds - elapsed
        if wait_seconds > 0:
            time.sleep(wait_seconds)

    request_clock["last_request_started_at"] = time.monotonic()


def get_json_with_retries(
    session: requests.Session,
    params: dict[str, Any],
    context: dict[str, Any],
    request_clock: dict[str, float | None],
    request_interval_seconds: float,
) -> dict[str, Any]:
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            wait_for_request_slot(request_clock, request_interval_seconds)
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
            sleep_seconds = min(retry_backoff_seconds(attempt), BACKOFF_MAX_SECONDS)
            write_backfill_log(
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
            write_backfill_log(
                level="warning",
                event="rate_limited",
                status_code=response.status_code,
                message=f"Sleeping {sleep_seconds}s until rate-limit reset.",
                **context,
            )
            time.sleep(sleep_seconds)
            continue

        if will_retry:
            sleep_seconds = min(retry_backoff_seconds(attempt), BACKOFF_MAX_SECONDS)
            write_backfill_log(
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


def backfill_window(
    *,
    session: requests.Session,
    state: dict[str, Any],
    hashtag_type: str,
    query: str,
    target_month: str,
    window_start: str,
    window_end: str,
    raw_path: Path,
    existing_post_ids: set[str],
    max_results: int,
    expected_total: int,
    expected_window_count: int | None,
    min_completion_ratio: float,
    request_clock: dict[str, float | None],
    request_interval_seconds: float,
    quiet: bool,
    ignore_checkpoint: bool,
) -> None:
    entry = checkpoint_entry(
        state,
        hashtag_type=hashtag_type,
        target_month=target_month,
        window_start=window_start,
        window_end=window_end,
    )
    completed_but_underfilled = (
        entry.get("status") == "completed"
        and not ignore_checkpoint
        and is_underfilled(
            int(entry.get("rows_returned_last_run") or entry.get("rows_returned") or 0),
            expected_window_count,
            min_completion_ratio,
        )
    )
    if (
        entry.get("status") == "completed"
        and not ignore_checkpoint
        and not completed_but_underfilled
    ):
        print_progress(
            f"{hashtag_type} {window_start[:10]}: already completed; "
            f"current unique rows={len(existing_post_ids):,}/{expected_total:,} "
            f"({progress_percent(len(existing_post_ids), expected_total)}).",
            quiet=quiet,
        )
        return

    if ignore_checkpoint or completed_but_underfilled:
        reset_entry_for_rerun(entry)
        if completed_but_underfilled:
            print_progress(
                f"{hashtag_type} {window_start[:10]}: completed checkpoint looks "
                f"underfilled; rerunning this window.",
                quiet=quiet,
            )

    next_token = None if ignore_checkpoint else entry.get("next_token")
    print_progress(
        f"{hashtag_type} {window_start[:10]}: backfill window started "
        f"({window_start} to {window_end}).",
        quiet=quiet,
    )

    rows_returned_this_run = 0
    rows_written_this_run = 0
    existing_or_duplicate_this_run = 0
    while True:
        context = {
            "hashtag_type": hashtag_type,
            "query": query,
            "target_month": target_month,
            "window_start": window_start,
            "window_end": window_end,
            "next_token": next_token or "",
        }
        params = build_request_params(
            query=query,
            window_start=window_start,
            window_end=window_end,
            max_results=max_results,
            next_token=next_token,
        )
        response_json = get_json_with_retries(
            session,
            params,
            context,
            request_clock,
            request_interval_seconds,
        )
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
        existing_or_duplicate_rows = len(tweets) - rows_written

        next_token = meta.get("next_token")
        rows_returned_this_run += len(tweets)
        rows_written_this_run += rows_written
        existing_or_duplicate_this_run += existing_or_duplicate_rows
        mark_progress(
            state,
            hashtag_type=hashtag_type,
            target_month=target_month,
            window_start=window_start,
            window_end=window_end,
            next_token=next_token,
            rows_returned_increment=len(tweets),
            rows_written_increment=rows_written,
        )

        write_backfill_log(
            level="info",
            event="page_collected",
            hashtag_type=hashtag_type,
            query=query,
            target_month=target_month,
            window_start=window_start,
            window_end=window_end,
            next_token=next_token or "",
            status_code=200,
            rows_returned=len(tweets),
            rows_written=rows_written,
            existing_or_duplicate_rows=existing_or_duplicate_rows,
            total_unique_post_ids=len(existing_post_ids),
            message=f"API result_count={meta.get('result_count', '')}",
        )

        print_progress(
            f"{hashtag_type} {window_start[:10]}: returned={len(tweets):,}, "
            f"new_rows_written={rows_written:,}, "
            f"existing_or_duplicate={existing_or_duplicate_rows:,}, "
            f"total_unique_rows={len(existing_post_ids):,}/{expected_total:,} "
            f"({progress_percent(len(existing_post_ids), expected_total)}).",
            quiet=quiet,
        )

        if not next_token:
            if is_underfilled(
                rows_returned_this_run,
                expected_window_count,
                min_completion_ratio,
            ):
                assert expected_window_count is not None
                mark_underfilled(
                    state,
                    hashtag_type=hashtag_type,
                    target_month=target_month,
                    window_start=window_start,
                    window_end=window_end,
                    expected_window_count=expected_window_count,
                    rows_returned_last_run=rows_returned_this_run,
                    min_completion_ratio=min_completion_ratio,
                )
                write_backfill_log(
                    level="warning",
                    event="window_underfilled",
                    hashtag_type=hashtag_type,
                    query=query,
                    target_month=target_month,
                    window_start=window_start,
                    window_end=window_end,
                    rows_returned=rows_returned_this_run,
                    rows_written=rows_written_this_run,
                    existing_or_duplicate_rows=existing_or_duplicate_this_run,
                    total_unique_post_ids=len(existing_post_ids),
                    message=(
                        f"Expected about {expected_window_count} rows from daily "
                        f"Counts API, but Search API returned {rows_returned_this_run}. "
                        "Retry with --window-granularity hour, minute15, minute5, "
                        "or auto."
                    ),
                )
                print_progress(
                    f"{hashtag_type} {window_start[:10]}: underfilled "
                    f"({rows_returned_this_run:,}/{expected_window_count:,} "
                    f"returned, {rows_written_this_run:,} new rows written). "
                    "Use a smaller window for this spike day.",
                    quiet=quiet,
                )
                return

            mark_completed(
                state,
                hashtag_type=hashtag_type,
                target_month=target_month,
                window_start=window_start,
                window_end=window_end,
                expected_window_count=expected_window_count,
                rows_returned_last_run=rows_returned_this_run,
            )
            write_backfill_log(
                level="info",
                event="window_completed",
                hashtag_type=hashtag_type,
                query=query,
                target_month=target_month,
                window_start=window_start,
                window_end=window_end,
                rows_returned=rows_returned_this_run,
                rows_written=rows_written_this_run,
                existing_or_duplicate_rows=existing_or_duplicate_this_run,
                total_unique_post_ids=len(existing_post_ids),
                message=(
                    f"Window completed; returned={rows_returned_this_run}, "
                    f"new_rows_written={rows_written_this_run}, "
                    f"existing_or_duplicate={existing_or_duplicate_this_run}"
                ),
            )
            print_progress(
                f"{hashtag_type} {window_start} -> {window_end}: "
                f"window completed; returned={rows_returned_this_run:,}, "
                f"new_rows_written={rows_written_this_run:,}, "
                f"existing_or_duplicate={existing_or_duplicate_this_run:,}, "
                f"total_unique_rows={len(existing_post_ids):,}/{expected_total:,} "
                f"({progress_percent(len(existing_post_ids), expected_total)}).",
                quiet=quiet,
            )
            return


def refresh_reports(hashtags: list[str], *, quiet: bool) -> None:
    from src.analysis.build_collected_monthly_counts import build_all_collected_monthly_counts
    from src.analysis.build_monthly_gap_report import write_gap_report

    monthly_paths = build_all_collected_monthly_counts(hashtags)
    gap_report_path = write_gap_report(DEFAULT_GAP_REPORT_PATH)
    for path in monthly_paths:
        print_progress(f"Refreshed {path}", quiet=quiet)
    print_progress(f"Refreshed {gap_report_path}", quiet=quiet)


def build_derived_files(hashtags: list[str], *, quiet: bool) -> None:
    from src.preprocessing.build_professor_submission import build_all_professor_submissions
    from src.analysis.quality_check import build_quality_report

    professor_paths = build_all_professor_submissions(hashtags)
    quality_path = build_quality_report(hashtags)
    for path in professor_paths:
        print_progress(f"Wrote {path}", quiet=quiet)
    print_progress(f"Wrote {quality_path}", quiet=quiet)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill large 2022 monthly gaps into existing raw X CSVs."
    )
    parser.add_argument(
        "--gap-report",
        type=Path,
        default=DEFAULT_GAP_REPORT_PATH,
        help="Monthly gap report generated by build_monthly_gap_report.py.",
    )
    parser.add_argument(
        "--min-missing",
        type=int,
        default=1000,
        help="Backfill months with at least this many missing posts.",
    )
    parser.add_argument(
        "--hashtags",
        nargs="+",
        choices=sorted(HASHTAG_CONFIG.keys()),
        default=None,
        help="Optional hashtag filter.",
    )
    parser.add_argument(
        "--months",
        nargs="+",
        default=None,
        help="Optional month filter, e.g. 2022-08 2022-09.",
    )
    parser.add_argument(
        "--window-granularity",
        choices=["auto", "minute5", "minute15", "hour", "day", "month"],
        default="day",
        help=(
            "Split selected months into month, day, hour, 15-minute, 5-minute, "
            "or Counts-driven auto windows."
        ),
    )
    parser.add_argument(
        "--days",
        nargs="+",
        default=None,
        help="Optional UTC day filter, e.g. 2022-09-07 2022-09-08.",
    )
    parser.add_argument(
        "--start-day",
        type=parse_day,
        default=None,
        help="Optional inclusive UTC range start, e.g. 2022-09-08.",
    )
    parser.add_argument(
        "--end-day",
        type=parse_day,
        default=None,
        help="Optional inclusive UTC range end, e.g. 2022-12-31.",
    )
    parser.add_argument(
        "--daily-counts-path",
        action="append",
        default=[],
        help=(
            "Optional Counts API daily CSV path. Use hashtag=path when more "
            "than one hashtag target is selected."
        ),
    )
    parser.add_argument(
        "--auto-max-count",
        type=int,
        default=400,
        help="For --window-granularity auto, target this many counted posts per window.",
    )
    parser.add_argument(
        "--min-completion-ratio",
        type=float,
        default=0.8,
        help=(
            "With --daily-counts-path, mark a full-day window underfilled if "
            "Search returns less than this fraction of the daily Counts total."
        ),
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=MAX_RESULTS,
        help="Results per request. X full-archive search allows up to 500.",
    )
    parser.add_argument(
        "--request-interval-seconds",
        type=float,
        default=3.2,
        help=(
            "Minimum seconds between X API search requests. The default keeps "
            "the original request pacing; verify current account limits before use."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print selected backfill targets without calling the X API.",
    )
    parser.add_argument(
        "--ignore-checkpoint",
        action="store_true",
        help="Re-run selected windows even if the backfill checkpoint says completed.",
    )
    parser.add_argument(
        "--no-refresh-reports",
        action="store_true",
        help="Do not rebuild monthly collected-count reports and gap report afterward.",
    )
    parser.add_argument(
        "--build-derived",
        action="store_true",
        help="After backfill, rebuild professor submission CSVs and quality report.",
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
    if args.max_results < 10 or args.max_results > MAX_RESULTS:
        raise ValueError(f"--max-results must be between 10 and {MAX_RESULTS}.")
    if args.auto_max_count <= 0:
        raise ValueError("--auto-max-count must be positive.")
    if not 0 < args.min_completion_ratio <= 1:
        raise ValueError("--min-completion-ratio must be greater than 0 and at most 1.")
    if args.request_interval_seconds < 0:
        raise ValueError("--request-interval-seconds cannot be negative.")
    has_day_range = args.start_day is not None or args.end_day is not None
    if has_day_range and (args.start_day is None or args.end_day is None):
        raise ValueError("Use --start-day and --end-day together.")
    if args.days and has_day_range:
        raise ValueError("Use either --days or --start-day/--end-day, not both.")
    if args.window_granularity == "month" and (args.days or has_day_range):
        raise ValueError(
            "Day filters cannot be combined with --window-granularity month."
        )
    if has_day_range and args.start_day > args.end_day:
        raise ValueError("--start-day cannot be later than --end-day.")

    if args.days:
        selected_days = {parse_day(day) for day in args.days}
    elif has_day_range:
        selected_days = set()
        current_day = args.start_day
        while current_day <= args.end_day:
            selected_days.add(current_day)
            current_day += timedelta(days=1)
    else:
        selected_days = None

    target_months = args.months
    if selected_days:
        selected_day_months = {day.strftime("%Y-%m") for day in selected_days}
        if target_months:
            omitted_months = selected_day_months - set(target_months)
            if omitted_months:
                raise ValueError(
                    "--months is missing month(s) required by the selected days: "
                    + ", ".join(sorted(omitted_months))
                )
        else:
            target_months = sorted(selected_day_months)

    targets = read_gap_targets(
        gap_report_path=args.gap_report,
        min_missing=args.min_missing,
        hashtags=args.hashtags,
        months=target_months,
    )
    if not targets:
        print("No backfill targets matched the selected criteria.")
        return 0
    if has_day_range:
        targets.sort(key=lambda target: (target["month"], target["hashtag_type"]))

    selected_hashtags = sorted({target["hashtag_type"] for target in targets})
    daily_counts_by_hashtag = load_daily_counts_by_hashtag(
        args.daily_counts_path,
        selected_hashtags,
    )
    if args.window_granularity == "auto" and not daily_counts_by_hashtag:
        raise ValueError("--window-granularity auto requires --daily-counts-path.")

    total_expected_to_search = sum(target["expected_count"] for target in targets)
    total_missing = sum(target["missing_count"] for target in targets)
    print_progress(
        f"Selected {len(targets)} month target(s); expected posts in those months="
        f"{total_expected_to_search:,}, current missing={total_missing:,}.",
        quiet=args.quiet,
    )
    total_selected_windows = 0
    total_expected_in_selected_days = 0
    for target in targets:
        target_windows = windows_for_month(
            target["month"],
            args.window_granularity,
            selected_days=selected_days,
            daily_counts_by_day=daily_counts_by_hashtag.get(target["hashtag_type"]),
            auto_max_count=args.auto_max_count,
        )
        total_selected_windows += len(target_windows)
        if selected_days:
            daily_counts = daily_counts_by_hashtag.get(target["hashtag_type"], {})
            total_expected_in_selected_days += sum(
                daily_counts.get(day.isoformat(), 0)
                for day in selected_days
                if day.strftime("%Y-%m") == target["month"]
            )
        print_progress(
            f"Target {target['hashtag_type']} {target['month']}: "
            f"expected={target['expected_count']:,}, "
            f"collected={target['collected_unique_posts']:,}, "
            f"missing={target['missing_count']:,}, "
            f"windows={len(target_windows)}.",
            quiet=args.quiet,
        )

    if selected_days:
        print_progress(
            f"Selected day filter: days={len(selected_days):,}, "
            f"expected_posts_in_selected_days={total_expected_in_selected_days:,}, "
            f"windows={total_selected_windows:,}.",
            quiet=args.quiet,
        )

    if args.dry_run:
        return 0

    if not args.allow_live_api:
        raise RuntimeError("Live API access is disabled. Use --dry-run or explicitly pass --allow-live-api.")

    load_local_token_files()
    bearer_token = os.environ.get(BEARER_TOKEN_ENV)
    if not bearer_token:
        raise RuntimeError(
            f"Missing bearer token. Set {BEARER_TOKEN_ENV} in x_api_token.env."
        )
    if bearer_token == "PASTE_YOUR_X_BEARER_TOKEN_HERE":
        raise RuntimeError(
            "The token file still contains the placeholder token. "
            "Paste your real X API Bearer Token into x_api_token.env first."
        )

    state = load_checkpoint()
    save_checkpoint(state)
    session = create_session(bearer_token)
    request_clock: dict[str, float | None] = {"last_request_started_at": None}

    existing_ids_by_hashtag: dict[str, set[str]] = {}
    expected_totals = {
        hashtag_type: int(HASHTAG_CONFIG[hashtag_type]["expected_count"])
        for hashtag_type in selected_hashtags
    }

    for hashtag_type in selected_hashtags:
        raw_path = HASHTAG_CONFIG[hashtag_type]["raw_master_path"]
        ensure_csv_header(raw_path, RAW_MASTER_COLUMNS)
        existing_ids_by_hashtag[hashtag_type] = load_existing_post_ids(raw_path)
        print_progress(
            f"{hashtag_type}: raw file starts with "
            f"{len(existing_ids_by_hashtag[hashtag_type]):,}/"
            f"{expected_totals[hashtag_type]:,} unique post IDs.",
            quiet=args.quiet,
        )

    write_backfill_log(
        level="info",
        event="backfill_started",
        message=(
            f"targets={len(targets)}, expected_posts_in_targets="
            f"{total_expected_to_search}, current_missing={total_missing}"
        ),
    )

    for target in targets:
        hashtag_type = target["hashtag_type"]
        config = HASHTAG_CONFIG[hashtag_type]
        raw_path = config["raw_master_path"]
        query = config["query"]
        daily_counts_by_day = daily_counts_by_hashtag.get(hashtag_type)
        for window_start, window_end in windows_for_month(
            target["month"],
            args.window_granularity,
            selected_days=selected_days,
            daily_counts_by_day=daily_counts_by_day,
            auto_max_count=args.auto_max_count,
        ):
            backfill_window(
                session=session,
                state=state,
                hashtag_type=hashtag_type,
                query=query,
                target_month=target["month"],
                window_start=window_start,
                window_end=window_end,
                raw_path=raw_path,
                existing_post_ids=existing_ids_by_hashtag[hashtag_type],
                max_results=args.max_results,
                expected_total=expected_totals[hashtag_type],
                expected_window_count=expected_count_for_window(
                    window_start,
                    window_end,
                    daily_counts_by_day,
                ),
                min_completion_ratio=args.min_completion_ratio,
                request_clock=request_clock,
                request_interval_seconds=args.request_interval_seconds,
                quiet=args.quiet,
                ignore_checkpoint=args.ignore_checkpoint,
            )

    write_backfill_log(level="info", event="backfill_finished")
    print_progress("Backfill finished.", quiet=args.quiet)

    if not args.no_refresh_reports:
        refresh_reports(selected_hashtags, quiet=args.quiet)

    if args.build_derived:
        build_derived_files(selected_hashtags, quiet=args.quiet)

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("Interrupted. Backfill progress was saved.", file=sys.stderr)
        raise SystemExit(130)
    except Exception as exc:
        write_backfill_log(level="error", event="backfill_failed", message=str(exc))
        print(f"Backfill failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
