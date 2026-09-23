# Research protocol — US/EU drug evidence intelligence

## Objective
Build a reproducible, copyright-conscious pipeline that converts private pharmacopoeia and public/regulatory/HTA PDFs into structured evidence for matched drug-level comparison.

The primary comparison keeps three domains separate:
1. **Quality standard:** USP–NF vs Ph. Eur.
2. **Regulatory clinical assessment:** FDA vs EMA.
3. **HTA/value assessment:** NICE (and later EU JCA).

No causal claim is made from pharmacopoeial restrictiveness to clinical efficacy.

## Utrecht-inspired extraction design
The workflow adopts the useful core idea from prior HTA text-mining work: define a finite extraction schema first, extract structured attributes from PDFs, preserve provenance, and evaluate against manually annotated gold-standard records. The extension here is multi-domain and cross-regional: pharmacopoeia + regulatory clinical evidence + HTA.

## Pharmacopoeia fields
For each monograph:
- monograph identity; API vs finished product; dosage form; edition
- identification test classes
- assay lower/upper acceptance limits, unit, basis, method class
- related substances / specified and unspecified impurities when extractable
- total impurities / disregard limit when extractable
- water / loss on drying
- pH
- residual solvents
- sulfated ash / optical rotation and other monograph-specific tests
- dissolution for finished products: apparatus, medium/volume, rpm, time, Q where extractable
- storage

Every extracted fact stores source page, short supporting snippet, method (rules or local LLM), and confidence.

## FDA / EMA fields
- assessment type and identifier
- indication
- disease stage / line of therapy
- population and biomarker restrictions
- combination regimen
- comparator
- clinical trials and study identifiers
- OS, PFS/DFS, ORR and other reported endpoints
- effect estimate, 95% CI, p-value when explicitly extractable
- key safety findings
- benefit–risk conclusion
- restrictions / uncertainty

## NICE HTA fields
The schema intentionally includes the core HTA attributes commonly used in automated extraction work:
- identifier / assessment type / date
- brand and INN where available
- indication
- final recommendation
- comparator
- relative-effectiveness conclusion
- cost-effectiveness conclusion
- managed-entry/commercial arrangement signal
- clinical restrictions

Additional fields: ICER/QALY wording when explicitly reported, key trial, subgroup, and uncertainty.

## Comparison rules
### Quality
- Compare only matched material type (API with API; finished product with same dosage form).
- Numeric ranges: same unit and basis required. Narrower interval is labelled **more restrictive for that parameter**, never “better”.
- Maximum-only impurity limits: lower maximum is labelled more restrictive.
- Different method classes are labelled `different_method`.
- Missing tests are `USP_only` or `PhEur_only`.
- Incompatible basis/unit/form is `not_directly_comparable`.

### FDA vs EMA
Before comparing conclusions, check matched drug + indication; later versions should also explicitly match population, line of therapy, biomarker and comparator. Output is `potentially_comparable`, `not_directly_comparable`, or `uncertain`.

### NICE
NICE is displayed as a value/reimbursement layer and is not treated as equivalent to FDA/EMA regulatory review.

## Evaluation
Create manual gold-standard rows for a pilot set (recommended: Capecitabine, Oxaliplatin, Regorafenib), then expand to 10 colorectal-cancer medicines.

Metrics:
- numeric fields: exact/tolerance accuracy
- categorical fields: exact normalized accuracy
- text fields: token F1; optional local-LLM semantic adjudication can be added
- error categories: wrong drug, wrong monograph type, wrong dosage form, wrong numeric value, wrong unit, wrong comparator, wrong indication/subgroup, wrong conclusion, hallucinated value

## Copyright/reproducibility
Do not publish the private USP/Ph. Eur. PDFs or full extracted monograph text. The database keeps local file path, SHA-256, normalized facts, short evidence snippets and page provenance. Code, schema, evaluation method and aggregate results can be published separately, subject to the terms of each source.
