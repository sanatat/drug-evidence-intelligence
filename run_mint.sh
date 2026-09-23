#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: ./run_mint.sh /path/to/drug-data [--llm] [--rebuild]"
  exit 2
fi

INPUT="$1"
shift || true
USE_LLM=0
REBUILD=0
for arg in "$@"; do
  [[ "$arg" == "--llm" ]] && USE_LLM=1
  [[ "$arg" == "--rebuild" ]] && REBUILD=1
done

BASE="$(cd "$(dirname "$0")" && pwd)"
cd "$BASE"
INPUT="$(readlink -f "$INPUT")"

if [[ ! -d "$INPUT" ]]; then
  echo "ERROR: input folder not found: $INPUT"
  exit 2
fi

# Keep compatibility with older local installs that already used ./venv.
VENV_DIR=".venv"
if [[ -d "venv" && ! -d ".venv" ]]; then
  VENV_DIR="venv"
fi
if [[ ! -d "$VENV_DIR" ]]; then
  python3 -m venv "$VENV_DIR"
fi
# shellcheck disable=SC1090
source "$VENV_DIR/bin/activate"
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

mkdir -p data/uploads data/inbox
if [[ "$REBUILD" == "1" ]]; then
  echo "Rebuilding database..."
  rm -f data/evidence.db data/evidence.db-shm data/evidence.db-wal
fi

if [[ "$USE_LLM" == "1" ]]; then
  python ingest.py --input "$INPUT" --db data/evidence.db --llm --model qwen3:8b
  python ingest_uploads.py --input data/uploads --db data/evidence.db --llm --model qwen3:8b
else
  python ingest.py --input "$INPUT" --db data/evidence.db
  python ingest_uploads.py --input data/uploads --db data/evidence.db
fi

python audit_documents.py --db data/evidence.db
python aggregate_report.py --db data/evidence.db --out AGGREGATE_RESULTS.md

echo
echo "Database: $BASE/data/evidence.db"
echo "Home: http://127.0.0.1:8080"
echo "Upload page: http://127.0.0.1:8080/upload"
echo "Exploratory meta-analysis: http://127.0.0.1:8080/meta-analysis"
echo "API docs: http://127.0.0.1:8080/docs"
echo "Press Ctrl+C to stop."
exec uvicorn app.main:app --host 127.0.0.1 --port 8080
