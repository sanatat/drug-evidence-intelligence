from __future__ import annotations
from pathlib import Path
import os, tempfile
from fastapi import FastAPI,Request,HTTPException,UploadFile,File,Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from .db import connect
from .compare import combined_matrix
from .uploading import process_uploaded_pdf
from .meta import meta_groups,select_group,run_meta_analysis,forest_svg
from . import __version__

BASE=Path(__file__).resolve().parents[1]
DB_PATH=os.getenv('DRUG_EVIDENCE_DB',str(BASE/'data/evidence.db'))
UPLOAD_ROOT=BASE/'data'/'uploads'
INBOX=BASE/'data'/'inbox'
app=FastAPI(title='Drug Evidence Intelligence', version=__version__)
templates=Jinja2Templates(directory=str(BASE/'app/templates'))

def db(): return connect(DB_PATH)


@app.get('/health')
def health():
    return {'status':'ok','version':__version__}

@app.get('/',response_class=HTMLResponse)
def home(request:Request,q:str=''):
    con=db()
    if q: drugs=con.execute("SELECT * FROM drugs WHERE lower(canonical_name) LIKE ? ORDER BY canonical_name",('%'+q.lower()+'%',)).fetchall()
    else: drugs=con.execute('SELECT * FROM drugs ORDER BY canonical_name').fetchall()
    enriched=[]
    for d in drugs:
        sources=[r['source'] for r in con.execute('SELECT DISTINCT source FROM documents WHERE drug_id=?',(d['id'],))]
        enriched.append((d,sources))
    stats=con.execute('''SELECT COUNT(*) drugs,
      (SELECT COUNT(*) FROM documents) documents,
      (SELECT COUNT(*) FROM quality_parameters) quality_parameters,
      (SELECT COUNT(*) FROM clinical_assessments) assessments,
      (SELECT COUNT(*) FROM documents WHERE doc_type='clinical_study') clinical_studies,
      (SELECT COUNT(*) FROM clinical_endpoints WHERE effect_measure IN ('HR','RR','OR') AND effect_value>0 AND ci_low>0 AND ci_high>0) meta_effects
      FROM drugs''').fetchone()
    recent_uploads=con.execute('SELECT * FROM upload_events ORDER BY id DESC LIMIT 5').fetchall()
    con.close()
    return templates.TemplateResponse(request,'index.html',{'drugs':enriched,'q':q,'stats':stats,'recent_uploads':recent_uploads})

@app.get('/drug/{drug_id}',response_class=HTMLResponse)
def drug(request:Request,drug_id:int):
    con=db(); d=con.execute('SELECT * FROM drugs WHERE id=?',(drug_id,)).fetchone()
    if not d: con.close(); raise HTTPException(404)
    matrix=combined_matrix(con,drug_id)
    docs=con.execute('SELECT * FROM documents WHERE drug_id=? ORDER BY source,subtype',(drug_id,)).fetchall()
    issues=con.execute('SELECT v.*,d.filename FROM validation_issues v LEFT JOIN documents d ON d.id=v.document_id WHERE d.drug_id=? ORDER BY v.severity DESC',(drug_id,)).fetchall()
    studies=con.execute('''SELECT d.id,d.filename,d.document_date,c.id assessment_id,
      (SELECT COUNT(*) FROM clinical_endpoints e WHERE e.assessment_id=c.id) endpoints,
      (SELECT COUNT(*) FROM clinical_endpoints e WHERE e.assessment_id=c.id AND e.effect_measure IN ('HR','RR','OR') AND e.effect_value>0 AND e.ci_low>0 AND e.ci_high>0) meta_ready
      FROM documents d JOIN clinical_assessments c ON c.document_id=d.id
      WHERE d.drug_id=? AND d.doc_type='clinical_study' ORDER BY d.id DESC''',(drug_id,)).fetchall()
    con.close()
    return templates.TemplateResponse(request,'drug.html',{'drug':d,'matrix':matrix,'docs':docs,'issues':issues,'studies':studies})

@app.get('/document/{document_id}',response_class=HTMLResponse)
def document(request:Request,document_id:int):
    con=db()
    d=con.execute('''SELECT d.*,dr.canonical_name FROM documents d JOIN drugs dr ON dr.id=d.drug_id WHERE d.id=?''',(document_id,)).fetchone()
    if not d: con.close(); raise HTTPException(404)
    monos=con.execute('SELECT * FROM pharmacopoeia_monographs WHERE document_id=?',(document_id,)).fetchall()
    qrows=con.execute('''SELECT q.*,m.monograph_name,m.material_type FROM quality_parameters q JOIN pharmacopoeia_monographs m ON m.id=q.monograph_id WHERE m.document_id=? ORDER BY m.id,q.category,q.parameter_name''',(document_id,)).fetchall()
    ca=con.execute('SELECT * FROM clinical_assessments WHERE document_id=?',(document_id,)).fetchone()
    endpoints=[]; trials=[]; safety=[]
    if ca:
        trials=con.execute('SELECT * FROM clinical_trials WHERE assessment_id=? ORDER BY id',(ca['id'],)).fetchall()
        endpoints=con.execute('SELECT * FROM clinical_endpoints WHERE assessment_id=? ORDER BY endpoint_name,id',(ca['id'],)).fetchall()
        safety=con.execute('SELECT * FROM safety_outcomes WHERE assessment_id=? ORDER BY id',(ca['id'],)).fetchall()
    issues=con.execute('SELECT * FROM validation_issues WHERE document_id=? ORDER BY id',(document_id,)).fetchall()
    con.close()
    return templates.TemplateResponse(request,'document.html',{'doc':d,'monos':monos,'qrows':qrows,'assessment':ca,'trials':trials,'endpoints':endpoints,'safety':safety,'issues':issues})

@app.get('/upload',response_class=HTMLResponse)
def upload_page(request:Request):
    con=db(); recent=con.execute('SELECT * FROM upload_events ORDER BY id DESC LIMIT 20').fetchall(); con.close()
    return templates.TemplateResponse(request,'upload.html',{'results':None,'recent':recent})

@app.post('/upload',response_class=HTMLResponse)
async def upload_pdf(request:Request,files:list[UploadFile]=File(...),drug_name:str=Form(''),use_llm:str|None=Form(None)):
    INBOX.mkdir(parents=True,exist_ok=True); UPLOAD_ROOT.mkdir(parents=True,exist_ok=True)
    results=[]
    for f in files:
        original=f.filename or 'upload.pdf'
        if not original.lower().endswith('.pdf'):
            results.append({'status':'error','message':f'{original}: only PDF files are accepted.'}); continue
        fd,tmpname=tempfile.mkstemp(prefix='dei_',suffix='.pdf',dir=INBOX)
        os.close(fd); tmp=Path(tmpname)
        size=0
        try:
            with tmp.open('wb') as out:
                while True:
                    chunk=await f.read(1024*1024)
                    if not chunk: break
                    size+=len(chunk)
                    if size>150*1024*1024:
                        raise ValueError('PDF exceeds 150 MB upload limit.')
                    out.write(chunk)
            if size==0: raise ValueError('Empty upload.')
            result=process_uploaded_pdf(DB_PATH,tmp,original,UPLOAD_ROOT,drug_override=drug_name or None,use_llm=bool(use_llm))
            results.append(result)
        except Exception as e:
            tmp.unlink(missing_ok=True); results.append({'status':'error','message':f'{original}: {e}'})
        finally:
            await f.close()
    con=db(); recent=con.execute('SELECT * FROM upload_events ORDER BY id DESC LIMIT 20').fetchall(); con.close()
    return templates.TemplateResponse(request,'upload.html',{'results':results,'recent':recent})

@app.get('/meta-analysis',response_class=HTMLResponse)
def meta_analysis(request:Request,drug_name:str='',endpoint:str='',effect_measure:str='',include_regulatory:int=0):
    con=db(); studies_only=not bool(include_regulatory)
    groups=meta_groups(con,clinical_studies_only=studies_only)
    result=None; rows=[]; svg=''
    if drug_name and endpoint and effect_measure:
        rows=select_group(con,drug_name,endpoint,effect_measure,clinical_studies_only=studies_only)
        result=run_meta_analysis(rows)
        if result.get('k',0)>=2: svg=forest_svg(result,effect_measure)
    con.close()
    return templates.TemplateResponse(request,'meta.html',{
        'groups':groups,'result':result,'rows':rows,'forest_svg':svg,
        'selected':{'drug_name':drug_name,'endpoint':endpoint,'effect_measure':effect_measure},
        'include_regulatory':bool(include_regulatory)
    })

@app.get('/api/drugs')
def api_drugs():
    con=db(); rows=[dict(r) for r in con.execute('SELECT * FROM drugs ORDER BY canonical_name')]; con.close(); return rows

@app.get('/api/drugs/{drug_id}/comparison')
def api_compare(drug_id:int):
    con=db(); d=con.execute('SELECT * FROM drugs WHERE id=?',(drug_id,)).fetchone()
    if not d: con.close(); raise HTTPException(404)
    out={'drug':dict(d),**combined_matrix(con,drug_id)}; con.close(); return out

@app.get('/api/meta-analysis')
def api_meta(drug_name:str,endpoint:str,effect_measure:str,include_regulatory:int=0):
    con=db(); rows=select_group(con,drug_name,endpoint,effect_measure,clinical_studies_only=not bool(include_regulatory)); result=run_meta_analysis(rows); con.close(); return {'drug':drug_name,'endpoint':endpoint,'effect_measure':effect_measure,**result}
