#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
V9_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
VENV_DIR="$V9_DIR/.venv-gce"

if ! command -v nvidia-smi >/dev/null 2>&1; then
  echo "BLOCKED: nvidia-smi is unavailable. Confirm that a GPU is attached and install its driver before setup." >&2
  exit 20
fi
GPU_LINE="$(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader,nounits | head -n 1)"
if [[ -z "$GPU_LINE" ]]; then
  echo "BLOCKED: no NVIDIA GPU was reported by nvidia-smi." >&2
  exit 21
fi
IFS=, read -r GPU_NAME GPU_MEMORY_MIB <<< "$GPU_LINE"
GPU_NAME="$(echo "$GPU_NAME" | xargs)"
GPU_MEMORY_MIB="$(echo "$GPU_MEMORY_MIB" | xargs)"
if ! [[ "$GPU_MEMORY_MIB" =~ ^[0-9]+$ ]] || (( GPU_MEMORY_MIB < 14336 )); then
  echo "BLOCKED: need at least 14 GiB of GPU memory; detected ${GPU_NAME:-unknown} ${GPU_MEMORY_MIB:-unknown} MiB." >&2
  exit 22
fi
python3 "$SCRIPT_DIR/verify_local_gce_bundle.py"
python3 --version
python3 -m venv "$VENV_DIR" || {
  echo "Could not create a venv. On Debian, install python3-venv, then rerun this script." >&2
  exit 23
}
"$VENV_DIR/bin/python" -m pip install --upgrade pip
"$VENV_DIR/bin/python" -m pip install torch --index-url https://download.pytorch.org/whl/cu128
"$VENV_DIR/bin/python" -m pip install -r "$V9_DIR/requirements-local-hf.txt"
"$VENV_DIR/bin/python" - <<'PY'
import torch
if not torch.cuda.is_available():
    raise SystemExit("BLOCKED: installed PyTorch cannot access CUDA on this VM")
name = torch.cuda.get_device_name(0)
size = torch.cuda.get_device_properties(0).total_memory
if size < 14 * 1024**3:
    raise SystemExit(f"BLOCKED: {name} has only {size / 1024**3:.1f} GiB; need at least 14 GiB")
print(f"GPU ready: {name}; {size / 1024**3:.1f} GiB")
PY
printf 'Setup complete. Use scripts/gce_run_slot.sh SLOT_NAME.\n'
