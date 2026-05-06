# Start uvicorn with env vars from prototype_llm_eval/local.env (all providers / keys in one file).
#
# Usage (from repo root):
#   .\prototype_llm_eval\scripts\start_demo_server.ps1
#
# Setup:
#   copy prototype_llm_eval\local.env.example prototype_llm_eval\local.env
#   notepad prototype_llm_eval\local.env
#
param(
    # Must not be named "Host" - that collides with PowerShell's automatic $Host variable and breaks parsing.
    [string]$BindHost = "127.0.0.1",
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
$scriptDir = $PSScriptRoot
$evalRoot = (Resolve-Path (Join-Path $scriptDir "..")).Path
$repoRoot = (Resolve-Path (Join-Path $scriptDir "..\..")).Path

Set-Location $repoRoot

$localEnvPath = Join-Path $evalRoot "local.env"
if (Test-Path -LiteralPath $localEnvPath) {
    Write-Host "Env file: $(Resolve-Path -LiteralPath $localEnvPath)" -ForegroundColor DarkGray
}
else {
    Write-Host "Env file: $localEnvPath (missing - copy from local.env.example)" -ForegroundColor Yellow
}

if (Test-Path (Join-Path $repoRoot ".venv\Scripts\Activate.ps1")) {
    . (Join-Path $repoRoot ".venv\Scripts\Activate.ps1")
}

. (Join-Path $scriptDir "Import-LocalEnv.ps1")
$names = @(Import-PrototypeLlmEvalLocalEnv -EvalRootPath $evalRoot -Quiet)
if ($names.Count -gt 0) {
    Write-Host "Loaded $($names.Count) key(s) from local.env: $($names -join ', ')" -ForegroundColor Cyan
}

function Get-LastGeminiApiKeyFromLocalEnvFile {
    param([string]$EnvFilePath)
    if (-not (Test-Path -LiteralPath $EnvFilePath)) { return $null }
    $last = $null
    Get-Content -LiteralPath $EnvFilePath -Encoding UTF8 | ForEach-Object {
        $line = $_.Trim().TrimStart([char]0xFEFF)
        $line = $line -replace '[\u200B-\u200D\uFEFF]', ''
        if (-not $line -or $line.StartsWith("#")) { return }
        $eq = $line.IndexOf("=")
        if ($eq -lt 1) { return }
        $n = $line.Substring(0, $eq).Trim()
        if ($n -ne "GEMINI_API_KEY") { return }
        $v = $line.Substring($eq + 1).Trim()
        if (($v.StartsWith('"') -and $v.EndsWith('"')) -or ($v.StartsWith("'") -and $v.EndsWith("'"))) {
            $v = $v.Substring(1, $v.Length - 2)
        }
        $v = $v.Trim().TrimStart([char]0xFEFF).TrimEnd([char]0xFEFF)
        $v = $v -replace '[\u200B-\u200D\uFEFF]', ''
        $last = $v
    }
    return $last
}

$fileGemini = Get-LastGeminiApiKeyFromLocalEnvFile -EnvFilePath $localEnvPath
$procGemini = [System.Environment]::GetEnvironmentVariable("GEMINI_API_KEY", "Process")
if ($null -eq $procGemini) { $procGemini = "" }
$fileLen = if ($null -ne $fileGemini) { $fileGemini.Length } else { 0 }
Write-Host "GEMINI_API_KEY length read from local.env (on disk): $fileLen" -ForegroundColor DarkGray
Write-Host "GEMINI_API_KEY length in process after import: $($procGemini.Length)" -ForegroundColor DarkGray
if ($null -ne $fileGemini -and ($fileGemini -eq "paste_your_key_here" -or $fileGemini.StartsWith("paste_your_"))) {
    Write-Host "WARNING: local.env still contains the template placeholder, not a real key. Save the file (Ctrl+S) with your full AI Studio key, then restart." -ForegroundColor Yellow
}
elseif ($fileLen -gt 0 -and $fileLen -lt 30) {
    Write-Host "WARNING: Key on disk is short ($fileLen chars). Real AI Studio keys are usually ~39. Unsaved editor buffer? Save prototype_llm_eval/local.env and restart." -ForegroundColor Yellow
}
if ($null -ne $fileGemini -and $fileGemini.Length -ge 30 -and $procGemini.Length -ne $fileGemini.Length) {
    Write-Warning "GEMINI_API_KEY length in process ($($procGemini.Length)) does not match value read from local.env ($($fileGemini.Length)). Re-applying from file (fixes stale or split assignments)."
    [System.Environment]::SetEnvironmentVariable("GEMINI_API_KEY", $fileGemini, "Process")
    $procGemini = $fileGemini
}

if (-not $procGemini) {
    Write-Host "Warning: GEMINI_API_KEY not in local.env - /demo-ui live generation and default Gemini calls will fail (503)." -ForegroundColor Yellow
}
else {
    Write-Host "Using GEMINI_API_KEY length: $($procGemini.Length) (AI Studio keys are usually 39 chars, prefix AIzaSy)." -ForegroundColor DarkGray
    if ($procGemini.Length -lt 30 -or -not $procGemini.StartsWith("AIza")) {
        Write-Host "Hint: If live generation returns 502, this may be the wrong secret type. Use an API key from https://aistudio.google.com/apikey" -ForegroundColor Yellow
    }
}

$url = "http://{0}:{1}/demo-ui" -f $BindHost, $Port
Write-Host "Starting uvicorn at $url ..." -ForegroundColor Green
python -m uvicorn prototype_llm_eval.backend.main:app --reload --host $BindHost --port $Port
