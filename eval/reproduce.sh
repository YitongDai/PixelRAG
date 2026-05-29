#!/bin/bash
# One-shot paper reproduction script.
# Runs one cell of Table 1 at a time.
#
# Usage:
#   bash eval/reproduce.sh <bench> <retrieval> [--grade]
#
# Examples:
#   bash eval/reproduce.sh nq naive
#   bash eval/reproduce.sh nq base
#   bash eval/reproduce.sh nq lora
#   bash eval/reproduce.sh nq traf
#   bash eval/reproduce.sh nqt base --grade
#   bash eval/reproduce.sh sqa base
#   bash eval/reproduce.sh livevqa base    # uses eval/run_livevqa.py
#
# Configs are locked to match the paper's S3 jsonl (q35_nothink_full_v1):
#   reader=Qwen3.5-4B, no_think, max_tokens=200, rtk=5, rk=3, LLM judge
#
# Ports (must be running):
#   8000  — Qwen3.5-4B vLLM reader (B200 via SSH tunnel)
#   30088 — base pixel serve (local CPU, normed_v2)
#   30096 — LoRA pixel serve (local CPU, normed_v3)
#   30097 — Trafilatura text serve (local CPU, text_1024_normed)
#   30095 — news pixel serve (H200 via SSH tunnel, for LiveVQA)

set -euo pipefail
cd "$(dirname "$0")/.."

BENCH="${1:?Usage: $0 <bench> <retrieval> [--grade]}"
RET="${2:?Usage: $0 <bench> <retrieval> [--grade]}"
GRADE="${3:-}"

PY=".venv/bin/python"
READER_PORT=8000
READER_MODEL="Qwen/Qwen3.5-4B"
PIXEL_INSTR="Retrieve images or text relevant to the user's query."
TEXT_INSTR="Retrieve text relevant to the user's query."
RTK=5
RK=3
MAX_TOKENS=200

# Ports
BASE_PIXEL="http://localhost:30088/search"
LORA_PIXEL="http://localhost:30096/search"
TEXT_TRAF="http://localhost:30097/search"
NEWS_PIXEL="http://localhost:30095/search"
WIKI_TILES="/home/yichuan/visrag-data/tiles"

# Output
OUT_DIR="eval/eval_output/reproduce"
mkdir -p "$OUT_DIR"

# Task-specific settings
# SQA uses nprobe=2000 for better retrieval (per paper final config)
case "$BENCH" in
  nq)       TASK="nq";        N=1000; EXTRA="" ;;
  nqt)      TASK="nq_tables"; N=1068; EXTRA="" ;;
  sqa)      TASK="simpleqa";  N=1000; EXTRA="--nprobe 2000" ;;
  mms)      TASK="mmsearch";  N=300;  EXTRA=""; MAX_TOKENS=2048 ;;
  evqa)     TASK="encyclopedic_vqa"; N=2000; EXTRA="--evqa-dataset-filter landmarks --evqa-question-type-filter automatic,templated"; MAX_TOKENS=2048 ;;
  livevqa)  TASK="livevqa";   N=0;    EXTRA="" ;;
  *)        echo "Unknown bench: $BENCH (choose: nq nqt sqa mms evqa livevqa)"; exit 1 ;;
esac

# Retrieval-specific settings
# MMS uses different query instruction per decision log
if [ "$BENCH" = "mms" ]; then
  MMS_INSTR="Retrieve relevant documents."
  PIXEL_INSTR_USED="$MMS_INSTR"
  TEXT_INSTR_USED="$MMS_INSTR"
else
  PIXEL_INSTR_USED="$PIXEL_INSTR"
  TEXT_INSTR_USED="$TEXT_INSTR"
fi

API_ARGS=()
case "$RET" in
  naive) ;;
  base)  API_ARGS=(--local-api --local-api-url "$BASE_PIXEL" --query-instruction "$PIXEL_INSTR_USED" --tiles-dir "$WIKI_TILES") ;;
  lora)  API_ARGS=(--local-api --local-api-url "$LORA_PIXEL" --query-instruction "$PIXEL_INSTR_USED" --tiles-dir "$WIKI_TILES") ;;
  traf)  API_ARGS=(--text-api --text-api-url "$TEXT_TRAF" --query-instruction "$TEXT_INSTR_USED") ;;
  *)     echo "Unknown retrieval: $RET (choose: naive base lora traf)"; exit 1 ;;
esac

OUTFILE="$OUT_DIR/${BENCH}_${RET}.jsonl"
LOGFILE="$OUT_DIR/${BENCH}_${RET}.log"

# LiveVQA uses a different script
if [ "$BENCH" = "livevqa" ]; then
  LIVEVQA_IMAGES="/mnt/data/yichuan/livevqa"
  TILES_DIR="/mnt/data/yichuan/news_tiles"
  PAGES_DB="/mnt/data/yichuan/news_state.db"

  case "$RET" in
    naive)
      echo "=== LiveVQA naive ==="
      exec $PY eval/run_livevqa.py \
        --mode naive \
        --api-base "http://localhost:$READER_PORT/v1" --model "$READER_MODEL" \
        --no-think --max-tokens $MAX_TOKENS \
        --livevqa-images "$LIVEVQA_IMAGES" \
        --output "$OUTFILE" 2>&1 | tee "$LOGFILE"
      ;;
    base)
      echo "=== LiveVQA base pixel ==="
      exec $PY eval/run_livevqa.py \
        --mode pixel \
        --pixel-api "$NEWS_PIXEL" \
        --pages-db "$PAGES_DB" --tiles-dir "$TILES_DIR" \
        --api-base "http://localhost:$READER_PORT/v1" --model "$READER_MODEL" \
        --no-think --max-tokens $MAX_TOKENS \
        --livevqa-images "$LIVEVQA_IMAGES" \
        --output "$OUTFILE" 2>&1 | tee "$LOGFILE"
      ;;
    *)
      echo "LiveVQA only supports: naive, base"; exit 1 ;;
  esac
  exit 0
fi

# Standard bench
echo "=== $BENCH $RET ==="
echo "Config: no_think, max_tokens=$MAX_TOKENS, rtk=$RTK, rk=$RK"
echo "Output: $OUTFILE"

$PY eval/run_bench.py \
  --task "$TASK" \
  --model "$READER_MODEL" \
  --api-base "http://localhost:$READER_PORT/v1" \
  --num-examples "$N" \
  --max-tokens "$MAX_TOKENS" \
  --no-think \
  --retrieval-top-k "$RTK" \
  --reader-top-k "$RK" \
  "${API_ARGS[@]}" \
  $EXTRA \
  --output "$OUTFILE" \
  --force \
  2>&1 | tee "$LOGFILE"

echo "Inference done: $OUTFILE ($(wc -l < "$OUTFILE") lines)"

# Grade if requested
if [ "$GRADE" = "--grade" ]; then
  echo "=== Grading ==="
  GRADER_ARGS=""
  # NQ/NQT: use LLM judge (paper uses is_correct, not exact match)
  if [ "$BENCH" = "nq" ] || [ "$BENCH" = "nqt" ]; then
    GRADER_ARGS="--llm-judge"
  fi
  OPENAI_API_KEY="${OPENAI_API_KEY:?Set OPENAI_API_KEY}" \
  OPENAI_BASE_URL="${OPENAI_BASE_URL:-https://us.api.openai.com/v1}" \
  PYTHONUNBUFFERED=1 \
  $PY eval/grade.py "$TASK" "$OUTFILE" $GRADER_ARGS 2>&1 | tee -a "$LOGFILE"
fi
