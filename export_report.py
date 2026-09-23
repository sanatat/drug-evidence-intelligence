from __future__ import annotations
import argparse, json
from pathlib import Path
from app.db import connect
from app.compare import combined_matrix

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--db',default='data/evidence.db'); ap.add_argument('--drug',required=True); ap.add_argument('--out',default='drug_report.json'); args=ap.parse_args()
    con=connect(args.db); d=con.execute("SELECT * FROM drugs WHERE lower(canonical_name)=lower(?)",(args.drug,)).fetchone()
    if not d: raise SystemExit('Drug not found')
    payload={'drug':dict(d),'comparison':combined_matrix(con,d['id'])}
    Path(args.out).write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8'); print(args.out)
if __name__=='__main__': main()
