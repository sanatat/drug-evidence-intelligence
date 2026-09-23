from __future__ import annotations
import argparse
from collections import Counter
from pathlib import Path
from app.db import connect
from app.compare import combined_matrix, agency_document_status
from app.meta import meta_groups

SHORT={
 'primary_clinical_assessment_available':'primary',
 'clinical_summary_available':'summary',
 'document_but_no_clinical_assessment':'support only',
 'identity_mismatch':'wrong drug',
 'review_required':'review',
 'no_document':'—'
}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--db',default='data/evidence.db'); ap.add_argument('--out',default='AGGREGATE_RESULTS.md'); args=ap.parse_args()
    con=connect(args.db); drugs=con.execute('SELECT * FROM drugs ORDER BY canonical_name').fetchall()
    lines=['# Aggregate research results','',f'Drugs: **{len(drugs)}**','', '## Evidence coverage','',
           '| Drug | USP | Ph. Eur. | FDA docs | FDA clinical | EMA docs | EMA clinical | NICE | Clinical Study PDFs |',
           '|---|---|---|---|---|---|---|---|---|']
    quality=Counter(); comparability=Counter(); alignment=Counter(); fstats=Counter(); estats=Counter()
    for d in drugs:
        present={r['source'] for r in con.execute('SELECT DISTINCT source FROM documents WHERE drug_id=?',(d['id'],))}
        fs=agency_document_status(con,d['id'],'FDA'); es=agency_document_status(con,d['id'],'EMA')
        fstats[fs['status']]+=1; estats[es['status']]+=1
        study_n=con.execute("SELECT COUNT(*) FROM documents WHERE drug_id=? AND doc_type='clinical_study'",(d['id'],)).fetchone()[0]
        lines.append('| '+d['canonical_name']+' | '+('✓' if 'USP' in present else '—')+' | '+('✓' if 'Ph. Eur.' in present else '—')+' | '+('✓' if 'FDA' in present else '—')+' | '+SHORT.get(fs['status'],fs['status'])+' | '+('✓' if 'EMA' in present else '—')+' | '+SHORT.get(es['status'],es['status'])+' | '+('✓' if 'NICE' in present else '—')+' | '+str(study_n or '—')+' |')
        m=combined_matrix(con,d['id']); quality.update(m['quality_summary']); comparability[m['clinical']['comparability']]+=1; alignment[m['clinical']['alignment']]+=1
    lines += ['', '## FDA clinical-document status','', '| Status | Drugs |','|---|---:|']
    for k,v in fstats.most_common(): lines.append(f'| {k} | {v} |')
    lines += ['', '## EMA clinical-document status','', '| Status | Drugs |','|---|---:|']
    for k,v in estats.most_common(): lines.append(f'| {k} | {v} |')
    lines += ['', '## Quality comparison outcomes','', '| Outcome | Count |','|---|---:|']
    for k,v in quality.most_common(): lines.append(f'| {k} | {v} |')
    lines += ['', '## FDA–EMA comparability (eligible documents only)','', '| Outcome | Drugs |','|---|---:|']
    for k,v in comparability.most_common(): lines.append(f'| {k} | {v} |')
    lines += ['', '## FDA–EMA structured conclusion alignment (eligible documents only)','', '| Outcome | Drugs |','|---|---:|']
    for k,v in alignment.most_common(): lines.append(f'| {k} | {v} |')
    mg=meta_groups(con,clinical_studies_only=True)
    lines += ['', '## Meta-analysis-ready independent study groups','', '| Drug | Endpoint | Effect | Studies | Poolable |','|---|---|---|---:|---|']
    if mg:
        for g in mg: lines.append(f"| {g['drug_name']} | {g['endpoint']} | {g['effect_measure']} | {g['n']} | {'yes' if g['eligible'] else 'no'} |")
    else: lines.append('| — | — | — | 0 | no |')
    issues=con.execute('SELECT severity,code,COUNT(*) n FROM validation_issues GROUP BY severity,code ORDER BY n DESC').fetchall()
    lines += ['', '## Validation / audit flags','', '| Severity | Code | Count |','|---|---|---:|']
    if issues:
        for r in issues: lines.append(f"| {r['severity']} | {r['code']} | {r['n']} |")
    else: lines.append('| — | — | 0 |')
    lines += ['', '> `EMA document present` is not treated as `EMA clinical assessment present`. PSUR, RMP, orphan designation, PIP, national-authorisation lists, SmPC, and generic/biosimilar summaries are kept as supporting/regulatory evidence but excluded from primary FDA–EMA efficacy comparison.', '', '> Pharmacopoeial quality differences and clinical benefit are separate domains; no causal inference is made between them.']
    Path(args.out).write_text('\n'.join(lines),encoding='utf-8'); print(args.out)
if __name__=='__main__': main()
