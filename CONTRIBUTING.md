# Contributing

Contributions are welcome for extraction rules, document classification, validation, evaluation, tests, and research-method improvements.

## Development setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
pytest -q
```

## Contribution rules

- Do not commit copyrighted or private source PDFs.
- Add or update tests for extraction/classification changes.
- Preserve evidence provenance: extracted values should keep page/snippet/method/confidence where possible.
- Prefer conservative classification over silently assigning uncertain evidence to the wrong drug or document type.
- Do not convert a pharmacopoeial difference into a clinical-effectiveness claim.
- Meta-analysis changes should explicitly document assumptions and should not silently pool clinically incompatible estimates.
