# 预下载 ACE-Step 主模型（turbo + VAE + 文本编码器 + 1.7B LM，约 10GB）
. (Join-Path $PSScriptRoot "common.ps1")

Set-Location $RepoRoot
Write-Host "开始下载主模型到 $ModelsDir ..." -ForegroundColor Cyan
$ErrorActionPreference = "Continue"

& $PythonExe (Join-Path $PSScriptRoot "download_models.py")

if ($LASTEXITCODE -ne 0) {
    Write-Host "下载失败，返回码 $LASTEXITCODE。可改用 ModelScope：" -ForegroundColor Red
    Write-Host "  `$env:ACESTEP_DOWNLOAD_SOURCE='modelscope'; python -m acestep.model_downloader --model main --dir $ModelsDir"
}
