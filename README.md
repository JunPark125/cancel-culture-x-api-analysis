# Cancel Culture Research with the X API

**Python automation, REST API integration, and reproducible data preparation for academic research.**

This portfolio documents my technical work as an Undergraduate Research Assistant at the **UBC Sauder School of Business**, supervised by **Professor Jen Park**. The research examines cancellation and boycotting language on X through two complementary workflows: historical hashtag counts and a collection of individual posts from 2022.

The portfolio pairs the implementation with an analysis of 11 years of monthly hashtag activity, a verified audit of the 2022 collection files, and an offline demonstration. It covers my technical contributions to the broader research project.

## Research scope

| Workflow | Research interval (UTC) | What it produces |
|---|---|---|
| Historical trends | January 2015–December 2025 | Daily API count buckets, monthly/yearly aggregates, and a monthly comparison plot |
| Post collection | January–December 2022 | Post-level CSVs, simplified research exports, quality checks, and collection-gap reports |

Both primary workflows use the exact queries `#cancel -is:retweet lang:en` and `#boycott -is:retweet lang:en`. These match hashtags in English posts and exclude retweets. They do not establish that every match concerns cancel culture. Replies and quote posts are not explicitly excluded. Broader phrase searches and causal or inferential statistical results are not claimed.

## Research Results & Visualizations

![Monthly Counts API trend lines for #cancel and #boycott, January 2015 through December 2025](results/figures/monthly_hashtag_trends_2015_2025.png)

**`#boycott` led in 128 of 132 months, while `#cancel` was more concentrated around its largest spike.** In the two series plotted above, `#boycott` totaled 753,216 matches and peaked at 12,794 in February 2017. `#cancel` totaled 173,985 and peaked at 33,147 in September 2022. That peak month contributed 19.1% of the `#cancel` series total, compared with 1.7% for the peak month of `#boycott`. The contrast describes hashtag use under these queries. It leaves the causes of spikes and the prevalence of offline behavior open.

The chart uses the archived `#hashtag_year_month` monthly Counts API tables. Both series contain every month from January 2015 to December 2025. The chart inputs and a separate set of daily-derived aggregates differ in monthly values and period totals. The results above use the chart inputs throughout. [One-page analysis case study](docs/analysis_case_study.md) · [Figure source and offline reproduction](results/README.md)

### 2022 collection quality

| Collection file | Stored rows | Distinct post IDs | Duplicate ID rows | Rows outside 2022 UTC |
|---|---:|---:|---:|---:|
| `#cancel` | 51,059 | 51,059 | 0 | 0 |
| `#boycott` | 55,218 | 55,218 | 0 | 0 |

The saved files share 137 IDs, yielding 106,140 distinct IDs combined. Every stored row had a nonblank ID and a parseable timestamp. These checks establish the quality and size of the saved files. Search availability and backfill history limit conclusions about collection coverage. [Collection audit CSV](data/summary/2022_collection_file_audit.csv)

## Technical contributions

- Automated full-archive requests with monthly time windows, pagination, structured CSV exports, and post-ID deduplication.
- Supported restartable collection with atomic checkpoint replacement, retry logs, exponential backoff, and waits informed by rate-limit headers.
- Built gap-driven backfill with monthly, daily, hourly, 15-minute, and 5-minute windows, plus count-guided window selection.
- Prepared research exports with full-text fallback, timestamp ordering, and engagement fields; checked duplicates, missing fields, and year boundaries.
- Aggregated historical count buckets and visualized monthly hashtag frequencies with pandas and Matplotlib.

These are practical data engineering and automation patterns: explicit schemas, restart state, observable failures, and separated collection and transformation stages. No cloud deployment, distributed infrastructure, or production service is claimed. [Contribution evidence and attribution](docs/technical_contributions.md) distinguishes original functionality from portfolio preparation.

## Architecture

```mermaid
flowchart TD
    A[Authorized X API access] --> B[Counts endpoint: daily buckets]
    B --> C[Monthly and yearly aggregation]
    C --> D[Monthly trend visualization]
    A --> E[Search endpoint: monthly windows and pagination]
    E --> F[Deduplicated raw post CSVs]
    F --> G[Quality checks and simplified exports]
    F --> H[Collected monthly counts]
    C --> I[Monthly gap report]
    H --> I
    I --> J[Targeted backfill with separate checkpoints]
    J --> F
```

The counts workflow uses `GET /2/tweets/counts/all`; the post workflow uses `GET /2/tweets/search/all`. A count bucket represents matching posts reported by the API, **not individually retrieved records**. The two workflows have different reliability implementations: the historical notebook uses a fixed wait on HTTP 429; the 2022 collector implements bounded retries and checkpoint recovery.

## Run the offline demonstration

Requires Python **3.10 or newer**. Run commands from the repository root.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m src.demo
python -m unittest discover -s tests -v
```

The demonstration uses invented text and nonnumeric synthetic IDs. It opens no network connections and writes only to a newly created temporary directory. For each hashtag it attempts four rows, suppresses one repeated ID, and produces three unique rows plus export, quality, monthly-count, and gap files. **Those numbers are demonstration outputs, not research findings.**

## Authorized research usage

CLI entry points provide `--help` without making API requests:

```bash
python -m src.api_collection.historical_counts --help
python -m src.api_collection.collect_x_posts_2022 --help
python -m src.api_collection.backfill_x_posts_2022 --help
```

Live collection requires credentials, account access, spending authorization, and an explicit `--allow-live-api` flag. No live request was used to prepare or validate this portfolio. See [usage](docs/usage.md) for input paths, offline processing, and backfill planning. Current access and billing must be checked with X before execution; old notebook cost estimates were removed.

## Engineering challenges and limitations

| Challenge | Implemented approach | Remaining limitation |
|---|---|---|
| Large paginated searches | Time windows, `next_token`, up to 500 results per request | Access and limits depend on the account; exhausted pagination does not prove complete coverage |
| Interrupted collection | Page-level checkpoints and deduplication against existing CSV IDs | CSV append and checkpoint update are not a single transaction; no concurrent-writer locking |
| Temporary API failures | Bounded retries and header-based waits in the 2022 collector | Historical counts have simpler retry handling and no checkpoint recovery |
| Count/search discrepancies | Monthly gap reports and smaller backfill windows | API counts are a reference, not a guaranteed recoverable population |
| Reproducibility | Released chart inputs, documented provenance, offline tests | The post-level collection stays private and the reason for the historical version differences remains unresolved |

## Repository structure

```text
cancel-culture-x-api-analysis/
├── README.md, requirements.txt, .env.example, .gitignore
├── RELEASE_FILES.txt          # Explicit staging allowlist
├── docs/                      # Scope, methodology, schemas, provenance, usage, security
├── src/
│   ├── config.py, demo.py
│   ├── api_collection/        # Counts, 2022 collection/backfill, historical pilot
│   ├── preprocessing/         # Simplified research exports
│   ├── analysis/              # Aggregation, quality checks, collection gaps
│   └── visualization/         # Monthly time-series plotting
├── notebooks/                # Sanitized source; original outputs removed
├── data/                      # Monthly chart inputs, file audit, synthetic fixtures
├── results/                   # Original trend figure and offline plotting instructions
├── reports/README.md          # Restricted-report availability
├── tests/                     # Offline tests with synthetic responses
└── tools/check_release.py     # Staged-file review checks
```

## Data availability and confidentiality

The private portfolio release includes the original monthly trend figure, its two reviewed aggregate inputs, and the collection file audit. Raw and processed post records, other count exports, internal reports, and credentials stay in the research workspace. [Release allowlist](RELEASE_FILES.txt).

The sharing review applies to these specific assets. [Data handling and policy references](docs/security_and_sharing.md) · [Data dictionary](docs/data_dictionary.md) · [Methodology](docs/methodology.md) · [Source provenance](docs/source_provenance.md)
