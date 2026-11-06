# 从零到一首歌：本机操作指南

本文件按本机**实际部署**写成（不是通用文档抄写）。所有命令都可以直接复制到 PowerShell 执行。

- conda 环境：`music-gen`（Python 3.12）
- Python：`$env:USERPROFILE\miniconda3\envs\music-gen\python.exe`
- 项目目录：`d:\ai\ai-composer\music-gen`
- 主模型：`acestep-v15-turbo`（2B DiT）
- 语言模型：`acestep-5Hz-lm-1.7B`
- UI：`http://127.0.0.1:7860`
- API：`http://127.0.0.1:8001`

> 12GB 显存下，UI 和 API 可以同时开着，但**同一时刻只让一个服务执行生成**，否则会 OOM。

---

## 一、先把服务跑起来

### 1. Gradio UI

```powershell
powershell -ExecutionPolicy Bypass -File "d:\ai\ai-composer\music-gen\scripts\start_ui.ps1"
```

默认会加载模型（首次 1-3 分钟）。看到 `Running on local URL: http://127.0.0.1:7860` 后，浏览器打开该地址。

如果只想先开界面、稍后手动加载模型：

```powershell
powershell -ExecutionPolicy Bypass -File "d:\ai\ai-composer\music-gen\scripts\start_ui.ps1" -InitService 0
```

然后在界面里点“初始化服务”。

### 2. REST API

```powershell
powershell -ExecutionPolicy Bypass -File "d:\ai\ai-composer\music-gen\scripts\start_api.ps1"
```

检查：

```powershell
curl.exe http://127.0.0.1:8001/health
```

本机实测返回：

```json
{
  "data": {
    "status": "ok",
    "service": "ACE-Step API",
    "version": "1.0",
    "models_initialized": true,
    "llm_initialized": true,
    "loaded_model": "acestep-v15-turbo",
    "loaded_lm_model": "acestep-5Hz-lm-1.7B"
  },
  "code": 200,
  "error": null,
  "timestamp": 1793947375895,
  "extra": null
}
```

---

## 二、歌词怎么写

### 段落标签

推荐只用这几个英文标签，实测最稳：

```text
[Verse 1]
[Chorus]
[Verse 2]
[Chorus]
[Bridge]
[Outro]
```

中文标签（`[主歌1]`、`[副歌]`）也能识别，但界面点“格式化”时可能被改写成 `[Verse]`，所以正式生成建议直接写英文。

### 分行

**一行 = 一个演唱乐句**。本机实测 6-12 个汉字一行最稳；过长会被挤进同一口气，容易吞字。

```text
[Verse 1]
夜色落在窗台
风把心事吹开
街灯一盏一盏
照着我慢慢走回来
```

- 段落之间空一行即可，空行不影响生成。
- 不要写 LRC 时间戳（`[00:01.00]`）。本机实测输入时间戳会被移除；LRC 是**生成后**由“自动 LRC / 获取 LRC”产出的。
- 标点可留可去；演唱时不会念标点。

### LRC 怎么用

1. 生成时勾选“自动 LRC”；
2. 生成完成后，在“歌词时间戳(样本 1..8)”里得到 LRC；
3. LRC 属于**输出**，不要粘回歌词输入框。

### 中文歌的两个必设项

- “人声语言”必须选 `zh`（默认是 `unknown` = 纯音乐/自动）。
- “纯音乐”必须**取消勾选**。

---

## 三、Gradio UI 实际操作

### 1. 生成模式

“生成模式 *”只有四个选项：`Simple` / `Custom` / `Remix` / `Repaint`。

- 自己写歌词、自己定风格，选 **Custom**。
- `Simple` 字段更少；`Remix` / `Repaint` 需要参考音频。

### 2. 实际字段

| 界面字段 | 必填 | 本机默认 | 怎么填 |
| :-- | :-- | :-- | :-- |
| 生成模式 * | 是 | Custom | 选 `Custom` |
| 歌曲描述 * | 是 | 空 | 曲风 + 乐器 + 人声 + 速度 + 情绪，见下方示例 |
| 歌词 | 要人声就必须填 | 空 | 你的中文歌词，带段落标签 |
| 纯音乐 | - | 未勾选 | 要人声就保持未勾选 |
| 人声语言 | 要人声就必须设 | `unknown` | 中文选 `zh` |
| 音频时长 (秒) | 否 | `-1`（随机） | 建议显式填 30-90；上限 600 |
| 批量大小 | 否 | 2 | 12GB 显存建议填 `1`；界面上限 4 |
| BPM | 否 | 空 | 想固定就填，并把“BPM 自动”取消勾选 |
| 调 | 否 | 空 | 如 `C Major`、`A minor`；取消“调 自动” |
| 拍号 | 否 | 空 | `2` / `3` / `4` / `6`；取消“拍号 自动” |
| 思考 | 否 | 未勾选 | 勾选会用 1.7B LM 先做结构规划，更稳但更慢 |
| DiT 推理步数 | 否 | 8 | turbo 模型上限 8，填更大无效 |
| 种子 | 否 | `-1` | `-1` 随机；固定种子可复现 |
| 自动 LRC | 否 | 未勾选 | 需要时间戳就勾选 |
| 音频格式 | 否 | `mp3` | `mp3` / `wav` / `flac` / `opus` / `aac` |

**没有“人声性别/音色”下拉框。** 声音写进“歌曲描述”，例如：

```text
温暖的中文民谣，木吉他分解和弦，男声，偏低沉，气声，慢速，情绪真挚
```

女声就写 `女声，清澈，偏明亮`；想要少年感写 `少年音，干净`。

### 3. 生成步骤

1. 启动 UI，等模型加载完。
2. 生成模式选 `Custom`。
3. 填“歌曲描述”。
4. 填“歌词”，确认“纯音乐”未勾选，“人声语言”=`zh`。
5. 时长填 `60`，批量填 `1`。
6. 需要时间戳就勾选“自动 LRC”。
7. 点生成；完成后在播放器试听、下载音频。

### 4. 不要点的两个按钮

- **“格式化”**
- **“增强歌词”**

这两个按钮走 `/format_input`，底层是 1.7B LM 的 query rewrite。本机实测：一次把中文歌词转成了拼音（输出形如 `[zh] ye4 se4 ...`），还会改写段落标签。正式歌词直接填原文，不要过这两个按钮。

---

## 四、REST API 实际操作（本机实测）

### 1. 先看模型

```powershell
curl.exe http://127.0.0.1:8001/v1/models
```

注意：`/v1/models` 是 OpenAI 风格，**没有** `data/code/error` 外层；其他业务接口才有。

```json
{
  "object": "list",
  "data": [
    {
      "id": "acestep/acestep-v15-turbo",
      "name": "ACE-Step acestep-v15-turbo",
      "description": "AI music generation model"
    }
  ]
}
```

### 2. 提交任务：`POST /release_task`

本机实测请求体（30 秒、中文、思考模式、8 步）：

```json
{
  "prompt": "温暖的中文民谣，木吉他分解和弦，男声，慢速，情绪真挚",
  "lyrics": "[Verse 1]\n夜色落在窗台\n风把心事吹开\n街灯一盏一盏\n照着我慢慢走回来\n\n[Chorus]\n如果明天还有风\n就让我唱给你听\n把未说出口的梦\n都写成这一首歌\n\n[Verse 2]\n旧吉他靠在墙角\n弦上还有你的笑\n城市太吵太匆忙\n至少旋律不会老\n\n[Chorus]\n如果明天还有风\n就让我唱给你听\n把未说出口的梦\n都写成这一首歌\n",
  "vocal_language": "zh",
  "audio_duration": 30,
  "audio_format": "mp3",
  "thinking": true,
  "inference_steps": 8,
  "batch_size": 1,
  "use_random_seed": true,
  "seed": -1,
  "bpm": 92,
  "key_scale": "C Major"
}
```

返回：

```json
{
  "data": {
    "task_id": "c48cd825-dcdf-4151-9b68-88399c756d44",
    "status": "queued",
    "queue_position": 1
  },
  "code": 200,
  "error": null,
  "timestamp": 1793947375923,
  "extra": null
}
```

字段说明：

| 字段 | 必填 | 说明 |
| :-- | :-- | :-- |
| `prompt` | 是 | 风格描述，人声性别/音色写这里 |
| `lyrics` | 要人声就必填 | 带段落标签；不要 LRC 时间戳 |
| `vocal_language` | 建议必填 | 中文 `zh`；纯音乐用 `unknown` |
| `audio_duration` | 否 | 秒；`-1` 随机；上限 600 |
| `audio_format` | 否 | `mp3` / `wav` / `flac` 等 |
| `thinking` | 否 | `true` 启用 1.7B LM 规划 |
| `inference_steps` | 否 | turbo 用 8 |
| `batch_size` | 否 | 12GB 用 1 |
| `use_random_seed` | 否 | `true` 随机 |
| `seed` | 否 | `-1` 随机，固定值可复现 |
| `bpm` | 否 | 整数 |
| `key_scale` | 否 | 如 `C Major` |

### 3. 轮询：`POST /query_result`

```json
{ "task_id_list": ["c48cd825-dcdf-4151-9b68-88399c756d44"] }
```

本机实测轮询过程：每 3 秒一次，`status` 从 `0` 到 `1` 用了约 30 秒。

状态含义：`0` 处理中，`1` 成功，`2` 失败。

成功时：

```json
{
  "data": [
    {
      "task_id": "c48cd825-dcdf-4151-9b68-88399c756d44",
      "result": "[{\"file\": \"/v1/audio?path=D%3A%5C...%5C9de0ca9e.mp3\", \"status\": 1, \"metas\": {\"bpm\": 92, \"duration\": 30.0, \"keyscale\": \"C Major\", \"timesignature\": \"4\", ...}, \"generation_info\": \"Total generation time: 24.54s ...\", \"seed_value\": \"3826483317\", \"lm_model\": \"acestep-5Hz-lm-1.7B\", \"dit_model\": \"acestep-v15-turbo\", \"progress\": 1.0, \"stage\": \"succeeded\"}]",
      "status": 1,
      "progress_text": "14:43:24 | DEBUG | [AudioSaver] Saved audio to ...mp3 (mp3, 48000Hz, 128k)"
    }
  ],
  "code": 200,
  "error": null,
  "timestamp": 1793947406112,
  "extra": null
}
```

**关键点：`data[0].result` 是 JSON 字符串，不是对象，必须再 `json.loads` 一次。**

解析后：

```json
[
  {
    "file": "/v1/audio?path=D%3A%5Cai%5Cai-composer%5Cmusic-gen%5CACE-Step-1.5%5C.cache%5Cacestep%5Ctmp%5Capi_audio%5C9de0ca9e-5661-5ffe-0ab5-f844b723c036.mp3",
    "wave": "",
    "status": 1,
    "create_time": 1793947375,
    "prompt": "温暖的中文民谣，木吉他分解和弦，男声，慢速，情绪真挚",
    "lyrics": "...",
    "metas": {
      "bpm": 92,
      "duration": 30.0,
      "genres": "N/A",
      "keyscale": "C Major",
      "timesignature": "4"
    },
    "generation_info": "Total generation time (1 song): 24.54s\n- LM phase: 21.52s\n- DiT phase: 3.02s",
    "seed_value": "3826483317",
    "lm_model": "acestep-5Hz-lm-1.7B",
    "dit_model": "acestep-v15-turbo",
    "progress": 1.0,
    "stage": "succeeded"
  }
]
```

### 4. 取回音频：`GET /v1/audio?path=...`

把 `file` 字段原样拼到 API 地址后面：

```powershell
curl.exe -o "d:\ai\ai-composer\music-gen\outputs\api_demo.mp3" "http://127.0.0.1:8001/v1/audio?path=D%3A%5Cai%5Cai-composer%5Cmusic-gen%5CACE-Step-1.5%5C.cache%5Cacestep%5Ctmp%5Capi_audio%5C9de0ca9e-5661-5ffe-0ab5-f844b723c036.mp3"
```

本机实测：文件 480812 字节，`ffprobe` 时长 30.000 秒，48kHz 双声道 MP3。

### 5. 完整可执行脚本（Python，最稳）

```python
import json, time, urllib.request

API = "http://127.0.0.1:8001"
lyrics = open(r"d:\ai\ai-composer\music-gen\outputs\lyrics_demo.txt", encoding="utf-8-sig").read()

payload = {
    "prompt": "温暖的中文民谣，木吉他分解和弦，男声，慢速，情绪真挚",
    "lyrics": lyrics,
    "vocal_language": "zh",
    "audio_duration": 30,
    "audio_format": "mp3",
    "thinking": True,
    "inference_steps": 8,
    "batch_size": 1,
    "use_random_seed": True,
    "seed": -1,
}

req = urllib.request.Request(
    API + "/release_task",
    data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
    method="POST",
)
req.add_header("Content-Type", "application/json")
sub = json.loads(urllib.request.urlopen(req).read())
task_id = sub["data"]["task_id"]

while True:
    time.sleep(3)
    req = urllib.request.Request(
        API + "/query_result",
        data=json.dumps({"task_id_list": [task_id]}).encode("utf-8"),
        method="POST",
    )
    req.add_header("Content-Type", "application/json")
    q = json.loads(urllib.request.urlopen(req).read())
    row = q["data"][0]
    if row["status"] == 1:
        result = json.loads(row["result"])
        url = API + result[0]["file"]
        audio = urllib.request.urlopen(url).read()
        open(r"d:\ai\ai-composer\music-gen\outputs\api_demo.mp3", "wb").write(audio)
        print("saved", len(audio), "bytes")
        break
    if row["status"] == 2:
        raise RuntimeError(row)
```

也可以直接用项目里的薄封装：

```powershell
& "$env:USERPROFILE\miniconda3\envs\music-gen\python.exe" "d:\ai\ai-composer\music-gen\music_gen.py" `
  --api http://127.0.0.1:8001 generate `
  --prompt "温暖的中文民谣，木吉他分解和弦，男声，慢速，情绪真挚" `
  --lyrics-file "d:\ai\ai-composer\music-gen\outputs\lyrics_demo.txt" `
  --language zh --duration 30 --steps 8 --thinking `
  --out "d:\ai\ai-composer\music-gen\outputs"
```

注意 `--api` 是**全局参数，必须写在 `generate` 前面**；写到后面会报 `unrecognized arguments`。

### 6. 认证（可选）

启动时加 `-ApiKey "你的key"`，之后每个请求带：

```text
Authorization: Bearer 你的key
```

### 7. 实测性能（RTX 3060 12GB）

| 场景 | 时长 | 耗时 | 显存峰值 |
| :-- | :-- | :-- | :-- |
| 首次 0.6B LM | 60s | 324s | 7694 MiB |
| 首次 1.7B LM | 30s | 241s | 11049 MiB |
| 热启动 1.7B，30s | 30s | 28.1s | 11263 MiB |
| 热启动 1.7B，60s | 60s | 38.8s | 11263 MiB |
| 本次 API 实测 30s（服务已热） | 30s | 30.3s 墙钟 / 24.54s 生成 | - |
| API 重启后首个请求（模型懒加载） | 30s | 340.9s 墙钟（含加载 DiT + 1.7B LM） | 7930 MiB 待机 |

> 实测：`/health` 在模型未加载时也会返回 `ok`（`models_initialized=false`），
> **模型是在第一次 `/release_task` 时才真正加载**。所以重启 API 后先发一个小任务预热，
> 之后的请求才是 30 秒级。

---

## 五、常见报错

| 现象 | 原因 | 处理 |
| :-- | :-- | :-- |
| `conda` 不是命令 | conda 未进 PATH | 全程用完整路径 `$env:USERPROFILE\miniconda3\...\python.exe`；脚本已内置 |
| 端口没监听 | 服务没起来或崩了 | 看 `scripts` 启动窗口的报错；`Get-NetTCPConnection -LocalPort 7860` 检查 |
| CUDA out of memory | UI/API 同时在生成，或 batch 太大 | 只保留一个服务生成；`批量大小=1` |
| 生成没有人声 | 纯音乐勾选 / 语言 unknown / 歌词空 | 取消“纯音乐”；语言选 `zh`；填歌词 |
| 中文被转成拼音 | 点了“格式化/增强歌词” | 不要点；填原文重新生成 |
| 下载失败/找不到模型 | 模型目录被移动 | 模型必须在 `ACE-Step-1.5\checkpoints`；运行 `scripts\start_ui.ps1` 会检查 |
| `Unexpected token ')'` | PowerShell 5.1 读无 BOM 中文脚本 | 脚本已保存为 UTF-8 with BOM；不要用记事本另存为 UTF-8 |
| ffmpeg 报错 | 系统 ffmpeg 2.8.4 过旧 | 启动脚本已把 `tools\ffmpeg\bin` 前置到 PATH |

---

## 六、生成前先润色歌词（可选）

项目里带了一个歌词润色工具，能查韵脚、破韵、重字、句长，并可用本地 Qwen3 或外部 LLM 改写：

```powershell
# 只诊断
& "$env:USERPROFILE\miniconda3\envs\music-gen\python.exe" "d:\ai\ai-composer\music-gen\lyrics_polish.py" analyze `
  --lyrics-file "d:\ai\ai-composer\music-gen\outputs\lyrics_demo.txt"

# 润色（本地 Qwen3-4B，需先下载；或 --backend openai）
& "$env:USERPROFILE\miniconda3\envs\music-gen\python.exe" "d:\ai\ai-composer\music-gen\lyrics_polish.py" polish `
  --lyrics-file "d:\ai\ai-composer\music-gen\outputs\lyrics_demo.txt" `
  --style "温暖的中文民谣" --voice "男声，偏低沉" --backend local
```

输出：

- `outputs\lyrics_polished.txt`：润色后可演唱版
- `outputs\lyrics_report.md`：韵脚表、问题清单、改动说明、前后对比

详细用法见 `README.md` 的“歌词润色”一节。
