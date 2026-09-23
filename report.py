from __future__ import annotations
import argparse, json
from app.db import connect
from app.compare import combined_matrix

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--db',default='data/evidence.db'); ap.add_argument('--drug'); args=ap.parse_args()
    con=connect(args.db)
    drugs=con.execute("SELECT * FROM drugs WHERE (? IS NULL OR lower(canonical_name) LIKE lower(?)) ORDER BY canonical_name",(args.drug, f"%{args.drug}%" if args.drug else None)).fetchall()
    for d in drugs:
        print('\n###',d['canonical_name'])
        matrix=combined_matrix(con,d['id'])
        print('Quality comparison:',json.dumps(matrix['quality_summary'],ensure_ascii=False))
        c=matrix['clinical']; print('FDA:', bool(c['fda']),'EMA:',bool(c['ema']),'NICE:',bool(c['nice']),'comparability:',c['comparability'],'alignment:',c['alignment'])
        for r in matrix['quality']:
            print(f"  {r['material_type']} | {r['parameter_name']} | {r['status']} | {r['note']}")
if __name__=='__main__': main()
