from __future__ import annotations
import re
from collections import defaultdict


def norm_name(s):
    if not s: return ""
    return re.sub(r"[^a-z0-9]+"," ",s.lower()).strip()


def token_similarity(a,b):
    A=set(norm_name(a).split()); B=set(norm_name(b).split())
    if not A or not B: return 0.0
    return len(A&B)/len(A|B)


def compare_numeric(a,b):
    """Compare same quality parameter from USP and Ph. Eur. without claiming superiority."""
    if a["unit"] and b["unit"] and a["unit"]!=b["unit"]:
        return "not_directly_comparable", "Different units"
    amin,amax=a["numeric_min"],a["numeric_max"]
    bmin,bmax=b["numeric_min"],b["numeric_max"]
    if amin is not None and amax is not None and bmin is not None and bmax is not None:
        if abs(amin-bmin)<1e-9 and abs(amax-bmax)<1e-9: return "equivalent", "Same extracted acceptance interval"
        aw=amax-amin; bw=bmax-bmin
        if abs(aw-bw)<1e-9: return "different_limits", "Same interval width but different limits"
        return ("USP_more_restrictive","USP has the narrower extracted acceptance interval") if aw<bw else ("PhEur_more_restrictive","Ph. Eur. has the narrower extracted acceptance interval")
    if amax is not None and bmax is not None and amin is None and bmin is None:
        if abs(amax-bmax)<1e-9: return "equivalent", "Same extracted maximum limit"
        return ("USP_more_restrictive","USP has the lower extracted maximum limit") if amax<bmax else ("PhEur_more_restrictive","Ph. Eur. has the lower extracted maximum limit")
    return "not_directly_comparable", "Insufficient compatible numeric limits"


def quality_comparison(con,drug_id):
    rows=con.execute('''
      SELECT d.source,m.material_type,m.monograph_name,q.*
      FROM quality_parameters q
      JOIN pharmacopoeia_monographs m ON m.id=q.monograph_id
      JOIN documents d ON d.id=m.document_id
      WHERE d.drug_id=? AND d.source IN ('USP','Ph. Eur.')
      ORDER BY m.material_type,q.category,q.parameter_name,d.source
    ''',(drug_id,)).fetchall()
    groups=defaultdict(dict)
    for r in rows:
        key=(r['material_type'],r['category'],norm_name(r['parameter_name']))
        groups[key][r['source']]=r
    out=[]
    for (material,category,_),g in groups.items():
        u=g.get('USP'); e=g.get('Ph. Eur.'); name=(u or e)['parameter_name']
        if u and e:
            status,note=compare_numeric(u,e)
            if status=='not_directly_comparable':
                if (u['method_name'] or '') and (e['method_name'] or ''):
                    if norm_name(u['method_name'])==norm_name(e['method_name']): status,note='method_aligned','Same extracted method class'
                    else: status,note='different_method','Different extracted method classes'
                elif (u['value_text'] or '') == (e['value_text'] or '') and u['value_text']:
                    status,note='equivalent','Same extracted text value'
        elif u: status,note='USP_only','Extracted only from USP'
        else: status,note='PhEur_only','Extracted only from Ph. Eur.'
        out.append({"material_type":material,"category":category,"parameter_name":name,"usp":dict(u) if u else None,"pheur":dict(e) if e else None,"status":status,"note":note})
    return out


def agency_document_status(con, drug_id, agency):
    rows=con.execute('''
      SELECT d.id,d.filename,d.subtype,d.evidence_role,d.comparison_eligible,d.drug_identity_status,d.document_note
      FROM documents d WHERE d.drug_id=? AND d.source=? ORDER BY d.id
    ''',(drug_id,agency)).fetchall()
    if not rows:
        return {"status":"no_document","documents":[]}
    docs=[dict(r) for r in rows]
    if any(r['drug_identity_status']=='mismatch' for r in rows) and not any(r['drug_identity_status']=='matched' for r in rows):
        return {"status":"identity_mismatch","documents":docs}
    eligible=[r for r in rows if r['comparison_eligible']==1 and r['drug_identity_status']=='matched']
    if eligible:
        roles={r['evidence_role'] for r in eligible}
        if 'primary_clinical_assessment' in roles:
            return {"status":"primary_clinical_assessment_available","documents":docs}
        return {"status":"clinical_summary_available","documents":docs}
    if any(r['drug_identity_status']=='review_required' for r in rows):
        return {"status":"review_required","documents":docs}
    return {"status":"document_but_no_clinical_assessment","documents":docs}


def best_assessment(con,drug_id,agency):
    priority={
      'EMA':{'assessment_report':1,'medicine_overview':2},
      'FDA':{'integrated_review':1,'summary_review':2,'clinical_review':3,'medical_review':4},
      'NICE':{'technology_appraisal':1},
    }
    rows=con.execute('''
      SELECT c.*,d.subtype,d.filename,d.id document_id,d.evidence_role,d.comparison_eligible,d.drug_identity_status
      FROM clinical_assessments c JOIN documents d ON d.id=c.document_id
      WHERE d.drug_id=? AND c.agency=?
    ''',(drug_id,agency)).fetchall()
    if not rows: return None
    if agency in ('FDA','EMA'):
        rows=[r for r in rows if r['comparison_eligible']==1 and r['drug_identity_status']=='matched']
        if not rows: return None
    rows=sorted(rows,key=lambda r:priority.get(agency,{}).get(r['subtype'],99))
    return rows[0]


def clinical_comparison(con,drug_id):
    fda_status=agency_document_status(con,drug_id,'FDA')
    ema_status=agency_document_status(con,drug_id,'EMA')
    fda=best_assessment(con,drug_id,'FDA'); ema=best_assessment(con,drug_id,'EMA'); nice=best_assessment(con,drug_id,'NICE')
    comp={
        "fda":dict(fda) if fda else None,
        "ema":dict(ema) if ema else None,
        "nice":dict(nice) if nice else None,
        "fda_status":fda_status,
        "ema_status":ema_status,
        "comparability":None,"alignment":None,"notes":[]
    }
    if not fda:
        comp['notes'].append(f"FDA: {fda_status['status']}")
    if not ema:
        comp['notes'].append(f"EMA: {ema_status['status']}")
    if fda and ema:
        sim=token_similarity(fda['indication'],ema['indication'])
        if not fda['indication'] or not ema['indication']:
            comp['comparability']='uncertain'; comp['notes'].append('Indication missing in one eligible regional assessment.')
        elif sim<0.12:
            comp['comparability']='not_directly_comparable'; comp['notes'].append('FDA and EMA indication text appears materially different; manual review required.')
        else:
            comp['comparability']='potentially_comparable'
        br1=fda['benefit_risk']; br2=ema['benefit_risk']
        if br1 and br2 and br1!='not_stated' and br2!='not_stated': comp['alignment']='aligned' if br1==br2 else 'discordant'
        else: comp['alignment']='insufficient_structured_conclusion'
    else:
        comp['comparability']='not_available'
        comp['alignment']='not_available'
    return comp


def combined_matrix(con,drug_id):
    q=quality_comparison(con,drug_id); c=clinical_comparison(con,drug_id)
    summary=defaultdict(int)
    for r in q: summary[r['status']]+=1
    return {"quality":q,"quality_summary":dict(summary),"clinical":c,
            "interpretation_rule":"Quality-standard restrictiveness and clinical benefit are reported as separate domains. No causal inference is made between them."}
