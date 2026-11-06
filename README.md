# ai-composer

在 Windows 本地跑 AI 作曲：ACE-Step 1.5（2B DiT + 1.7B 语言模型）+ 一个中文歌词润色工具。
支持 Gradio 界面与 REST API，双显卡档位按 12GB 显存调优，含「从零到一首歌」实操手册。

> 本仓库只保存代码、脚本、文档、样曲与歌词示例。
> **模型权重、上游 ACE-Step 代码、ffmpeg 二进制、缓存与日志都不入库**，需要按下面「模型与数据结构」自行放置。

## 1. 目录结构

```
ai-composer/
├─ start.bat                     # 一键启动（Windows）：UI + API + 健康检查 + 打开浏览器
├─ music-gen/
│  ├─ ACE-Step-1.5/              # 上游代码，按需 clone（不入库）
│  ├─ checkpoints → ACE-Step-1.5/checkpoints   # 模型权重（不入库）
│  ├─ models/polish-llm/         # 歌词润色模型（不入库）
│  ├─ scripts/                   # common / start_ui / start_api / start_local / download_models
│  ├─ tools/                     # ffmpeg 9.x（不入库）
│  ├─ outputs/                   # 样曲 mp3、示例歌词、润色报告
│  ├─ music_gen.py               # REST API 命令行薄封装（纯标准库）
│  ├─ lyrics_polish.py           # 歌词润色：韵脚分析 + 演唱排版 + LLM 改写
│  ├─ README.md                  # 环境、安装、性能、排错
│  └─ GUIDE.md                   # UI 字段逐项说明 + 可直接执行的 API 请求
└─ ai-music-local-deployment/    # 选型调研报告（HTML）
```

## 2. 快速开始（Windows）

```powershell
# 1) 获取上游代码（不入库，必须单独 clone）
git clone https://github.com/ACE-Step/ACE-Step-1.5.git d:\ai\ai-composer\music-gen\ACE-Step-1.5

# 2) 创建 conda 环境并安装依赖（详见 music-gen/README.md 第 8 节）
conda create -n music-gen python=3.12 -y
#   然后按 README 第 8 节安装 torch 2.7.1+cu126 与 requirements-conda.txt

# 3) 放好模型权重（见第 3 节）与 ffmpeg（见第 5 节）

# 4) 一键启动
双击 start.bat
```

`start.bat` 会自动：

- 探测 conda（可用 `MUSIC_GEN_PYTHON` / `MUSIC_GEN_CONDA_ROOT` 覆盖），不写死路径；
- 拉起 Gradio UI（<http://127.0.0.1:7860>）与 REST API（<http://127.0.0.1:8001>，文档 `/docs`）；
- 等健康检查通过后打开浏览器；日志写 `music-gen\logs\ui.log`、`api.log`；
- 端口已在用则复用现有服务，可重复执行；缺 conda / 缺环境 / 缺模型 / 显存不足会分别给中文提示并返回不同退出码。

## 3. 模型与数据结构

### 3.1 权重放哪里

| 用途 | 目录（相对仓库根） | 实测体积 | 内容 |
| :- | :- | :- | :- |
| ACE-Step 全部模型 | `music-gen/ACE-Step-1.5/checkpoints/` | **10.68 GiB** | 5 个子目录，见下表 |
| 歌词润色（本地） | `music-gen/models/polish-llm/Qwen3-4B/` | **7.51 GiB** | 3 个分片 safetensors + tokenizer/config |
| 润色小模型（可选） | `music-gen/models/polish-llm/Qwen3-1.7B/` | 约 3.8 GiB | 效果较差，仅作兜底 |

`checkpoints` 下应有且只有这 5 个目录：

| 子目录 | 体积 | 关键文件 |
| :- | :- | :- |
| `acestep-v15-turbo` | 4.46 GiB | `model.safetensors`、`config.json`、`silence_latent.pt` |
| `acestep-5Hz-lm-1.7B` | 3.50 GiB | `model.safetensors`、`tokenizer.json`、`vocab.json`、`merges.txt` |
| `acestep-5Hz-lm-0.6B` | 1.28 GiB | 同上（低显存档兜底） |
| `Qwen3-Embedding-0.6B` | 1.12 GiB | `model.safetensors`、`config.json` |
| `vae` | 0.31 GiB | `diffusion_pytorch_model.safetensors`、`config.json` |

以上目录全部被根目录 `.gitignore` 排除（`music-gen/ACE-Step-1.5/`、`music-gen/models/`），
不会进入仓库，也不必担心误提交。

### 3.2 从移动硬盘拷贝后怎么确认

拷贝完成后，在仓库根目录执行：

```powershell
# ① 目录清单：应为 5 个
Get-ChildItem music-gen\ACE-Step-1.5\checkpoints -Directory | Select-Object -ExpandProperty Name

# ② 体积量级（GiB）：checkpoints ≈10.68，Qwen3-4B ≈7.51
(Get-ChildItem music-gen\ACE-Step-1.5\checkpoints -Recurse -File | Measure-Object Length -Sum).Sum / 1GB
(Get-ChildItem music-gen\models\polish-llm\Qwen3-4B -Recurse -File | Measure-Object Length -Sum).Sum / 1GB

# ③ 关键文件存在性（缺一个都会导致加载失败）
Test-Path music-gen\ACE-Step-1.5\checkpoints\acestep-v15-turbo\model.safetensors
Test-Path music-gen\ACE-Step-1.5\checkpoints\acestep-5Hz-lm-1.7B\tokenizer.json
Test-Path music-gen\models\polish-llm\Qwen3-4B\model.safetensors.index.json
```

体积明显偏小（例如只有几 MB）通常说明拷贝中断，只复制了 `.incomplete` 或索引文件，需重新拷贝。

### 3.3 缺失时会报什么错、怎么补

| 缺失项 | 现象 | 补齐方式 |
| :- | :- | :- |
| `ACE-Step-1.5` 代码目录 | 启动脚本报「未找到 ACE-Step 代码目录：…」 | 按第 2 节第 1 步 clone |
| 主模型 `acestep-v15-turbo` | `start.bat` 输出「[错误] 未找到主模型：…\checkpoints\acestep-v15-turbo」，退出码 3 | 从移动硬盘 copy，或跑 `music-gen\scripts\download_models.ps1` |
| 语言模型 `acestep-5Hz-lm-1.7B` | 「[错误] 未找到语言模型：…」退出码 3 | 同上；也可设 `ACESTEP_LM_MODEL_PATH` 指向已有 LM |
| `Qwen3-4B`（润色用） | `lyrics_polish.py --backend local` 报「本地润色模型不存在：…」并打印 ModelScope 下载命令 | 拷贝到 `music-gen\models\polish-llm\Qwen3-4B`，或改用 `--backend rule` / `--backend openai` |
| ffmpeg | 启动时无新版 ffmpeg，转码报错或音频格式异常 | 见第 5 节 |

## 4. 文档

- [music-gen/README.md](music-gen/README.md)：环境事实、安装、模型下载记录、实测性能、常见报错、重装步骤。
- [music-gen/GUIDE.md](music-gen/GUIDE.md)：UI 实际字段（必填/可省）、段落标签写法、LRC、REST API 真实请求与返回结构、完整中文示例。
- [ai-music-local-deployment/](ai-music-local-deployment/)：本地部署选型调研报告（HTML）。

## 5. 依赖与外部组件

| 组件 | 说明 |
| :- | :- |
| conda 环境 `music-gen` | Python 3.12.16，torch 2.7.1+cu126；创建步骤见 `music-gen/README.md` 第 8 节 |
| ACE-Step 1.5 | 上游 MIT 项目，需 clone 到 `music-gen\ACE-Step-1.5`，不随本仓库分发 |
| ffmpeg 9.x | 仓库不含二进制。可 `winget install Gyan.FFmpeg`，或把 `ffmpeg.exe / ffprobe.exe` 放到 `music-gen\tools\ffmpeg\bin`（脚本会自动前置 PATH） |
| 歌词润色模型 | Qwen3-4B（约 7.5 GiB），仅 `--backend local` 需要；不装可用规则或外部 LLM |

## 6. 许可

本仓库自有代码按仓库内约定使用；`music-gen/ACE-Step-1.5` 为上游 ACE-Step 项目（MIT），
其许可证与版权归原作者所有，随上游仓库分发。
