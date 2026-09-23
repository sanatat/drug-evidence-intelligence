from __future__ import annotations
import argparse,csv,re
from collections import defaultdict
from app.db import connect

def norm(x): return re.sub(r"\s+"," ",(x or '').strip().lower())
def token_f1(a,b):
    A=norm(a).split(); B=norm(b).split()
    if not A and not B: return 1.0
    if not A or not B: return 0.0
    from collections import Counter
    ca,cb=Counter(A),Counter(B); common=sum((ca&cb).values())
    p=common/len(A); r=common/len(B); return 2*p*r/(p+r) if p+r else 0

def get_pred(con,drug,source,field):
    d=con.execute("SELECT id FROM drugs WHERE lower(canonical_name)=lower(?)",(drug,)).fetchone()
    if not d: return None
    if field.startswith('clinical.'):
        col=field.split('.',1)[1]
        allowed={'indication','population','comparator','relative_effectiveness','benefit_risk','cost_effectiveness','managed_entry','recommendation','restrictions','uncertainty'}
        if col not in allowed: return None
        r=con.execute(f'''SELECT c.{col} v FROM clinical_assessments c JOIN documents x ON x.id=c.document_id WHERE x.drug_id=? AND x.source=? ORDER BY c.confidence DESC LIMIT 1''',(d['id'],source)).fetchone(); return r['v'] if r else None
    if field in ('quality.assay_min','quality.assay_max'):
        col='min' if field.endswith('min') else 'max'
        r=con.execute(f'''SELECT q.numeric_{col} v FROM quality_parameters q JOIN pharmacopoeia_monographs m ON m.id=q.monograph_id JOIN documents x ON x.id=m.document_id WHERE x.drug_id=? AND x.source=? AND q.category='assay' ORDER BY CASE WHEN m.material_type='API' THEN 0 ELSE 1 END,q.confidence DESC LIMIT 1''',(d['id'],source)).fetchone(); return str(r['v']) if r and r['v'] is not None else None
    return None

def score_rows(db_path,gold_path):
    con=connect(db_path); details=[]
    with open(gold_path,encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            expected=(r.get('expected_value') or '').strip()
            if expected=='': continue
            pred=get_pred(con,r['drug'],r['source'],r['field_path'])
            typ=r.get('value_type') or 'text'
            if typ=='numeric':
                try: score=1.0 if abs(float(expected)-float(pred))<=float(r.get('tolerance') or 0) else 0.0
                except: score=0.0
            elif typ=='categorical': score=1.0 if norm(expected)==norm(pred) else 0.0
            else: score=token_f1(expected,pred)
            details.append({**r,'prediction':pred or '','score':score,'type':typ})
    return details

def evaluate_db(db_path,gold_path):
    details=score_rows(db_path,gold_path)
    if not details: return {'n':0,'mean_score':0,'numeric_accuracy':0,'categorical_accuracy':0,'text_token_f1':0}
    def avg(xs): return sum(xs)/len(xs) if xs else 0
    numeric=[x['score'] for x in details if x['type']=='numeric']; categorical=[x['score'] for x in details if x['type']=='categorical']; text=[x['score'] for x in details if x['type']=='text']
    return {'n':len(details),'mean_score':avg([x['score'] for x in details]),'numeric_accuracy':avg(numeric),'categorical_accuracy':avg(categorical),'text_token_f1':avg(text)}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--db',default='data/evidence.db'); ap.add_argument('--gold',default='evaluation/gold_standard_template.csv'); ap.add_argument('--details'); args=ap.parse_args()
    details=score_rows(args.db,args.gold); metrics=evaluate_db(args.db,args.gold)
    print('N',metrics['n']); print('Mean score',f"{metrics['mean_score']:.3f}"); print('Numeric accuracy',f"{metrics['numeric_accuracy']:.3f}"); print('Categorical accuracy',f"{metrics['categorical_accuracy']:.3f}"); print('Text token F1',f"{metrics['text_token_f1']:.3f}")
    grouped=defaultdict(list)
    for x in details: grouped[(x['source'],x['field_path'])].append(x['score'])
    print('\nSOURCE\tFIELD\tN\tMEAN_SCORE')
    for k,v in sorted(grouped.items()): print(f"{k[0]}\t{k[1]}\t{len(v)}\t{sum(v)/len(v):.3f}")
    if args.details:
        with open(args.details,'w',newline='',encoding='utf-8') as f:
            fields=list(details[0].keys()) if details else ['drug','source','field_path','prediction','score']; w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(details)
if __name__=='__main__': main()
