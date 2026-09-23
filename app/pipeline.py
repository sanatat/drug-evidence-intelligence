from __future__ import annotations
import json, re
from pathlib import Path
from .db import connect
from .pdf import load_pdf, sha256, clean
from .classify import classify, infer_drug, assess_drug_identity
from .extract_rules import extract_pharmacopoeia, extract_clinical
from .extract_llm import available as llm_available, extract_clinical_llm, merge_missing


def copyright_note(source,text):
    if source=="USP": return "Licensed/copyrighted USP-NF content. Keep source private; do not redistribute full text."
    if source=="Ph. Eur.": return "Licensed/copyrighted Ph. Eur. content. Keep source private unless reuse rights permit otherwise."
    if source=="EMA":
        if re.search(r"Reproduction is authorised provided the source is acknowledged",text,re.I): return "EMA document states reproduction is authorised provided the source is acknowledged."
        return "Retain source attribution and check the specific EMA reuse notice."
    if source=="NICE": return "Follow NICE notice of rights and current AI/reuse terms; public access does not automatically grant unrestricted AI reuse or republication."
    if source=="FDA": return "US federal source; verify third-party material notices in the specific document."
    if source=="Clinical Study": return "Journal article/research report; retain citation and verify reuse rights for the source PDF."
    return None


def get_drug_id(con,name):
    con.execute("INSERT OR IGNORE INTO drugs(canonical_name) VALUES (?)",(name,))
    return con.execute("SELECT id FROM drugs WHERE canonical_name=?",(name,)).fetchone()[0]


def add_evidence(con,document_id,field_path,evidence,method="rules"):
    if not evidence or (not evidence.snippet and evidence.page is None): return None
    cur=con.execute('''INSERT INTO evidence_spans(document_id,field_path,page_number,snippet,extraction_method,confidence) VALUES (?,?,?,?,?,?)''',
      (document_id,field_path,evidence.page,clean(evidence.snippet,900),method,evidence.confidence))
    return cur.lastrowid


def add_issue(con,document_id,severity,code,field,message):
    con.execute("INSERT INTO validation_issues(document_id,severity,code,field_path,message) VALUES (?,?,?,?,?)",(document_id,severity,code,field,message))


def validate_quality(con,document_id,monograph_id):
    rows=con.execute("SELECT * FROM quality_parameters WHERE monograph_id=?",(monograph_id,)).fetchall()
    for r in rows:
        if r['numeric_min'] is not None and r['numeric_max'] is not None and r['numeric_min']>r['numeric_max']:
            add_issue(con,document_id,'error','MIN_GT_MAX',r['parameter_name'],'Extracted minimum is greater than maximum.')
        if r['category']=='assay' and r['unit']=='%' and r['numeric_min'] is not None and not (50<=r['numeric_min']<=110):
            add_issue(con,document_id,'warning','ASSAY_RANGE_SUSPICIOUS',r['parameter_name'],'Assay percentage is outside the expected parser sanity range; review source.')


def extract_document_date(text: str, source: str) -> str | None:
    """Best-effort date metadata extraction; never used as clinical evidence."""
    head=text[:16000]
    patterns=[
        r"(?i)(?:document date|assessment date|date of issue|effective date|revision date|last updated|date)\s*[:\-]\s*((?:\d{1,2}\s+)?(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+20\d{2})",
        r"(?i)\b((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+20\d{2})\b",
        r"\b(20\d{2}-\d{2}-\d{2})\b",
        r"\b(\d{1,2}[./-]\d{1,2}[./-]20\d{2})\b",
    ]
    for pat in patterns:
        m=re.search(pat,head)
        if m: return clean(m.group(1),80)
    return None


def extract_application_metadata(text: str, source: str):
    application_number=product_name=None
    if source=='FDA':
        m=re.search(r"(?:Application Number|NDA)\s*[:#]?\s*([0-9]{5,6})",text,re.I); application_number=m.group(1) if m else None
        m=re.search(r"(?:Trade Name|Proprietary Name|Product Name)\s*[:]?\s*([^\n]+)",text,re.I); product_name=clean(m.group(1),200) if m else None
    elif source=='EMA':
        m=re.search(r"(?im)^\s*(?:Name of the medicinal product|Medicine)\s*[:\-]\s*([^\n]+)",text[:12000])
        if m: product_name=clean(m.group(1),200)
    return application_number,product_name


def insert_pdf(con,path:Path,use_llm=False,llm_model="qwen3:8b",drug_override: str|None=None,ingest_origin='folder',category_path: str|None=None,classification_confidence: float=0.85):
    pdf=load_pdf(path); text=pdf.text; digest=sha256(path)
    duplicate=con.execute("SELECT id,filename FROM documents WHERE sha256=?",(digest,)).fetchone()
    if duplicate: return False,f"skip duplicate {path.name}",duplicate['id']

    drug=(drug_override or infer_drug(path)).strip()
    source,region,doc_type,subtype,evidence_role,comparison_eligible=classify(path.name,text)
    drug_id=get_drug_id(con,drug)
    identity_status, identity_note = assess_drug_identity(drug, text) if doc_type in ('clinical_regulatory','hta','clinical_study') else ('matched', None)
    # Independent trial articles often use brand/combination wording. A mismatch is still stored,
    # but never allowed into automatic meta-analysis unless the selected drug is actually present.
    if identity_status != 'matched': comparison_eligible = 0

    application_number,product_name=extract_application_metadata(text,source)
    document_date=extract_document_date(text,source)
    cur=con.execute('''INSERT INTO documents(
      drug_id,source,region,doc_type,subtype,title,file_path,filename,sha256,page_count,application_number,product_name,
      copyright_note,extraction_method,evidence_role,comparison_eligible,drug_identity_status,document_note,document_date,
      classification_confidence,ingest_origin,category_path)
      VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(
      drug_id,source,region,doc_type,subtype,clean(text[:600],300),str(path),path.name,digest,pdf.page_count,
      application_number,product_name,copyright_note(source,text),'rules+llm' if use_llm else 'rules',evidence_role,
      comparison_eligible,identity_status,identity_note,document_date,classification_confidence,ingest_origin,category_path))
    document_id=cur.lastrowid

    if identity_status == 'mismatch':
        add_issue(con,document_id,'warning','DRUG_IDENTITY_MISMATCH',None,identity_note or 'Document may belong to another active substance.')
    elif identity_status == 'review_required':
        add_issue(con,document_id,'info','COMBINATION_SCOPE_REVIEW',None,identity_note or 'Possible combination-product scope; manual review required.')
    if source=='FDA' and subtype=='orange_book':
        add_issue(con,document_id,'info','FDA_ADMINISTRATIVE_NOT_CLINICAL',None,'Orange Book/cumulative supplement is administrative product-list evidence, not a clinical efficacy assessment.')
    if source=='EMA' and subtype in ('orphan_designation','paediatric_investigation_plan','national_authorisation_list'):
        add_issue(con,document_id,'info','EMA_DOCUMENT_NOT_CLINICAL_ASSESSMENT',None,f'{subtype} is an EMA regulatory/administrative document, not a primary clinical efficacy assessment.')
    if source=='EMA' and subtype in ('risk_management_plan','psur_scientific_conclusions'):
        add_issue(con,document_id,'info','EMA_SAFETY_SUPPORT_ONLY',None,f'{subtype} is useful for safety/pharmacovigilance but is not a primary efficacy assessment.')
    if source=='EMA' and subtype in ('generic_medicine_overview','biosimilar_medicine_overview'):
        add_issue(con,document_id,'info','EMA_GENERIC_BIOSIMILAR_SUMMARY',None,'This overview relies on a reference medicine and is not treated as the primary clinical efficacy assessment for the active substance.')

    conf=0.3
    if doc_type=='pharmacopoeia':
        monos=extract_pharmacopoeia(pdf,drug,source)
        for mono in monos:
            mc=con.execute('''INSERT INTO pharmacopoeia_monographs(document_id,monograph_name,material_type,dosage_form,salt_form,edition,effective_date,confidence) VALUES (?,?,?,?,?,?,?,?)''',
              (document_id,mono.monograph_name,mono.material_type,mono.dosage_form,mono.salt_form,mono.edition,mono.effective_date,mono.confidence))
            mid=mc.lastrowid
            for p in mono.parameters:
                evid=add_evidence(con,document_id,f"quality.{mono.monograph_name}.{p.category}.{p.parameter_name}",p.evidence,'rules')
                con.execute('''INSERT INTO quality_parameters(monograph_id,category,parameter_name,value_text,numeric_min,numeric_max,operator,unit,method_name,method_details_json,basis,source_page,confidence,evidence_span_id)
                  VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(mid,p.category,p.parameter_name,clean(p.value_text,1200),p.numeric_min,p.numeric_max,p.operator,p.unit,p.method_name,json.dumps(p.method_details,ensure_ascii=False),p.basis,p.evidence.page,p.evidence.confidence,evid))
            validate_quality(con,document_id,mid)
            conf=max(conf,mono.confidence)
        edition=next((m.edition for m in monos if m.edition),None)
        effective_date=next((m.effective_date for m in monos if m.effective_date),None)
        con.execute("UPDATE documents SET edition=?,version_date=?,extraction_confidence=? WHERE id=?",(edition,effective_date,conf,document_id))
        if not monos:
            add_issue(con,document_id,'warning','NO_MONOGRAPH_EXTRACTED',None,'Pharmacopoeia source was detected but no monograph block was extracted; review the PDF layout.')

    elif doc_type in ('clinical_regulatory','hta','clinical_study'):
        c=extract_clinical(pdf,source,subtype)
        method='rules'
        if use_llm and llm_available() and source in ('FDA','EMA','NICE','Clinical Study'):
            try:
                c=merge_missing(c,extract_clinical_llm(pdf,source,subtype,model=llm_model)); method='rules+ollama'
            except Exception as e:
                add_issue(con,document_id,'warning','LLM_FAILED',None,f'Local LLM extraction failed: {e}')
        ca=con.execute('''INSERT INTO clinical_assessments(document_id,agency,assessment_type,assessment_date,indication,disease_stage,line_of_therapy,population,biomarker,combination_therapy,comparator,relative_effectiveness,benefit_risk,cost_effectiveness,managed_entry,recommendation,restrictions,uncertainty,confidence)
          VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(document_id,c.agency,c.assessment_type,c.assessment_date,clean(c.indication,3500),clean(c.disease_stage,500),clean(c.line_of_therapy,500),clean(c.population,2500),clean(c.biomarker,700),clean(c.combination_therapy,700),clean(c.comparator,3000),clean(c.relative_effectiveness,2500),c.benefit_risk,clean(c.cost_effectiveness,1600),c.managed_entry,clean(c.recommendation,3500),clean(c.restrictions,3500),clean(c.uncertainty,1800),c.confidence))
        aid=ca.lastrowid
        for field,e in c.evidence.items(): add_evidence(con,document_id,f"clinical.{field}",e,method)
        trial_map={}
        for t in c.trials:
            tc=con.execute('''INSERT INTO clinical_trials(assessment_id,trial_name,trial_id,phase,randomized,blinded,sample_size,population,treatment_arm,comparator_arm,follow_up,confidence) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',(aid,t.trial_name,t.trial_id,t.phase,t.randomized,t.blinded,t.sample_size,clean(t.population,1400),clean(t.treatment_arm,1000),clean(t.comparator_arm,1000),t.follow_up,t.confidence))
            if t.trial_id: trial_map[t.trial_id.lower()]=tc.lastrowid
        for ep in c.endpoints:
            trial_fk=trial_map.get((ep.study_label or '').lower()) if ep.study_label else None
            con.execute('''INSERT INTO clinical_endpoints(assessment_id,trial_id,study_label,endpoint_name,timepoint,treatment_value,comparator_value,effect_measure,effect_value,ci_low,ci_high,p_value,unit,agency_interpretation,source_page,confidence) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(aid,trial_fk,ep.study_label,ep.endpoint_name,ep.timepoint,ep.treatment_value,ep.comparator_value,ep.effect_measure,ep.effect_value,ep.ci_low,ep.ci_high,ep.p_value,ep.unit,clean(ep.agency_interpretation,1200),ep.source_page,ep.confidence))
        for s in c.safety:
            con.execute('''INSERT INTO safety_outcomes(assessment_id,event_name,category,treatment_value,comparator_value,unit,grade,seriousness,interpretation,source_page,confidence) VALUES (?,?,?,?,?,?,?,?,?,?,?)''',(aid,s.event_name,s.category,s.treatment_value,s.comparator_value,s.unit,s.grade,s.seriousness,clean(s.interpretation,1200),s.source_page,s.confidence))
        con.execute("UPDATE documents SET extraction_method=?,extraction_confidence=? WHERE id=?",(method,c.confidence,document_id)); conf=c.confidence
        if source=='Clinical Study':
            eligible_complete=con.execute('''SELECT COUNT(*) FROM clinical_endpoints WHERE assessment_id=? AND effect_measure IN ('HR','RR','OR') AND effect_value>0 AND ci_low>0 AND ci_high>0''',(aid,)).fetchone()[0]
            if eligible_complete==0:
                add_issue(con,document_id,'info','NO_META_ANALYSIS_EFFECT',None,'No complete HR/RR/OR + 95% CI was extracted automatically. The study is stored, but it is not pooled until a complete compatible effect estimate is available.')
    else:
        add_issue(con,document_id,'warning','UNKNOWN_DOCUMENT_TYPE',None,'Document source/type could not be classified.')

    return True,f"{drug}: {source}/{subtype} <- {path.name}",document_id


def ingest_folder(input_dir,db_path,use_llm=False,llm_model='qwen3:8b'):
    root=Path(input_dir).expanduser().resolve(); con=connect(db_path)
    run=con.execute("INSERT INTO extraction_runs(input_path,llm_model) VALUES (?,?)",(str(root),llm_model if use_llm else None)).lastrowid
    seen=inserted=0; warnings=[]
    for path in sorted(root.rglob('*.pdf')):
        # Avoid re-crawling program-managed uploads when the project itself lives inside INPUT.
        if '/data/uploads/' in str(path).replace('\\','/') or '/data/inbox/' in str(path).replace('\\','/'):
            continue
        seen+=1
        try:
            ok,msg,_=insert_pdf(con,path,use_llm=use_llm,llm_model=llm_model); inserted+=int(ok); print(msg)
        except Exception as e:
            warnings.append(f"{path}: {e}"); print('WARN',path,e)
    con.execute("UPDATE extraction_runs SET finished_at=CURRENT_TIMESTAMP,documents_seen=?,documents_inserted=?,warnings=? WHERE id=?",(seen,inserted,'\n'.join(warnings),run)); con.commit()
    return {"seen":seen,"inserted":inserted,"warnings":warnings,"db":db_path}


def ingest_managed_uploads(upload_dir,db_path,use_llm=False,llm_model='qwen3:8b'):
    """Re-ingest program-managed uploads after a deliberate database rebuild.

    Layout is data/uploads/<drug>/<source>/<subtype>/<file.pdf>. Needs_Review is intentionally
    excluded until the user resolves the drug/source ambiguity.
    """
    root=Path(upload_dir).expanduser().resolve(); con=connect(db_path)
    seen=inserted=0; warnings=[]
    if not root.is_dir(): return {"seen":0,"inserted":0,"warnings":[],"db":db_path}
    for path in sorted(root.rglob('*.pdf')):
        try:
            rel=path.relative_to(root)
            if not rel.parts or rel.parts[0]=='Needs_Review': continue
            drug=rel.parts[0].replace('_',' ')
            seen+=1
            ok,msg,_=insert_pdf(con,path,use_llm=use_llm,llm_model=llm_model,drug_override=drug,ingest_origin='upload',category_path=str(path.relative_to(root.parent.parent)),classification_confidence=0.95)
            inserted+=int(ok); print(msg)
        except Exception as e:
            warnings.append(f"{path}: {e}"); print('WARN',path,e)
    con.commit(); con.close()
    return {"seen":seen,"inserted":inserted,"warnings":warnings,"db":db_path}
