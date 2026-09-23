# Changelog

## 2.3.0 — GitHub-ready research release

- Added a public-repository data/copyright policy and expanded `.gitignore` to prevent accidental commits of PDFs, archives, uploads, and SQLite databases.
- Added GitHub Actions CI and a small automated test suite.
- Added `/health` endpoint and package version metadata.
- Added PDF file-signature validation for browser uploads.
- Strengthened exploratory meta-analysis safeguards:
  - exact duplicate estimates for a named study are deduplicated;
  - conflicting estimates for the same named study block automatic pooling;
  - missing/different indication, population, comparator, or time-point metadata generate review warnings;
  - the UI explicitly labels the method as exploratory and DerSimonian–Laird.
- Refreshed README, architecture, validation, and research-scope documentation.

## 2.2.0

- Browser PDF upload and automatic document/drug candidate classification.
- Local category filing and ingestion into SQLite.
- Independent clinical-study extraction and basic fixed/random-effects pooling with forest plot.

## 2.1.0

- FDA/EMA clinical-document gating and identity checks.
