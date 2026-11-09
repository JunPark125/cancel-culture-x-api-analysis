# Offline validation

Validation date: **2026-11-09**. No live X or model API operation was executed.

The portfolio was checked with Python 3.13 in a new isolated virtual environment. Installed direct dependencies were requests 2.34.2, pandas 2.3.3, Matplotlib 3.11.2, and Tweepy 4.17.0. `pip check` found no broken requirements. Version ranges in `requirements.txt` are not an exact environment lock; other supported Python versions were not tested.

Thirteen offline tests passed. They cover:

- Contiguous time windows and partial-month boundaries.
- Duplicate suppression across file reloads and full-text fallback.
- Paginated collection interrupted after a page, persisted resume tokens, and completed-window skipping.
- HTTP 429 waits, later reset-header selection, bounded transport retries, permanent HTTP errors, and invalid JSON.
- Backfill subdivision, distinct checkpoint keys, and underfilled-day status.
- Counts pagination and daily/monthly/yearly total reconciliation on synthetic buckets.
- CSV validation, invalid timestamps, year boundaries, export ordering, and arithmetic gaps.
- Live-execution guards, credential-free backfill dry-run, and the plot's retained zero-fill behavior.

Tests block socket connections and use synthetic API responses. The offline demo separately blocks network connections and exercises the copied flattening, deduplication, export, monthly-count, quality, and gap-report functions. Plot output was generated only as a temporary synthetic test artifact.

Python source and notebook code cells were parsed; original notebook outputs and execution counts were removed. Relative Markdown links were checked. The local release audit records exact staged paths, credential comparisons, original-file integrity checks, and Git history review. External ownership and sharing permission are separate requirements and cannot be established by automated tests.

The tests verify selected behaviors; they do not prove production robustness, research completeness, real-world classifier accuracy, or current API entitlement. Existing limitations are listed in [methodology](methodology.md).
