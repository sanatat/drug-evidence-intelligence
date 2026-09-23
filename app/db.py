from __future__ import annotations
import sqlite3
from pathlib import Path

SCHEMA = r'''
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS drugs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  canonical_name TEXT NOT NULL UNIQUE,
  disease_scope TEXT,
  aliases_json TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS documents (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  drug_id INTEGER NOT NULL REFERENCES drugs(id) ON DELETE CASCADE,
  source TEXT NOT NULL,
  region TEXT,
  doc_type TEXT NOT NULL,
  subtype TEXT,
  title TEXT,
  file_path TEXT NOT NULL,
  filename TEXT NOT NULL,
  sha256 TEXT NOT NULL UNIQUE,
  page_count INTEGER,
  edition TEXT,
  version_date TEXT,
  document_date TEXT,
  application_number TEXT,
  product_name TEXT,
  copyright_note TEXT,
  extraction_method TEXT,
  extraction_confidence REAL DEFAULT 0.0,
  classification_confidence REAL DEFAULT 0.0,
  evidence_role TEXT,
  comparison_eligible INTEGER DEFAULT 0,
  drug_identity_status TEXT DEFAULT 'unknown',
  document_note TEXT,
  ingest_origin TEXT DEFAULT 'folder',
  category_path TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS evidence_spans (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  field_path TEXT NOT NULL,
  page_number INTEGER,
  snippet TEXT,
  extraction_method TEXT,
  confidence REAL,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS pharmacopoeia_monographs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  monograph_name TEXT,
  material_type TEXT,
  dosage_form TEXT,
  salt_form TEXT,
  edition TEXT,
  effective_date TEXT,
  confidence REAL DEFAULT 0.0
);

CREATE TABLE IF NOT EXISTS quality_parameters (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  monograph_id INTEGER NOT NULL REFERENCES pharmacopoeia_monographs(id) ON DELETE CASCADE,
  category TEXT NOT NULL,
  parameter_name TEXT NOT NULL,
  value_text TEXT,
  numeric_min REAL,
  numeric_max REAL,
  operator TEXT,
  unit TEXT,
  method_name TEXT,
  method_details_json TEXT,
  basis TEXT,
  source_page INTEGER,
  confidence REAL,
  evidence_span_id INTEGER REFERENCES evidence_spans(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS clinical_assessments (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  document_id INTEGER NOT NULL UNIQUE REFERENCES documents(id) ON DELETE CASCADE,
  agency TEXT,
  assessment_type TEXT,
  assessment_date TEXT,
  indication TEXT,
  disease_stage TEXT,
  line_of_therapy TEXT,
  population TEXT,
  biomarker TEXT,
  combination_therapy TEXT,
  comparator TEXT,
  relative_effectiveness TEXT,
  benefit_risk TEXT,
  cost_effectiveness TEXT,
  managed_entry TEXT,
  recommendation TEXT,
  restrictions TEXT,
  uncertainty TEXT,
  confidence REAL DEFAULT 0.0
);

CREATE TABLE IF NOT EXISTS clinical_trials (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  assessment_id INTEGER NOT NULL REFERENCES clinical_assessments(id) ON DELETE CASCADE,
  trial_name TEXT,
  trial_id TEXT,
  phase TEXT,
  randomized TEXT,
  blinded TEXT,
  sample_size INTEGER,
  population TEXT,
  treatment_arm TEXT,
  comparator_arm TEXT,
  follow_up TEXT,
  confidence REAL DEFAULT 0.0
);

CREATE TABLE IF NOT EXISTS clinical_endpoints (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  assessment_id INTEGER NOT NULL REFERENCES clinical_assessments(id) ON DELETE CASCADE,
  trial_id INTEGER REFERENCES clinical_trials(id) ON DELETE SET NULL,
  study_label TEXT,
  endpoint_name TEXT NOT NULL,
  timepoint TEXT,
  treatment_value REAL,
  comparator_value REAL,
  effect_measure TEXT,
  effect_value REAL,
  ci_low REAL,
  ci_high REAL,
  p_value REAL,
  unit TEXT,
  agency_interpretation TEXT,
  source_page INTEGER,
  confidence REAL DEFAULT 0.0
);

CREATE TABLE IF NOT EXISTS safety_outcomes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  assessment_id INTEGER NOT NULL REFERENCES clinical_assessments(id) ON DELETE CASCADE,
  event_name TEXT NOT NULL,
  category TEXT,
  treatment_value REAL,
  comparator_value REAL,
  unit TEXT,
  grade TEXT,
  seriousness TEXT,
  interpretation TEXT,
  source_page INTEGER,
  confidence REAL DEFAULT 0.0
);

CREATE TABLE IF NOT EXISTS validation_issues (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  document_id INTEGER REFERENCES documents(id) ON DELETE CASCADE,
  severity TEXT NOT NULL,
  code TEXT NOT NULL,
  field_path TEXT,
  message TEXT NOT NULL,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS extraction_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  started_at TEXT DEFAULT CURRENT_TIMESTAMP,
  finished_at TEXT,
  input_path TEXT,
  llm_model TEXT,
  documents_seen INTEGER DEFAULT 0,
  documents_inserted INTEGER DEFAULT 0,
  warnings TEXT
);

CREATE TABLE IF NOT EXISTS upload_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  original_filename TEXT NOT NULL,
  stored_path TEXT,
  detected_drug TEXT,
  detected_source TEXT,
  detected_subtype TEXT,
  detection_confidence REAL,
  status TEXT NOT NULL,
  message TEXT,
  document_id INTEGER REFERENCES documents(id) ON DELETE SET NULL,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_docs_drug ON documents(drug_id);
CREATE INDEX IF NOT EXISTS idx_docs_source ON documents(source);
CREATE INDEX IF NOT EXISTS idx_qp_monograph ON quality_parameters(monograph_id);
CREATE INDEX IF NOT EXISTS idx_qp_name ON quality_parameters(parameter_name);
CREATE INDEX IF NOT EXISTS idx_ev_doc ON evidence_spans(document_id);
CREATE INDEX IF NOT EXISTS idx_ep_effect ON clinical_endpoints(effect_measure,effect_value,ci_low,ci_high);
'''


def _columns(con: sqlite3.Connection, table: str) -> set[str]:
    return {r[1] for r in con.execute(f'PRAGMA table_info({table})').fetchall()}


def connect(db_path: str):
    p = Path(db_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(p)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)

    # Lightweight migrations for databases created by v2.0/v2.1.
    doc_cols = _columns(con, 'documents')
    doc_migrations = [
        ('evidence_role', "ALTER TABLE documents ADD COLUMN evidence_role TEXT"),
        ('comparison_eligible', "ALTER TABLE documents ADD COLUMN comparison_eligible INTEGER DEFAULT 0"),
        ('drug_identity_status', "ALTER TABLE documents ADD COLUMN drug_identity_status TEXT DEFAULT 'unknown'"),
        ('document_note', "ALTER TABLE documents ADD COLUMN document_note TEXT"),
        ('document_date', "ALTER TABLE documents ADD COLUMN document_date TEXT"),
        ('classification_confidence', "ALTER TABLE documents ADD COLUMN classification_confidence REAL DEFAULT 0.0"),
        ('ingest_origin', "ALTER TABLE documents ADD COLUMN ingest_origin TEXT DEFAULT 'folder'"),
        ('category_path', "ALTER TABLE documents ADD COLUMN category_path TEXT"),
    ]
    for name, sql in doc_migrations:
        if name not in doc_cols:
            con.execute(sql)

    ep_cols = _columns(con, 'clinical_endpoints')
    if 'study_label' not in ep_cols:
        con.execute("ALTER TABLE clinical_endpoints ADD COLUMN study_label TEXT")

    con.commit()
    return con
