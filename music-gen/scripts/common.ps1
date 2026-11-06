# 公共环境配置：被其他启动脚本 dot-source 引用
# conda 路径不再写死：优先环境变量覆盖，其次 PATH 中的 conda、常见安装目录。

$ErrorActionPreference = "Stop"

$ProjectRoot  = Split-Path -Parent $PSScriptRoot
$RepoRoot     = Join-Path $ProjectRoot "ACE-Step-1.5"
$ModelsDir    = Join-Path $RepoRoot "checkpoints"
$OutputsDir   = Join-Path $ProjectRoot "outputs"
$LogsDir      = Join-Path $ProjectRoot "logs"
$FfmpegBin    = Join-Path $ProjectRoot "tools\ffmpeg\bin"
$CondaEnvName = if ($env:MUSIC_GEN_ENV_NAME) { $env:MUSIC_GEN_ENV_NAME } else { "music-gen" }

function Get-CondaRootCandidates {
    $list = @()
    if ($env:MUSIC_GEN_CONDA_ROOT) { $list += $env:MUSIC_GEN_CONDA_ROOT }
    if ($env:CONDA_ROOT) { $list += $env:CONDA_ROOT }

    $condaCmd = Get-Command conda -ErrorAction SilentlyContinue
    if ($condaCmd) {
        try {
            $base = (& $condaCmd.Source info --base 2>$null | Select-Object -First 1)
            if ($base) { $list += $base.Trim() }
        } catch { }
    }

    $names = @("miniconda3", "anaconda3", "miniforge3", "mambaforge")
    $bases = @($env:USERPROFILE)
    if ($env:LOCALAPPDATA) { $bases += $env:LOCALAPPDATA }
    if ($env:ProgramData)  { $bases += $env:ProgramData }
    foreach ($base in $bases) {
        foreach ($name in $names) {
            $list += (Join-Path $base $name)
        }
    }

    $unique = @()
    foreach ($path in $list) {
        if (-not $path) { continue }
        try { $full = [IO.Path]::GetFullPath($path) } catch { continue }
        if ((Test-Path $full) -and ($unique -notcontains $full)) { $unique += $full }
    }
    return $unique
}

function Resolve-MusicGenPython {
    if ($env:MUSIC_GEN_PYTHON) {
        if (Test-Path $env:MUSIC_GEN_PYTHON) {
            return (Resolve-Path $env:MUSIC_GEN_PYTHON).Path
        }
        throw "环境变量 MUSIC_GEN_PYTHON 指向的文件不存在：`n  $($env:MUSIC_GEN_PYTHON)"
    }

    $roots = Get-CondaRootCandidates
    foreach ($root in $roots) {
        $candidate = Join-Path $root "envs\$CondaEnvName\python.exe"
        if (Test-Path $candidate) { return $candidate }
    }

    # 环境已在 PATH 中（python.exe 直接指向 music-gen 环境）
    $pyCmd = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($pyCmd) {
        try {
            $exe = (& $pyCmd.Source -c "import sys; print(sys.executable)" 2>$null | Select-Object -First 1)
            if ($exe -and ($exe -match "\\envs\\$([regex]::Escape($CondaEnvName))\\")) {
                return $exe.Trim()
            }
        } catch { }
    }

    if ($roots.Count -eq 0) {
        throw @"
未检测到 conda（miniconda / anaconda / miniforge）安装。

已尝试的位置：
  %USERPROFILE%\miniconda3、anaconda3、miniforge3、mambaforge
  %LOCALAPPDATA%\miniconda3、anaconda3 ...
  %ProgramData%\miniconda3、anaconda3 ...
  以及 PATH 中的 conda

请任选其一：
  1) 已装在其他目录：设置环境变量后重新运行
       set MUSIC_GEN_CONDA_ROOT=D:\path\to\miniconda3
       set MUSIC_GEN_PYTHON=D:\path\to\miniconda3\envs\$CondaEnvName\python.exe
  2) 尚未安装 conda：先安装 Miniconda，再按 music-gen\README.md 第 8 节创建环境
"@
    }

    $rootsText = ($roots | ForEach-Object { "  $_" }) -join "`n"
    throw @"
已找到 conda，但没有环境「$CondaEnvName」。

conda 安装位置：
$rootsText

请任选其一：
  1) 已有环境但不在上述目录：设置环境变量后重新运行
       set MUSIC_GEN_PYTHON=D:\path\to\conda\envs\$CondaEnvName\python.exe
  2) 还没有环境：按 music-gen\README.md 第 8 节创建
       conda create -n $CondaEnvName python=3.12
       pip install -r music-gen\requirements-conda.txt
"@
}

$PythonExe = Resolve-MusicGenPython

if (-not (Test-Path $RepoRoot)) {
    throw "未找到 ACE-Step 代码目录：$RepoRoot`n请确认目录结构完整（music-gen\ACE-Step-1.5）。"
}

New-Item -ItemType Directory -Force -Path $ModelsDir, $OutputsDir, $LogsDir | Out-Null

# ---- 模型与下载 ----
$env:ACESTEP_CHECKPOINTS_DIR = $ModelsDir
$env:ACESTEP_PROJECT_ROOT    = $RepoRoot
$env:HF_ENDPOINT             = "https://hf-mirror.com"
$env:HF_HOME                 = Join-Path $ProjectRoot ".hf-cache"
$env:HF_HUB_CACHE            = Join-Path $env:HF_HOME "hub"
$env:ACESTEP_DOWNLOAD_SOURCE = "huggingface"

# ---- 默认模型档位（档 B：2B turbo + 1.7B LM）----
if (-not $env:ACESTEP_CONFIG_PATH) { $env:ACESTEP_CONFIG_PATH = "acestep-v15-turbo" }
if (-not $env:ACESTEP_LM_MODEL_PATH) { $env:ACESTEP_LM_MODEL_PATH = "acestep-5Hz-lm-1.7B" }
if (-not $env:ACESTEP_LM_BACKEND) { $env:ACESTEP_LM_BACKEND = "vllm" }
if (-not $env:ACESTEP_INIT_LLM) { $env:ACESTEP_INIT_LLM = "auto" }

# 12.0GB 会被官方档位判定卡在 tier4（只允许 0.6B LM）。
# 这里按 12.1GB 上报，进入 tier5（12-16GB，支持 1.7B LM + 自动 offload）。
# 若想强制回退 0.6B，删除这一行即可。
if (-not $env:MAX_CUDA_VRAM) { $env:MAX_CUDA_VRAM = "12.1" }

# ---- 编码 ----
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

# ---- 新 ffmpeg（系统自带 2.8.4 过旧）----
if (Test-Path (Join-Path $FfmpegBin "ffmpeg.exe")) {
    $env:PATH = "$FfmpegBin;$env:PATH"
}

Write-Host "[env] python : $PythonExe"
Write-Host "[env] repo   : $RepoRoot"
Write-Host "[env] models : $ModelsDir"
Write-Host "[env] ffmpeg : $FfmpegBin"
Write-Host "[env] HF     : $env:HF_ENDPOINT"
