# Ernie — the Ernestifier (M3 demo)

The 3-column compare demo. Proof that **fine-tuning beats prompting** for voice.

- **Left** — you paste text to rewrite (default), or ask a question.
- **Middle** — `ernie:epoch3` with a *neutral* system prompt. The voice lives in the weights.
- **Right** — the *same* base model (`qwen2.5:3b`) honestly prompted to write like Hemingway. The fair fight.

## Run it locally
1. Make sure Ollama is running and both models are installed:
   `ollama list` should show `ernie:epoch3` and `qwen2.5:3b`.
2. `./run_demo.ps1`  (or `python -m uvicorn server:app --port 8000`)
3. Open http://127.0.0.1:8000

## Going public (RunPod) — the seam is already built
The model host for each column lives in `TARGETS` in `server.py`, one entry per column.
To serve Ernie from RunPod instead of local Ollama, set env vars before launch — no UI change,
and the API key never reaches the browser:

```
$env:ERNIE_BASE  = "https://<your-runpod-endpoint>/v1"
$env:ERNIE_MODEL = "<deployed-model-name>"
$env:ERNIE_KEY   = "<runpod-api-key>"
```

(First deploy Ernie's merged weights onto a RunPod serverless vLLM endpoint — that's the real
launch work; this config is the easy last step.)
