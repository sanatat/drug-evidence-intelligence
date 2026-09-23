from __future__ import annotations
import argparse, sys
from pathlib import Path
from app.pipeline import ingest_folder

def main():
    ap=argparse.ArgumentParser(description='Build the local Drug Evidence Intelligence database from private PDF folders.')
    ap.add_argument('--input',required=True,help='Root folder containing one subfolder per drug.')
    ap.add_argument('--db',default='data/evidence.db')
    ap.add_argument('--llm',action='store_true',help='Use local Ollama for complex/missing clinical fields; rule extraction remains primary for numeric quality facts.')
    ap.add_argument('--model',default='qwen3:8b')
    args=ap.parse_args()
    if not Path(args.input).expanduser().is_dir():
        print('ERROR: --input must be an extracted folder.',file=sys.stderr); return 2
    res=ingest_folder(args.input,args.db,args.llm,args.model)
    print(f"\nDone: {res['inserted']}/{res['seen']} PDFs inserted -> {res['db']}")
    if res['warnings']: print(f"Warnings: {len(res['warnings'])}")
    return 0
if __name__=='__main__': raise SystemExit(main())
