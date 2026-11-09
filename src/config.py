"""Shared configuration for the 2022 X hashtag collection workflow."""

from pathlib import Path
import os


PROJECT_ROOT = Path(__file__).resolve().parents[1]

DATA_DIR = Path(os.environ.get("X_DATA_DIR", str(PROJECT_ROOT / "data"))).expanduser().resolve()
RAW_DIR = DATA_DIR / "raw"
PROFESSOR_SUBMISSION_DIR = DATA_DIR / "professor_submission"
PROCESSED_DIR = DATA_DIR / "processed"
REPORTS_DIR = DATA_DIR / "reports"
LOGS_DIR = DATA_DIR / "logs"

BEARER_TOKEN_ENV = "X_BEARER_TOKEN"
ENV_FILE_PATH = PROJECT_ROOT / ".env"
VISIBLE_TOKEN_FILE_PATH = PROJECT_ROOT / "x_api_token.env"

# X API v2 full-archive search endpoint.
FULL_ARCHIVE_SEARCH_URL = "https://api.twitter.com/2/tweets/search/all"
SOURCE_ENDPOINT_LABEL = "GET /2/tweets/search/all"

START_TIME = "2022-01-01T00:00:00Z"
END_TIME = "2023-01-01T00:00:00Z"

# Full-archive search allows up to 500 results per request.
MAX_RESULTS = 500

REQUEST_TIMEOUT_SECONDS = 30
MAX_RETRIES = 6
BACKOFF_BASE_SECONDS = 2
BACKOFF_MAX_SECONDS = 300
RATE_LIMIT_BUFFER_SECONDS = 10

TWEET_FIELDS = [
    "id",
    "text",
    "created_at",
    "author_id",
    "public_metrics",
    "lang",
    "entities",
    "referenced_tweets",
    "conversation_id",
    "in_reply_to_user_id",
    "note_tweet",
]

# Research baseline totals are intentionally omitted. Zero means unspecified,
# not an observed zero. Supply authorized totals through the environment.
HASHTAG_CONFIG = {
    "cancel": {
        "query": "#cancel -is:retweet lang:en",
        "expected_count": int(os.environ.get("X_CANCEL_EXPECTED_COUNT", "0")),
        "raw_master_path": RAW_DIR / "x_2022_cancel_raw_master.csv",
        "professor_submission_path": (
            PROFESSOR_SUBMISSION_DIR / "x_2022_cancel_posts.csv"
        ),
    },
    "boycott": {
        "query": "#boycott -is:retweet lang:en",
        "expected_count": int(os.environ.get("X_BOYCOTT_EXPECTED_COUNT", "0")),
        "raw_master_path": RAW_DIR / "x_2022_boycott_raw_master.csv",
        "professor_submission_path": (
            PROFESSOR_SUBMISSION_DIR / "x_2022_boycott_posts.csv"
        ),
    },
}

RAW_MASTER_COLUMNS = [
    "post_id",
    "created_at",
    "author_id",
    "text",
    "post_text_full",
    "like_count",
    "repost_count",
    "reply_count",
    "quote_count",
    "bookmark_count",
    "impression_count",
    "lang",
    "hashtag_type",
    "query",
    "month_window_start",
    "month_window_end",
    "collected_at",
    "source_endpoint",
    "raw_json",
]

PROFESSOR_SUBMISSION_COLUMNS = [
    "timestamp",
    "user_id",
    "post_text",
    "like_count",
    "repost_count",
]

QUALITY_REPORT_PATH = REPORTS_DIR / "x_2022_quality_report.csv"
COLLECTION_LOG_PATH = LOGS_DIR / "collection_log.csv"
FAILED_REQUESTS_LOG_PATH = LOGS_DIR / "failed_requests.csv"
CHECKPOINT_STATE_PATH = LOGS_DIR / "checkpoint_state.json"

COLLECTION_LOG_COLUMNS = [
    "timestamp",
    "level",
    "event",
    "hashtag_type",
    "query",
    "month_window_start",
    "month_window_end",
    "next_token",
    "status_code",
    "rows_returned",
    "rows_written",
    "message",
]

FAILED_REQUESTS_COLUMNS = [
    "timestamp",
    "hashtag_type",
    "query",
    "month_window_start",
    "month_window_end",
    "next_token",
    "attempt",
    "status_code",
    "error_type",
    "will_retry",
    "message",
    "response_text",
]

QUALITY_REPORT_COLUMNS = [
    "hashtag_type",
    "expected_count",
    "collected_rows",
    "unique_post_ids",
    "duplicate_post_ids",
    "missing_created_at",
    "missing_author_id",
    "missing_text",
    "missing_like_count",
    "missing_repost_count",
    "rows_outside_2022",
    "first_timestamp",
    "last_timestamp",
]
