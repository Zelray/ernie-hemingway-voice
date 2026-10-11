"""
PHASE A (one-time): push the merged fp16 Ernie (epoch 3) to a PRIVATE HuggingFace
repo so RunPod's vLLM can pull it by name. ~5.8 GB upload, once.

STEPS:
  1) pip install -U "huggingface_hub[cli]"
  2) huggingface-cli login          # paste a WRITE token from hf.co/settings/tokens
  3) python demo/upload_ernie_hf.py <your-hf-username>

The repo is PRIVATE. RunPod pulls it with your HF token (Phase B).
"""
import sys
from huggingface_hub import HfApi, create_repo

SRC = r"C:\Users\mcgeo\antigravity_projects\~Hemingway\ernie_local\epoch3_merged"

def main():
    if len(sys.argv) < 2:
        print("Usage: python demo/upload_ernie_hf.py <your-hf-username>")
        sys.exit(1)
    repo = f"{sys.argv[1]}/ernie-epoch3"
    create_repo(repo, repo_type="model", private=True, exist_ok=True)
    print(f"Uploading {SRC}\n     -> {repo} (private). ~5.8 GB, one time. Be patient...")
    HfApi().upload_folder(
        folder_path=SRC, repo_id=repo, repo_type="model",
        commit_message="Ernie epoch3 — merged fp16 (Qwen2.5-3B-Instruct + LoRA r16)")
    print(f"\nDONE. https://huggingface.co/{repo}  (private)")
    print(f"In RunPod (Phase B) set the vLLM model name to:  {repo}")

if __name__ == "__main__":
    main()
