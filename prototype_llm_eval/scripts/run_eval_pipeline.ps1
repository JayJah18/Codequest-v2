param(
    [Parameter(Mandatory = $true)]
    [string]$GeminiApiKey,
    [string]$GeminiModel = "models/gemini-2.5-flash"
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $repoRoot

if (Test-Path ".venv\Scripts\Activate.ps1") {
    . ".venv\Scripts\Activate.ps1"
}

$env:GEMINI_API_KEY = $GeminiApiKey
$env:GEMINI_MODEL = $GeminiModel

Write-Host "Using model: $GeminiModel"
Write-Host "Running dataset preparation..."
python -m prototype_llm_eval.backend.prepare_fixed_dataset
if ($LASTEXITCODE -ne 0) { throw "prepare_fixed_dataset failed with exit code $LASTEXITCODE" }

Write-Host "Generating answer variants..."
python -m prototype_llm_eval.backend.generate_answer_variants
if ($LASTEXITCODE -ne 0) { throw "generate_answer_variants failed with exit code $LASTEXITCODE" }

Write-Host "Running marking evaluation..."
python -m prototype_llm_eval.evaluation.run_sample_eval
if ($LASTEXITCODE -ne 0) { throw "run_sample_eval failed with exit code $LASTEXITCODE" }

Write-Host "Done."
Write-Host "Now fill: prototype_llm_eval/evaluation/results/human_marks.csv"
Write-Host "Then run: python -m prototype_llm_eval.evaluation.compare_results"
