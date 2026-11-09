# Security and sharing

This release is restricted to reviewed code, documentation, and invented fixtures. A private GitHub repository is still external storage. Permission for the research software, project descriptions, and methodology must be confirmed before upload if ownership is unclear. No reuse license is granted here pending that determination.

## Exclusions

Never stage credentials, populated `.env` files, raw or simplified post datasets, real post/user IDs, labeled data, API response bodies, operational logs, pagination/checkpoint state, unpublished reports, or research results. Aggregate counts and figures are also withheld until approved. Removing usernames or cleaning text does not establish permission to redistribute a dataset.

One original pilot contained an embedded credential. The portfolio copy reads the environment instead. The original was preserved, and the local audit records its location without copying the secret into documentation. The credential owner should assess rotation before future use or sharing of that original file.

## Policy review

Reviewed on 2026-11-09:

- [X Developer Policy, content redistribution](https://docs.x.com/developer-terms/policy#content-redistribution) restricts redistribution and places conditions on research-related ID sharing. This repository distributes neither real IDs nor post content. No assumption is made that an academic or private-repository exception authorizes this project.
- [UBC research data policies, standards, and guidelines](https://rdm.ubc.ca/understanding-requirements/policies-standards-guidelines) describes research information security obligations and the need to determine ownership of research data and software. The local source files do not establish project-specific external-storage permission.

The applicable project agreements, ethics requirements, funding terms, and X access agreement were not supplied. This is a conservative release decision, not a legal determination of ownership or permission. No one was contacted on the user's behalf.

## Explicit staging and review

`RELEASE_FILES.txt` is an exact path allowlist. Review changes before adding a new path; `.gitignore` alone is insufficient. After permission is confirmed, stage only the approved set:

```bash
git add --pathspec-from-file=RELEASE_FILES.txt
python tools/check_release.py
git diff --cached --stat
git diff --cached
```

The checker reads staged blobs, checks path membership, rejects notebook outputs, and scans for common credential and identifier patterns. It is a supporting check, not proof of rights or a complete secret detector. The preparation audit additionally compared source credential values against the release without printing those values.

Do not use `git add .`, force-add ignored artifacts, or copy the local audit into this repository. Before the first upload, inspect all commits and verify the repository is private. No CI deployment, scheduled job, or live-API automation is configured.
