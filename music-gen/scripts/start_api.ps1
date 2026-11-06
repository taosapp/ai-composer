# 启动官方异步 REST API（默认 http://127.0.0.1:8001）
param(
    [int]$Port = 8001,
    [string]$HostName = "127.0.0.1",
    [string]$ApiKey = "",
    [bool]$InitLlm = $true
)

. (Join-Path $PSScriptRoot "common.ps1")

$cliArgs = @(
    "-m", "acestep.api_server",
    "--host", $HostName,
    "--port", "$Port",
    "--lm-model-path", $env:ACESTEP_LM_MODEL_PATH
)
if ($ApiKey) { $cliArgs += @("--api-key", $ApiKey) }
if ($InitLlm) { $cliArgs += "--init-llm" }

Write-Host "启动 API Server ... 首次请求会加载模型。" -ForegroundColor Cyan
Set-Location $RepoRoot
$ErrorActionPreference = "Continue"

& $PythonExe @cliArgs

if ($LASTEXITCODE -ne 0) {
    Write-Host "API Server 退出，返回码 $LASTEXITCODE。" -ForegroundColor Red
}
