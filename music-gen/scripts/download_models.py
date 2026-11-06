"""使用项目自带的下载逻辑，优先走 HuggingFace 镜像，失败自动回退 ModelScope。"""

import os
import sys
from pathlib import Path

from acestep.model_downloader import download_main_model, download_submodel


def main() -> int:
    models_dir = Path(os.environ["ACESTEP_CHECKPOINTS_DIR"])
    prefer = os.environ.get("ACESTEP_DOWNLOAD_SOURCE", "huggingface").lower()
    models_dir.mkdir(parents=True, exist_ok=True)

    print(f"[download] 目标目录: {models_dir}")
    print(f"[download] 首选源: {prefer} (HF_ENDPOINT={os.environ.get('HF_ENDPOINT')})")

    ok, msg = download_main_model(models_dir, prefer_source=prefer)
    print(msg)
    if not ok:
        return 1

    if "--with-sft" in sys.argv:
        print("[download] 追加下载 acestep-v15-sft ...")
        ok, msg = download_submodel("acestep-v15-sft", models_dir, prefer_source=prefer)
        print(msg)
        if not ok:
            return 1

    print("[download] 完成")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
