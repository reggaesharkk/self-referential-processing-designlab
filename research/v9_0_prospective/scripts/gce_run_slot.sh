#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 {qwen_7b|gemma_9b|llama_8b|mistral_7b}" >&2
  exit 2
fi
SLOT="$1"
case "$SLOT" in
  qwen_7b|gemma_9b|llama_8b|mistral_7b) ;;
  *) echo "Unknown slot: $SLOT" >&2; exit 2 ;;
esac
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
V9_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
PACKAGE_ROOT="$(cd -- "$V9_DIR/../.." && pwd)"
VENV_DIR="$V9_DIR/.venv-gce"
POOL="$PACKAGE_ROOT/items_pool_v1.json"
CHECKPOINT_ROOT="${DESIGNLAB_CHECKPOINT_DIR:-$HOME/designlab_v9_gce/checkpoints}"
LOG_ROOT="${DESIGNLAB_LOG_DIR:-$HOME/designlab_v9_gce/logs}"
CHECKPOINT="$CHECKPOINT_ROOT/confirmatory_local_hf_${SLOT}.json"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOG="$LOG_ROOT/${SLOT}_${STAMP}.log"

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  echo "Run scripts/gce_setup_existing_vm.sh first." >&2
  exit 3
fi
if [[ ! -f "$POOL" ]]; then
  echo "Item pool is missing from the extracted bundle." >&2
  exit 4
fi
mkdir -p "$CHECKPOINT_ROOT" "$LOG_ROOT"
export HF_HOME="${HF_HOME:-$HOME/.cache/huggingface}"
export HF_HUB_DISABLE_IMPLICIT_TOKEN=1
export HF_HUB_DISABLE_TELEMETRY=1
mkdir -p "$HF_HOME"

COMMAND=("$VENV_DIR/bin/python" -u "$V9_DIR/confirmatory_v9.py" --backend local-hf --slot "$SLOT" --items "$POOL" --output "$CHECKPOINT" --execute)
if [[ -f "$CHECKPOINT" ]]; then
  COMMAND+=(--resume-from "$CHECKPOINT")
fi
printf 'Slot: %s\nCheckpoint: %s\nLog: %s\n' "$SLOT" "$CHECKPOINT" "$LOG"
"${COMMAND[@]}" 2>&1 | tee -a "$LOG"
