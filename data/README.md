# Data availability

## Historical Counts API chart inputs

The released historical tables are exact copies of the two monthly inputs from the original `project2 for Trend/#hashtag_year_month/` directory. Each has 132 rows, one per UTC month from January 2015 to December 2025. `month` is a YYYY-MM bucket and `monthly_count` is the X API match count aggregated over that month. The queries were `#cancel -is:retweet lang:en` and `#boycott -is:retweet lang:en`. The distinct daily-derived series stays separate because its values differ from these chart inputs. [Cancel monthly CSV](historical/x_cancel_monthly_counts_2015_2025.csv) · [Boycott monthly CSV](historical/x_boycott_monthly_counts_2015_2025.csv)

## 2022 collection audit

The 2022 collection file audit is a two-row summary computed from the saved raw-master files for `#cancel` and `#boycott`. It records stored rows, distinct IDs, duplicate and missing IDs, invalid timestamps, and rows outside the 2022 UTC window. These are file checks based on parsing the two CSVs and comparing IDs in memory. The exported summary contains only collection labels and counters. [Collection audit CSV](summary/2022_collection_file_audit.csv).

Post records, ID lists, daily count buckets, and the remaining time series stay in the research workspace. The sample fixture contains invented records for offline testing. Runtime subdirectories are ignored by Git. [Sample fixture](sample/README.md) · [Data dictionary](../docs/data_dictionary.md) · [Usage guide](../docs/usage.md)
