# My existing GCE VM run path

I prepared this package for an existing Debian x86_64 Compute Engine VM. I do not create or resize a VM here. The terminal screenshot I received shows Debian x86_64, about 31 GiB RAM, and a 492 GB root filesystem; it does not show whether a GPU is attached. My setup checks for an NVIDIA CUDA GPU with at least 14 GiB of VRAM before installing Python packages or downloading weights. It stops if the VM is CPU-only.

## I verify the VM first

From the existing SSH terminal, I run:

~~~bash
nvidia-smi --query-gpu=name,memory.total --format=csv
~~~

I expect a CUDA GPU with at least 14 GiB of VRAM. If nvidia-smi is missing, I first confirm in the Compute Engine VM details that a GPU is attached. If the GPU is attached but its driver is missing, Google documents its [GPU driver installer](https://docs.cloud.google.com/compute/docs/gpus/install-drivers-gpu) for Debian 12 and Debian 13. The installer requires sudo and may require a reboot; I run it only after confirming the attached GPU:

~~~bash
curl -fSsL -o /tmp/cuda_installer.pyz https://storage.googleapis.com/compute-gpu-installation-us/installer/latest/cuda_installer.pyz
sudo python3 /tmp/cuda_installer.pyz install_driver
~~~

I reconnect after any installer-requested reboot, then run nvidia-smi again. If the instance has no GPU attached, this local GPU runner cannot start on it; I do not silently switch to a slow CPU run.

## I upload and verify the bundle

I upload both v9_0_gce_local_confirmatory_bundle.zip and its v9_0_gce_local_confirmatory_bundle.zip.sha256 sidecar through the existing SSH-in-browser Upload File control into my home directory. I then run:

~~~bash
cd "$HOME"
sha256sum -c "$HOME/v9_0_gce_local_confirmatory_bundle.zip.sha256"
mkdir -p "$HOME/designlab_v9_gce"
unzip -o "$HOME/v9_0_gce_local_confirmatory_bundle.zip" -d "$HOME/designlab_v9_gce"
cd "$HOME/designlab_v9_gce"
python3 research/v9_0_prospective/scripts/verify_local_gce_bundle.py
~~~

I keep the extracted code, checkpoint JSON files, logs, and Hugging Face cache on the VM's persistent boot disk. Stopping and restarting preserves a persistent boot disk; deleting a VM may delete its boot disk if that disk is marked auto-delete. I check the disk setting before I rely on it as my only checkpoint copy.

## I install the local runtime

~~~bash
bash research/v9_0_prospective/scripts/gce_setup_existing_vm.sh
~~~

The setup installs a virtual environment in this extracted package, PyTorch from its [official CUDA 12.8 wheel index](https://pytorch.org/get-started/locally/), and the runner's Python requirements. It makes no inference API requests and reads no API keys. It downloads public model weights during execution, so the VM needs outbound internet access and enough disk space. Model inference API spend is USD 0.00; Google Cloud compute, disks, and network may still be billed. Google's [current price page](https://cloud.google.com/products/compute/pricing) lists the T4 GPU component at USD 0.35 per GPU-hour before VM and disk charges; I check my region's billing page before running.

## I run and resume one model slot at a time

~~~bash
bash research/v9_0_prospective/scripts/gce_run_slot.sh qwen_7b
bash research/v9_0_prospective/scripts/gce_run_slot.sh gemma_9b
bash research/v9_0_prospective/scripts/gce_run_slot.sh llama_8b
bash research/v9_0_prospective/scripts/gce_run_slot.sh mistral_7b
~~~

Each slot writes its own checkpoint under $HOME/designlab_v9_gce/checkpoints. The script automatically passes --resume-from when that slot's checkpoint already exists. If SSH disconnects while a slot is running, I reconnect and run the same command; completed items are already saved. For long runs, I start the same command inside tmux or with nohup so the process is not tied to the browser tab.

When I have four complete slot checkpoints, I merge them with:

~~~bash
cd "$HOME/designlab_v9_gce"
.venv/bin/python - <<'PY'
from pathlib import Path
import sys
research = Path("research/v9_0_prospective").resolve()
sys.path.insert(0, str(research))
from local_hf_confirmatory_v9 import merge_slot_checkpoints
root = Path.home() / "designlab_v9_gce" / "checkpoints"
slots = ["qwen_7b", "gemma_9b", "llama_8b", "mistral_7b"]
paths = [root / f"confirmatory_local_hf_{slot}.json" for slot in slots]
result = merge_slot_checkpoints(paths, root / "confirmatory_local_hf_merged.json")
print(result["run_status"], result["complete_pipeline"])
PY
~~~

I treat this as a distinct local-HF v9 variant. I do not treat it as an execution of frozen v8.6.3. I have not run the model on this VM; my local-HF live-run count remains zero until I inspect a saved result.
