# 启动官方 Gradio UI（中文界面，默认 http://127.0.0.1:7860）
param(
    [int]$Port = 7860,
    [string]$ServerName = "127.0.0.1",
    [bool]$InitService = $true
)

. (Join-Path $PSScriptRoot "common.ps1")

Write-Host "启动 Gradio UI ... 首次运行会自动下载模型（约 10GB），请耐心等待。" -ForegroundColor Cyan
Set-Location $RepoRoot
$initFlag = if ($InitService) { "true" } else { "false" }
$ErrorActionPreference = "Continue"

& $PythonExe -m acestep.acestep_v15_pipeline `
    --port $Port `
    --server-name $ServerName `
    --language zh `
    --config_path $env:ACESTEP_CONFIG_PATH `
    --lm_model_path $env:ACESTEP_LM_MODEL_PATH `
    --backend $env:ACESTEP_LM_BACKEND `
    --init_service $initFlag

if ($LASTEXITCODE -ne 0) {
    Write-Host "Gradio 退出，返回码 $LASTEXITCODE。可查看 README 的常见报错章节。" -ForegroundColor Red
}
