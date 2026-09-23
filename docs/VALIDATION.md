# Validation plan

The system should be evaluated against manually annotated source documents before research conclusions are reported.

## Recommended pilot

Use a small manually curated set first (for example, 3 medicines) and then scale to the full cohort.

For each gold-standard row store:

- drug;
- source;
- document;
- field path;
- expected value;
- value type;
- acceptable tolerance where relevant;
- page/source note.

## Metrics

### Numeric fields

Use exact or pre-specified tolerance accuracy for values such as assay limits and effect estimates.

### Categorical fields

Use normalized exact accuracy for fields such as source, subtype, role, benefit–risk category, and comparison eligibility.

### Text fields

Use token F1 for a reproducible baseline. A separate blinded semantic adjudication can be added for publication if pre-specified.

## Error taxonomy

Record errors as at least one of:

- wrong drug;
- wrong document source/subtype;
- API vs finished-product confusion;
- wrong dosage form;
- wrong numeric value;
- wrong unit/basis;
- wrong comparator;
- wrong indication or subgroup;
- wrong trial identity;
- wrong endpoint/time point;
- wrong conclusion;
- hallucinated value;
- missed value.

## Meta-analysis validation

Before pooling, manually verify:

1. unique study identity;
2. same clinical question / compatible indication;
3. compatible population and line of therapy;
4. compatible comparator;
5. same endpoint definition;
6. same or justifiably compatible time point;
7. effect measure orientation;
8. correct estimate and confidence interval;
9. no duplicated publication/report of the same trial;
10. protocol-specified choice of fixed/random effects and sensitivity analyses.

The built-in DerSimonian–Laird calculation is suitable for software demonstration and exploratory research support, not by itself a publication-quality systematic-review protocol.
