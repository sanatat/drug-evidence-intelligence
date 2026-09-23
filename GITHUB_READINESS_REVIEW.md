# GitHub readiness review

## Status

**Ready for a public code repository after the repository URL/author metadata are added.**

## Issues found in the v2.2 working build

### 1. Private-data leakage risk — fixed

The previous `.gitignore` did not exclude `data/uploads/`, `data/inbox/`, all PDFs, or archive files. A public commit could therefore accidentally include licensed pharmacopoeial material or other private source documents.

The public build now ignores those paths and file types by default.

### 2. Meta-analysis grouping was too permissive — improved

The earlier implementation grouped by drug + endpoint + effect measure. That is not enough to establish clinical comparability.

The public build now:

- flags missing/different indication, population, comparator, and time-point context;
- deduplicates identical estimates from the same named study;
- blocks automatic pooling when conflicting estimates are found for the same named study;
- labels the analysis as exploratory and requires manual verification.

A publication-quality review still needs a pre-specified systematic-review protocol and human eligibility assessment.

### 3. Uploads were checked by extension only — fixed

The upload path now checks the `%PDF-` file signature before treating a file as a PDF.

### 4. No automated tests / CI — fixed

A pytest suite and GitHub Actions workflow now cover:

- source/subtype classification;
- synonym mapping (`Aciclovir`/`Acyclovir`, `Paracetamol`/`Acetaminophen`);
- database creation;
- PDF signature validation;
- meta-analysis calculation;
- duplicate/conflicting trial safeguards;
- API health endpoint.

### 5. Public-repository documentation was incomplete — fixed

Added:

- MIT licence;
- data/copyright notice;
- security note;
- contribution guide;
- architecture documentation;
- validation plan;
- research-scope documentation;
- GitHub publishing instructions;
- changelog.

## Local verification performed

- Python syntax compilation: passed.
- pytest suite: passed.
- FastAPI `/`, `/upload`, `/meta-analysis`, `/health`, and `/api/drugs`: smoke-tested successfully.
- Sample pharmacopoeia + two independent study PDFs: ingested successfully.
- Sample HR meta-analysis: calculation and review warnings generated successfully.

## Remaining scientific work before a paper

- create and lock the manual gold standard;
- report field-level extraction accuracy with confidence intervals where appropriate;
- manually validate trial eligibility and extracted effect estimates;
- define the systematic-review/meta-analysis protocol before interpreting pooled clinical results;
- expand drug/source coverage using matched documents;
- perform error analysis by source/document type;
- decide whether the LLM benchmark is part of the main paper or a supplementary experiment.
