from __future__ import annotations
import argparse
from app.db import connect
from app.compare import agency_document_status

def main():
    ap=argparse.ArgumentParser(description='Audit whether FDA/EMA PDFs are actually suitable clinical-assessment documents.')
    ap.add_argument('--db',default='data/evidence.db')
    args=ap.parse_args(); con=connect(args.db)
    for d in con.execute('SELECT * FROM drugs ORDER BY canonical_name'):
        print(f"\n=== {d['canonical_name']} ===")
        for agency in ('FDA','EMA'):
            st=agency_document_status(con,d['id'],agency)
            print(f"{agency}: {st['status']}")
            for x in st['documents']:
                elig='YES' if x['comparison_eligible'] else 'NO'
                print(f"  - {x['filename']} | {x['subtype']} | role={x['evidence_role']} | comparison={elig} | identity={x['drug_identity_status']}")
                if x.get('document_note'): print(f"      note: {x['document_note']}")

if __name__=='__main__': main()
