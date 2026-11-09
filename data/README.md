# Data availability

The 2022 collection file audit is a two-row summary computed from the saved raw-master files for `#cancel` and `#boycott`. It records stored rows, distinct IDs, duplicate and missing IDs, invalid timestamps, and rows outside the 2022 UTC window. These are file checks based on parsing the two CSVs and comparing IDs in memory. The exported summary contains only collection labels and counters. [Collection audit CSV](summary/2022_collection_file_audit.csv).

Original and processed post records, ID lists, API count buckets, and historical and collection time series remain in the research workspace. The separate sample fixture contains invented records for offline testing. Runtime subdirectories are ignored by Git. [Sample fixture](sample/README.md), [data dictionary](../docs/data_dictionary.md), and [usage guide](../docs/usage.md).
