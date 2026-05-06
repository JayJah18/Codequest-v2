# Test GEMINI_API_KEY using the same Python provider path as the app (see test_gemini_key.py).
# Usage (from repo root):
#   .\prototype_llm_eval\scripts\test_gemini_key.ps1

$ErrorActionPreference = "Stop"
$scriptDir = $PSScriptRoot
$repoRoot = (Resolve-Path (Join-Path $scriptDir "..\..")).Path

Set-Location $repoRoot
if (Test-Path (Join-Path $repoRoot ".venv\Scripts\Activate.ps1")) {
    . (Join-Path $repoRoot ".venv\Scripts\Activate.ps1")
}

python (Join-Path $scriptDir "test_gemini_key.py")
exit $LASTEXITCODE
