# 一键启动：Gradio UI + REST API（Windows）
# 被项目根目录 start.bat 调用；也可单独执行：
#   powershell -ExecutionPolicy Bypass -File music-gen\scripts\start_local.ps1
#
# 行为：
#   1. 自动定位 music-gen 环境（见 common.ps1，可用 MUSIC_GEN_PYTHON / MUSIC_GEN_CONDA_ROOT 覆盖）
#   2. 检查模型目录与显存
#   3. 端口已就绪则复用，不再起第二份；端口被占用但未就绪则等待
#   4. 等健康检查通过后打开 http://127.0.0.1:7860
#   5. 日志写入 music-gen\logs

param(
    [int]$UiPort = 7860,
    [int]$ApiPort = 8001,
    [string]$ServerName = "127.0.0.1",
    [int]$TimeoutSeconds = 300,
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"

try {
    . (Join-Path $PSScriptRoot "common.ps1")
} catch {
    Write-Host ""
    Write-Host "[错误] 环境检查失败：" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Yellow
    exit 2
}

New-Item -ItemType Directory -Force -Path $LogsDir | Out-Null

# ---------- 工具函数 ----------
function Test-TcpPort {
    param([int]$Port)
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $iar = $client.BeginConnect("127.0.0.1", $Port, $null, $null)
        if (-not $iar.AsyncWaitHandle.WaitOne(800)) { return $false }
        $client.EndConnect($iar)
        return $true
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

function Test-UiReady {
    param([int]$Port)
    try {
        $resp = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/" -UseBasicParsing -TimeoutSec 3
        return ($resp.StatusCode -eq 200)
    } catch {
        return $false
    }
}

function Test-ApiReady {
    param([int]$Port)
    try {
        $resp = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/health" -TimeoutSec 3
        return ($resp.code -eq 200)
    } catch {
        return $false
    }
}

function Show-LogTail {
    param([string]$Path, [string]$Title)
    if (-not (Test-Path $Path)) { return }
    Write-Host "  —— $Title（末尾 20 行）——" -ForegroundColor DarkGray
    Get-Content -Path $Path -Tail 20 -Encoding UTF8 -ErrorAction SilentlyContinue |
        ForEach-Object { Write-Host "    $_" -ForegroundColor DarkGray }
}

function Start-ServiceWindow {
    param([string[]]$PyArgs, [string]$LogPath)
    $quote = { param($s) "'" + ($s -replace "'", "''") + "'" }
    $quotedArgs = ($PyArgs | ForEach-Object { & $quote $_ }) -join " "
    $command = "& $(& $quote $PythonExe) $quotedArgs *>&1 | ForEach-Object { `$line = `"`$_`"; Write-Host `$line; `$line } | Out-File -FilePath $(& $quote $LogPath) -Append -Encoding utf8"
    $encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($command))
    return Start-Process -FilePath "powershell.exe" `
        -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-EncodedCommand", $encoded) `
        -WorkingDirectory $RepoRoot -PassThru
}

function Wait-Service {
    param(
        [string]$Name,
        [scriptblock]$Check,
        [System.Diagnostics.Process]$Process,
        [int]$Timeout,
        [string]$OutLog,
        [string]$ErrLog,
        [int]$FailCode
    )
    $deadline = (Get-Date).AddSeconds($Timeout)
    while ((Get-Date) -lt $deadline) {
        if ($Process -and $Process.HasExited) {
            Write-Host ""
            Write-Host "[错误] $Name 启动后立即退出（退出码 $($Process.ExitCode)）。" -ForegroundColor Red
            Show-LogTail -Path $ErrLog -Title "$Name 错误日志"
            Show-LogTail -Path $OutLog -Title "$Name 标准输出"
            Write-Host "完整日志：$OutLog / $ErrLog" -ForegroundColor Yellow
            exit $FailCode
        }
        if (& $Check) { return $true }
        Start-Sleep -Seconds 2
    }
    Write-Host ""
    Write-Host "[错误] 等待 $Name 就绪超时（$Timeout 秒）。" -ForegroundColor Red
    Show-LogTail -Path $ErrLog -Title "$Name 错误日志"
    Show-LogTail -Path $OutLog -Title "$Name 标准输出"
    Write-Host "完整日志：$OutLog / $ErrLog" -ForegroundColor Yellow
    exit $FailCode
}

# ---------- 模型检查 ----------
$DitDir = Join-Path $ModelsDir $env:ACESTEP_CONFIG_PATH
$LmDir  = Join-Path $ModelsDir $env:ACESTEP_LM_MODEL_PATH

if (-not (Test-Path $DitDir)) {
    Write-Host ""
    Write-Host "[错误] 未找到主模型：$DitDir" -ForegroundColor Red
    Write-Host "模型尚未下载。请执行：" -ForegroundColor Yellow
    Write-Host "  powershell -ExecutionPolicy Bypass -File `"$ProjectRoot\scripts\download_models.ps1`""
    Write-Host "或确认 ACESTEP_CONFIG_PATH 指向 checkpoints 下已有的模型目录。" -ForegroundColor Yellow
    exit 3
}
if (-not (Test-Path $LmDir)) {
    Write-Host ""
    Write-Host "[错误] 未找到语言模型：$LmDir" -ForegroundColor Red
    Write-Host "请执行 download_models.ps1 下载，或设置 ACESTEP_LM_MODEL_PATH 使用已有的 LM 目录。" -ForegroundColor Yellow
    exit 3
}

# ---------- 端口与既有服务 ----------
$uiReady  = Test-UiReady -Port $UiPort
$apiReady = Test-ApiReady -Port $ApiPort
$uiBusy   = if ($uiReady) { $true } else { Test-TcpPort -Port $UiPort }
$apiBusy  = if ($apiReady) { $true } else { Test-TcpPort -Port $ApiPort }
$needLaunch = -not ($uiReady -and $apiReady)

# ---------- 显存检查（仅在需要新起服务时）---------
$freeText = $null
try { $freeText = & nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits 2>$null } catch { }
if ($needLaunch -and $freeText) {
    $freeMiB = 0
    try { $freeMiB = [int](($freeText | Select-Object -First 1).ToString().Trim()) } catch { }
    if ($freeMiB -gt 0 -and $freeMiB -lt 3000) {
        Write-Host ""
        Write-Host "[错误] 可用显存仅 $freeMiB MiB，模型加载需要约 8-11GB。" -ForegroundColor Red
        Write-Host "请先关闭占用显卡的程序（游戏、浏览器硬件加速、其他 AI 服务），再重新运行。" -ForegroundColor Yellow
        exit 4
    } elseif ($freeMiB -gt 0 -and $freeMiB -lt 8000) {
        Write-Host "[提示] 当前可用显存 $freeMiB MiB，生成时可能吃紧；建议批量大小=1、只让一个服务生成。" -ForegroundColor Yellow
    }
} elseif ($needLaunch) {
    Write-Host "[提示] 未检测到 nvidia-smi：如果不是 NVIDIA 显卡或驱动异常，生成会失败或极慢。" -ForegroundColor Yellow
}

$uiProc = $null
$apiProc = $null
$uiOut = Join-Path $LogsDir "ui.log"
$uiErr = Join-Path $LogsDir "ui.err.log"
$apiOut = Join-Path $LogsDir "api.log"
$apiErr = Join-Path $LogsDir "api.err.log"

if ($uiReady) {
    Write-Host "[复用] Gradio UI 已在运行：http://$ServerName`:$UiPort" -ForegroundColor Green
} elseif ($uiBusy) {
    Write-Host "[等待] 端口 $UiPort 已被占用但界面未就绪，等待现有进程..." -ForegroundColor Yellow
} else {
    Write-Host "[启动] Gradio UI（端口 $UiPort）..." -ForegroundColor Cyan
    $uiArgs = @(
        "-m", "acestep.acestep_v15_pipeline",
        "--port", "$UiPort",
        "--server-name", $ServerName,
        "--language", "zh",
        "--config_path", $env:ACESTEP_CONFIG_PATH,
        "--lm_model_path", $env:ACESTEP_LM_MODEL_PATH,
        "--backend", $env:ACESTEP_LM_BACKEND,
        "--init_service", "false"
    )
    if (Test-Path $uiOut) { Remove-Item $uiOut -Force -ErrorAction SilentlyContinue }
    $uiProc = Start-ServiceWindow -PyArgs $uiArgs -LogPath $uiOut
}

if ($apiReady) {
    Write-Host "[复用] REST API 已在运行：http://$ServerName`:$ApiPort" -ForegroundColor Green
} elseif ($apiBusy) {
    Write-Host "[等待] 端口 $ApiPort 已被占用但 API 未就绪，等待现有进程..." -ForegroundColor Yellow
} else {
    Write-Host "[启动] REST API（端口 $ApiPort）..." -ForegroundColor Cyan
    $apiArgs = @(
        "-m", "acestep.api_server",
        "--host", $ServerName,
        "--port", "$ApiPort",
        "--lm-model-path", $env:ACESTEP_LM_MODEL_PATH
    )
    if ($env:ACESTEP_API_KEY) { $apiArgs += @("--api-key", $env:ACESTEP_API_KEY) }
    if (Test-Path $apiOut) { Remove-Item $apiOut -Force -ErrorAction SilentlyContinue }
    $apiProc = Start-ServiceWindow -PyArgs $apiArgs -LogPath $apiOut
}

# ---------- 健康检查 ----------
if (-not $uiReady) {
    $uiReady = Wait-Service -Name "Gradio UI" -Check { Test-UiReady -Port $UiPort } -Process $uiProc `
        -Timeout $TimeoutSeconds -OutLog $uiOut -ErrLog $uiErr -FailCode 5
}
if (-not $apiReady) {
    $apiReady = Wait-Service -Name "REST API" -Check { Test-ApiReady -Port $ApiPort } -Process $apiProc `
        -Timeout 120 -OutLog $apiOut -ErrLog $apiErr -FailCode 6
}

# ---------- 结果 ----------
Write-Host ""
Write-Host "================================================" -ForegroundColor Green
Write-Host " 启动完成" -ForegroundColor Green
Write-Host "   UI  : http://$ServerName`:$UiPort" -ForegroundColor Green
Write-Host "   API : http://$ServerName`:$ApiPort  (文档 /docs)" -ForegroundColor Green
Write-Host "  日志 : $LogsDir" -ForegroundColor Green
Write-Host "================================================" -ForegroundColor Green
Write-Host "两个服务均为懒加载：第一次生成时才加载模型（约 1-5 分钟），之后 30 秒级。" -ForegroundColor DarkGray

if (-not $NoBrowser) {
    try {
        Start-Process "http://127.0.0.1:$UiPort" | Out-Null
        Write-Host "[打开] 已在浏览器打开 http://127.0.0.1:$UiPort" -ForegroundColor Cyan
    } catch {
        Write-Host "[提示] 自动打开浏览器失败，请手动访问 http://127.0.0.1:$UiPort" -ForegroundColor Yellow
    }
}

exit 0
