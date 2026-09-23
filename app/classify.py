from __future__ import annotations
import re
from pathlib import Path

SOURCE_PATTERNS = [
    ("USP", "US", [r"USP Monographs", r"USPC", r"USPNF_", r"United States Pharmacopeia", r"USP[-– ]NF"]),
    ("Ph. Eur.", "EU", [r"EUROPEAN PHARMACOPOEIA", r"Ph\. Eur\.", r"European Pharmacopoeia"]),
    ("NICE", "UK", [r"Technology appraisal guidance", r"nice\.org\.uk/guidance/ta"]),
    ("FDA", "US", [
        r"CENTER FOR DRUG EVALUATION AND RESEARCH", r"CLINICAL REVIEW", r"SUMMARY REVIEW",
        r"OFFICE OF CLINICAL PHARMACOLOGY REVIEW", r"APPLICATION NUMBER", r"Food and Drug Administration",
        r"Prescription and Over-the-Counter Drug Product List", r"Approved Drug Products with Therapeutic Equivalence Evaluations"
    ]),
    ("EMA", "EU", [r"European Medicines Agency", r"EPAR", r"EU Risk Management Plan", r"SUMMARY OF PRODUCT CHARACTERISTICS"]),
]

# Explicit spelling/synonym map. Both variants resolve to one existing drug record when possible.
ALIASES = {
    "aciclovir": {"aciclovir", "acyclovir"},
    "acyclovir": {"aciclovir", "acyclovir"},
    "acetaminophen": {"acetaminophen", "paracetamol"},
    "paracetamol": {"acetaminophen", "paracetamol"},
    "fluorouracil": {"fluorouracil", "5 fluorouracil", "5-fluorouracil", "5 fu"},
}

SALT_WORDS = {
    "hydrochloride", "hydrobromide", "sulfate", "sulphate", "calcium", "sodium", "potassium",
    "monohydrate", "dihydrate", "hydrate", "phosphate", "acetate", "maleate", "mesylate", "succinate"
}

GENERIC_FILENAME_WORDS = {
    "usp", "usp-nf", "uspnf", "ep", "pheur", "ph", "eur", "ema", "fda", "nice", "review", "assessment",
    "report", "label", "overview", "monograph", "clinical", "study", "trial", "article", "document", "final",
}


def infer_drug(path: Path) -> str:
    return re.sub(r"[_-]+", " ", path.parent.name).strip()


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def drug_aliases(drug: str) -> set[str]:
    n = _norm(drug)
    out = {n}
    if n in ALIASES:
        out |= {_norm(x) for x in ALIASES[n]}
    toks = n.split()
    base = " ".join(t for t in toks if t not in SALT_WORDS).strip()
    if base:
        out.add(base)
        if base in ALIASES:
            out |= {_norm(x) for x in ALIASES[base]}
    return {x for x in out if x}


def resolve_existing_drug(candidate: str, existing_names: list[str] | tuple[str, ...] | None) -> str:
    if not candidate:
        return candidate
    if not existing_names:
        return candidate.strip()
    cn = _norm(candidate)
    c_aliases = drug_aliases(candidate)
    # Exact/alias match first.
    for name in existing_names:
        if cn == _norm(name) or c_aliases & drug_aliases(name):
            return name
    # Base active-moiety match when the only difference is a common salt word.
    cbase = " ".join(t for t in cn.split() if t not in SALT_WORDS)
    for name in existing_names:
        n = _norm(name)
        nbase = " ".join(t for t in n.split() if t not in SALT_WORDS)
        if cbase and cbase == nbase:
            return name
    return candidate.strip()


def assess_drug_identity(drug: str, text: str) -> tuple[str, str | None]:
    header_raw = text[:8000]
    header = _norm(header_raw)
    aliases = drug_aliases(drug)
    if not any(a in header for a in aliases):
        return "mismatch", f"The selected drug ({drug}) is not identified in the document header/first pages; it may only be mentioned later as background or comparator text."

    combo_patterns = [
        r"contains\s+(?:two|three|four)\s+active\s+substances",
        r"fixed[ -]dose combination",
        r"combination product",
        r"(?:two|three|four)\s+approved\s+(?:principal\s+)?constituents",
    ]
    if any(re.search(p, header_raw, re.I | re.S) for p in combo_patterns):
        return "review_required", "Possible combination product; verify that the assessment matches the single-active scope intended by the project."
    for alias in aliases:
        a = re.escape(alias).replace(r"\ ", r"\s+")
        pats = [
            rf"{a}\s*\d+(?:\.\d+)?%\s*/\s*[a-z]",
            rf"\d+(?:\.\d+)?%\s*{a}\s+and\s+\d+(?:\.\d+)?%\s*[a-z]",
        ]
        if any(re.search(p, header_raw, re.I | re.S) for p in pats):
            return "review_required", "Possible combination product; verify that the assessment matches the single-active scope intended by the project."
    return "matched", None


def evidence_role(source: str, subtype: str) -> tuple[str, int]:
    if source in ("USP", "Ph. Eur."):
        return "pharmacopoeia", 0
    if source == "NICE":
        return "hta", 0
    if source == "Clinical Study":
        return "primary_study", 0
    if source == "FDA":
        if subtype in {"integrated_review", "summary_review", "clinical_review", "medical_review"}:
            return "primary_clinical_assessment", 1
        if subtype == "clinical_pharmacology_review":
            return "pharmacology_support", 0
        if subtype == "label":
            return "product_information", 0
        if subtype == "orange_book":
            return "administrative", 0
        return "regulatory_other", 0
    if source == "EMA":
        if subtype == "assessment_report":
            return "primary_clinical_assessment", 1
        if subtype == "medicine_overview":
            return "clinical_summary", 1
        if subtype in {"generic_medicine_overview", "biosimilar_medicine_overview"}:
            return "generic_or_biosimilar_summary", 0
        if subtype in {"risk_management_plan", "psur_scientific_conclusions"}:
            return "safety_support", 0
        if subtype == "smPC":
            return "product_information", 0
        if subtype == "orphan_designation":
            return "orphan_designation", 0
        if subtype == "paediatric_investigation_plan":
            return "paediatric_plan", 0
        if subtype == "national_authorisation_list":
            return "administrative", 0
        return "regulatory_other", 0
    return "unknown", 0


def classify(filename: str, text: str):
    broad = filename + "\n" + text[:30000]
    head = filename + "\n" + text[:6000]
    source, region = "Unknown", None
    for s, r, pats in SOURCE_PATTERNS:
        if any(re.search(p, broad, re.I) for p in pats):
            source, region = s, r
            break
    low = broad.lower()
    h = head.lower()

    if source in ("USP", "Ph. Eur."):
        subtype = "monograph"
        role, eligible = evidence_role(source, subtype)
        return source, region, "pharmacopoeia", subtype, role, eligible

    if source == "NICE":
        subtype = "technology_appraisal"
        role, eligible = evidence_role(source, subtype)
        return source, region, "hta", subtype, role, eligible

    if source == "FDA":
        if "prescription and over-the-counter drug product list" in h or "approved drug products with therapeutic equivalence evaluations" in h or "cumulative supplement" in h:
            subtype = "orange_book"
        else:
            title_zone = h[:2500]
            labels = [
                ("summary review", "summary_review"),
                ("office of clinical pharmacology review", "clinical_pharmacology_review"),
                ("clinical pharmacology review", "clinical_pharmacology_review"),
                ("clinical review", "clinical_review"),
                ("integrated review", "integrated_review"),
                ("medical review", "medical_review"),
            ]
            found = [(title_zone.find(label), subtype_name) for label, subtype_name in labels if title_zone.find(label) >= 0]
            if found:
                subtype = min(found, key=lambda x: x[0])[1]
            elif "prescribing information" in h or re.search(r"\blabel\b", filename, re.I):
                subtype = "label"
            else:
                subtype = "review"
        role, eligible = evidence_role(source, subtype)
        return source, region, "clinical_regulatory", subtype, role, eligible

    if source == "EMA":
        if "public summary of opinion on orphan designation" in h or ("orphan designation" in h and "committee for orphan medicinal products" in h):
            subtype = "orphan_designation"
        elif "risk management plan" in h:
            subtype = "risk_management_plan"
        elif "scientific conclusions and grounds for the variation" in h or "prac assessment report on the psur" in h or ("psusa/" in h and "scientific conclusions" in h):
            subtype = "psur_scientific_conclusions"
        elif "paediatric investigation plan" in h or "pediatric investigation plan" in h:
            subtype = "paediatric_investigation_plan"
        elif "list of nationally authorised medicinal products" in h or "list of nationally authorized medicinal products" in h:
            subtype = "national_authorisation_list"
        elif ("an overview of" in h or "epar summary for the public" in h) and ("generic medicine" in low or ("reference medicine" in low and "do not need to be repeated" in low)):
            subtype = "generic_medicine_overview"
        elif ("an overview of" in h or "epar summary for the public" in h) and "biosimilar" in low:
            subtype = "biosimilar_medicine_overview"
        elif "an overview of" in h and "authorised in the eu" in h:
            subtype = "medicine_overview"
        elif "epar summary for the public" in h:
            subtype = "medicine_overview"
        elif "summary of product characteristics" in h:
            subtype = "smPC"
        elif "public assessment report" in h or re.search(r"\bassessment report\b", h, re.I):
            subtype = "assessment_report"
        else:
            subtype = "ema_document"
        role, eligible = evidence_role(source, subtype)
        return source, region, "clinical_regulatory", subtype, role, eligible

    # Independent journal/clinical-trial article. Keep this after regulatory detection so an
    # FDA/EMA report mentioning trials is not accidentally reclassified as a study.
    study_score = 0
    for p in [r"\brandomi[sz]ed\b", r"\bphase\s+(?:ii|iii|2|3)\b", r"\bclinical trial\b", r"\bNCT\d{8}\b", r"\bhazard ratio\b", r"\b95\s*%\s*CI\b", r"\bdoi\s*:"]:
        if re.search(p, broad, re.I):
            study_score += 1
    if study_score >= 3:
        source, region, subtype = "Clinical Study", None, "journal_article"
        role, eligible = evidence_role(source, subtype)
        return source, region, "clinical_study", subtype, role, eligible

    role, eligible = evidence_role(source, "unknown")
    return source, region, "unknown", "unknown", role, eligible


def _clean_filename_candidate(filename: str) -> str | None:
    stem = Path(filename).stem
    stem = re.sub(r"(?i)(?:[-_ ](?:usp|uspnf|usp[-_ ]?nf|ep|pheur|ph[-_ ]?eur|ema|fda|nice|clinical|study|trial|review|label|report|monograph))(?:[-_ ].*)?$", "", stem).strip(" _-")
    stem = re.sub(r"[_]+", " ", stem)
    stem = re.sub(r"\s+", " ", stem).strip()
    if not stem or len(stem) < 3 or stem.lower() in GENERIC_FILENAME_WORDS:
        return None
    # Strip common dosage/product suffixes only if a useful active name remains.
    stem = re.sub(r"(?i)\s+(tablets?|capsules?|injection|cream|gel|oral solution)\s*$", "", stem).strip()
    return stem or None


def infer_drug_from_document(filename: str, text: str, source: str, existing_names: list[str] | None = None) -> tuple[str | None, float, str]:
    """Infer active substance for an uploaded PDF without relying on a parent folder.

    Conservative ordering: existing database aliases in the header -> explicit active-substance
    fields -> pharmacopoeia header -> descriptive filename. Low-confidence results should be
    reviewed by the user rather than silently attached to the wrong drug.
    """
    head_raw = text[:12000]
    head = _norm(head_raw)
    existing_names = existing_names or []

    # Existing drugs are the safest automatic match. Longest alias wins.
    hits: list[tuple[int, str]] = []
    for name in existing_names:
        for alias in drug_aliases(name):
            if len(alias) >= 4 and re.search(rf"\b{re.escape(alias)}\b", head):
                hits.append((len(alias), name))
    if hits:
        hits.sort(reverse=True)
        return hits[0][1], 0.97, "matched an existing drug name/alias in the document header"

    explicit_patterns = [
        r"(?im)^\s*(?:active substance|active ingredient|generic name|inn|international nonproprietary name)\s*[:\-]\s*([^\n]{3,100})",
        r"(?im)^\s*(?:drug substance|established name)\s*[:\-]\s*([^\n]{3,100})",
    ]
    for pat in explicit_patterns:
        m = re.search(pat, head_raw)
        if m:
            cand = re.split(r"[;,/(]", m.group(1))[0].strip()
            cand = re.sub(r"\b\d+(?:\.\d+)?\s*(?:mg|g|mcg|%|ml).*", "", cand, flags=re.I).strip()
            if 2 < len(cand) < 100:
                return resolve_existing_drug(cand, existing_names), 0.94, "explicit active-substance field"

    if source in ("USP", "Ph. Eur."):
        # Pharmacopoeial files normally place the monograph title near the first page. Prefer
        # a descriptive filename because it is less likely to capture a running header.
        fc = _clean_filename_candidate(filename)
        if fc:
            return resolve_existing_drug(fc, existing_names), 0.90, "pharmacopoeia filename/title"
        lines = [re.sub(r"\s+", " ", x).strip() for x in head_raw.splitlines() if x.strip()]
        skip = re.compile(r"(?i)pharmacopoeia|monographs?|official|copyright|stage|page|general notices|usp[- ]?nf")
        for line in lines[:80]:
            if skip.search(line) or len(line) < 3 or len(line) > 90:
                continue
            if re.fullmatch(r"[A-Za-z][A-Za-z0-9 ,()'\-]+", line) and len(line.split()) <= 8:
                return resolve_existing_drug(line, existing_names), 0.68, "candidate monograph title from first page"

    fc = _clean_filename_candidate(filename)
    if fc:
        return resolve_existing_drug(fc, existing_names), 0.72, "descriptive filename"

    return None, 0.0, "drug name could not be inferred safely"
