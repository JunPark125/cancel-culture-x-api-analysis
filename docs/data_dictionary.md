# Data dictionary

Schemas below describe private runtime files; no original records are included.

## Historical Counts API tables

| Field | Meaning |
|---|---|
| `start`, `end` | UTC bucket boundaries; daily source rows |
| `tweet_count` | API-reported matches in the bucket, not stored post rows |
| `year`, `month` | Derived aggregation keys (`YYYY`, `YYYY-MM`) |
| `monthly_count`, `yearly_count` | Sums of daily bucket counts |

The filenames identify a nominal research interval. Verify actual boundaries and source versions; a filename does not establish query provenance or equivalence.

## Raw post master schema

| Fields | Type and meaning |
|---|---|
| `post_id`, `author_id` | Identifiers retained as strings; restricted |
| `created_at` | Original post timestamp in UTC |
| `text`, `post_text_full` | Returned text and long-form text fallback; restricted |
| `like_count`, `repost_count`, `reply_count`, `quote_count` | Available public metrics; repost maps from `retweet_count` |
| `bookmark_count`, `impression_count` | Optional metrics when returned; blank is not zero |
| `lang` | Returned language code |
| `hashtag_type`, `query` | Dataset label and exact request query |
| `month_window_start`, `month_window_end` | Request boundaries; in backfill these may be submonthly despite the field names |
| `collected_at`, `source_endpoint` | Collection timestamp and endpoint label |
| `raw_json` | Serialized original post object; potentially contains additional identifiers and metadata |

`entities`, `referenced_tweets`, `conversation_id`, and `in_reply_to_user_id` are requested but retained inside `raw_json`, not flattened into their own columns. Deduplication is per hashtag, so cross-hashtag overlap is not removed automatically.

## Derived schemas

| Table | Fields and interpretation |
|---|---|
| Simplified export | `timestamp` (date only), `user_id`, `post_text`, `like_count`, `repost_count`; retains personal data |
| Collected monthly counts | `hashtag_type`, `month`, `collected_rows`, `unique_post_count`; counts retrieved records |
| Quality report | Baseline, row/ID totals, duplicates, missing fields, out-of-year rows, first/last timestamps |
| Monthly gap report | Baseline, row/unique totals, arithmetic gap, ratio, severity, recommendation, proposed backfill boundaries |
| Operational logs | Request context, pagination state, status, timing, and error response snippets; restricted |
| Checkpoints | Window status, next pagination token, row counters, and timestamps; restricted |

The configuration's optional `expected_count` is a progress reference. In this portfolio, `0` means **unspecified** unless an authorized baseline is supplied; do not interpret it as a research observation.

X-specific labeled exports were found separately, with relevance, confidence, filter reason, target type, and target-name columns. They are excluded, and no validity claim is made for those labels.
