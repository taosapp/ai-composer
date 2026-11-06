# ACE-Step 1.5 本地 AI 作曲

在 Windows 11 + RTX 3060 12GB 上本地运行 ACE-Step 1.5（档 B：2B DiT + 1.7B LM），
支持中文歌词、人声演唱与整曲生成，提供官方 Gradio UI、官方异步 REST API 和一个零依赖命令行封装。

## 1. 环境事实（已实测）

| 项目 | 值 |
| --- | --- |
| conda | `$env:USERPROFILE\miniconda3\Scripts\conda.exe`（未加入 PATH） |
| 环境名 | `music-gen` |
| Python | 3.12.16 |
| PyTorch | 2.7.1+cu126（`torch.cuda.is_available() == True`） |
| GPU | RTX 3060 12GB，驱动 CUDA 13.4 |
| ffmpeg | 9.0.2 静态版，位于 `tools\ffmpeg\bin`（系统自带的 2.8.4 不再使用） |
| 模型 | 10.68 GB，位于 `ACE-Step-1.5\checkpoints` |

> 官方 Windows 依赖表写的是 `torch 2.7.1+cu128`；本项目按你的要求装的是 **cu126**，
> 已完成导入、CUDA、1.7B LM、中文歌曲生成全链路验证。

## 2. 目录结构

```
music-gen/
├─ ACE-Step-1.5/                 # 官方代码（MIT）
│  └─ checkpoints/               # ACE 模型权重（API/UI 默认读取这里）
├─ models/polish-llm/            # 歌词润色用的 Qwen3-4B（可选，约 8GB）
├─ outputs/                      # 生成的音频
│  ├─ demo_first.mp3             # 首次中文生成，60s
│  ├─ demo_thinking.mp3          # 1.7B LM 思考模式，30s
│  ├─ demo_warm60.mp3            # 热启动 60s
│  ├─ lyrics_demo.txt            # 示例中文歌词
│  ├─ lyrics_polished.txt        # 润色后可演唱版
│  └─ lyrics_report.md           # 韵脚表 + 改动说明
├─ scripts/
│  ├─ common.ps1                 # 统一环境变量 / PATH / 模型目录
│  ├─ start_ui.ps1               # 启动 Gradio UI
│  ├─ start_api.ps1              # 启动异步 REST API
│  ├─ start_all.ps1              # 同时开两个窗口（懒加载，避免显存叠加）
│  ├─ download_models.ps1        # 重新下载模型
│  └─ download_models.py         # HF 镜像优先、失败回退 ModelScope
├─ tools/ffmpeg/bin              # ffmpeg 9.0.2
├─ logs/                         # api.log / ui.log / gen60.log
├─ music_gen.py                  # REST API 薄封装（纯标准库）
├─ lyrics_polish.py              # 歌词润色：韵脚分析 / 演唱排版 / LLM 改写
├─ GUIDE.md                      # 从零到一首歌：UI + API 实操手册
└─ requirements-conda.txt        # 除 torch 外的 Python 依赖
```

## 3. 模型下载记录

- 路径：`D:\ai\ai-composer\music-gen\ACE-Step-1.5\checkpoints`
- 体积：**10.68 GB**
  - `acestep-v15-turbo`（2B DiT）：4.46 GB
  - `acestep-5Hz-lm-1.7B`：3.50 GB
  - `Qwen3-Embedding-0.6B`：1.12 GB
  - `vae`：0.31 GB
  - `acestep-5Hz-lm-0.6B`：1.28 GB（首次自动降档时下载，保留作兜底）
- 下载源：配置了 `HF_ENDPOINT=https://hf-mirror.com` 并优先尝试 HuggingFace；
  实测该镜像对本仓库返回“找不到文件”，项目自动回退 **ModelScope**，约 18-20 MB/s，
  主模型 9.40 GB 约 5 分钟完成。
- 歌词润色模型（可选）：`models\polish-llm\Qwen3-4B`，约 **8.04 GB**，
  ModelScope 下载，实测约 4 分钟；只用于 `lyrics_polish.py --backend local`。

## 4. 快速开始

### 4.1 Gradio UI（中文）

```powershell
powershell -ExecutionPolicy Bypass -File d:\ai\ai-composer\music-gen\scripts\start_ui.ps1 -InitService $true
```

打开 <http://127.0.0.1:7860>。首次加载模型约 1-2 分钟（LM tokenizer 约 26 秒）。
若还要同时跑 API，建议改成 `-InitService $false`，避免两套模型同时占显存。

### 4.2 REST API

```powershell
powershell -ExecutionPolicy Bypass -File d:\ai\ai-composer\music-gen\scripts\start_api.ps1 -InitLlm $true
```

- 健康检查：<http://127.0.0.1:8001/health>
- Swagger：<http://127.0.0.1:8001/docs>
- 可选 API Key：`start_api.ps1 -ApiKey "your-key"`，请求带 `Authorization: Bearer your-key`

### 4.3 同时启动（懒加载）

```powershell
powershell -ExecutionPolicy Bypass -File d:\ai\ai-composer\music-gen\scripts\start_all.ps1
```

两个服务都不预加载模型，端口立即可访问；**先执行生成的那个会占用约 11GB 显存**，
不要在 UI 和 API 上同时生成。

### 4.4 命令行生成（推荐给脚本 / 前端）

```powershell
$env:USERPROFILE\miniconda3\envs\music-gen\python.exe d:\ai\ai-composer\music-gen\music_gen.py generate `
  --prompt "温暖的中文流行民谣，木吉他，钢琴，女声，慢速" `
  --lyrics-file d:\ai\ai-composer\music-gen\outputs\lyrics_demo.txt `
  --language zh --duration 60 --steps 8 --thinking --out d:\ai\ai-composer\music-gen\outputs\new.mp3
```

常用参数：

| 参数 | 说明 |
| --- | --- |
| `--prompt` | 风格 / 编曲 / 人声描述 |
| `--lyrics` / `--lyrics-file` | 歌词，支持 `[Verse]`、`[Chorus]` 段落标记 |
| `--language zh` | 中文歌词 |
| `--duration` | 10-600 秒 |
| `--thinking` | 启用 5Hz LM 规划（更慢更稳，需 LM 已加载） |
| `--steps 8` | turbo 用 8；sft/base 建议 32-64 |
| `--batch` | 一次生成数量 |
| `--seed` | 固定种子复现 |
| `--out` | 文件或目录 |

其他命令：

```powershell
python music_gen.py health
python music_gen.py models
```

### 4.5 生成前润色歌词（可选）

ACE-Step 自带的 `/format_input` 只做 query rewrite（本机实测还会把中文转成拼音），
不做韵脚优化。项目自带 `lyrics_polish.py`，三条后端：

| 后端 | 作用 | 依赖 |
| --- | --- | --- |
| `rule` | 统一段落标签、去行末标点、超长句断句、韵脚/重字/句长诊断，不改词 | 无 |
| `local` | 本机 Qwen3-4B：只重写破韵/超长句，逐行校验韵脚与字数，最多 8 次候选 | `models\polish-llm\Qwen3-4B`（约 8GB） |
| `openai` | 任意 OpenAI 兼容 `/chat/completions` 服务，整段语义改写 | 外部 API Key |

```powershell
# 只诊断（不占显存，随时可跑）
$env:USERPROFILE\miniconda3\envs\music-gen\python.exe d:\ai\ai-composer\music-gen\lyrics_polish.py analyze `
  --lyrics-file d:\ai\ai-composer\music-gen\outputs\lyrics_demo.txt

# 本地 4B 润色（会占约 9GB 显存，先把 API 停掉，或加 --device cpu）
$env:USERPROFILE\miniconda3\envs\music-gen\python.exe d:\ai\ai-composer\music-gen\lyrics_polish.py polish `
  --lyrics-file d:\ai\ai-composer\music-gen\outputs\lyrics_demo.txt `
  --style "温暖的中文民谣" --voice "男声，偏低沉" --backend local
```

输出 `outputs\lyrics_polished.txt` 与 `outputs\lyrics_report.md`（韵脚表、问题清单、改动说明、前后对比）。

外部 LLM 配置：

```powershell
$env:ACESTEP_POLISH_BASE_URL = "https://api.deepseek.com/v1"
$env:ACESTEP_POLISH_API_KEY  = "sk-..."
$env:ACESTEP_POLISH_MODEL    = "deepseek-chat"
```

然后 `--backend openai` 即可。

> 实测结论：ACE-Step 自带的 1.7B LM 是为音频语义码训练的，直接问文本会输出 BPM/caption 元数据，
> **不能**做歌词改写；所以本地改写改用 Qwen3-4B，ACE 1.7B 只负责音乐生成。

本地模型下载（约 8GB，ModelScope）：

```powershell
$env:USERPROFILE\miniconda3\envs\music-gen\python.exe -c "from modelscope import snapshot_download; snapshot_download('Qwen/Qwen3-4B', local_dir=r'd:\ai\ai-composer\music-gen\models\polish-llm\Qwen3-4B')"
```

## 5. 实测性能（RTX 3060 12GB）

| 场景 | 时长 | 耗时 | 显存峰值 |
| --- | --- | --- | --- |
| 首次生成（0.6B LM，含下载/加载） | 60s | 324s | 7694 MiB |
| 首次生成（1.7B LM，思考模式，含加载） | 30s | 241s | 11049 MiB |
| 热启动（1.7B LM，思考模式） | 30s | **28.1s** | 11263 MiB |
| 热启动（1.7B LM，思考模式） | 60s | **38.8s** | 11263 MiB |

- 输出统一为 48 kHz 双声道；默认 MP3 128kbps。
- 冷启动的主要耗时在 LM tokenizer（约 26s）与权重加载，不在采样本身。
- 峰值 11.0-11.3GB，已接近 12GB 上限；生成时不要开大型游戏/浏览器 GPU 加速。

## 6. 关键配置与官方默认的差异

1. **cu126 而非官方 cu128**：按需求安装，已全链路验证。
2. **12.0GB 档位边界**：官方把 12.0GB 判成 tier4，只允许 0.6B LM。
   `scripts\common.ps1` 设置 `MAX_CUDA_VRAM=12.1` 进入 tier5，从而加载 1.7B LM；
   若要强制回退 0.6B，删掉该行即可。
3. **模型目录**：API/UI 内部固定读 `ACE-Step-1.5\checkpoints`，
   因此模型已放在该目录，而不是工作区根部的 `models`。
4. **ffmpeg**：使用 `tools\ffmpeg\bin\ffmpeg.exe` 9.0.2，启动脚本自动前置 PATH。
5. **后端**：`ACESTEP_LM_BACKEND=vllm`（nano-vllm）。Windows + Python 3.12 没有 Triton，
   会自动回退 SDPA 原生 kernel，功能正常。

## 7. 常见报错

| 现象 | 原因 / 处理 |
| --- | --- |
| `conda: 无法将“conda”项识别为...` | conda 未进 PATH。脚本已用完整路径；手动执行用 `$env:USERPROFILE\miniconda3\envs\music-gen\python.exe` |
| PowerShell 提示 `Unexpected token ')'` | 脚本需 UTF-8 BOM。仓库内 `.ps1` 已带 BOM，编辑后请另存为“UTF-8 带 BOM” |
| `Skipping import of cpp extensions due to incompatible torch version ... torchao 0.16.0` | 只是 torchao 预编译扩展跳过，纯 Python 路径可用；不影响推理 |
| `bitsandbytes not installed. Using standard AdamW.` | 仅训练相关，推理忽略 |
| 只加载了 `acestep-5Hz-lm-0.6B` | 12.0GB 被判为 tier4；确认 `MAX_CUDA_VRAM=12.1` 已生效 |
| 启动后又开始重复下载模型 | 模型不在 `ACE-Step-1.5\checkpoints`；把它们移到该目录，或删除半成品后重下 |
| HuggingFace 镜像报 `cannot find requested files` | 本项目实测会发生，已自动回退 ModelScope；也可手动 `ACESTEP_DOWNLOAD_SOURCE=modelscope` |
| `CUDA out of memory` | UI 与 API 都加载了模型。只保留一个生成服务；或关闭占用显存的程序后重试 |
| 7860 / 8001 被占用 | 换端口：`start_ui.ps1 -Port 7861`、`start_api.ps1 -Port 8002` |
| 生成成功但无声音 / 播放失败 | 用 `tools\ffmpeg\bin\ffprobe.exe` 检查时长与声道；确认播放器支持 48kHz MP3 |
| 首次生成很慢（3-5 分钟） | 冷启动需加载 DiT + LM tokenizer；后续热启动 30s 歌曲约 28s |

## 8. 重新安装 / 维护

```powershell
# 重建环境
$env:USERPROFILE\miniconda3\Scripts\conda.exe create -n music-gen python=3.12 -y
$env:USERPROFILE\miniconda3\envs\music-gen\python.exe -m pip install torch==2.7.1 torchvision==0.22.1 torchaudio==2.7.1 --index-url https://download.pytorch.org/whl/cu126
$env:USERPROFILE\miniconda3\envs\music-gen\python.exe -m pip install -r d:\ai\ai-composer\music-gen\requirements-conda.txt
$env:USERPROFILE\miniconda3\envs\music-gen\python.exe -m pip install -e d:\ai\ai-composer\music-gen\ACE-Step-1.5 --no-deps
$env:USERPROFILE\miniconda3\envs\music-gen\python.exe -m pip install -e d:\ai\ai-composer\music-gen\ACE-Step-1.5\acestep\third_parts\nano-vllm --no-deps
# 歌词润色工具依赖（韵脚分析用）
$env:USERPROFILE\miniconda3\envs\music-gen\python.exe -m pip install pypinyin

# 重新下载模型
powershell -ExecutionPolicy Bypass -File d:\ai\ai-composer\music-gen\scripts\download_models.ps1
```

## 9. 参考

- 从零到一首歌实操手册（UI 字段逐项说明 + 可直接执行的 API 请求）：[GUIDE.md](file:///d:/ai/ai-composer/music-gen/GUIDE.md)
- 选型调研报告：[ai-music-local-deployment.html](file:///d:/ai/ai-composer/ai-music-local-deployment/ai-music-local-deployment.html)
- 上游代码：<https://github.com/ACE-Step/ACE-Step-1.5>
- 官方中文文档：`ACE-Step-1.5/docs/zh/`
