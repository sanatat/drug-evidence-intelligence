# Architecture

```text
Private / lawfully accessed PDFs
          │
          ▼
 PDF text extraction (PyMuPDF)
          │
          ├──────────────┐
          ▼              ▼
 document classifier   drug/alias resolver
          │              │
          └──────┬───────┘
                 ▼
        role / identity gates
                 │
        ┌────────┼────────┐
        ▼        ▼        ▼
 pharmacopoeia  regulatory/HTA  clinical-study
 extraction      extraction      extraction
        │        │        │
        └────────┼────────┘
                 ▼
             SQLite
                 │
   ┌─────────────┼─────────────┐
   ▼             ▼             ▼
 provenance   comparison   exploratory pooling
   │             │             │
   └─────────────┼─────────────┘
                 ▼
           FastAPI web UI
```

## Provenance model

Each source document has a SHA-256 hash and source metadata. Extracted evidence is linked back to the document and, when possible, a page number and short supporting snippet. This is designed to support auditability without republishing the full source document.

## Storage

SQLite is intentionally used to keep the first research implementation local and reproducible. Source PDFs remain outside version control. Browser uploads are stored under `data/uploads/` and are ignored by Git.

## Classification philosophy

The classifier is intentionally conservative. If the source or active drug cannot be inferred with adequate confidence, the uploaded file is moved to `Needs_Review` rather than silently contaminating the evidence database.

Regulatory-document role is separated from source identity. For example, an EMA PDF can be a primary assessment report, medicine overview, RMP, PSUR, orphan document, SmPC, or administrative list; those roles are not treated as equivalent clinical evidence.
