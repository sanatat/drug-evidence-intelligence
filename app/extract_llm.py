from __future__ import annotations
import json, os, re, urllib.request
from typing import Any
from .pdf import PDFDocument, clean

DEFAULT_MODEL=os.getenv("OLLAMA_MODEL","qwen3:8b")
DEFAULT_URL=os.getenv("OLLAMA_URL","http://127.0.0.1:11434/api/chat")

ATTRIBUTE_SCHEMA = {
  "indication": "string|null",
  "population": "string|null",
  "disease_stage": "string|null",
  "line_of_therapy": "string|null",
  "biomarker": "string|null",
  "combination_therapy": "string|null",
  "comparator": "string|null",
  "relative_effectiveness": "positive|equal|negative|uncertain|not_stated",
  "benefit_risk": "positive|negative|uncertain|conditional|not_stated",
  "cost_effectiveness": "positive|negative|uncertain|conditional|not_stated",
  "managed_entry": "yes|no|not_stated",
  "recommendation": "string|null",
  "restrictions": "string|null",
  "uncertainty": "string|null",
  "evidence": {"field": {"page": "integer|null", "snippet": "short string|null"}}
}

KEYWORDS=["recommend", "comparator", "overall survival", "progression-free", "benefit-risk", "cost effective", "cost-effective", "indication", "efficacy", "safety"]


def select_context(doc:PDFDocument,max_chars=18000):
    scored=[]
    for p in doc.pages:
        low=p.text.lower(); score=sum(k in low for k in KEYWORDS)
        if score: scored.append((score,p.number,p.text))
    scored.sort(reverse=True)
    chunks=[]; used=0
    for _,num,text in scored:
        piece=f"\n--- PAGE {num} ---\n{text}"
        if used+len(piece)>max_chars: continue
        chunks.append(piece); used+=len(piece)
        if used>=max_chars: break
    if not chunks:
        for p in doc.pages[:8]:
            piece=f"\n--- PAGE {p.number} ---\n{p.text}"
            if used+len(piece)>max_chars: break
            chunks.append(piece); used+=len(piece)
    return "".join(chunks)


def available(url=DEFAULT_URL,timeout=0.6):
    try:
        req=urllib.request.Request(url.replace('/api/chat','/api/tags'))
        with urllib.request.urlopen(req,timeout=timeout) as r: return r.status==200
    except Exception: return False


def extract_clinical_llm(doc:PDFDocument,source:str,subtype:str,model=DEFAULT_MODEL,url=DEFAULT_URL,timeout=180):
    context=select_context(doc)
    system=(
      "You extract structured pharmaceutical evidence. Use only the supplied pages. "
      "Never infer missing facts. Return strict JSON only. If a field is absent use null or not_stated. "
      "Keep evidence snippets short and copy only the minimum wording needed to support the field. "
      "Comparator and relative-effectiveness fields require explicit evidence."
    )
    user=f"""Source: {source}\nDocument type: {subtype}\nSchema:\n{json.dumps(ATTRIBUTE_SCHEMA,ensure_ascii=False)}\n\nPages:\n{context}"""
    payload={"model":model,"stream":False,"format":"json","messages":[{"role":"system","content":system},{"role":"user","content":user}],"options":{"temperature":0}}
    data=json.dumps(payload).encode()
    req=urllib.request.Request(url,data=data,headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(req,timeout=timeout) as r:
        obj=json.loads(r.read().decode())
    content=obj.get("message",{}).get("content","")
    return json.loads(content)


def merge_missing(rule_obj, llm:dict[str,Any]):
    """Only fill missing/weak rule fields. Deterministic numeric facts are never overwritten."""
    fields=["indication","population","disease_stage","line_of_therapy","biomarker","combination_therapy","comparator","relative_effectiveness","benefit_risk","cost_effectiveness","managed_entry","recommendation","restrictions","uncertainty"]
    for f in fields:
        incoming=llm.get(f)
        current=getattr(rule_obj,f,None)
        if incoming not in (None,"",[],{}) and (current in (None,"", "not_stated") or (isinstance(current,str) and len(current)<15)):
            setattr(rule_obj,f,incoming)
    # evidence stays provenance-only and can be attached by pipeline
    rule_obj.confidence=max(rule_obj.confidence,0.8)
    return rule_obj
