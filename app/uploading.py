from __future__ import annotations
import re, shutil
from pathlib import Path
from .db import connect
from .pdf import load_pdf, sha256
from .classify import classify, infer_drug_from_document, resolve_existing_drug
from .pipeline import insert_pdf


def has_pdf_signature(path: Path) -> bool:
    try:
        with path.open('rb') as f:
            return f.read(5) == b'%PDF-'
    except OSError:
        return False


def safe_name(name: str) -> str:
    name=Path(name or 'upload.pdf').name
    stem=re.sub(r'[^A-Za-z0-9._ ()+\-]+','_',name).strip(' ._')
    if not stem.lower().endswith('.pdf'): stem += '.pdf'
    return stem[:180]


def slug(s: str) -> str:
    x=re.sub(r'[^A-Za-z0-9._+-]+','_',s or 'Unknown').strip('_')
    return x[:100] or 'Unknown'


def unique_path(folder: Path, filename: str) -> Path:
    folder.mkdir(parents=True,exist_ok=True)
    p=folder/filename
    if not p.exists(): return p
    stem=p.stem; suf=p.suffix
    i=2
    while True:
        q=folder/f'{stem}_{i}{suf}'
        if not q.exists(): return q
        i+=1


def process_uploaded_pdf(db_path: str, temp_path: Path, original_filename: str, upload_root: Path, drug_override: str|None=None, use_llm=False, llm_model='qwen3:8b'):
    con=connect(db_path)
    filename=safe_name(original_filename)
    try:
        if not has_pdf_signature(temp_path):
            dest=unique_path(upload_root/'Needs_Review'/'Invalid_File',filename); shutil.move(str(temp_path),dest)
            con.execute('''INSERT INTO upload_events(original_filename,stored_path,detection_confidence,status,message) VALUES (?,?,?,?,?)''',(filename,str(dest),0.0,'review_required','File extension is PDF but the file does not have a PDF signature.'))
            con.commit()
            return {'status':'review_required','message':'The uploaded file is not a valid PDF by file signature.','stored_path':str(dest)}

        digest=sha256(temp_path)
        dup=con.execute('SELECT d.id,d.filename,dr.canonical_name,d.source,d.subtype FROM documents d JOIN drugs dr ON dr.id=d.drug_id WHERE d.sha256=?',(digest,)).fetchone()
        if dup:
            con.execute('''INSERT INTO upload_events(original_filename,detected_drug,detected_source,detected_subtype,detection_confidence,status,message,document_id)
                           VALUES (?,?,?,?,?,?,?,?)''',(filename,dup['canonical_name'],dup['source'],dup['subtype'],1.0,'duplicate',f"Already in database as {dup['filename']}",dup['id']))
            con.commit(); temp_path.unlink(missing_ok=True)
            return {'status':'duplicate','message':f"Already in database: {dup['filename']}",'document_id':dup['id'],'drug':dup['canonical_name'],'source':dup['source'],'subtype':dup['subtype']}

        pdf=load_pdf(temp_path); text=pdf.text
        if not text.strip():
            dest=unique_path(upload_root/'Needs_Review'/'No_Text',filename); shutil.move(str(temp_path),dest)
            con.execute('''INSERT INTO upload_events(original_filename,stored_path,detection_confidence,status,message) VALUES (?,?,?,?,?)''',(filename,str(dest),0.0,'review_required','PDF contains no extractable text; OCR/manual review required.'))
            con.commit()
            return {'status':'review_required','message':'PDF has no extractable text. OCR/manual review is required.','stored_path':str(dest)}

        source,region,doc_type,subtype,role,eligible=classify(filename,text)
        existing=[r['canonical_name'] for r in con.execute('SELECT canonical_name FROM drugs ORDER BY length(canonical_name) DESC')]
        if drug_override and drug_override.strip():
            drug=resolve_existing_drug(drug_override.strip(),existing); dconf=1.0; reason='manual drug override'
        else:
            drug,dconf,reason=infer_drug_from_document(filename,text,source,existing)

        if source=='Unknown' or not drug or dconf<0.55:
            dest=unique_path(upload_root/'Needs_Review'/slug(source)/slug(subtype),filename); shutil.move(str(temp_path),dest)
            msg=f"Needs review: source={source}; drug={drug or 'unknown'} ({reason})."
            con.execute('''INSERT INTO upload_events(original_filename,stored_path,detected_drug,detected_source,detected_subtype,detection_confidence,status,message)
                           VALUES (?,?,?,?,?,?,?,?)''',(filename,str(dest),drug,source,subtype,dconf,'review_required',msg))
            con.commit()
            return {'status':'review_required','message':msg,'drug':drug,'source':source,'subtype':subtype,'confidence':dconf,'stored_path':str(dest)}

        dest=unique_path(upload_root/slug(drug)/slug(source)/slug(subtype),filename)
        shutil.move(str(temp_path),dest)
        rel_category=str(dest.relative_to(upload_root.parent.parent)) if upload_root.parent.parent in dest.parents else str(dest)
        ok,msg,document_id=insert_pdf(con,dest,use_llm=use_llm,llm_model=llm_model,drug_override=drug,ingest_origin='upload',category_path=rel_category,classification_confidence=dconf)
        status='inserted' if ok else 'duplicate'
        con.execute('''INSERT INTO upload_events(original_filename,stored_path,detected_drug,detected_source,detected_subtype,detection_confidence,status,message,document_id)
                       VALUES (?,?,?,?,?,?,?,?,?)''',(filename,str(dest),drug,source,subtype,dconf,status,msg,document_id))
        con.commit()
        return {'status':status,'message':msg,'document_id':document_id,'drug':drug,'source':source,'subtype':subtype,'confidence':dconf,'stored_path':str(dest),'reason':reason}
    except Exception as e:
        try:
            con.execute('''INSERT INTO upload_events(original_filename,detection_confidence,status,message) VALUES (?,?,?,?)''',(filename,0.0,'error',str(e)))
            con.commit()
        except Exception:
            pass
        temp_path.unlink(missing_ok=True)
        return {'status':'error','message':str(e)}
    finally:
        con.close()
