# Source provenance and preparation changes

All source research folders were preserved. The following paths are relative to the original `Cancel_culture` workspace and identify provenance, not files distributed with this repository.

| Original source | Portfolio copy or extraction | Changes |
|---|---|---|
| `Hashtag_cancel_bboycott/x_2022_cancel_boycott_project/src/config.py` | `src/config.py` | Portable runtime data directory; original unpublished baseline values replaced by optional environment settings |
| Same original `src/collect_x_posts_2022.py` | `src/api_collection/collect_x_posts_2022.py` | Package imports; explicit live-API CLI flag |
| Same original `src/backfill_x_posts_2022.py` | `src/api_collection/backfill_x_posts_2022.py` | Package imports; live flag after dry-run branch; rate-limit help text no longer asserts a current quota |
| Same original `src/build_professor_submission.py` | `src/preprocessing/build_professor_submission.py` | Package imports only |
| Same original `src/build_collected_monthly_counts.py`, `quality_check.py` | `src/analysis/` matching modules | Package imports only |
| Same original `src/build_monthly_gap_report.py` | `src/analysis/build_monthly_gap_report.py` | Package imports; counts reference under the new data root |
| `project2 for Trend/cancel_trend.ipynb`, original cell 3 | Historical collection and aggregation modules | Parameterized bearer token, CLI wrapper, explicit live flag; removed obsolete cost estimate; aggregation retained |
| Same notebook, original cell 7 | `src/visualization/monthly_trends.py` | Explicit input/output paths and title; original outer merge, zero-fill, and plotting retained |
| Same original notebook | `notebooks/historical_trends.ipynb` | Outputs/metadata removed; shared functions substituted; duplicate explanatory code removed; live requests disabled by default |
| `Hashtag_cancel_bboycott/x_2022_cancel_boycott_project/compare/compare.ipynb` | `notebooks/collected_monthly_counts.ipynb` | Outputs/metadata removed; repository-root detection |
| `balenciaga_test.py` | `src/api_collection/balenciaga_pilot.py` | Removed embedded credential; main guard and live flag; private output path; original query, fixed interval, single-page behavior retained |

No raw or derived CSV was copied into the release. Existing plot outputs, report documents, model-labeling prompts/scripts, logs, checkpoint states, token files, and local environments are excluded. File-level inventory, SHA-256 hashes, exact data statistics, and count-version reconciliation are retained in the separate local audit.

The collection and processing modules are source copies with documented edits, not newly invented evidence of prior functionality. Synthetic fixtures, tests, the demo, and documentation are new preparation artifacts.
