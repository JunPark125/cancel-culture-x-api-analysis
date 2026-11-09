# Security and sharing

The project owner confirmed supervisor approval and that the applicable X terms allow the original monthly trend figure and its two aggregate CSV inputs to be shared in this private GitHub repository. The release review applies to those specific assets, the collection audit, and the reviewed code and documentation.

## Exclusions

Keep credentials, populated `.env` files, raw and simplified post datasets, post and user IDs, labeled data, API response bodies, operational logs, checkpoints, and unpublished reports local. The reviewed time series contain only month and aggregate count. The separate 2022 file audit records local file checks.

One original pilot contained an embedded credential. The portfolio copy reads the environment instead. The original was preserved, and the local audit records its location without copying the secret into documentation. The credential owner should assess rotation before future use or sharing of that original file.

## Policy review

Reviewed on 2026-11-09:

- The X Developer Agreement defines X Content broadly, including API-returned data and derivatives, and restricts transfer except as expressly permitted. Repository visibility and supervisor approval do not determine X redistribution scope. [X Developer Agreement](https://docs.x.com/developer-terms/agreement).
- The Developer Policy limits redistribution and conditions academic ID sharing. Supervisor approval does not establish the X authorization needed to publish an ID dataset for a portfolio. [X Developer Policy](https://docs.x.com/developer-terms/policy#content-redistribution).

The release treats the 2022 audit as an inventory of the project's local files. It does not contain X response values or measure platform-wide activity or API performance.

## Explicit staging and review

`RELEASE_FILES.txt` is an exact path allowlist. Review changes before adding a new path; `.gitignore` alone is insufficient. After permission is confirmed, stage only the approved set:

```bash
git add --pathspec-from-file=RELEASE_FILES.txt
python tools/check_release.py
git diff --cached --stat
git diff --cached
```

The checker reads staged blobs, checks path membership and aggregate schemas, verifies the original PNG fingerprint, rejects notebook outputs, and scans for common credential and identifier patterns. The preparation audit additionally compared source credential values against the release without printing those values.

Do not use `git add .`, force-add ignored artifacts, or copy the local audit into this repository. Before the first upload, inspect all commits and verify the repository is private. No CI deployment, scheduled job, or live-API automation is configured.
