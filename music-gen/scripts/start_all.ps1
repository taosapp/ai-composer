# 同时启动 UI 与 API（各占一个 PowerShell 窗口）
# 12GB 显存无法同时加载两套模型：这里默认两个服务都“懒加载”，
# 端口先可访问，谁先执行生成就由谁加载模型；不要在两边同时生成。
. (Join-Path $PSScriptRoot "common.ps1")

$uiScript  = Join-Path $PSScriptRoot "start_ui.ps1"
$apiScript = Join-Path $PSScriptRoot "start_api.ps1"

Start-Process powershell -WorkingDirectory $ProjectRoot -ArgumentList @(
    "-NoExit", "-ExecutionPolicy", "Bypass",
    "-Command", "& '$uiScript' -InitService 0"
)
Start-Sleep -Seconds 2
Start-Process powershell -WorkingDirectory $ProjectRoot -ArgumentList @(
    "-NoExit", "-ExecutionPolicy", "Bypass",
    "-Command", "& '$apiScript' -InitLlm 0"
)

Write-Host "已打开两个窗口：Gradio 7860 / API 8001。" -ForegroundColor Green
Write-Host "两个服务默认不预加载模型；先执行生成的那个会占用约 11GB 显存。"
Write-Host "若要 UI 启动即加载模型，先关闭 API，再执行："
Write-Host "  .\scripts\start_ui.ps1 -InitService `$true"
