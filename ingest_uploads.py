from __future__ import annotations
import argparse
from app.pipeline import ingest_managed_uploads

def main():
    ap=argparse.ArgumentParser(description='Re-ingest program-managed uploaded PDFs after a database rebuild.')
    ap.add_argument('--input',default='data/uploads')
    ap.add_argument('--db',default='data/evidence.db')
    ap.add_argument('--llm',action='store_true')
    ap.add_argument('--model',default='qwen3:8b')
    args=ap.parse_args()
    r=ingest_managed_uploads(args.input,args.db,args.llm,args.model)
    print(f"Managed uploads: {r['inserted']}/{r['seen']} inserted")
    if r['warnings']: print(f"Warnings: {len(r['warnings'])}")
if __name__=='__main__': main()
