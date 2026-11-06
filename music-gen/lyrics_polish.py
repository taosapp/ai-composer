"""中文歌词润色工具：韵脚分析、演唱排版、可选本地/外部 LLM 改写。

用法：
    python lyrics_polish.py analyze --lyrics-file outputs/lyrics_demo.txt
    python lyrics_polish.py polish  --lyrics-file outputs/lyrics_demo.txt \
        --style "温暖的中文民谣" --voice "男声，偏低沉" \
        --backend auto --out outputs/lyrics_polished.txt --report outputs/lyrics_report.md

后端：
    rule   - 纯本地规则：统一段落标签、去行末标点、超长句断句、韵脚/重字/句长诊断（不改词）。
    local  - 本机 Qwen3-1.7B-Instruct（需先下载到 models/polish-llm/Qwen3-1.7B）。
    openai - 任意 OpenAI 兼容 /chat/completions 服务，配置见环境变量说明。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from pypinyin import Style, lazy_pinyin

PROJECT_ROOT = Path(__file__).resolve().parent
MODEL_CANDIDATES = [
    PROJECT_ROOT / "models" / "polish-llm" / "Qwen3-4B",
    PROJECT_ROOT / "models" / "polish-llm" / "Qwen3-1.7B",
]
DEFAULT_MODEL_DIR = MODEL_CANDIDATES[0]
DEFAULT_OUT = PROJECT_ROOT / "outputs" / "lyrics_polished.txt"
DEFAULT_REPORT = PROJECT_ROOT / "outputs" / "lyrics_report.md"

LRC_RE = re.compile(r"^\[(\d{1,2}):(\d{2})(?:[.:](\d{2,3}))?\]")
TAG_RE = re.compile(r"^\[[^\d][^\]]{0,30}\]$")

# 近韵组：同一组内视为可押（流行歌常见处理）
RHYME_GROUPS: dict[str, set[str]] = {
    "ai": {"ai", "uai"},
    "ei": {"ei", "ui", "uei"},
    "ao": {"ao", "iao"},
    "ou": {"ou", "iu", "iou"},
    "an": {"an", "ian", "uan", "van"},
    "en": {"en", "in", "uen", "un", "vn"},
    "ang": {"ang", "iang", "uang"},
    "eng": {"eng", "ing"},
    "ong": {"ong", "iong"},
    "i": {"i", "v"},
    "u": {"u"},
    "e": {"e", "o", "uo"},
    "er": {"er"},
}
FINAL_TO_GROUP = {final: group for group, finals in RHYME_GROUPS.items() for final in finals}

TAG_MAP = {
    "第一段": "Verse 1", "第二段": "Verse 2", "第三段": "Verse 3",
    "主歌": "Verse", "主歌一": "Verse 1", "主歌1": "Verse 1",
    "主歌二": "Verse 2", "主歌2": "Verse 2", "主歌三": "Verse 3", "主歌3": "Verse 3",
    "副歌": "Chorus", "合唱": "Chorus", "副歌一": "Chorus 1", "副歌1": "Chorus 1",
    "桥段": "Bridge", "桥": "Bridge", "预副歌": "Pre-Chorus",
    "前奏": "Intro", "间奏": "Interlude", "尾奏": "Outro", "尾声": "Outro",
}

# 句尾可选词库（规则后端只给建议，不擅自替换，避免破坏原意）
RHYME_BANK: dict[str, list[str]] = {
    "ai": ["回来", "未来", "期待", "明白", "开怀", "窗台", "等待", "离开"],
    "ei": ["回忆", "自己", "美丽", "委屈", "梦里", "眼泪", "为谁", "体会"],
    "ao": ["微笑", "拥抱", "心跳", "骄傲", "寻找", "到老", "街角", "燃烧"],
    "ou": ["温柔", "以后", "回头", "等候", "左右", "自由", "接受", "停留"],
    "an": ["遗憾", "答案", "晚安", "温暖", "缓慢", "孤单", "勇敢", "判断"],
    "en": ["认真", "沉默", "简单", "身边", "眼前", "从前", "渐渐", "思念"],
    "ang": ["时光", "模样", "远方", "原谅", "成长", "收藏", "歌唱", "流浪"],
    "eng": ["风景", "心情", "安静", "相信", "决定", "清醒", "曾经", "约定"],
    "ong": ["星空", "冲动", "从容", "重逢", "听懂", "普通", "夜空", "相拥"],
    "i": ["回忆", "自己", "秘密", "意义", "勇气", "足迹", "旋律", "四季"],
    "u": ["故事", "孤独", "付出", "祝福", "旅途", "幸福", "当初", "落幕"],
    "e": ["情歌", "快乐", "值得", "舍得", "寂寞", "颜色", "深刻", "忐忑"],
    "er": ["而已", "偶尔", "女儿", "这儿", "那儿"],
}

PHRASE_HINTS: dict[str, list[str]] = {
    "ai": ["还在等待", "无法忘怀", "慢慢走回来", "窗台之外", "别再离开"],
    "ei": ["留在梦里", "还是很美", "流下眼泪", "慢慢体会"],
    "ao": ["还在微笑", "简单美好", "一起到老", "城市热闹", "别太计较"],
    "ou": ["走到最后", "别无所求", "在你左右", "很久以后", "不会回头"],
    "an": ["慢慢靠近", "留在身边", "说声晚安", "不再遗憾", "勇敢一点"],
    "en": ["留在心间", "说着从前", "认真一点", "不再思念"],
    "ang": ["你的模样", "去往远方", "慢慢成长", "别来无恙", "放在心房"],
    "eng": ["这一场梦", "明天的风", "夜里的风", "心里的梦", "唱给你听"],
    "ong": ["这片星空", "在你眼中", "慢慢相拥", "做完这场梦"],
    "i": ["都是回忆", "写进旋律", "给我勇气", "留在四季"],
    "u": ["讲个故事", "学会孤独", "得到祝福", "走过旅途"],
    "e": ["简单快乐", "真的值得", "不要难过", "学会舍得"],
    "er": ["只是偶尔", "就到这里", "别太在意"],
}

SYSTEM_PROMPT = """你是一位中文歌词润色师，只为“可演唱性”做修改。
硬性要求：
1. 保留原意、叙事顺序和段落结构，不新增故事，不删核心意象。
2. 每个段落内部统一韵脚：同段句尾押同一韵组（允许 eng/ing、an/ian、ao/iao 等近韵）。
3. 每行 6-12 个汉字，方便换气；过长必须断句，过短可合并或补足。
4. 消除连续重复字、无意义语气词和口水词；保留有意的叠词。
5. 段落标签只用 [Verse 1]、[Chorus]、[Bridge]、[Pre-Chorus]、[Outro]。
6. 不要输出 LRC 时间戳，不要解释创作过程。
输出严格 JSON：
{"lyrics": "完整歌词，段落之间空一行", "changes": ["每处改动一句说明"]}
"""


@dataclass
class LineInfo:
    text: str
    chars: int
    final: str
    group: str
    no: int
    issues: list[str] = field(default_factory=list)


@dataclass
class SectionInfo:
    tag: str
    lines: list[LineInfo]
    dominant: str = ""
    dominant_finals: list[str] = field(default_factory=list)
    median: int = 0


def last_final(text: str) -> str:
    """返回一行最后一个汉字的韵母（无声调）；没有汉字则返回空串。"""
    chinese = [ch for ch in text if "\u4e00" <= ch <= "\u9fff"]
    if not chinese:
        return ""
    result = lazy_pinyin(chinese[-1], style=Style.FINALS, errors="ignore")
    return result[0] if result else ""


def rhyme_group(final: str) -> str:
    return FINAL_TO_GROUP.get(final, final)


def canonical_tag(tag: str) -> str:
    raw = tag.strip()
    if raw in TAG_MAP:
        return TAG_MAP[raw]
    lowered = raw.lower().replace("_", " ").strip()
    english = {
        "verse": "Verse", "chorus": "Chorus", "bridge": "Bridge",
        "intro": "Intro", "outro": "Outro", "interlude": "Interlude",
        "pre-chorus": "Pre-Chorus", "prechorus": "Pre-Chorus", "hook": "Hook",
    }
    match = re.match(r"([^\d]+?)\s*(\d+)?$", lowered)
    if match:
        base = match.group(1).strip().rstrip("0123456789 ")
        number = match.group(2)
        if base in english:
            return english[base] + (f" {number}" if number else "")
    return raw


def parse_lyrics(text: str) -> tuple[list[tuple[str, list[str]]], list[str]]:
    """把歌词拆成 (标签, 内容行) 列表，同时返回输入侧警告。"""
    sections: list[tuple[str, list[str]]] = []
    warnings: list[str] = []
    current_tag = "Verse 1"
    current_lines: list[str] = []
    has_tag = False

    for raw_line in text.replace("\r\n", "\n").split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        lrc = LRC_RE.match(line)
        if lrc:
            line = LRC_RE.sub("", line).strip()
            if line:
                warnings.append("歌词里含 LRC 时间戳，已移除；LRC 由生成后的“自动 LRC/获取 LRC”产出")
        if not line:
            continue
        if TAG_RE.match(line):
            if current_lines:
                sections.append((current_tag, current_lines))
                current_lines = []
            current_tag = canonical_tag(line[1:-1])
            has_tag = True
            continue
        current_lines.append(line)

    if current_lines:
        sections.append((current_tag, current_lines))
    if not has_tag and sections:
        warnings.append("输入没有段落标签，已按 [Verse 1] 处理；建议补 [Verse 1]/[Chorus]")
    return sections, warnings


def analyze_sections(raw_sections: list[tuple[str, list[str]]]) -> list[SectionInfo]:
    result: list[SectionInfo] = []
    for tag, texts in raw_sections:
        infos = []
        for no, text in enumerate(texts, 1):
            final = last_final(text)
            infos.append(LineInfo(
                text=text,
                chars=len(re.findall(r"[\u4e00-\u9fff]", text)),
                final=final,
                group=rhyme_group(final) if final else "",
                no=no,
            ))
        section = SectionInfo(tag=tag, lines=infos)
        groups = Counter(info.group for info in infos if info.group)
        if groups:
            section.dominant = groups.most_common(1)[0][0]
            section.dominant_finals = sorted(RHYME_GROUPS.get(section.dominant, {section.dominant}))
        lengths = [info.chars for info in infos]
        section.median = sorted(lengths)[len(lengths) // 2] if lengths else 0
        result.append(section)
    return result


def flag_issues(sections: list[SectionInfo]) -> list[str]:
    problems: list[str] = []
    for section in sections:
        for info in section.lines:
            if info.chars == 0:
                info.issues.append("没有汉字")
            if info.chars > 12:
                info.issues.append(f"句长 {info.chars} 字，偏长（建议 6-12）")
            elif info.chars < 4:
                info.issues.append(f"句长 {info.chars} 字，偏短")
            if info.group and section.dominant and info.group != section.dominant:
                info.issues.append(f"破韵：韵组 {info.group} 不在本节主韵 {section.dominant}")
            repeated = re.findall(r"(.)\1+", info.text)
            if repeated:
                info.issues.append("连续重复字：" + "、".join(repeated))
            abab = re.findall(r"([\u4e00-\u9fff]{2})\1", info.text)
            if abab:
                info.issues.append("连续重复词：" + "、".join(abab))
            if info.issues:
                problems.append(f"[{section.tag}] 第{info.no}句「{info.text}」：" + "；".join(info.issues))

        endings = Counter(info.text[-1] for info in section.lines if info.text)
        for char, count in endings.items():
            if count >= 3:
                problems.append(f"[{section.tag}] 句尾同字「{char}」出现 {count} 次，注意单调")
        duplicates = [t for t, c in Counter(info.text for info in section.lines).items() if c > 1]
        for text in duplicates:
            problems.append(f"[{section.tag}] 整行重复：{text}")
    return problems


def rule_polish(raw_sections: list[tuple[str, list[str]]]) -> tuple[list[tuple[str, list[str]]], list[str]]:
    """规则后端：只做不改原意的排版整理，返回 (新段落, 改动说明)。"""
    changes: list[str] = []
    polished: list[tuple[str, list[str]]] = []
    for tag, texts in raw_sections:
        new_tag = canonical_tag(tag)
        if new_tag != tag:
            changes.append(f"段落标签 [{tag}] → [{new_tag}]")
        lines: list[str] = []
        for text in texts:
            original = text
            text = text.strip()
            stripped = re.sub(r"[，。！？；、,.!?;]+$", "", text).strip()
            if stripped != text:
                changes.append(f"去行末标点：「{text}」→「{stripped}」")
                text = stripped
            chars = len(re.findall(r"[\u4e00-\u9fff]", text))
            if chars > 12 and re.search(r"[，、；;]", text):
                parts = [p.strip() for p in re.split(r"[，、；;]", text) if p.strip()]
                if len(parts) > 1 and all(len(re.findall(r"[\u4e00-\u9fff]", p)) >= 3 for p in parts):
                    lines.extend(parts)
                    changes.append(f"超长句断句：「{text}」→「{'」/「'.join(parts)}」")
                    continue
            if chars > 12:
                changes.append(f"超长句未断（无标点可切）：{text}，建议手动断句")
            lines.append(text)
        polished.append((new_tag, lines))
    return polished, changes


def _join_sections(sections: Iterable[tuple[str, list[str]]]) -> str:
    blocks = []
    for tag, lines in sections:
        blocks.append(f"[{tag}]\n" + "\n".join(lines))
    return "\n\n".join(blocks) + "\n"


def _analysis_json(sections: list[SectionInfo], problems: list[str], warnings: list[str]) -> dict:
    return {
        "sections": [
            {
                "tag": section.tag,
                "dominant_rhyme_group": section.dominant,
                "dominant_finals": section.dominant_finals,
                "median_line_chars": section.median,
                "lines": [
                    {
                        "no": info.no,
                        "text": info.text,
                        "chars": info.chars,
                        "final": info.final,
                        "group": info.group,
                        "issues": info.issues,
                    }
                    for info in section.lines
                ],
            }
            for section in sections
        ],
        "problems": problems,
        "warnings": warnings,
    }


def _rhyme_table(sections: list[SectionInfo]) -> str:
    rows = [
        "| 段落 | 句 | 歌词 | 字数 | 韵母 | 韵组 | 状态 |",
        "| :-- | :-- | :-- | :-- | :-- | :-- | :-- |",
    ]
    for section in sections:
        for info in section.lines:
            status = "✅" if not info.issues else "⚠️ " + "；".join(info.issues)
            rows.append(
                f"| {section.tag} | {info.no} | {info.text} | {info.chars} | "
                f"{info.final or '-'} | {info.group or '-'} | {status} |"
            )
    return "\n".join(rows)


def _suggestions(sections: list[SectionInfo]) -> list[str]:
    tips = []
    for section in sections:
        bank = RHYME_BANK.get(section.dominant, [])
        if bank:
            tips.append(
                f"[{section.tag}] 主韵 **{section.dominant}**（{', '.join(section.dominant_finals)}），"
                f"句尾可考虑：{' / '.join(bank[:6])}"
            )
    return tips


def build_report(
    source_text: str,
    polished_text: str,
    sections: list[SectionInfo],
    problems: list[str],
    warnings: list[str],
    changes: list[str],
    backend: str,
    style: str,
    voice: str,
) -> str:
    lines = [
        "# 歌词润色报告",
        "",
        f"- 曲风：{style or '未填写'}",
        f"- 演唱偏好：{voice or '未填写'}",
        f"- 后端：{backend}",
        f"- 输入警告：{'；'.join(warnings) if warnings else '无'}",
        "",
        "## 1. 韵脚表",
        "",
        _rhyme_table(sections),
        "",
        "## 2. 问题清单",
        "",
    ]
    lines.extend(f"- {item}" for item in problems) if problems else lines.append("- 未发现明显问题")
    lines.extend(["", "## 3. 韵脚建议", ""])
    suggestions = _suggestions(sections)
    lines.extend(f"- {item}" for item in suggestions) if suggestions else lines.append("- 无")
    lines.extend(["", "## 4. 改动说明", ""])
    lines.extend(f"- {item}" for item in changes) if changes else lines.append("- 无文字改动（规则后端只做排版）")
    lines.extend([
        "",
        "## 5. 原词",
        "",
        "```text",
        source_text.strip(),
        "```",
        "",
        "## 6. 润色后（可演唱版）",
        "",
        "```text",
        polished_text.strip(),
        "```",
        "",
    ])
    return "\n".join(lines)


def _read_lyrics(path: str | None, inline: str | None) -> str:
    if inline:
        return inline
    if not path:
        raise SystemExit("请用 --lyrics-file 或 --lyrics 提供歌词")
    return Path(path).read_text(encoding="utf-8-sig")


def _chat_completion(base_url: str, api_key: str, model: str, messages: list[dict], timeout: int = 180) -> str:
    url = base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.7,
        "top_p": 0.9,
        "max_tokens": 2000,
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    if api_key:
        req.add_header("Authorization", f"Bearer {api_key}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"LLM 接口 HTTP {exc.code}：{detail}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"无法连接 LLM 接口 {url}：{exc.reason}") from exc
    return data["choices"][0]["message"]["content"]


def _extract_json(text: str) -> dict | None:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                return None
    return None


def _polish_with_openai(lyrics: str, style: str, voice: str, args: argparse.Namespace) -> tuple[str, list[str]]:
    base_url = args.base_url or os.environ.get("ACESTEP_POLISH_BASE_URL", "")
    api_key = args.api_key or os.environ.get("ACESTEP_POLISH_API_KEY", "")
    model = args.model or os.environ.get("ACESTEP_POLISH_MODEL", "")
    if not base_url or not model:
        raise SystemExit(
            "外部 LLM 未配置。请设置：\n"
            "  $env:ACESTEP_POLISH_BASE_URL = \"https://api.deepseek.com/v1\"\n"
            "  $env:ACESTEP_POLISH_API_KEY  = \"sk-...\"\n"
            "  $env:ACESTEP_POLISH_MODEL    = \"deepseek-chat\"\n"
            "或改用 --backend local（需先下载 Qwen3-1.7B）或 --backend rule"
        )
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"曲风：{style or '未指定'}\n演唱偏好：{voice or '未指定'}\n\n原歌词：\n{lyrics}"},
    ]
    reply = _chat_completion(base_url, api_key, model, messages)
    parsed = _extract_json(reply)
    if not parsed or "lyrics" not in parsed:
        raise SystemExit(f"LLM 返回无法解析为 JSON，原始回复：\n{reply[:800]}")
    changes = [str(item) for item in parsed.get("changes", [])]
    return str(parsed["lyrics"]).strip(), changes


def _pick_model_dir(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit)
    for candidate in MODEL_CANDIDATES:
        if (candidate / "config.json").exists() and not list(candidate.glob("*.incomplete")):
            return candidate
    return DEFAULT_MODEL_DIR


def _needs_rewrite(section: SectionInfo) -> bool:
    if not section.dominant:
        return False
    for info in section.lines:
        if info.chars > 12 or info.chars < 4:
            return True
        if info.group and info.group != section.dominant:
            return True
    return False


def _line_prompt(
    lines: list[str],
    idx: int,
    target: str,
    section: SectionInfo,
    style: str,
    voice: str,
) -> str:
    no = idx + 1
    original = lines[idx]
    origin_last = original[-1]
    finals = "、".join(section.dominant_finals)
    chars = "、".join(RHYME_BANK.get(target, [])[:8]) or "同韵常用字"
    phrases = "、".join(PHRASE_HINTS.get(target, [])[:5]) or "同韵短语"
    context = "\n".join(f"{i+1}. {line}" for i, line in enumerate(lines))
    return (
        f"下面是中文歌词的一段，共 {len(lines)} 行。第 {no} 行句尾「{origin_last}」不押 {target} 韵，其他行已经押韵。\n"
        f"请只改写第 {no} 行，其他行必须原样保留。\n"
        f"段落：{section.tag}；曲风：{style or '未指定'}；演唱偏好：{voice or '未指定'}。\n"
        f"第 {no} 行硬性要求：\n"
        f"- 句尾必须押 {target} 韵（可用韵母：{finals}；可结尾字：{chars}）。\n"
        f"- 原句尾字「{origin_last}」不押 {target}，改写后句尾不能再是「{origin_last}」。\n"
        "- 整行 6-12 个汉字；保留原意，自然通顺，像正常歌词，不要生造词。\n"
        f"- 可以参考这些句尾短语：{phrases}。\n"
        "不要编号、不要解释、不要合并句子。\n\n"
        f"原歌词：\n{context}\n改写后："
    )


def _parse_reply_lines(reply: str) -> list[str]:
    lines: list[str] = []
    for raw in reply.replace("\r\n", "\n").split("\n"):
        line = raw.strip()
        if not line:
            continue
        line = re.sub(r"^\s*(?:\d+[.、)）]|[-*•])\s*", "", line)
        line = re.sub(r"[，。！？；、,.!?;]+$", "", line).strip()
        if re.search(r"[\u4e00-\u9fff]", line):
            lines.append(line)
    return lines


def _pick_rewrite(reply: str, original: str, idx: int, total: int, target: str, banned: str,
                  neighbour_endings: set[str]) -> str | None:
    candidates = _parse_reply_lines(reply)
    if not candidates:
        return None
    if len(candidates) >= total:
        candidates = [candidates[idx]]
    elif len(candidates) != 1:
        return None

    best, best_score = None, None
    for cand in candidates:
        chars = len(re.findall(r"[\u4e00-\u9fff]", cand))
        final = last_final(cand)
        if not final or rhyme_group(final) != target:
            continue
        if cand[-1] == banned or chars < 5 or chars > 13:
            continue
        prefix = 0
        for a, b in zip(original, cand):
            if a != b:
                break
            prefix += 1
        score = prefix * 2 - abs(chars - 8)
        if cand[-1] in neighbour_endings:
            score -= 3
        if best_score is None or score > best_score:
            best, best_score = cand, score
    return best


def _polish_with_local(lyrics: str, style: str, voice: str, args: argparse.Namespace) -> tuple[str, list[str]]:
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    model_dir = _pick_model_dir(args.model_dir)
    if not model_dir.exists():
        raise SystemExit(
            f"本地润色模型不存在：{model_dir}\n"
            "下载命令（ModelScope）：\n"
            "  python -c \"from modelscope import snapshot_download; "
            f"snapshot_download('Qwen/Qwen3-4B', local_dir=r'{MODEL_CANDIDATES[0]}')\"\n"
            "或改用 --backend openai / rule"
        )
    device = args.device
    if device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.bfloat16 if device == "cuda" else torch.float32
    print(f"[local] loading {model_dir.name} on {device} ...", file=sys.stderr)
    tokenizer = AutoTokenizer.from_pretrained(str(model_dir), trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(
        str(model_dir), dtype=dtype, device_map=device, trust_remote_code=True
    )
    model.eval()

    def generate(prompt: str, max_new_tokens: int, temperature: float = 0.75) -> str:
        messages = [{"role": "user", "content": prompt}]
        try:
            text = tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True, enable_thinking=False
            )
        except TypeError:
            text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = tokenizer(text, return_tensors="pt").to(device)
        with torch.no_grad():
            output = model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                do_sample=True,
                temperature=temperature,
                top_p=0.9,
                repetition_penalty=1.05,
            )
        return tokenizer.decode(output[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)

    raw_sections, _ = parse_lyrics(lyrics)
    polished: list[tuple[str, list[str]]] = []
    changes: list[str] = []
    cache: dict[tuple[str, ...], list[str]] = {}

    for tag, lines in raw_sections:
        key = tuple(lines)
        if key in cache:
            new_lines = list(cache[key])
        else:
            section = analyze_sections([(tag, lines)])[0]
            new_lines = list(lines)
            if _needs_rewrite(section):
                target = section.dominant
                for idx, info in enumerate(section.lines):
                    needs_fix = (
                        (info.group and info.group != target)
                        or info.chars > 12
                        or info.chars < 4
                    )
                    if not needs_fix:
                        continue
                    neighbours = {
                        line[-1] for j, line in enumerate(new_lines) if j != idx and line
                    }
                    best = None
                    banned = lines[idx][-1]
                    for attempt in range(8):
                        prompt = _line_prompt(new_lines, idx, target, section, style, voice)
                        if attempt >= 3:
                            prompt += (
                                f"\n加强要求：改写后的第{idx + 1}行不能出现原句尾字「{banned}」，"
                                "必须换一个自然的说法。\n改写后："
                            )
                        reply = generate(prompt, 120, temperature=0.7 + 0.04 * min(attempt, 5))
                        candidate = _pick_rewrite(
                            reply, new_lines[idx], idx, len(new_lines), target,
                            banned, neighbours,
                        )
                        if candidate:
                            best = candidate
                            break
                    if best:
                        new_lines[idx] = best
                    else:
                        changes.append(f"[{tag}] 第{idx + 1}行未能自动押韵，保留原句")
            cache[key] = new_lines

        for old, new in zip(lines, new_lines):
            if old != new:
                changes.append(f"[{tag}] 「{old}」→「{new}」")
        polished.append((tag, new_lines))

    return _join_sections(polished), list(dict.fromkeys(changes))


def cmd_analyze(args: argparse.Namespace) -> None:
    text = _read_lyrics(args.lyrics_file, args.lyrics)
    raw_sections, warnings = parse_lyrics(text)
    sections = analyze_sections(raw_sections)
    problems = flag_issues(sections)
    data = _analysis_json(sections, problems, warnings)
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return

    print("# 歌词韵脚分析\n")
    print(f"- 曲风：{args.style or '未填写'}；演唱偏好：{args.voice or '未填写'}")
    for warning in warnings:
        print(f"- ⚠️ {warning}")
    print("\n## 韵脚表\n")
    print(_rhyme_table(sections))
    print("\n## 问题\n")
    print("\n".join(f"- {item}" for item in problems) if problems else "- 未发现明显问题")
    print("\n## 韵脚建议\n")
    for tip in _suggestions(sections):
        print(f"- {tip}")


def cmd_polish(args: argparse.Namespace) -> None:
    text = _read_lyrics(args.lyrics_file, args.lyrics)
    raw_sections, warnings = parse_lyrics(text)

    backend = args.backend
    if backend == "auto":
        if Path(args.model_dir or DEFAULT_MODEL_DIR).exists():
            backend = "local"
        elif os.environ.get("ACESTEP_POLISH_BASE_URL"):
            backend = "openai"
        else:
            backend = "rule"
            print("[auto] 未发现本地润色模型，也未配置外部 LLM，退回 rule 排版模式", file=sys.stderr)

    changes: list[str] = []
    if backend == "rule":
        polished_sections, changes = rule_polish(raw_sections)
        polished_text = _join_sections(polished_sections)
    else:
        if backend == "local":
            polished_text, changes = _polish_with_local(text, args.style, args.voice, args)
        else:
            polished_text, changes = _polish_with_openai(text, args.style, args.voice, args)
        polished_sections, _ = parse_lyrics(polished_text)

    sections = analyze_sections(polished_sections)
    problems = flag_issues(sections)
    report = build_report(
        text, polished_text, sections, problems, warnings, changes,
        backend=backend, style=args.style, voice=args.voice,
    )

    out_path = Path(args.out or DEFAULT_OUT)
    report_path = Path(args.report or DEFAULT_REPORT)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(polished_text, encoding="utf-8")
    report_path.write_text(report, encoding="utf-8")

    print(f"[backend] {backend}")
    print(f"[lyrics ] {out_path}")
    print(f"[report ] {report_path}")
    print(f"[changes] {len(changes)}")
    for item in changes[:8]:
        print(f"  - {item}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="中文歌词润色：韵脚分析 / 演唱排版 / LLM 改写")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--lyrics-file", default=None, help="UTF-8 歌词文件")
        p.add_argument("--lyrics", default=None, help="直接传入歌词文本")
        p.add_argument("--style", default="", help="曲风，如：温暖的中文民谣")
        p.add_argument("--voice", default="", help="演唱偏好，如：男声、偏低沉、气声")

    analyze = sub.add_parser("analyze", help="只分析韵脚/重字/句长，不改词")
    add_common(analyze)
    analyze.add_argument("--json", action="store_true", help="输出 JSON")
    analyze.set_defaults(func=cmd_analyze)

    polish = sub.add_parser("polish", help="润色并输出可演唱版 + 报告")
    add_common(polish)
    polish.add_argument("--backend", default="auto", choices=["auto", "rule", "local", "openai"],
                        help="润色后端，默认 auto")
    polish.add_argument("--model-dir", default=None, help="本地 Qwen3 模型目录")
    polish.add_argument("--device", default="auto", choices=["auto", "cpu", "cuda"],
                        help="本地模型设备；API 占用显存时用 cpu")
    polish.add_argument("--base-url", default=None, help="OpenAI 兼容服务地址")
    polish.add_argument("--api-key", default=None, help="外部 LLM API Key")
    polish.add_argument("--model", default=None, help="外部 LLM 模型名，如 deepseek-chat")
    polish.add_argument("--out", default=None, help="润色后歌词输出路径")
    polish.add_argument("--report", default=None, help="报告输出路径")
    polish.set_defaults(func=cmd_polish)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
