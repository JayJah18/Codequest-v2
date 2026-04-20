# Load all variables from prototype_llm_eval/local.env into the CURRENT PowerShell session.
# Use this before running evaluation scripts (run_sample_eval, run_feedback_eval, etc.).
#
# Usage (repo root — note the leading dot):
#   . .\prototype_llm_eval\scripts\load_local_env.ps1
#
# Then e.g.:
#   python -m prototype_llm_eval.evaluation.run_sample_eval
#
$ErrorActionPreference = "Stop"
$scriptDir = $PSScriptRoot
$evalRoot = (Resolve-Path (Join-Path $scriptDir "..")).Path
. (Join-Path $scriptDir "Import-LocalEnv.ps1")
$names = @(Import-PrototypeLlmEvalLocalEnv -EvalRootPath $evalRoot -Quiet)
if ($names.Count -gt 0) {
    Write-Host "local.env applied ($($names.Count) variable(s)). Repo-relative paths assume you run Python from repo root." -ForegroundColor Green
}
else {
    Write-Host "Nothing loaded — create prototype_llm_eval\local.env from local.env.example" -ForegroundColor Yellow
}
