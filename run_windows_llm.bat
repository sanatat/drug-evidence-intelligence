@echo off
setlocal
if "%~1"=="" (
  echo Usage: run_windows_llm.bat "C:\DrugEvidence\data"
  exit /b 1
)
if not exist venv py -m venv venv
call venv\Scripts\activate.bat
python -m pip install -r requirements.txt
python ingest.py --input "%~1" --db data\evidence.db --llm --model qwen3:8b
start http://127.0.0.1:8080
uvicorn app.main:app --host 127.0.0.1 --port 8080
