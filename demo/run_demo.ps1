# Ernie demo launcher.  Double-click or run:  ./run_demo.ps1
# Prereqs: Ollama running with `ernie:epoch3` and `qwen2.5:3b` installed.
# Then open http://127.0.0.1:8000 in your browser.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
Write-Host "Starting Ernie demo at http://127.0.0.1:8000  (Ctrl+C to stop)" -ForegroundColor Green
python -m uvicorn server:app --host 127.0.0.1 --port 8000
