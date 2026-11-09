# Methodology and implementation boundaries

## Queries and time boundaries

Primary queries are `#cancel -is:retweet lang:en` and `#boycott -is:retweet lang:en`. These are hashtag searches, not a comprehensive vocabulary of cancellation or boycotting language. The `lang:en` operator depends on platform language classification. Excluding retweets does not exclude replies or quote posts.

Historical requests cover `[2015-01-01T00:00:00Z, 2026-01-01T00:00:00Z)`. Post collection defaults to `[2022-01-01T00:00:00Z, 2023-01-01T00:00:00Z)`. Start is inclusive and end is exclusive in the implemented window construction. Original notebook source supplies the exact query syntax; prose reports contain shorthand and are not the authority for reconstructing a request.

## Historical counts

`api_collection/historical_counts.py` extracts the original notebook's daily counts request loop. It follows `meta.next_token`, waits 60 seconds on HTTP 429, raises other HTTP errors, and sleeps one second between successful pages. It has no persistent checkpoint, bounded 429 retry budget, or explicit transport-error recovery. Successful response-page counts are not a billable-request ledger.

`analysis/historical_counts.py` converts timestamps to UTC, casts `tweet_count` to integer, sorts daily buckets, and sums them by month and year. No normalization by overall platform activity, significance test, causal model, or semantic relevance filter is implemented in this branch.

`visualization/monthly_trends.py` preserves the original outer join on month and zero-fill rule. Zero filling missing series values can hide missing coverage. Use inputs from one documented version and verify coverage before interpretation. The original plot reads a separate set of monthly files; that set differs from the daily-derived tables in the trend directory. Neither is silently substituted for the other here.

## Individual post collection

`collect_x_posts_2022.py` splits the time interval into monthly windows, requests the configured post fields, and follows pagination. It flattens each post into the raw schema and uses a set of existing IDs to prevent duplicate appends within each hashtag dataset. `note_tweet.text` is preferred when present. The original JSON is preserved in private runtime output.

The collector handles request exceptions and selected retryable HTTP statuses with up to six attempts. Backoff is exponential and capped; HTTP 429 waits use numeric `retry-after` or `x-rate-limit-reset` headers plus a buffer, with a fallback. Invalid JSON is an explicit failure. Checkpoints are written to a temporary file and replaced atomically after a page write; completed windows are skipped on restart.

Completion means the selected pagination windows were exhausted, not that the collected posts equal all Counts API matches. Availability, retrieval timing, query alignment, deletions, and endpoint behavior can affect comparisons; the files alone do not identify which cause explains a particular gap.

## Processing and backfill

- The simplified export keeps calendar date, author ID, preferred text, likes, and reposts, with stable sorting by full timestamp before reducing to date. It is still identifying research data.
- Quality checks report total rows, unique and repeated IDs, missing core fields, invalid/missing timestamps, and rows outside 2022. A missing input produces a zero-row quality entry in the original implementation; this must not be mistaken for a successful empty collection.
- The monthly-count CLI emits observed months and separately counts CSV rows and unique nonblank IDs. The copied comparison notebook fills all 12 months; its pandas aggregation also treats blank IDs differently from the CLI. These are distinct implementations. Gap reporting uses baseline months and defaults absent collected months to zero.
- The gap report subtracts unique collected posts from monthly API counts and assigns the original absolute-gap thresholds. Its rate is zero when the baseline is zero; the value is not statistical coverage in that case.
- Backfill ranks selected months by missing count and supports month, day, hour, 15-minute, or 5-minute windows. Automatic subdivision uses daily Counts API totals and a configurable threshold; it does not assume actual within-day activity is uniform.
- Backfill has its own logs/checkpoints, minimum request spacing, and underfilled-day detection. Only whole-day windows have a directly comparable expected count. The underfill heuristic measures rows returned in the current invocation, so a resumed partial-day search can be conservatively marked underfilled.

## Known reliability limits preserved

There is no database transaction connecting CSV append and checkpoint replacement, no file locking for concurrent writers, and no general automatic recovery for an expired pagination token. A fresh process rereads CSV IDs to reduce duplicate risk after interruption. Main-collector checkpoint keys contain hashtag and month, not the full query or partial interval: use isolated data directories for different runs and do not reuse checkpoints after changing a query/window.

Backfill report refresh currently expects both hashtags' monthly inputs even when only one is selected. Provide both baseline/report pairs or use `--no-refresh-reports` and rebuild explicitly. Both the gap report and quality checks are fixed to 2022 even though collection accepts custom dates. These behaviors are documented rather than silently redesigned.

## Portfolio changes

Module imports and paths were reorganized; `X_DATA_DIR` can isolate runtime artifacts. Unpublished numeric baselines were removed from code. Live CLI entry points require explicit opt-in, notebook outputs and execution metadata were cleared, an embedded pilot credential was replaced with an environment lookup, and obsolete notebook pricing estimates were removed. Tests and the synthetic demo are new portfolio preparation work. No substantive collection or research algorithm was changed. See [source provenance](source_provenance.md).
