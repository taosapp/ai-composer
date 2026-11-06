"""ACE-Step 1.5 异步 REST API 的薄封装。

用法示例：
    python music_gen.py health
    python music_gen.py generate --prompt "温暖的中文流行歌" --lyrics-file lyrics.txt \
        --duration 60 --language zh --out outputs/demo.mp3

只依赖 Python 标准库，供脚本 / 前端直接调用官方 acestep-api。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


DEFAULT_API = os.environ.get("ACESTEP_API_URL", "http://127.0.0.1:8001")


def _request_json(method: str, url: str, payload: dict | None = None,
                  api_key: str | None = None, timeout: int = 60) -> dict:
    """发送 JSON 请求并返回统一响应体中的 data 字段。"""
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Content-Type", "application/json")
    if api_key:
        req.add_header("Authorization", f"Bearer {api_key}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"HTTP {exc.code} 调用 {url} 失败：{detail}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"无法连接 {url}，请确认 API 已启动：{exc.reason}") from exc

    data = json.loads(raw)
    if data.get("code") != 200:
        raise SystemExit(f"API 返回错误：{data.get('error') or data}")
    return data.get("data")


def cmd_health(args: argparse.Namespace) -> None:
    data = _request_json("GET", f"{args.api}/health", api_key=args.api_key)
    print(json.dumps(data, ensure_ascii=False, indent=2))


def cmd_models(args: argparse.Namespace) -> None:
    req = urllib.request.Request(f"{args.api}/v1/models")
    if args.api_key:
        req.add_header("Authorization", f"Bearer {args.api_key}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    print(json.dumps(data, ensure_ascii=False, indent=2))


def cmd_generate(args: argparse.Namespace) -> None:
    lyrics = args.lyrics
    if args.lyrics_file:
        lyrics = Path(args.lyrics_file).read_text(encoding="utf-8-sig")

    payload = {
        "prompt": args.prompt,
        "lyrics": lyrics,
        "vocal_language": args.language,
        "audio_duration": args.duration,
        "audio_format": args.format,
        "thinking": args.thinking,
        "inference_steps": args.steps,
        "batch_size": args.batch,
        "use_random_seed": args.seed < 0,
        "seed": args.seed,
    }
    if args.bpm is not None:
        payload["bpm"] = args.bpm
    if args.key_scale:
        payload["key_scale"] = args.key_scale
    if args.model:
        payload["model"] = args.model

    submitted = _request_json("POST", f"{args.api}/release_task", payload, args.api_key)
    task_id = submitted["task_id"]
    print(f"[submit] task_id={task_id} status={submitted.get('status')}")

    started = time.time()
    while True:
        if time.time() - started > args.timeout:
            raise SystemExit(f"任务 {task_id} 超过 {args.timeout}s 仍未完成")
        time.sleep(args.poll)

        rows = _request_json("POST", f"{args.api}/query_result",
                             {"task_id_list": [task_id]}, args.api_key)
        row = rows[0] if isinstance(rows, list) and rows else {}
        status = row.get("status")
        if status == 2:
            raise SystemExit(f"任务失败：{row}")
        if status != 1:
            print(f"[wait] {time.time() - started:.0f}s status={status}")
            continue

        results = json.loads(row["result"]) if isinstance(row.get("result"), str) else row["result"]
        out_dir = Path(args.out)
        if out_dir.suffix:
            out_dir.parent.mkdir(parents=True, exist_ok=True)
        else:
            out_dir.mkdir(parents=True, exist_ok=True)

        saved = []
        for index, item in enumerate(results):
            file_url = item["file"]
            if out_dir.suffix:
                target = out_dir if len(results) == 1 else out_dir.with_name(
                    f"{out_dir.stem}_{index}{out_dir.suffix}")
            else:
                target = out_dir / f"{task_id}_{index}.{args.format}"
            download_url = file_url if file_url.startswith("http") else args.api + file_url
            req = urllib.request.Request(download_url)
            if args.api_key:
                req.add_header("Authorization", f"Bearer {args.api_key}")
            with urllib.request.urlopen(req, timeout=120) as resp:
                target.write_bytes(resp.read())

            meta = {
                "path": str(target.resolve()),
                "seed": item.get("seed_value"),
                "dit_model": item.get("dit_model"),
                "lm_model": item.get("lm_model"),
                "metas": item.get("metas"),
            }
            saved.append(meta)
            print(f"[done] {meta['path']}")

        summary = {
            "task_id": task_id,
            "elapsed_seconds": round(time.time() - started, 1),
            "audios": saved,
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ACE-Step 1.5 生成封装")
    parser.add_argument("--api", default=DEFAULT_API, help="acestep-api 地址")
    parser.add_argument("--api-key", default=os.environ.get("ACESTEP_API_KEY"),
                        help="可选 API Key")

    sub = parser.add_subparsers(dest="command", required=True)

    health = sub.add_parser("health", help="健康检查")
    health.set_defaults(func=cmd_health)

    models = sub.add_parser("models", help="列出可用 DiT 模型")
    models.set_defaults(func=cmd_models)

    gen = sub.add_parser("generate", help="提交生成任务并下载结果")
    gen.add_argument("--prompt", required=True, help="音乐风格 / 描述")
    gen.add_argument("--lyrics", default="", help="歌词文本，支持 [Verse] 等段落标记")
    gen.add_argument("--lyrics-file", default=None, help="从 UTF-8 文件读取歌词")
    gen.add_argument("--language", default="zh", help="歌词语言，中文用 zh")
    gen.add_argument("--duration", type=float, default=60, help="时长（秒，10-600）")
    gen.add_argument("--format", default="mp3", choices=["mp3", "wav", "flac"])
    gen.add_argument("--steps", type=int, default=8,
                     help="turbo 推荐 8，sft/base 推荐 32-64")
    gen.add_argument("--batch", type=int, default=1, help="一次生成数量（1-8）")
    gen.add_argument("--seed", type=int, default=-1, help="固定种子，-1 表示随机")
    gen.add_argument("--bpm", type=int, default=None)
    gen.add_argument("--key-scale", default="", help="例如 C Major / Am")
    gen.add_argument("--model", default=None, help="指定 DiT 模型，例如 acestep-v15-turbo")
    gen.add_argument("--thinking", action="store_true",
                     help="启用 5Hz LM 生成音频代码（更慢，需要 LM 已加载）")
    gen.add_argument("--out", required=True, help="输出文件或目录")
    gen.add_argument("--poll", type=float, default=2.0, help="轮询间隔（秒）")
    gen.add_argument("--timeout", type=int, default=900, help="整体超时（秒）")
    gen.set_defaults(func=cmd_generate)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
