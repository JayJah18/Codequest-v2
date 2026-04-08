# Run from repo root:  Codequest-v2\
# Usage:  .\prototype_llm_eval\scripts\prepare_fixed_dataset.ps1
Set-Location $PSScriptRoot\..\..
python -m prototype_llm_eval.backend.prepare_fixed_dataset
