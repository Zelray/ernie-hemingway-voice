"""
build_notebook.py — emits Ernie_Train_Colab.ipynb, the turnkey M2 training notebook.

WHY a generator instead of hand-written .ipynb JSON: the cell SOURCE is fragile to
escape by hand (quotes, backslashes, the Qwen <|im_start|> markers). Authoring the cells
as ordinary Python strings here and serializing once gives a notebook that is correct by
construction and trivially re-buildable when the Unsloth API shifts.

Recipe is LOCKED + verified against the live official Unsloth notebook (2026-06-29):
Qwen2.5-3B-Instruct, QLoRA 4-bit via Unsloth, r16/alpha16 all-linear, LR 2e-4, seq-len 1024,
3 epochs with a per-epoch checkpoint (the 1/2/3-epoch sweep from ONE run). Pinned
transformers==4.56.2 / trl==0.22.2 (the #1 reason copy-pasted notebooks break in 2026).

Run:  python pipeline/train/build_notebook.py
Out:  pipeline/train/Ernie_Train_Colab.ipynb
"""
import json
import os

# ---------------------------------------------------------------------------
# Cell sources. md() = markdown cell, code() = code cell. Kept verbatim-close to
# the official Unsloth notebook; the only deviations are the three locked specs
# (seq-len 1024, the 3B-Instruct repo, the "messages" key) + per-epoch checkpoints
# + a generation cell that produces exactly what the local eval harness consumes.
# ---------------------------------------------------------------------------

INTRO = r"""# Ernie — Hemingway Voice Fine-Tuning (Colab T4)

**What this notebook does, in plain English:** it teaches a small open model (Qwen2.5-3B)
to answer in Ernest Hemingway's writing voice, by showing it ~1,200 example question→answer
pairs we built. It trains **three versions** (after 1, 2, and 3 passes through the data) so we
can pick the best one. Then it writes the three versions' answers — plus a fair "just-prompt-it"
baseline — on 100 held-out test questions, into one small file you bring back for scoring.

**Cost: $0** (free Colab T4 GPU). **Time: ~1 hour.** You do not need to read or write any code.

---

### Before you press anything — set the GPU (10 seconds, one time)

1. Top menu → **Runtime → Change runtime type**.
2. Set **Hardware accelerator = T4 GPU**. Save.

### Then run it

- Top menu → **Runtime → Run all**.
- Step 2 will pop up a **file picker** — select the two files from your computer:
  **`train.jsonl`** and **`eval_holdout.jsonl`** (Joey gave you these).
- Everything else runs by itself. When it finishes, your browser **downloads `generations.json`** —
  send that one file back to Joey for scoring.

> If a cell ever turns red with an error, stop and send Joey a screenshot. Don't try to fix it —
> that's my job, not yours.
"""

CELL_INSTALL = r"""#@title Step 1 — Install the tools (≈2 min, lots of text is normal)
# This pins transformers==4.56.2 / trl==0.22.2 on purpose — letting pip pick newer
# versions is the single biggest cause of "it worked last month, not today" breakage.
%%capture
import os, re
if "COLAB_" not in "".join(os.environ.keys()):
    !pip install unsloth
else:
    import torch; v = re.match(r'[\d]{1,}\.[\d]{1,}', str(torch.__version__)).group(0)
    xformers = 'xformers==' + {'2.10':'0.0.34','2.9':'0.0.33.post1','2.8':'0.0.32.post2'}.get(v, "0.0.34")
    !pip install sentencepiece protobuf "datasets==4.3.0" "huggingface_hub>=0.34.0" hf_transfer
    !pip install --no-deps unsloth_zoo bitsandbytes accelerate {xformers} peft trl triton unsloth
    !pip install --no-deps --upgrade "torchao>=0.16.0"
!pip install transformers==4.56.2
!pip install --no-deps trl==0.22.2
"""

CELL_UPLOAD = r"""#@title Step 2 — Upload the data (a file picker will appear)
# Select BOTH files from your computer when prompted: train.jsonl and eval_holdout.jsonl
from google.colab import files
print("Pick train.jsonl and eval_holdout.jsonl  (you can multi-select)")
uploaded = files.upload()
assert "train.jsonl" in uploaded, "train.jsonl was not uploaded — re-run this cell."
assert "eval_holdout.jsonl" in uploaded, "eval_holdout.jsonl was not uploaded — re-run this cell."
import json
n_train = sum(1 for _ in open("train.jsonl", encoding="utf-8"))
n_eval  = sum(1 for _ in open("eval_holdout.jsonl", encoding="utf-8"))
print(f"OK — {n_train} training pairs, {n_eval} held-out test questions.")
"""

CELL_LOAD = r"""#@title Step 3 — Load the base model (Qwen2.5-3B-Instruct, 4-bit)
from unsloth import FastLanguageModel
import torch

max_seq_length = 1024     # locked spec
dtype = None              # auto -> float16 on T4 (T4 has no bfloat16; leave as None)
load_in_4bit = True

model, tokenizer = FastLanguageModel.from_pretrained(
    model_name = "unsloth/Qwen2.5-3B-Instruct",   # the INSTRUCT model — it already answers; we only shift its voice
    max_seq_length = max_seq_length,
    dtype = dtype,
    load_in_4bit = load_in_4bit,
)
print("Base model loaded.")
"""

CELL_LORA = r"""#@title Step 4 — Attach the LoRA adapter (the small, trainable "voice" layer)
model = FastLanguageModel.get_peft_model(
    model,
    r = 16,
    target_modules = ["q_proj", "k_proj", "v_proj", "o_proj",
                      "gate_proj", "up_proj", "down_proj"],   # all linear layers
    lora_alpha = 16,
    lora_dropout = 0,
    bias = "none",
    use_gradient_checkpointing = "unsloth",   # fits comfortably in T4's 16GB
    random_state = 3407,
    use_rslora = False,
    loftq_config = None,
)
print("LoRA attached.")
"""

CELL_FORMAT = r"""#@title Step 5 — Format the data with Qwen2.5's chat template
from datasets import load_dataset
from unsloth.chat_templates import get_chat_template

dataset = load_dataset("json", data_files="train.jsonl", split="train")

tokenizer = get_chat_template(tokenizer, chat_template="qwen-2.5")

def formatting_prompts_func(examples):
    # our rows are already {"role","content"} under the "messages" key (OpenAI/ChatML),
    # so we map directly — no standardize_sharegpt (that's for {"from","value"} data).
    convos = examples["messages"]
    texts = [tokenizer.apply_chat_template(c, tokenize=False, add_generation_prompt=False)
             for c in convos]
    return {"text": texts}

dataset = dataset.map(formatting_prompts_func, batched=True)
print("Formatted", len(dataset), "examples. Sample:\n")
print(dataset[0]["text"][:600])
"""

CELL_TRAINER = r"""#@title Step 6 — Configure training (3 epochs, a checkpoint saved at each)
from trl import SFTConfig, SFTTrainer
from transformers import DataCollatorForSeq2Seq

trainer = SFTTrainer(
    model = model,
    tokenizer = tokenizer,
    train_dataset = dataset,
    dataset_text_field = "text",
    max_seq_length = max_seq_length,
    data_collator = DataCollatorForSeq2Seq(tokenizer = tokenizer),
    packing = False,   # MUST be False for response-only masking to line up
    args = SFTConfig(
        per_device_train_batch_size = 1,
        gradient_accumulation_steps = 4,     # effective batch = 4 (T4-safe for a 3B 4-bit)
        warmup_steps = 5,
        num_train_epochs = 3,                # the full sweep in one run
        learning_rate = 2e-4,
        logging_steps = 5,
        optim = "paged_adamw_8bit",
        weight_decay = 0.001,
        lr_scheduler_type = "linear",
        seed = 3407,
        output_dir = "outputs",
        save_strategy = "epoch",             # <-- gives us the epoch-1 / epoch-2 / epoch-3 sweep
        save_total_limit = 3,
        report_to = "none",
    ),
)
"""

CELL_MASK = r"""#@title Step 6b — Train ONLY on the Hemingway answers (mask the questions)
# So the model learns the VOICE of the answers, not how to parrot the questions.
from unsloth.chat_templates import train_on_responses_only
trainer = train_on_responses_only(
    trainer,
    instruction_part = "<|im_start|>user\n",
    response_part    = "<|im_start|>assistant\n",
)
print("Loss will fire on the assistant turns only.")
"""

CELL_TRAIN = r"""#@title Step 7 — Train (≈30–60 min on a T4; the loss number should drift down)
trainer_stats = trainer.train()
print("\nDone. Trained for", trainer_stats.metrics.get("train_runtime", "?"), "seconds.")
"""

CELL_CHECKPOINTS = r"""#@title Step 8 — Confirm the three epoch checkpoints exist
import glob
ckpts = sorted(glob.glob("outputs/checkpoint-*"), key=lambda p: int(p.split('-')[-1]))
print("Found", len(ckpts), "epoch checkpoints:")
for i, c in enumerate(ckpts, 1):
    print(f"  epoch {i}: {c}")
assert len(ckpts) >= 1, "No checkpoints saved — check Step 6 save_strategy."
"""

CELL_SAVE_ADAPTERS = r"""#@title Step 8.5 — SAVE the trained models first (insurance — downloads a small zip)
# Colab is temporary: if anything below hiccups, this zip is your whole hour of training, saved.
# It downloads ernie_adapters.zip (just tens of MB — the trained "voice" layers, not the heavy
# optimizer files). If a later step ever errors, send Joey this zip and he recovers everything.
import os, glob, zipfile
ckpts = sorted(glob.glob("outputs/checkpoint-*"), key=lambda p: int(p.split('-')[-1]))
SKIP = ("optimizer", "scheduler", "rng_state", "trainer_state", "training_args", "global_step")
with zipfile.ZipFile("ernie_adapters.zip", "w", zipfile.ZIP_DEFLATED) as z:
    for i, ck in enumerate(ckpts, 1):
        for fn in os.listdir(ck):
            if fn.startswith(SKIP):
                continue   # skip heavy optimizer state — only the adapter is needed to recover
            full = os.path.join(ck, fn)
            if os.path.isfile(full):
                z.write(full, arcname=f"epoch{i}/{fn}")
print(f"Saved {len(ckpts)} trained adapters to ernie_adapters.zip")
from google.colab import files
files.download("ernie_adapters.zip")
"""

CELL_GENERATE = r"""#@title Step 9 — Generate answers for scoring (fine-tuned ×3 epochs + fair baseline + capability probes)
# This produces generations.json with everything the local scorer needs:
#   rows[]       : for each of the 100 held-out questions
#                    - each epoch's fine-tuned answer (NEUTRAL prompt — voice from weights)
#                    - the SAME base model given an honest "write like Hemingway" prompt
#                      (the FAIR FIGHT right column — a strong prompt, never a strawman)
#   capability[] : ~12 off-distribution probes (math/code/facts), base vs each epoch, NEUTRAL
#                    prompt both sides — the catastrophic-forgetting tripwire.
import json, glob, gc, torch
from unsloth import FastLanguageModel

# ---- The fair-fight baseline system prompt (the honest "write like Hemingway" prompt) ----
# This is the prompted competitor our fine-tune must beat. It is deliberately STRONG:
# a rigged win is worthless. Joey may tune this once before the final number.
BASELINE_SYSTEM = (
    "You are a writing assistant. Answer the user's request in the distinctive prose style of "
    "Ernest Hemingway: short, plain, declarative sentences; simple concrete words; the 'iceberg' "
    "restraint where feeling is shown through fact and action rather than stated outright; very few "
    "adjectives and adverbs; the occasional use of 'and' to link clauses into a longer rhythm. "
    "Keep the answer accurate, helpful, and on the point of the request — never sacrifice substance "
    "for style. Do not mention Hemingway or that you are imitating any style. Just answer in that voice."
)
NEUTRAL_SYSTEM = "You are a helpful assistant."   # what the fine-tuned model ships with

# ---- Capability-retention probes (off-distribution: facts / math / code / reasoning) ----
# 'expect' = lowercase substrings; ANY present = the model still got the gist right.
CAP_PROBES = [
    {"id": "fact_paris",  "kind": "fact", "q": "What is the capital of France?", "expect": ["paris"]},
    {"id": "fact_japan",  "kind": "fact", "q": "What is the capital of Japan?", "expect": ["tokyo"]},
    {"id": "fact_rj",     "kind": "fact", "q": "Who wrote the play Romeo and Juliet?", "expect": ["shakespeare"]},
    {"id": "fact_cont",   "kind": "fact", "q": "How many continents are there on Earth?", "expect": ["seven", "7"]},
    {"id": "math_mul",    "kind": "math", "q": "What is 17 times 4?", "expect": ["68"]},
    {"id": "math_div",    "kind": "math", "q": "What is 144 divided by 12?", "expect": ["12"]},
    {"id": "math_pct",    "kind": "math", "q": "What is 25 percent of 80?", "expect": ["20"]},
    {"id": "math_speed",  "kind": "math", "q": "A train travels 60 miles in 2 hours. What is its average speed in miles per hour?", "expect": ["30"]},
    {"id": "code_sq",     "kind": "code", "q": "Write a Python function that returns the square of a number.", "expect": ["def", "return"]},
    {"id": "code_even",   "kind": "code", "q": "Write a Python function that checks whether a number is even.", "expect": ["def", "% 2", "%2"]},
    {"id": "reason_apple","kind": "reason", "q": "If I have 3 apples and I eat one, how many apples are left?", "expect": ["2", "two"]},
    {"id": "reason_order","kind": "reason", "q": "Put these in order from smallest to largest: 8, 3, 11, 1.", "expect": ["1, 3, 8, 11", "1 3 8 11"]},
]

evalset = [json.loads(l) for l in open("eval_holdout.jsonl", encoding="utf-8")]
def user_content(row):  # the user turn is message[1]
    return row["messages"][1]["content"]

@torch.no_grad()
def gen_one(model, tokenizer, system_prompt, user_text, max_new=256):
    messages = [{"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_text}]
    inputs = tokenizer.apply_chat_template(
        messages, tokenize=True, add_generation_prompt=True, return_tensors="pt").to("cuda")
    out = model.generate(input_ids=inputs, max_new_tokens=max_new, do_sample=False,  # greedy = reproducible eval
                         use_cache=True, pad_token_id=tokenizer.eos_token_id)
    return tokenizer.decode(out[0][inputs.shape[1]:], skip_special_tokens=True).strip()

def gen_eval(model, tokenizer, system_prompt):
    FastLanguageModel.for_inference(model)
    return [gen_one(model, tokenizer, system_prompt, user_content(r)) for r in evalset]

def gen_probes(model, tokenizer):
    # capability is always tested under the NEUTRAL prompt (raw ability, not the voice prompt)
    return [gen_one(model, tokenizer, NEUTRAL_SYSTEM, p["q"], max_new=200) for p in CAP_PROBES]

def free(m):
    del m; gc.collect(); torch.cuda.empty_cache()

# Free the just-trained model AND the trainer. trainer.model still references the model,
# so without deleting the trainer, gc can't reclaim the VRAM and the base-model load below can OOM.
try:
    del trainer, trainer_stats
except NameError:
    pass
free(model)  # now headroom is actually freed for a clean reload

rows = {r["id"]: {"id": r["id"], "task": r["task"], "question": user_content(r),
                  "reference": r["messages"][2]["content"]} for r in evalset}
caps = {p["id"]: {"id": p["id"], "kind": p["kind"], "question": p["q"], "expect": p["expect"]}
        for p in CAP_PROBES}

# 1) base model: eval answers with the FAIR Hemingway prompt + probe answers with NEUTRAL prompt
print("Generating baseline (base model) ...")
m, tok = FastLanguageModel.from_pretrained("unsloth/Qwen2.5-3B-Instruct",
            max_seq_length=1024, dtype=None, load_in_4bit=True)
for r, a in zip(evalset, gen_eval(m, tok, BASELINE_SYSTEM)):
    rows[r["id"]]["baseline"] = a
for p, a in zip(CAP_PROBES, gen_probes(m, tok)):
    caps[p["id"]]["base"] = a
free(m)

# 2) each epoch's fine-tuned model: eval answers + probe answers, both NEUTRAL prompt
ckpts = sorted(glob.glob("outputs/checkpoint-*"), key=lambda p: int(p.split('-')[-1]))
for i, ck in enumerate(ckpts, 1):
    print(f"Generating epoch {i} ({ck}) ...")
    try:
        m, tok = FastLanguageModel.from_pretrained(ck, max_seq_length=1024, dtype=None, load_in_4bit=True)
    except Exception as e:
        print(f"  !! Could not load {ck}: {e}\n"
              f"  !! Skipping epoch {i}. Your trained models are SAFE in ernie_adapters.zip (Step 8.5) —\n"
              f"  !! send Joey that zip plus this message and he recovers it. Continuing with the rest.")
        continue
    for r, a in zip(evalset, gen_eval(m, tok, NEUTRAL_SYSTEM)):
        rows[r["id"]][f"epoch{i}"] = a
    for p, a in zip(CAP_PROBES, gen_probes(m, tok)):
        caps[p["id"]][f"epoch{i}"] = a
    free(m)

payload = {"baseline_system_prompt": BASELINE_SYSTEM, "n_epochs": len(ckpts),
           "rows": list(rows.values()), "capability": list(caps.values())}
json.dump(payload, open("generations.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print(f"\nWrote generations.json — {len(rows)} held-out questions + {len(caps)} probes x {len(ckpts)} epochs + baseline.")
from google.colab import files
files.download("generations.json")
"""

CELL_EXPORT = r"""#@title Step 10 — (LATER, after we pick the winning epoch) Export for the local demo
# DO NOT run this yet. Once Joey scores generations.json and tells you which epoch won,
# set WINNING_EPOCH below and run this cell to download a GGUF you can serve locally (Ollama / LM Studio).
WINNING_EPOCH = 2  #@param {type:"integer"}
import glob
from unsloth import FastLanguageModel
ckpts = sorted(glob.glob("outputs/checkpoint-*"), key=lambda p: int(p.split('-')[-1]))
ck = ckpts[WINNING_EPOCH - 1]
print("Exporting", ck)
m, tok = FastLanguageModel.from_pretrained(ck, max_seq_length=1024, dtype=None, load_in_4bit=True)
m.save_pretrained_gguf("ernie_gguf", tok, quantization_method="q4_k_m")
import shutil
shutil.make_archive("ernie_gguf", "zip", "ernie_gguf")
from google.colab import files
files.download("ernie_gguf.zip")
"""

# ---------------------------------------------------------------------------
cells = [
    ("md",   INTRO),
    ("code", CELL_INSTALL),
    ("code", CELL_UPLOAD),
    ("code", CELL_LOAD),
    ("code", CELL_LORA),
    ("code", CELL_FORMAT),
    ("code", CELL_TRAINER),
    ("code", CELL_MASK),
    ("code", CELL_TRAIN),
    ("code", CELL_CHECKPOINTS),
    ("code", CELL_SAVE_ADAPTERS),
    ("code", CELL_GENERATE),
    ("code", CELL_EXPORT),
]


def to_lines(src: str):
    # nbformat stores source as a list of lines, each (except the last) ending in \n
    lines = src.splitlines(keepends=True)
    return lines if lines else [""]


nb = {
    "cells": [],
    "metadata": {
        "accelerator": "GPU",
        "colab": {"provenance": [], "gpuType": "T4"},
        "kernelspec": {"display_name": "Python 3", "name": "python3"},
        "language_info": {"name": "python"},
    },
    "nbformat": 4,
    "nbformat_minor": 0,
}

for kind, src in cells:
    if kind == "md":
        nb["cells"].append({"cell_type": "markdown", "metadata": {}, "source": to_lines(src)})
    else:
        nb["cells"].append({
            "cell_type": "code",
            "execution_count": None,
            "metadata": {"cellView": "form"} if src.lstrip().startswith("#@title") else {},
            "outputs": [],
            "source": to_lines(src),
        })

out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Ernie_Train_Colab.ipynb")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(nb, f, ensure_ascii=False, indent=1)

print("Wrote", out_path)
print("Cells:", len(nb["cells"]))
