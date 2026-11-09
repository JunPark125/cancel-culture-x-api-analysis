# Usage

Run all commands from the repository root with the environment described in the README. `python -m src.demo` is the recommended offline entry point and does not need credentials.

## Private runtime layout

Set `X_DATA_DIR` in the shell **before** starting a process to select a private working directory. Otherwise runtime inputs/outputs use the ignored `data/` tree. The two copied notebooks use their documented repository-local data paths; the historical notebook additionally uses `X_DATA_DIR` through shared configuration. Keep each query/window variant in a separate working directory.

```text
<X_DATA_DIR>/
  raw/x_2022_{cancel,boycott}_raw_master.csv
  counts/x_{cancel,boycott}_monthly_counts_2015_2025.csv
  reports/
  professor_submission/
  logs/
```

Populate this layout only with authorized research inputs, keeping baseline versions aligned. The released chart inputs live separately under `data/historical/`. Simplified exports from the 2022 workflow contain user IDs and text and stay private.

## Offline processing

```bash
python -m src.analysis.build_collected_monthly_counts
python -m src.analysis.build_monthly_gap_report
python -m src.analysis.quality_check
python -m src.preprocessing.build_professor_submission
```

The gap report requires the two monthly Counts API reference CSVs under `counts/`. The quality report's progress baseline defaults to unspecified (`0`); authorized totals can be supplied through `X_CANCEL_EXPECTED_COUNT` and `X_BOYCOTT_EXPECTED_COUNT` before launching. Environment settings must be exported; putting these optional settings only in `.env` does not configure modules already imported.

Backfill planning is offline:

```bash
python -m src.api_collection.backfill_x_posts_2022 --dry-run
```

It reads the existing gap report and prints matching targets. It does not request credentials or make X calls. Use `--help` for optional date filters, daily-count references, and automatic subdivision. A completed search window is not proof that a reference total was reached.

## Live collection

Obtain project permission, confirm current X access and billing, then provide `X_BEARER_TOKEN` through the environment or an ignored local token file for the 2022 collectors. The historical module reads the environment directly. The environment takes precedence over local files. Do not paste real tokens into source code, notebooks, Git commands, or chat.

Live CLI execution is blocked without `--allow-live-api`. That flag makes the choice explicit but does not set a spending ceiling. Imported collection functions can also make requests if called directly. The notebook uses `ALLOW_LIVE_API = False` as its default guard. No live invocation is part of tests or demonstration instructions.

The Balenciaga pilot preserves a fixed February 2026 recent-search window and the original query's operator grouping. It is archival implementation evidence, not a currently runnable historical query or a validated brand analysis. Do not use it as a general full-archive collector.

## Plotting authorized inputs

The plot CLI requires both monthly CSV paths, an output path, and a title identifying the period and whether the inputs are synthetic:

```bash
python -m src.visualization.monthly_trends --help
```

Use a separate filename for generated figures. Only the reviewed original PNG is staged from `results/figures/`. The offline plotting command uses the released CSVs. [Reproduction instructions](../results/README.md)
