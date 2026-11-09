# Technical contributions and attribution

The project owner identifies this work as undergraduate research assistance under Professor Jen Park at UBC Sauder. Local files establish implementation evidence; they do not independently establish authorship of every line, individual ownership rights, or the broader team's division of research responsibility.

| Demonstrated skill | Existing implementation evidence | Portfolio location |
|---|---|---|
| Python automation and REST integration | Full-archive request/session construction and CSV flattening | `src/api_collection/collect_x_posts_2022.py` |
| Reliability and recovery | Retry classification, header-based waits, atomic checkpoint replacement, per-ID append filtering | Collector and backfill modules |
| Data engineering | Raw schema, full-text fallback, stable export ordering, counts/ID distinction | `src/config.py`, `src/preprocessing/`, `src/analysis/` |
| Collection diagnostics | Monthly reference comparison and targeted submonthly backfill | Gap-report and backfill modules |
| Analysis and visualization | Daily-to-monthly/yearly aggregation and monthly line comparison | Historical aggregation and visualization modules |

The project provides evidence for software engineering, data engineering, and automation skills. It does not demonstrate a deployed cloud system, container orchestration, infrastructure-as-code, or operational service-level guarantees.

The following were added during portfolio preparation and should not be presented as pre-existing research achievements: package layout, portable data paths, live-request opt-in, external-file exclusions, documentation, a synthetic demo, offline tests, and release-review tooling. The historical notebook's functions were extracted into modules while retaining their algorithmic behavior. The older pilot's embedded credential was removed only from its copy.

The repository does not claim validated classifier accuracy, hypothesis-test results, comprehensive capture of all matching X posts, or causation from time-series peaks. The broader research interpretation remains with the research team.
