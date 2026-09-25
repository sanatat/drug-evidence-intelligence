# Drug Evidence Intelligence

A local, research-oriented pipeline for turning heterogeneous drug-evidence PDFs into a structured, auditable database across four evidence layers:

1. **Pharmacopoeial quality standards** — USP–NF and Ph. Eur.
2. **Regulatory clinical evidence** — FDA and EMA.
3. **HTA/value evidence** — currently NICE-oriented.
4. **Independent clinical studies** — effect-estimate extraction and exploratory meta-analysis.

The project is designed around a simple principle: **extract first, preserve provenance, validate before comparing, and never collapse distinct evidence domains into one “best” score.**

> Research software only. It is not a clinical decision-support tool, regulatory submission system, or replacement for a protocol-driven systematic review.

## Why this project exists

Drug evidence is fragmented across pharmacopoeial monographs, regulatory reviews, HTA reports, labels, safety updates, and journal articles. These documents use different structures and answer different questions. Drug Evidence Intelligence provides a reproducible local workflow to:

- ingest PDFs recursively or through a browser upload page;
- classify document source and subtype;
- infer the active drug conservatively;
- extract structured quality, regulatory, HTA, and trial fields;
- keep API and finished-product monographs separate;
- preserve source page, snippet, method, confidence, and document hash;
- compare matched USP vs Ph. Eur. parameters;
- gate FDA vs EMA comparisons by document role and drug identity;
- identify independent study effect estimates;
- generate an **exploratory** inverse-variance meta-analysis for compatible HR/RR/OR estimates;
- evaluate extraction against a manually annotated gold standard.
- 
- ## Dataset

The pilot dataset associated with this project is publicly available on Mendeley Data:

**Drug Evidence Intelligence: Derived Pilot Metadata for Cross-Regional Pharmacopoeial and Regulatory Evidence Comparison**

**DOI:** https://doi.org/10.17632/p63y9h3yhm.1

The dataset contains derived metadata, validation and audit information, and a manual gold-standard template for the pilot corpus.

The dataset is intended to support reproducibility and evaluation of the extraction and comparison workflow described in this repository.

## Methodological inspiration

The schema-first, manually validated extraction design is inspired by work from Utrecht University on automated extraction of structured HTA attributes from NICE reports using rule-based NLP, classification models, and LLMs:

> Versteeg J-W, de Bruin M, Schermer M, et al. *Text Mining Methods for Automated Data Extraction from Health Technology Assessment Reports of Medicines Using Classical Natural Language Processing and Generative Artificial Intelligence.* JAMIA Open. 2026;9(2):ooag051. doi:10.1093/jamiaopen/ooag051

This project extends that concept beyond HTA into pharmacopoeial quality standards, regulatory evidence, and study-level clinical evidence.

## What is extracted

### Pharmacopoeia

For USP–NF / Ph. Eur. monographs, the rule-based layer targets fields such as:

- monograph identity;
- API vs finished-product status;
- dosage/salt form;
- edition/effective date when available;
- identification tests;
- assay limits and method;
- related substances / impurity limits;
- total or unspecified impurities where extractable;
- water / loss on drying;
- pH;
- residual solvents;
- sulfated ash / optical rotation and selected monograph-specific tests;
- dissolution details for finished products;
- storage.

### FDA / EMA / NICE

The clinical/regulatory/HTA layer targets:

- document/assessment type;
- indication;
- population, biomarker, stage, and line of therapy where extractable;
- comparator;
- trial identifiers;
- OS / PFS / DFS / ORR and other endpoints;
- HR / RR / OR, 95% CI, and p-value when explicitly reported;
- safety summaries;
- benefit–risk statements;
- HTA recommendation / relative-effectiveness / cost-effectiveness fields;
- restrictions and uncertainty.

### Independent clinical studies

Independent study PDFs can contribute study-level effect estimates. Complete HR/RR/OR + 95% CI pairs are candidates for exploratory pooling.

## Evidence safeguards

The pipeline deliberately separates:

- **quality-standard restrictiveness**;
- **regulatory benefit–risk**;
- **HTA/value conclusions**;
- **pooled clinical effects**.

A narrower assay range or lower impurity limit is described only as *more restrictive for that matched parameter*. It is **not** interpreted as proof of superior clinical effectiveness.

For FDA/EMA evidence, merely having a PDF is not enough. The classifier distinguishes primary clinical assessments from labels, PSURs, RMPs, orphan-designation documents, Orange Book material, national-authorisation lists, and other supporting/administrative documents.

## Exploratory meta-analysis safeguards

The built-in meta-analysis is intentionally conservative and transparent:

- independent clinical-study PDFs are used by default;
- FDA/EMA summaries are excluded by default to reduce double-counting;
- exact duplicate estimates for a named trial are deduplicated;
- conflicting estimates for the same named trial block automatic pooling;
- missing or differing indication/population/comparator/time-point metadata generate review warnings;
- both inverse-variance fixed effect and DerSimonian–Laird random effects are reported;
- Q, I², tau², weights, and a forest plot are displayed.

**Important:** automated grouping does not establish clinical exchangeability. A human reviewer must verify indication, population, comparator, endpoint definition, time point, subgroup, and trial identity before publication.

## Quick start — Linux Mint / Ubuntu

```bash
git clone <your-repository-url>
cd drug-evidence-intelligence
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Run against a private source folder containing one subfolder per drug:

```bash
./run_mint.sh "/home/YOURUSER/DrugEvidence/data" --rebuild
```

Then open:

- Home: `http://127.0.0.1:8080`
- Upload: `http://127.0.0.1:8080/upload`
- Exploratory meta-analysis: `http://127.0.0.1:8080/meta-analysis`
- FastAPI docs: `http://127.0.0.1:8080/docs`
- Health check: `http://127.0.0.1:8080/health`

For later runs, omit `--rebuild` unless you intentionally want a fresh database.

## Browser upload workflow

The upload page accepts one or more PDFs and attempts to detect:

- source: `USP`, `Ph. Eur.`, `FDA`, `EMA`, `NICE`, or `Clinical Study`;
- document subtype;
- drug name / known alias;
- document date or pharmacopoeial edition when extractable.

If source or drug identification is too uncertain, the file is placed under:

```text
data/uploads/Needs_Review/
```

rather than being silently attached to the database.

Confidently classified files are stored locally under a structure such as:

```text
data/uploads/
└── Alanine/
    └── USP/
        └── monograph/
            └── Alanine-usp.pdf
```

These local uploads are ignored by Git and should not be published.

## Recommended private data layout

```text
DrugEvidence/
├── Capecitabine/
│   ├── Capecitabine-usp.pdf
│   ├── Capecitabine-pheur.pdf
│   ├── Capecitabine-fda-review.pdf
│   └── Capecitabine-ema-assessment.pdf
├── Oxaliplatin/
└── Regorafenib/
```

The immediate parent folder is used as the canonical drug name during folder ingestion. Browser uploads use conservative name/alias inference with a review gate.

## Optional local LLM enrichment

The deterministic rules are the primary layer for numeric pharmacopoeial fields. A local Ollama model can be used to enrich missing contextual clinical fields:

```bash
ollama pull qwen3:8b
./run_mint.sh "/home/YOURUSER/DrugEvidence/data" --llm
```

The application does not require a paid external LLM API.

## Manual commands

```bash
python ingest.py --input "/path/to/private/data" --db data/evidence.db
python audit_documents.py --db data/evidence.db
python aggregate_report.py --db data/evidence.db --out AGGREGATE_RESULTS.md
uvicorn app.main:app --host 127.0.0.1 --port 8080
```

## Evaluation

A template is provided at `evaluation/gold_standard_template.csv`.

Create a manual gold standard from legally accessed source documents, then run:

```bash
python evaluate.py \
  --db data/evidence.db \
  --gold evaluation/gold_standard.csv \
  --details evaluation/evaluation_details.csv
```

Supported evaluation modes include:

- tolerance/exact accuracy for numeric fields;
- normalized exact accuracy for categorical fields;
- token F1 for textual fields.

A multi-model local benchmark is also available through `benchmark_models.py`.

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

The GitHub Actions workflow runs syntax checks and tests on Python 3.10 and 3.12.

## Repository structure

```text
app/
  classify.py        source/subtype and drug identity logic
  extract_rules.py   deterministic field extraction
  extract_llm.py     optional local Ollama enrichment
  pipeline.py        document ingestion and database writes
  compare.py         USP vs Ph. Eur. and FDA vs EMA comparison logic
  meta.py            exploratory meta-analysis
  uploading.py       upload classification and local filing
  db.py              SQLite schema / migrations
  main.py            FastAPI application

docs/
  ARCHITECTURE.md
  VALIDATION.md
  RESEARCH_SCOPE.md

evaluation/
  gold_standard_template.csv
```

## Data and copyright

This repository must not contain private or licensed source PDFs. The `.gitignore` excludes PDFs, archives, uploaded source documents, and local databases by default.

See [NOTICE.md](NOTICE.md) for the data/copyright and research-use policy.

## Current limitations

- PDF extraction is text-based; scanned documents require OCR/manual handling.
- document classification is heuristic and must be reviewed for uncertain cases;
- clinical context extraction can be incomplete or semantically variable;
- meta-analysis is a basic research aid and does not implement full systematic-review methodology, risk-of-bias assessment, Hartung–Knapp adjustment, publication-bias diagnostics, network meta-analysis, or GRADE;
- pharmacopoeial methods can differ in ways that make simple numeric comparison invalid;
- licensing terms differ by source and must be checked independently.

## Research protocol

See [RESEARCH_PROTOCOL.md](RESEARCH_PROTOCOL.md) for the study design and comparison rules.

## Licence

Code is released under the MIT License. Source documents and extracted source content remain subject to their own rights and terms.
