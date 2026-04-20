# Dot-source this file, then call Import-PrototypeLlmEvalLocalEnv:
#   . .\prototype_llm_eval\scripts\Import-LocalEnv.ps1
#   Import-PrototypeLlmEvalLocalEnv -EvalRootPath (Resolve-Path .\prototype_llm_eval)

function Import-PrototypeLlmEvalLocalEnv {
    param(
        [Parameter(Mandatory = $true)]
        [string]$EvalRootPath,
        [switch]$Quiet
    )
    $envFile = Join-Path $EvalRootPath "local.env"
    if (-not (Test-Path $envFile)) {
        if (-not $Quiet) {
            Write-Host "No local.env at: $envFile" -ForegroundColor Yellow
            Write-Host "Copy prototype_llm_eval\local.env.example -> prototype_llm_eval\local.env" -ForegroundColor Yellow
        }
        return @()
    }
    $loaded = [System.Collections.Generic.List[string]]::new()
    $priorGemini = $null
    $lineNum = 0
    Get-Content -LiteralPath $envFile -Encoding UTF8 | ForEach-Object {
        $lineNum++
        $line = $_.Trim().TrimStart([char]0xFEFF)
        $line = $line -replace '[\u200B-\u200D\uFEFF]', ''
        if (-not $line -or $line.StartsWith("#")) { return }
        $eq = $line.IndexOf("=")
        if ($eq -lt 1) { return }
        $name = $line.Substring(0, $eq).Trim()
        if (-not $name) { return }
        $val = $line.Substring($eq + 1).Trim()
        if (($val.StartsWith('"') -and $val.EndsWith('"')) -or ($val.StartsWith("'") -and $val.EndsWith("'"))) {
            $val = $val.Substring(1, $val.Length - 2)
        }
        $val = $val.Trim().TrimStart([char]0xFEFF).TrimEnd([char]0xFEFF)
        $val = $val -replace '[\u200B-\u200D\uFEFF]', ''
        if ($name -eq "GEMINI_API_KEY" -and $null -ne $priorGemini -and $priorGemini -ne $val.Length) {
            if (-not $Quiet) {
                Write-Warning "local.env line ${lineNum}: duplicate GEMINI_API_KEY (earlier value length $($priorGemini), this line $($val.Length)). Last assignment wins."
            }
        }
        if ($name -eq "GEMINI_API_KEY") { $priorGemini = $val.Length }
        # Process scope + .NET API avoids edge cases with $env:NAME parsing and matches what Python inherits.
        [System.Environment]::SetEnvironmentVariable($name, $val, "Process")
        [void]$loaded.Add($name)
        if (-not $Quiet) {
            $isSecret = $name -match '(?i)(api_?key|secret|token|password|auth)'
            if ($isSecret) {
                Write-Host "Loaded env: $name (value hidden)" -ForegroundColor DarkGray
            }
            else {
                Write-Host "Loaded env: $name"
            }
        }
    }
    return @($loaded)
}
