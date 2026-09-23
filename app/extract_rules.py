from __future__ import annotations
import json, re
from pathlib import Path
from .pdf import PDFDocument, clean, find_page_for_text
from .schemas import Evidence, QualityParameter, MonographExtraction, ClinicalExtraction, TrialExtraction, EndpointExtraction, SafetyExtraction

HEADINGS = [
    "DEFINITION", "CHARACTERS", "IDENTIFICATION", "TESTS", "ASSAY", "STORAGE",
    "IMPURITIES", "FUNCTIONALITY-RELATED CHARACTERISTICS", "DISSOLUTION", "UNIFORMITY OF DOSAGE UNITS",
]


def extract_between(text: str, starts, ends, limit=5000):
    start = None
    for pat in starts:
        m = re.search(pat, text, re.I | re.M)
        if m and (start is None or m.end() < start):
            start = m.end()
    if start is None:
        return None
    tail = text[start:]
    end = len(tail)
    for pat in ends:
        m = re.search(pat, tail, re.I | re.M)
        if m:
            end = min(end, m.start())
    return clean(tail[:end], limit)


def extract_section(text: str, heading: str, limit=6000):
    m = re.search(rf"(?im)^\s*{re.escape(heading)}\s*$", text)
    if not m:
        # USP bullets often render as • ASSAY / • TESTS
        m = re.search(rf"(?im)^\s*[•●]?\s*{re.escape(heading)}\s*$", text)
    if not m:
        return None
    tail = text[m.end():]
    end = len(tail)
    for h in HEADINGS:
        if h == heading:
            continue
        mm = re.search(rf"(?im)^\s*[•●]?\s*{re.escape(h)}\s*$", tail)
        if mm:
            end = min(end, mm.start())
    return clean(tail[:end], limit)


def split_monographs(text: str, drug: str, source: str):
    name = re.escape(drug.strip())
    candidates = []
    if source == "Ph. Eur.":
        pat = rf"(?im)^\s*\d{{2}}/\d{{4}}:\d+\s*$\s*^\s*({name}[^\n]*)\s*$"
        for m in re.finditer(pat, text):
            candidates.append((m.start(), m.group(1).strip()))
        if not candidates:
            for m in re.finditer(rf"(?im)^\s*({name}(?:\s+[^\n]{{0,80}})?)\s*$", text):
                title = m.group(1).strip()
                if title.lower().startswith(drug.lower()):
                    candidates.append((m.start(), title))
    else:
        # USP source extracts often repeat the drug name inside impurity tables.
        # Treat the first near-exact title line as the monograph start and do not
        # split again on later table rows such as "Regorafenib" or related-compound names.
        exact = re.compile(rf"(?im)^\s*[^\w\s]{{0,3}}\s*({name})\s*$")
        m = exact.search(text)
        if m:
            candidates.append((m.start(), m.group(1).strip()))
        else:
            m = re.search(rf"(?im)^\s*[^\w\s]{{0,3}}\s*({name}(?:[^\S\r\n]+(?:tablets?|capsules?|injection|oral solution))?)\s*$", text)
            if m: candidates.append((m.start(), m.group(1).strip()))
    if not candidates:
        return [(drug, text)]
    candidates = sorted(dict(candidates).items())
    out = []
    for i, (pos, title) in enumerate(candidates):
        end = candidates[i + 1][0] if i + 1 < len(candidates) else len(text)
        seg = text[pos:end]
        if len(seg) > 500:
            out.append((title, seg))
    return out or [(drug, text)]


def assay_param(segment: str, pages) -> QualityParameter | None:
    definition = extract_section(segment, "DEFINITION", 2500)
    assay = extract_section(segment, "ASSAY", 4500)
    scope = (definition or "") + "\n" + (assay or "") + "\n" + segment[:2500]
    patterns = [
        (r"NLT\s*(\d+(?:\.\d+)?)\s*%\s*and\s*NMT\s*(\d+(?:\.\d+)?)\s*%", "NLT/NMT"),
        (r"Content\s*:\s*(\d+(?:\.\d+)?)\s*per\s*cent\s*to\s*(\d+(?:\.\d+)?)\s*per\s*cent", "range"),
        (r"(\d+(?:\.\d+)?)\s*%\s*(?:to|–|-)\s*(\d+(?:\.\d+)?)\s*%", "range"),
    ]
    for pat, basis in patterns:
        m = re.search(pat, scope, re.I)
        if m:
            snippet = clean(scope[max(0,m.start()-180):m.end()+220], 650)
            return QualityParameter(
                category="assay", parameter_name="Assay acceptance range",
                value_text=f"{m.group(1)}–{m.group(2)}%", numeric_min=float(m.group(1)), numeric_max=float(m.group(2)),
                unit="%", basis=basis, method_name=_assay_method(assay),
                evidence=Evidence(page=find_page_for_text(pages, snippet), snippet=snippet, confidence=0.96)
            )
    return None


def _assay_method(section: str | None):
    if not section:
        return None
    if re.search(r"liquid chromatography|chromatographic system|HPLC|LC", section, re.I):
        return "Liquid chromatography"
    if re.search(r"titrate|titration|potentiometr", section, re.I):
        return "Titration"
    if re.search(r"spectrophot", section, re.I):
        return "Spectrophotometry"
    return None


def identification_params(segment, pages):
    sec = extract_section(segment, "IDENTIFICATION", 4500)
    if not sec:
        return []
    methods = [
        ("Infrared spectroscopy", r"infrared|IR spectrum"),
        ("UV/Visible spectroscopy", r"ultraviolet|UV[- /]?Vis"),
        ("Liquid chromatography", r"liquid chromatography|chromatograph|retention time"),
        ("Thin-layer chromatography", r"thin[- ]layer chromatography|TLC"),
        ("Specific optical rotation", r"specific optical rotation|optical rotation"),
        ("Chemical identification", r"Identification Tests—General|chemical identification|reaction \([a-z]\)"),
    ]
    out = []
    for name, pat in methods:
        m = re.search(pat, sec, re.I)
        if m:
            snippet = clean(sec[max(0,m.start()-140):m.end()+260], 600)
            out.append(QualityParameter(
                category="identification", parameter_name=name, value_text="Required",
                method_name=name, evidence=Evidence(page=find_page_for_text(pages, snippet), snippet=snippet, confidence=0.88)
            ))
    if not out:
        out.append(QualityParameter(category="identification", parameter_name="Identification tests", value_text=clean(sec,700), evidence=Evidence(page=find_page_for_text(pages, sec), snippet=clean(sec,600), confidence=0.65)))
    return out


def test_params(segment, pages):
    sec = extract_section(segment, "TESTS", 8500) or ""
    # Ph. Eur. may place tests as standalone subsections without TESTS heading
    scope = sec if sec else segment
    patterns = [
        ("related_substances", "Related substances", r"Related substances"),
        ("water", "Water", r"(?im)^\s*Water(?:\s*\([^\n]+\))?\s*[:.]"),
        ("loss_on_drying", "Loss on drying", r"Loss on drying"),
        ("ph", "pH", r"(?im)^\s*pH(?:\s*\([^\n]+\))?\s*[:.]"),
        ("residual_solvents", "Residual solvents", r"Residual solvents"),
        ("sulfated_ash", "Sulfated ash", r"Sulfated ash"),
        ("optical_rotation", "Optical rotation", r"Specific optical rotation|Optical rotation"),
    ]
    out=[]
    for cat,name,pat in patterns:
        m=re.search(pat,scope,re.I)
        if not m: continue
        snippet=clean(scope[m.start():m.start()+900],900)
        numeric_min=numeric_max=None; op=None; unit=None
        # capture common max/min percentage values near the test heading
        mm=re.search(r"(?:maximum|NMT|not more than)\s*(\d+(?:\.\d+)?)\s*(per cent|%)",snippet,re.I)
        if mm:
            numeric_max=float(mm.group(1)); op="<="; unit="%"
        mn=re.search(r"(?:minimum|NLT|not less than)\s*(\d+(?:\.\d+)?)\s*(per cent|%)",snippet,re.I)
        if mn:
            numeric_min=float(mn.group(1)); op=">="; unit="%"
        out.append(QualityParameter(category=cat,parameter_name=name,value_text=snippet,numeric_min=numeric_min,numeric_max=numeric_max,operator=op,unit=unit,evidence=Evidence(page=find_page_for_text(pages,snippet),snippet=snippet,confidence=0.78)))
    # impurity acceptance criteria: capture common total/unspecified statements wherever they appear
    for pname,pat in [
        ("Total impurities",r"total(?:\s+of)?\s+impurities[^\n]{0,120}?(?:maximum|NMT|not more than)?\s*(\d+(?:\.\d+)?)\s*(?:per cent|%)"),
        ("Unspecified impurity",r"(?:other|unspecified) impurit(?:y|ies)[^\n]{0,160}?(\d+(?:\.\d+)?)\s*(?:per cent|%)"),
        ("Disregard limit",r"disregard limit[^\n]{0,100}?(\d+(?:\.\d+)?)\s*(?:per cent|%)"),
    ]:
        m=re.search(pat,segment,re.I)
        if m:
            snippet=clean(segment[max(0,m.start()-120):m.end()+180],600)
            out.append(QualityParameter(category="impurity",parameter_name=pname,value_text=snippet,numeric_max=float(m.group(1)),operator="<=",unit="%",evidence=Evidence(page=find_page_for_text(pages,snippet),snippet=snippet,confidence=0.76)))
    return out


def dissolution_params(segment,pages):
    sec=extract_section(segment,"DISSOLUTION",6500)
    if not sec:
        m=re.search(r"(?i)Dissolution\s*<711>|Dissolution\s*\(2\.9\.3\)",segment)
        if m: sec=clean(segment[m.end():m.end()+4500],4500)
    if not sec: return []
    details={}
    for key,pat in [
        ("apparatus",r"Apparatus\s*(?:1|2)?[^\n]{0,80}|basket|paddle"),
        ("rpm",r"(\d{2,3})\s*rpm"),
        ("time_min",r"(\d{1,3})\s*min(?:utes?)?"),
        ("volume_ml",r"(\d{2,4})\s*mL"),
        ("q_percent",r"Q\s*=\s*(\d+(?:\.\d+)?)\s*%|NLT\s*(\d+(?:\.\d+)?)\s*%[^\n]{0,100}dissolv"),
    ]:
        m=re.search(pat,sec,re.I)
        if m: details[key]=next((g for g in m.groups() if g),m.group(0))
    return [QualityParameter(category="dissolution",parameter_name="Dissolution",value_text=clean(sec,1100),method_name="Dissolution test",method_details=details,evidence=Evidence(page=find_page_for_text(pages,sec),snippet=clean(sec,700),confidence=0.75))]


def storage_param(segment,pages):
    sec=extract_section(segment,"STORAGE",1800)
    if not sec: return []
    return [QualityParameter(category="storage",parameter_name="Storage",value_text=sec,evidence=Evidence(page=find_page_for_text(pages,sec),snippet=clean(sec,500),confidence=0.82))]


def extract_pharmacopoeia(doc: PDFDocument, drug: str, source: str):
    text=doc.text
    out=[]
    for title,segment in split_monographs(text,drug,source):
        lower=title.lower()
        material="finished_product" if re.search(r"\b(tablets?|capsules?|injection|oral solution|solution for|concentrate)\b",lower) else "API"
        dosage=None
        m=re.search(r"\b(tablets?|capsules?|injection|oral solution|solution for [^,;]+|concentrate)\b",title,re.I)
        if m: dosage=m.group(1)
        edition=None
        mm=re.search(r"EUROPEAN PHARMACOPOEIA\s+([0-9.]+)",text,re.I)
        if mm: edition=mm.group(1)
        mm=re.search(r"©\s*(20\d{2})\s+USPC",text,re.I)
        if mm and not edition: edition=mm.group(1)
        params=[]
        a=assay_param(segment,doc.pages)
        if a: params.append(a)
        params += identification_params(segment,doc.pages)
        params += test_params(segment,doc.pages)
        if material=="finished_product": params += dissolution_params(segment,doc.pages)
        params += storage_param(segment,doc.pages)
        out.append(MonographExtraction(monograph_name=title,material_type=material,dosage_form=dosage,edition=edition,confidence=max([p.evidence.confidence for p in params] or [0.55]),parameters=params))
    return out


def section_by_question(text,start_q,next_qs,limit=3500):
    m=re.search(re.escape(start_q),text,re.I)
    if not m: return None
    tail=text[m.end():]; end=len(tail)
    for q in next_qs:
        mm=re.search(re.escape(q),tail,re.I)
        if mm: end=min(end,mm.start())
    return clean(tail[:end],limit)


def _parse_effect_from_snippet(snippet):
    """Return effect measure/value/CI/p-value from a local evidence window.

    The parser is intentionally conservative. Meta-analysis only accepts rows with a positive
    effect estimate and a complete positive 95% CI, so partial extractions remain visible as
    evidence but are not pooled automatically.
    """
    effect_measure=effect_value=ci_low=ci_high=p_value=None
    pats=[
        ("HR", r"(?:HR|hazard ratio)\s*(?:of|was|=|:|,)?\s*(0?\.\d+|\d+(?:\.\d+)?)"),
        ("RR", r"(?:RR|risk ratio|relative risk)\s*(?:of|was|=|:|,)?\s*(0?\.\d+|\d+(?:\.\d+)?)"),
        ("OR", r"(?:OR|odds ratio)\s*(?:of|was|=|:|,)?\s*(0?\.\d+|\d+(?:\.\d+)?)"),
    ]
    for measure,pat in pats:
        m=re.search(pat,snippet,re.I)
        if m:
            effect_measure=measure; effect_value=float(m.group(1)); break
    ci_patterns=[
        r"95\s*%\s*(?:CI|confidence interval)\s*(?:of|was|=|:|,)?\s*[\[(]?\s*([0-9.]+)\s*(?:to|[-–—,])\s*([0-9.]+)",
        r"\(95\s*%\s*(?:CI)?\s*[,;:]?\s*([0-9.]+)\s*(?:to|[-–—,])\s*([0-9.]+)\)",
    ]
    for pat in ci_patterns:
        m=re.search(pat,snippet,re.I)
        if m:
            ci_low=float(m.group(1)); ci_high=float(m.group(2)); break
    pm=re.search(r"\bp\s*(?:=|<|≤)\s*(0?\.\d+|\d+(?:\.\d+)?)",snippet,re.I)
    if pm:
        try: p_value=float(pm.group(1))
        except ValueError: pass
    return effect_measure,effect_value,ci_low,ci_high,p_value


def _nearest_study_label(snippet, text=None):
    for pat in [r"\b(NCT\d{8})\b", r"\b(CORRECT|CONCUR|TERRA|RESORCE|MOSAIC|NO16968)\b", r"\b(?:Study|Trial)\s+([A-Z0-9_-]{3,24})\b"]:
        m=re.search(pat,snippet,re.I)
        if m: return m.group(1).upper() if m.group(1).upper().startswith('NCT') else m.group(1)
    return None


def _endpoint_candidates(text,pages):
    out=[]; seen=set()
    endpoint_patterns=[
        ("Overall survival",r"overall survival|\bOS\b"),
        ("Progression-free survival",r"progression[- ]free survival|\bPFS\b"),
        ("Disease-free survival",r"disease[- ]free survival|\bDFS\b"),
        ("Objective response rate",r"objective response rate|overall response rate|\bORR\b"),
        ("Event-free survival",r"event[- ]free survival|\bEFS\b"),
        ("DAS28",r"DAS28"),
    ]
    for name,pat in endpoint_patterns:
        # Allow several occurrences because an article can report multiple trial/subgroup estimates.
        for m in list(re.finditer(pat,text,re.I))[:12]:
            snippet=clean(text[max(0,m.start()-420):m.end()+1100],1600)
            effect_measure,effect_value,ci_low,ci_high,p_value=_parse_effect_from_snippet(snippet)
            label=_nearest_study_label(snippet,text)
            key=(name,label,effect_measure,effect_value,ci_low,ci_high)
            if key in seen: continue
            # Keep endpoint evidence even without an effect estimate; only complete rows are pooled.
            conf=0.58
            if effect_measure and effect_value is not None: conf=0.76
            if effect_measure and effect_value is not None and ci_low is not None and ci_high is not None: conf=0.88
            out.append(EndpointExtraction(endpoint_name=name,study_label=label,effect_measure=effect_measure,effect_value=effect_value,ci_low=ci_low,ci_high=ci_high,p_value=p_value,agency_interpretation=snippet,source_page=find_page_for_text(pages,snippet),confidence=conf))
            seen.add(key)
            # Regulatory documents are verbose; cap repeated weak rows. Complete trial rows may continue.
            if len([x for x in out if x.endpoint_name==name])>=4: break
    # If an article reports an effect ratio without spelling the endpoint nearby, do not invent the endpoint.
    return out


def _trial_candidates(text):
    names=[]
    for m in re.finditer(r"\b(?:Study|Trial)\s+([A-Z][A-Z0-9_-]{2,20}|\d{3,8})\b|\b(NCT\d{8})\b",text,re.I):
        val=next(g for g in m.groups() if g)
        if val.lower() not in [x.lower() for x in names]: names.append(val)
        if len(names)>=12: break
    for m in re.finditer(r"\b(CORRECT|CONCUR|TERRA|RESORCE|NO16968|MOSAIC)\b",text,re.I):
        val=m.group(1).upper()
        if val not in names: names.append(val)
    return [TrialExtraction(trial_name=n,trial_id=n,confidence=0.65) for n in names[:15]]


def extract_clinical_study(doc:PDFDocument,subtype:str):
    text=doc.text
    c=ClinicalExtraction(agency="Clinical Study",assessment_type=subtype,confidence=0.72)
    # Abstract/title are stored as contextual fields, not interpreted as regulatory conclusions.
    title_lines=[clean(x,300) for x in text[:3500].splitlines() if clean(x,300)]
    if title_lines:
        c.recommendation=title_lines[0]
    # Capture a concise population/methods fragment when possible.
    m=re.search(r"(?is)\b(?:patients|participants)\b(.{0,1600}?)(?:\bresults\b|\bprimary endpoint\b)",text[:25000])
    if m: c.population=clean(m.group(0),1600)
    c.trials=_trial_candidates(text)
    c.endpoints=_endpoint_candidates(text,doc.pages)
    # Try to copy a detected NCT/study name into endpoint rows lacking a local label.
    fallback=(c.trials[0].trial_id if len(c.trials)==1 else None)
    if fallback:
        for ep in c.endpoints:
            if not ep.study_label: ep.study_label=fallback
    return c


def extract_ema(doc:PDFDocument,subtype:str):
    text=doc.text
    c=ClinicalExtraction(agency="EMA",assessment_type=subtype,confidence=0.62)
    if subtype=="medicine_overview":
        c.indication=section_by_question(text,"What is",["How is","How does","What benefits"],2500)
        eff=section_by_question(text,"What benefits",["What are the risks","Why is"],3000)
        safety=section_by_question(text,"What are the risks",["Why is","What measures"],2800)
        br=section_by_question(text,"Why is",["What measures","Other information"],2200)
        c.relative_effectiveness=eff
        c.benefit_risk=_categorize_benefit_risk(br)
        c.recommendation=br
        c.confidence=0.88
        for field,val in [("indication",c.indication),("relative_effectiveness",eff),("recommendation",br)]:
            if val: c.evidence[field]=Evidence(page=find_page_for_text(doc.pages,val),snippet=clean(val,650),confidence=0.88)
        c.safety += _safety_from_summary(safety,doc.pages)
    elif subtype=="smPC":
        c.indication=extract_between(text,[r"(?im)^4\.1\s+Therapeutic indications"],[r"(?im)^4\.2\s+Posology"],3000)
        safety=extract_between(text,[r"(?im)^4\.8\s+Undesirable effects"],[r"(?im)^4\.9\s+Overdose",r"(?im)^5\s+PHARMACOLOGICAL"],3000)
        c.safety += _safety_from_summary(safety,doc.pages); c.confidence=0.82
    elif subtype=="risk_management_plan":
        c.uncertainty="Risk Management Plan: use mainly for safety/pharmacovigilance; not the primary efficacy source."
        # capture summary table area
        s=extract_between(text,[r"(?im)^.*Summary of safety concerns.*$"],[r"(?im)^.*Pharmacovigilance Plan.*$",r"(?im)^Part III"],4200)
        c.safety += _safety_from_summary(s,doc.pages); c.confidence=0.72
    elif subtype=="psur_scientific_conclusions":
        s=extract_between(text,[r"Scientific conclusions"],[r"Grounds for",r"Annex II"],4000)
        c.safety += _safety_from_summary(s,doc.pages); c.uncertainty="PSUR/PRAC safety update; not primary efficacy evidence."; c.confidence=0.76
    elif subtype in ("assessment_report","ema_document"):
        c.indication=extract_between(text,[r"Therapeutic indication",r"Indication"],[r"Posology",r"Dose"],2500)
        c.recommendation=extract_between(text,[r"Benefit[-– ]risk balance",r"Conclusions? on the benefit[-– ]risk"],[r"Recommendation",r"Risk management"],3000)
        c.benefit_risk=_categorize_benefit_risk(c.recommendation); c.confidence=0.74
    c.trials=_trial_candidates(text)
    c.endpoints=_endpoint_candidates(text,doc.pages)
    return c


def _categorize_benefit_risk(text):
    if not text: return None
    low=text.lower()
    if "benefits" in low and "outweigh" in low and "risk" in low: return "positive"
    if "positive benefit-risk" in low or "benefit-risk balance is positive" in low: return "positive"
    if "negative benefit-risk" in low: return "negative"
    return "not_stated"


def _safety_from_summary(text,pages):
    if not text: return []
    out=[]
    # one compact summary record + selected common phrases
    out.append(SafetyExtraction(event_name="Safety summary",category="summary",interpretation=clean(text,1200),source_page=find_page_for_text(pages,text),confidence=0.7))
    for m in list(re.finditer(r"(?:most common|serious) (?:side effects|adverse events?)[^.!?]{0,450}",text,re.I))[:4]:
        sn=clean(m.group(0),600)
        out.append(SafetyExtraction(event_name="Reported adverse events",category="adverse_event",interpretation=sn,source_page=find_page_for_text(pages,sn),confidence=0.64))
    return out


def extract_fda(doc:PDFDocument,subtype:str):
    text=doc.text
    c=ClinicalExtraction(agency="FDA",assessment_type=subtype,confidence=0.68)
    def one(pat):
        m=re.search(pat,text,re.I|re.M); return clean(m.group(1),600) if m else None
    c.indication=one(r"Indication(?:\(s\))?\s*[:]?\s+([^\n]+)")
    rec=extract_between(text,[r"(?im)^\s*RECOMMENDATIONS?\s*$",r"(?im)^\s*Benefit[-– ]Risk Assessment\s*$"],[r"(?im)^\s*1\.",r"(?im)^\s*2\s+",r"(?im)^\s*Executive Summary"],2500)
    executive=extract_between(text,[r"(?im)^\s*(?:1\s+)?EXECUTIVE SUMMARY\s*$",r"(?im)^\s*SUMMARY REVIEW\s*$"],[r"(?im)^\s*2\s+",r"(?im)^\s*RECOMMENDATIONS?\s*$"],4200)
    c.recommendation=rec
    c.benefit_risk=_categorize_benefit_risk((rec or "")+" "+(executive or ""))
    if c.indication: c.evidence["indication"]=Evidence(page=find_page_for_text(doc.pages,c.indication),snippet=c.indication,confidence=0.8)
    if rec: c.evidence["recommendation"]=Evidence(page=find_page_for_text(doc.pages,rec),snippet=clean(rec,650),confidence=0.72)
    c.trials=_trial_candidates(text)
    c.endpoints=_endpoint_candidates(text,doc.pages)
    # safety signals from executive section if present
    c.safety += _safety_from_summary(executive,doc.pages)
    return c


def extract_nice(doc:PDFDocument,subtype:str):
    text=doc.text
    c=ClinicalExtraction(agency="NICE",assessment_type=subtype,confidence=0.82)
    title=re.search(r"^(.+?)\nTechnology appraisal guidance",text,re.I|re.M)
    if title: c.indication=clean(title.group(1),700)
    rec=extract_between(text,[r"(?im)^\s*1\s+Recommendations\s*$"],[r"(?im)^\s*2\s+Information about",r"(?im)^\s*2\s+The technology"],4200)
    c.recommendation=rec
    # comparator-focused section
    comp=extract_between(text,[r"(?im)^\s*Comparators?\s*$",r"(?im)^\s*Comparators?\s+\d"],[r"(?im)^\s*Clinical effectiveness",r"(?im)^\s*Company",r"(?im)^\s*Cost effectiveness"],2200)
    if not comp:
        m=re.search(r"Comparators?\s+3\.\d(.{0,2400})",text,re.I|re.S)
        if m: comp=clean(m.group(1),2000)
    c.comparator=comp
    # cost-effectiveness conclusion; keep concise
    ce=None
    for m in re.finditer(r"[^.]{0,220}(?:cost effective|cost-effective|acceptable use of NHS resources)[^.]{0,320}\.",text,re.I):
        ce=clean(m.group(0),700)
        if "committee" in ce.lower() or "recommended" in ce.lower(): break
    c.cost_effectiveness=ce
    reff=None
    for m in re.finditer(r"[^.]{0,240}(?:overall survival|progression-free survival|relative effectiveness|similar benefits)[^.]{0,420}\.",text,re.I):
        candidate=clean(m.group(0),800)
        if "committee" in candidate.lower() or "concluded" in candidate.lower(): reff=candidate; break
    c.relative_effectiveness=reff
    c.managed_entry="not_stated"
    if re.search(r"managed access|managed entry|commercial arrangement",text,re.I): c.managed_entry="mentioned"
    c.restrictions=rec
    for field,val,conf in [("indication",c.indication,0.9),("recommendation",rec,0.9),("comparator",comp,0.72),("cost_effectiveness",ce,0.68),("relative_effectiveness",reff,0.66)]:
        if val: c.evidence[field]=Evidence(page=find_page_for_text(doc.pages,val),snippet=clean(val,650),confidence=conf)
    c.trials=_trial_candidates(text)
    c.endpoints=_endpoint_candidates(text,doc.pages)
    return c


def extract_clinical(doc:PDFDocument,source:str,subtype:str):
    if source=="EMA": return extract_ema(doc,subtype)
    if source=="FDA": return extract_fda(doc,subtype)
    if source=="NICE": return extract_nice(doc,subtype)
    if source=="Clinical Study": return extract_clinical_study(doc,subtype)
    return ClinicalExtraction(agency=source,assessment_type=subtype,confidence=0.3)
