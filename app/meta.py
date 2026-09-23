from __future__ import annotations

import html
import math
import re
from collections import defaultdict

_Z975 = 1.959963984540054


def norm_endpoint(s: str | None) -> str:
    if not s:
        return ""
    x = re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()
    aliases = {
        "overall survival": "overall survival",
        "os": "overall survival",
        "progression free survival": "progression free survival",
        "pfs": "progression free survival",
        "disease free survival": "disease free survival",
        "dfs": "disease free survival",
        "objective response rate": "objective response rate",
        "overall response rate": "objective response rate",
        "orr": "objective response rate",
        "event free survival": "event free survival",
        "efs": "event free survival",
    }
    return aliases.get(x, x)


def _norm_context(s: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def eligible_effect_rows(con, drug_id: int | None = None, clinical_studies_only: bool = True):
    where = [
        "e.effect_measure IN ('HR','RR','OR')",
        "e.effect_value>0",
        "e.ci_low>0",
        "e.ci_high>0",
        "e.ci_low<e.ci_high",
    ]
    args: list[object] = []
    if drug_id is not None:
        where.append("d.drug_id=?")
        args.append(drug_id)
    if clinical_studies_only:
        where.append("d.doc_type='clinical_study'")
    sql = f"""
      SELECT e.*,d.id document_id,d.filename,d.source,d.doc_type,d.sha256,
             dr.canonical_name drug_name,
             a.indication,a.population,a.comparator,
             COALESCE(e.study_label,t.trial_id,t.trial_name,d.filename) study_name
      FROM clinical_endpoints e
      JOIN clinical_assessments a ON a.id=e.assessment_id
      JOIN documents d ON d.id=a.document_id
      JOIN drugs dr ON dr.id=d.drug_id
      LEFT JOIN clinical_trials t ON t.id=e.trial_id
      WHERE {' AND '.join(where)}
      ORDER BY dr.canonical_name,e.endpoint_name,e.effect_measure,d.id,e.id
    """
    rows = [dict(r) for r in con.execute(sql, args).fetchall()]

    # Dedupe exact repeated estimates within one PDF. Cross-document duplicates are
    # intentionally handled later using the study label so we do not silently merge studies.
    seen = set()
    out = []
    for r in rows:
        key = (
            r["document_id"],
            norm_endpoint(r["endpoint_name"]),
            r["effect_measure"],
            round(r["effect_value"], 8),
            round(r["ci_low"], 8),
            round(r["ci_high"], 8),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def _stable_study_key(row: dict) -> str:
    """Return a conservative study key used only to detect obvious duplicate trial reports."""
    name = str(row.get("study_name") or "").strip()
    filename = str(row.get("filename") or "").strip()
    n = _norm_context(name)
    f = _norm_context(filename)
    # If the fallback is just the PDF filename, treat each document as distinct.
    if not n or n == f or name.lower().endswith(".pdf"):
        return f"document:{row.get('document_id')}"
    return f"study:{n}"


def _dedupe_cross_document(rows: list[dict]) -> tuple[list[dict], list[str], bool]:
    """Remove exact duplicated estimates for the same named study.

    If the same named study has conflicting estimates, do not pool automatically. That can
    represent a subgroup, time point, adjusted analysis, or extraction error and needs review.
    """
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        groups[_stable_study_key(row)].append(row)

    out: list[dict] = []
    warnings: list[str] = []
    conflict = False
    for key, items in groups.items():
        if len(items) == 1 or key.startswith("document:"):
            out.extend(items)
            continue
        estimates = {
            (
                round(float(x["effect_value"]), 8),
                round(float(x["ci_low"]), 8),
                round(float(x["ci_high"]), 8),
                _norm_context(x.get("timepoint")),
            )
            for x in items
        }
        if len(estimates) == 1:
            chosen = max(items, key=lambda x: float(x.get("confidence") or 0.0))
            out.append(chosen)
            warnings.append(
                f"Duplicate report detected for {chosen.get('study_name') or key}; "
                "one identical estimate was retained."
            )
        else:
            conflict = True
            label = items[0].get("study_name") or key
            warnings.append(
                f"Conflicting extracted estimates were found for the same study ({label}). "
                "Resolve the trial/timepoint/subgroup manually before pooling."
            )
    return out, warnings, conflict


def _context_warnings(rows: list[dict]) -> list[str]:
    warnings: list[str] = []
    for field, label in [
        ("indication", "indication"),
        ("population", "population"),
        ("comparator", "comparator"),
        ("timepoint", "time point"),
    ]:
        values = {_norm_context(r.get(field)) for r in rows if _norm_context(r.get(field))}
        if len(values) > 1:
            warnings.append(
                f"The extracted {label} is not identical across candidate studies. "
                "Verify clinical comparability manually."
            )
        elif not values:
            warnings.append(
                f"No structured {label} was available for the candidate studies; "
                "pooling requires manual verification of the source papers."
            )
    return warnings


def meta_groups(con, clinical_studies_only: bool = True):
    rows = eligible_effect_rows(con, None, clinical_studies_only)
    groups = defaultdict(list)
    for r in rows:
        groups[(r["drug_name"], norm_endpoint(r["endpoint_name"]), r["effect_measure"])].append(r)
    out = []
    for (drug, endpoint, measure), items in sorted(groups.items()):
        deduped, warnings, conflict = _dedupe_cross_document(items)
        out.append(
            {
                "drug_name": drug,
                "endpoint": endpoint,
                "effect_measure": measure,
                "n": len(deduped),
                "eligible": len(deduped) >= 2 and not conflict,
                "review_required": bool(warnings or _context_warnings(deduped)),
            }
        )
    return out


def _study_stats(row):
    y = math.log(float(row["effect_value"]))
    low = float(row["ci_low"])
    high = float(row["ci_high"])
    se = (math.log(high) - math.log(low)) / (2 * _Z975)
    if not math.isfinite(se) or se <= 0:
        raise ValueError("invalid confidence interval")
    return y, se, se * se


def run_meta_analysis(rows):
    """Exploratory generic inverse-variance meta-analysis on log HR/RR/OR.

    Returns inverse-variance fixed effect and DerSimonian-Laird random effects. This is a
    research aid, not a replacement for protocol-driven systematic review. The caller must
    verify that indication, population, comparator, endpoint definition, time point, and study
    identity are clinically compatible.
    """
    deduped, review_warnings, duplicate_conflict = _dedupe_cross_document(list(rows))
    review_warnings.extend(_context_warnings(deduped))
    if duplicate_conflict:
        return {
            "k": len(deduped),
            "error": "Conflicting estimates for the same study require manual review before pooling.",
            "review_warnings": review_warnings,
            "method": "Generic inverse variance; DerSimonian-Laird random effects",
        }

    usable = []
    for r in deduped:
        try:
            y, se, var = _study_stats(r)
            usable.append({**r, "log_effect": y, "se": se, "variance": var})
        except Exception:
            continue
    k = len(usable)
    if k < 2:
        return {
            "k": k,
            "error": "At least two complete compatible studies are required.",
            "review_warnings": review_warnings,
            "method": "Generic inverse variance; DerSimonian-Laird random effects",
        }

    w = [1 / x["variance"] for x in usable]
    sw = sum(w)
    mu_fixed = sum(wi * x["log_effect"] for wi, x in zip(w, usable)) / sw
    se_fixed = math.sqrt(1 / sw)
    q = sum(wi * (x["log_effect"] - mu_fixed) ** 2 for wi, x in zip(w, usable))
    df = k - 1
    i2 = max(0.0, (q - df) / q * 100.0) if q > 0 else 0.0
    c = sw - sum(wi * wi for wi in w) / sw
    tau2 = max(0.0, (q - df) / c) if c > 0 else 0.0
    wr = [1 / (x["variance"] + tau2) for x in usable]
    swr = sum(wr)
    mu_random = sum(wi * x["log_effect"] for wi, x in zip(wr, usable)) / swr
    se_random = math.sqrt(1 / swr)

    for x, wi, wri in zip(usable, w, wr):
        x["fixed_weight_pct"] = 100 * wi / sw
        x["random_weight_pct"] = 100 * wri / swr

    return {
        "k": k,
        "studies": usable,
        "fixed": {
            "effect": math.exp(mu_fixed),
            "ci_low": math.exp(mu_fixed - _Z975 * se_fixed),
            "ci_high": math.exp(mu_fixed + _Z975 * se_fixed),
        },
        "random": {
            "effect": math.exp(mu_random),
            "ci_low": math.exp(mu_random - _Z975 * se_random),
            "ci_high": math.exp(mu_random + _Z975 * se_random),
        },
        "Q": q,
        "df": df,
        "I2": i2,
        "tau2": tau2,
        "review_warnings": review_warnings,
        "method": "Generic inverse variance; DerSimonian-Laird random effects",
    }


def select_group(con, drug_name: str, endpoint: str, effect_measure: str, clinical_studies_only: bool = True):
    rows = eligible_effect_rows(con, None, clinical_studies_only)
    return [
        r
        for r in rows
        if r["drug_name"] == drug_name
        and norm_endpoint(r["endpoint_name"]) == norm_endpoint(endpoint)
        and r["effect_measure"] == effect_measure
    ]


def forest_svg(result, effect_measure: str, width=980, row_h=38):
    if not result or result.get("k", 0) < 2 or "random" not in result:
        return ""
    studies = result["studies"]
    pooled = result["random"]
    vals = []
    for s in studies:
        vals.extend([s["ci_low"], s["ci_high"], s["effect_value"]])
    vals.extend([pooled["ci_low"], pooled["ci_high"], pooled["effect"]])
    vals = [v for v in vals if v and v > 0]
    lo = min(vals)
    hi = max(vals)
    lo = min(lo, 1.0)
    hi = max(hi, 1.0)
    llo = math.log(lo)
    lhi = math.log(hi)
    pad = max(0.12, (lhi - llo) * 0.08)
    llo -= pad
    lhi += pad
    plot_x0 = 360
    plot_x1 = 810

    def sx(v):
        lv = math.log(max(v, 1e-12))
        return plot_x0 + (lv - llo) / (lhi - llo) * (plot_x1 - plot_x0)

    height = 110 + row_h * (len(studies) + 2)
    parts = [
        f'<svg viewBox="0 0 {width} {height}" width="100%" role="img" aria-label="Forest plot">',
        '<style>text{font-family:Inter,Arial,sans-serif;fill:#17202a}.small{font-size:12px}.label{font-size:13px}.muted{fill:#667085}.axis{stroke:#98a2b3;stroke-width:1}.line{stroke:#344054;stroke-width:2}.box{fill:#475467}.diamond{fill:#111827}</style>',
        f'<text x="20" y="28" class="label">Study</text><text x="820" y="28" class="label">{html.escape(effect_measure)} (95% CI)</text>',
        f'<line x1="{sx(1.0):.1f}" x2="{sx(1.0):.1f}" y1="42" y2="{height-46}" class="axis" stroke-dasharray="4 4"/>',
    ]
    y = 64
    for s in studies:
        name = html.escape(str(s.get("study_name") or s.get("filename") or "Study"))[:80]
        parts.append(f'<text x="20" y="{y+4}" class="small">{name}</text>')
        parts.append(
            f'<line x1="{sx(s["ci_low"]):.1f}" x2="{sx(s["ci_high"]):.1f}" y1="{y}" y2="{y}" class="line"/>'
        )
        box = 4 + 8 * math.sqrt(max(0, s.get("random_weight_pct", 0)) / 100)
        parts.append(
            f'<rect x="{sx(s["effect_value"])-box/2:.1f}" y="{y-box/2:.1f}" width="{box:.1f}" height="{box:.1f}" class="box"/>'
        )
        parts.append(
            f'<text x="820" y="{y+4}" class="small">{s["effect_value"]:.3f} ({s["ci_low"]:.3f}–{s["ci_high"]:.3f})</text>'
        )
        y += row_h
    pe, pl, ph = pooled["effect"], pooled["ci_low"], pooled["ci_high"]
    cx = sx(pe)
    left = sx(pl)
    right = sx(ph)
    dy = 9
    parts.append(f'<text x="20" y="{y+4}" class="label">Random-effects pooled</text>')
    parts.append(
        f'<polygon points="{left:.1f},{y} {cx:.1f},{y-dy} {right:.1f},{y} {cx:.1f},{y+dy}" class="diamond"/>'
    )
    parts.append(f'<text x="820" y="{y+4}" class="label">{pe:.3f} ({pl:.3f}–{ph:.3f})</text>')
    axis_y = height - 34
    parts.append(f'<line x1="{plot_x0}" x2="{plot_x1}" y1="{axis_y}" y2="{axis_y}" class="axis"/>')
    for v in sorted(set([lo, 1.0, hi])):
        x = sx(v)
        parts.append(
            f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{axis_y-4}" y2="{axis_y+4}" class="axis"/><text x="{x-18:.1f}" y="{axis_y+20}" class="small muted">{v:.2g}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)
