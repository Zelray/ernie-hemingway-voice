# Launch the Ernie demo wired to the RunPod CLOUD GPUs (not local Ollama).
# Runs the SAME proxy + UI, just pointed at the RunPod endpoints (full-precision fp16).
#
# First set your RunPod key for this terminal, then run:
#     $env:RUNPOD_KEY = "rpa_xxxxxxxx"
#     ./run_demo_cloud.ps1
# Then open http://127.0.0.1:8000
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if (-not $env:RUNPOD_KEY) { Write-Error "Set `$env:RUNPOD_KEY = 'rpa_...' first (your RunPod API key)."; exit 1 }

# Served model ids are LOWERCASE (vLLM lowercases them) — must match /openai/v1/models.
# Endpoint ids come from the environment (never hardcode them):
#     $env:ERNIE_ENDPOINT_ID     — your fine-tuned model's serverless endpoint id
#     $env:BASELINE_ENDPOINT_ID  — the base-model endpoint id
$ernieId    = $env:ERNIE_ENDPOINT_ID
$baselineId = $env:BASELINE_ENDPOINT_ID
if (-not $ernieId)    { Write-Error "Set `$env:ERNIE_ENDPOINT_ID first (your fine-tuned model's endpoint id)."; exit 1 }
if (-not $baselineId) { Write-Error "Set `$env:BASELINE_ENDPOINT_ID first (the base model's endpoint id)."; exit 1 }

$env:ERNIE_BASE     = "https://api.runpod.ai/v2/$ernieId/openai/v1"
$env:ERNIE_MODEL    = $env:ERNIE_MODEL_ID    # e.g. "<hf-user>/<model>" — must be lowercase
$env:ERNIE_KEY      = $env:RUNPOD_KEY
$env:BASELINE_BASE  = "https://api.runpod.ai/v2/$baselineId/openai/v1"
$env:BASELINE_MODEL = "qwen/qwen2.5-3b-instruct"
$env:BASELINE_KEY   = $env:RUNPOD_KEY

Write-Host "Starting Ernie demo (CLOUD / RunPod fp16) at http://127.0.0.1:8000  (Ctrl+C to stop)" -ForegroundColor Green
python -m uvicorn server:app --host 127.0.0.1 --port 8000
