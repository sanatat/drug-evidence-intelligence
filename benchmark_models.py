from __future__ import annotations
import argparse,csv,tempfile,shutil
from pathlib import Path
from app.extract_llm import available
from app.pipeline import ingest_folder
from app.db import connect
from evaluate import evaluate_db

def main():
    ap=argparse.ArgumentParser(description='Benchmark multiple local Ollama models against the same manually annotated gold standard.')
    ap.add_argument('--input',required=True); ap.add_argument('--gold',required=True); ap.add_argument('--models',default='qwen3:8b,gemma3:4b,llama3.1:8b'); ap.add_argument('--out',default='model_benchmark.csv'); args=ap.parse_args()
    if not available(): raise SystemExit('Ollama is not reachable at http://127.0.0.1:11434. Start Ollama first.')
    rows=[]
    with tempfile.TemporaryDirectory() as td:
        for model in [x.strip() for x in args.models.split(',') if x.strip()]:
            db=str(Path(td)/(model.replace(':','_').replace('/','_')+'.db'))
            print(f'\n=== {model} ===')
            try:
                ingest_folder(args.input,db,use_llm=True,llm_model=model)
                metrics=evaluate_db(db,args.gold)
                rows.append({'model':model,**metrics})
            except Exception as e:
                rows.append({'model':model,'n':0,'mean_score':0,'numeric_accuracy':0,'categorical_accuracy':0,'text_token_f1':0,'error':str(e)})
    fields=['model','n','mean_score','numeric_accuracy','categorical_accuracy','text_token_f1','error']
    with open(args.out,'w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader();
        for r in rows: w.writerow({k:r.get(k,'') for k in fields})
    print('\nSaved:',args.out)
if __name__=='__main__': main()
