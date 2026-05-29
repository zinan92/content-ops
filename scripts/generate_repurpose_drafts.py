#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import math
from datetime import datetime
from pathlib import Path


ROOT = Path("/Users/wendy")
OUT = ROOT / "park-io/outbox"
ASSETS = OUT / ".system/data/assets.json"
PLATFORMS = Path(__file__).resolve().parents[1] / "platforms.json"
TARGET_PLATFORMS = [
    "xiaohongshu",
    "wechat_mp",
    "wechat_channels",
    "x",
    "youtube",
    "bilibili",
    "zhihu",
]


def today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def slugify(value: str, fallback: str) -> str:
    value = value.lower()
    value = re.sub(r"#[^\s#]+", "", value)
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value[:48] or fallback


def hashtags(text: str) -> list[str]:
    tags = re.findall(r"#([A-Za-z0-9_\-\u4e00-\u9fff]+)", text or "")
    seen: set[str] = set()
    out: list[str] = []
    for tag in tags:
        if tag not in seen:
            seen.add(tag)
            out.append(tag)
    return out[:8]


def concise_title(asset: dict, limit: int = 28) -> str:
    title = (asset.get("title") or asset.get("description") or "").strip()
    title = re.sub(r"#[^\s#]+", "", title)
    title = re.sub(r"\s+", " ", title)
    return title[:limit].rstrip("，。,. ") or "未命名选题"


def count_for_platform(total_assets: int, ratio: float) -> int:
    return max(1, round(total_assets * ratio))


def transcript_text(asset: dict) -> str:
    transcript_json = asset.get("organized_transcript_json") or asset.get("transcript_json")
    if transcript_json and Path(transcript_json).exists():
        try:
            data = json.loads(Path(transcript_json).read_text(encoding="utf-8"))
            return clean_text(data.get("organized_text") or data.get("full_text") or "")
        except (json.JSONDecodeError, OSError):
            pass
    transcript_md = asset.get("organized_transcript_md") or asset.get("transcript_md")
    if transcript_md and Path(transcript_md).exists():
        try:
            text = Path(transcript_md).read_text(encoding="utf-8")
            text = re.sub(r"^# .+?$", "", text, flags=re.M)
            text = re.sub(r"^- .+?$", "", text, flags=re.M)
            text = re.sub(r"^## Transcript$", "", text, flags=re.M)
            text = re.sub(r"\[\d{2}:\d{2}\]\s*", "", text)
            return clean_text(text)
        except OSError:
            pass
    return clean_text(asset.get("description") or asset.get("title") or "")


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def read_json_path(path: str | None) -> dict:
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def raw_segments(asset: dict) -> list[dict]:
    data = read_json_path(asset.get("transcript_json"))
    return data.get("segments") or []


def chapter_rows(asset: dict) -> list[dict]:
    raw = asset.get("raw") or {}
    chapter_info = raw.get("recommend_chapter_info") or {}
    return chapter_info.get("recommend_chapter_list") or []


def segment_text_between(segments: list[dict], start_s: float, end_s: float | None) -> str:
    parts = []
    for seg in segments:
        seg_start = float(seg.get("start") or 0)
        if seg_start < start_s:
            continue
        if end_s is not None and seg_start >= end_s:
            continue
        text = clean_text(str(seg.get("text") or ""))
        if text:
            parts.append(text)
    return clean_text(" ".join(parts))


def chunk_text_by_chars(text: str, target_chars: int = 1800) -> list[str]:
    text = clean_text(text)
    if not text:
        return []
    pieces = re.split(r"[。！？!?]\\s*", text)
    if len(pieces) <= 1:
        pieces = re.split(r"(?=\\b(?:第一|第二|第三|第四|最后|所以|但是|比如说|我觉得|未来|AI|如果)\\b)", text)
    chunks: list[str] = []
    current = ""
    for piece in pieces:
        piece = clean_text(piece)
        if not piece:
            continue
        if current and len(current) + len(piece) > target_chars:
            chunks.append(current.strip())
            current = piece
        else:
            current = clean_text(f"{current} {piece}")
    if current:
        chunks.append(current.strip())
    return chunks


def xhs_units_for_asset(asset: dict) -> list[dict]:
    if asset.get("content_type") == "gallery" and not asset.get("transcript_json"):
        return [
            {
                "unit_title": concise_title(asset),
                "text": clean_text(asset.get("description") or asset.get("title") or ""),
                "start_s": None,
                "end_s": None,
                "points": [],
            }
        ]

    segments = raw_segments(asset)
    chapters = chapter_rows(asset)
    units: list[dict] = []
    if chapters and segments:
        useful = []
        for idx, chapter in enumerate(chapters):
            title = clean_text(str(chapter.get("desc") or ""))
            if title in {"引言"}:
                continue
            start_s = float(chapter.get("timestamp") or 0) / 1000
            next_ts = None
            if idx + 1 < len(chapters):
                next_ts = float(chapters[idx + 1].get("timestamp") or 0) / 1000
            text = segment_text_between(segments, start_s, next_ts)
            points = chapter.get("points") or []
            detail_text = clean_text(" ".join(clean_text(str(point.get("detail") or point.get("desc") or "")) for point in points))
            if len(text) < 260 and not detail_text:
                continue
            useful.append(
                {
                    "unit_title": title or concise_title(asset),
                    "text": text or detail_text,
                    "start_s": start_s,
                    "end_s": next_ts,
                    "points": points,
                }
            )
        if useful:
            return useful[:10]

    text = transcript_text(asset)
    chunks = chunk_text_by_chars(text, 2200)
    for idx, chunk in enumerate(chunks[:10], start=1):
        units.append(
            {
                "unit_title": f"{concise_title(asset, 18)} {idx}",
                "text": chunk,
                "start_s": None,
                "end_s": None,
                "points": [],
            }
        )
    return units or [
        {
            "unit_title": concise_title(asset),
            "text": clean_text(asset.get("description") or asset.get("title") or ""),
            "start_s": None,
            "end_s": None,
            "points": [],
        }
    ]


def xhs_count_for_asset(asset: dict) -> int:
    return len(xhs_units_for_asset(asset))


def selected_assets(assets: list[dict], platform: str, target: int) -> list[tuple[dict, int]]:
    if platform == "xiaohongshu":
        return [(asset, idx) for asset in assets for idx in range(1, xhs_count_for_asset(asset) + 1)]
    return [(asset, 1) for asset in assets[:target]]


def split_readable_lines(text: str, max_lines: int = 7) -> list[str]:
    text = clean_text(text)
    if not text:
        return []
    candidates = re.split(r"(?=\\b(?:我觉得|所以|但是|比如说|第一|第二|第三|如果|未来|AI|这件事|因为)\\b)", text)
    if len(candidates) <= 2:
        candidates = [text[i : i + 95] for i in range(0, len(text), 95)]
    lines = []
    for candidate in candidates:
        candidate = clean_text(candidate)
        if len(candidate) < 12:
            continue
        if len(candidate) > 120:
            candidate = candidate[:118].rstrip("，。,. ") + "。"
        else:
            candidate = candidate.rstrip("，。,. ") + "。"
        lines.append(candidate)
        if len(lines) >= max_lines:
            break
    return lines


def xhs_title_from_unit(unit: dict, asset: dict) -> str:
    title = clean_text(unit.get("unit_title") or concise_title(asset))
    text = unit.get("text") or ""
    rules = [
        ("止损", "交易前先想清楚怎么输"),
        ("止盈", "交易前先想清楚怎么输"),
        ("沟通", "用AI别憋完美问题"),
        ("底层", "底层框架决定你的上限"),
        ("价值观", "底层框架决定你的上限"),
        ("不变", "AI时代先找到不变"),
        ("存储", "我为什么看好存储"),
        ("职业", "未来职业要提前换打法"),
        ("AI共存", "别把AI当工具用"),
        ("合作伙伴", "别把AI当工具用"),
        ("结论", "第一性原理才是护城河"),
        ("赚钱", "100件事99件不赚钱"),
    ]
    haystack = f"{title} {text}"
    for key, candidate in rules:
        if key in haystack:
            return candidate[:20]
    return title[:20] or "这条值得单独讲"


def xhs_tags(asset: dict, unit: dict) -> list[str]:
    tags = hashtags(asset.get("description") or asset.get("title") or "")
    base = ["AI", "自我迭代", "认知框架"]
    text = f"{unit.get('unit_title','')} {unit.get('text','')}"
    if "交易" in text:
        base.extend(["交易复盘", "风险管理"])
    if "AI" in text or "Prompt" in text:
        base.extend(["AI工具", "AI工作流"])
    if "赚钱" in text or "职业" in text:
        base.extend(["赚钱思维", "个人成长"])
    merged = []
    for tag in tags + base:
        tag = re.sub(r"[^A-Za-z0-9_\\-\\u4e00-\\u9fff]", "", tag)
        if tag and tag not in merged:
            merged.append(tag)
    return merged[:8]


def xhs_cards(title: str, unit: dict) -> list[str]:
    lines = split_readable_lines(unit.get("text") or "", 7)
    cards = [f"{title}\n先抓住一个最可搜索、最值得收藏的判断。"]
    for idx, line in enumerate(lines[:6], start=2):
        cards.append(line)
    if len(cards) < 7:
        cards.append("最后问自己：这件事到底是在积累资产，还是只是在消耗时间？")
    return cards[:8]


def xhs_note_brief(title: str, asset: dict, unit: dict) -> dict:
    text = clean_text(unit.get("text") or "")
    tags = xhs_tags(asset, unit)
    evidence = split_readable_lines(text, 3)
    if "交易" in text:
        intent = "交易复盘、风险管理、预期差判断"
        reader = "做交易或关注资产价格，但容易被碎片信息带着走的人"
        conflict = "很多人以为自己缺信息，实际是没有先找出主导变量。"
    elif "AI" in text or "人工智能" in text:
        intent = "AI时代、个人成长、工作流升级"
        reader = "正在用 AI 工具，但还停留在技巧和工具清单层面的人"
        conflict = "很多人以为会用工具就够了，实际要先升级判断框架。"
    else:
        intent = "认知框架、个人成长、决策复盘"
        reader = "想把复杂问题想清楚，并形成稳定行动判断的人"
        conflict = "普通人容易把表面动作当成核心问题。"
    return {
        "search_keywords": tags[:5],
        "search_intent": intent,
        "target_reader": reader,
        "core_claim": title,
        "cognitive_conflict": conflict,
        "source_evidence": evidence,
        "reader_payoff": "带走一个可复盘、可收藏、能反复使用的判断框架。",
    }


def xhs_body(asset: dict, index: int) -> tuple[str, str]:
    units = xhs_units_for_asset(asset)
    unit = units[min(index - 1, len(units) - 1)]
    title = xhs_title_from_unit(unit, asset)
    lines = split_readable_lines(unit.get("text") or "", 8)
    tags = xhs_tags(asset, unit)
    tag_line = " ".join(f"#{tag}" for tag in tags[:6])
    cards = xhs_cards(title, unit)
    opening = lines[0] if lines else clean_text(unit.get("text") or asset.get("description") or "")
    supporting = lines[1:6]
    if not supporting and opening:
        supporting = [opening]

    body_parts = [
        opening,
        "这条我想单独拎出来讲，是因为它不是一个技巧，而是一个判断框架。",
    ]
    body_parts.extend(supporting)
    body_parts.append("所以这件事的关键，不是更努力地做更多事，而是先判断：这件事到底还值不值得做。")
    body_parts.append("你现在最想重新判断的一件事是什么？")
    body = "\n\n".join(part for part in body_parts if part)
    body = f"{body}\n\n{tag_line}"
    return title, body


def wechat_body(asset: dict, _index: int) -> tuple[str, str]:
    title = concise_title(asset, 13)
    body = f"""# {title}

## 开场

从这个抖音观点展开，但不要逐字搬运。公众号文章需要补完整上下文、例子和判断。

## 核心观点

{asset.get("description") or asset.get("title") or ""}

## 可展开的三个部分

1. 这个判断为什么重要
2. 它对普通人/开发者/创业者意味着什么
3. 接下来应该怎么行动

## 结尾

用一个明确判断收束，而不是泛泛总结。

封面图建议：
使用高对比大字标题，突出一个核心判断。
"""
    return title, body


def short_video_body(asset: dict, platform: str) -> tuple[str, str]:
    title = concise_title(asset, 36)
    body = f"""标题：
{title}

来源抖音：
{asset.get("source_url")}

发布说明：
- 优先复用原视频素材
- 检查封面、字幕、标题是否适合 {platform}
- 不自动发布，人工确认后再发送

原始描述：
{asset.get("description") or asset.get("title") or ""}
"""
    return title, body


def x_body(asset: dict, _index: int) -> tuple[str, str]:
    title = concise_title(asset, 40)
    body = f"""Draft X post/thread:

{asset.get("description") or asset.get("title") or ""}

Rewrite direction:
- Make the first line a sharp claim.
- If the idea needs context, turn it into a 3-5 tweet thread.
- Keep one idea per tweet.

Source: {asset.get("source_url")}
"""
    return title, body


def zhihu_body(asset: dict, _index: int) -> tuple[str, str]:
    title = f"如何看待：{concise_title(asset, 26)}"
    body = f"""# {title}

回答草稿方向：

先给明确判断，再解释边界条件。知乎不要写成短视频口播，要补足逻辑链。

原始抖音观点：
{asset.get("description") or asset.get("title") or ""}

建议结构：

1. 结论
2. 为什么这个问题容易被误解
3. 具体例子
4. 对个人选择的影响

来源：{asset.get("source_url")}
"""
    return title, body


def draft_content(platform: str, asset: dict, index: int) -> tuple[str, str]:
    if platform == "xiaohongshu":
        return xhs_body(asset, index)
    if platform == "wechat_mp":
        return wechat_body(asset, index)
    if platform == "wechat_channels":
        return short_video_body(asset, "视频号")
    if platform == "youtube":
        return short_video_body(asset, "YouTube")
    if platform == "bilibili":
        return short_video_body(asset, "Bilibili")
    if platform == "x":
        return x_body(asset, index)
    if platform == "zhihu":
        return zhihu_body(asset, index)
    raise ValueError(f"unsupported platform: {platform}")


def write_draft(platform: str, asset: dict, index: int, publish_date: str, overwrite: bool) -> bool:
    source_id = str(asset["source_content_id"])
    local_id = f"{platform}-{source_id[-6:]}-{index:02d}"
    title, body = draft_content(platform, asset, index)
    slug = slugify(title or asset.get("title") or "", f"douyin-{source_id[-6:]}")
    basename = f"{publish_date}--{slug}--{local_id}"
    draft_dir = OUT / "drafts" / platform
    draft_dir.mkdir(parents=True, exist_ok=True)
    md_path = draft_dir / f"{basename}.md"
    json_path = draft_dir / f"{basename}.json"
    existing = list(draft_dir.glob(f"*--{local_id}.json")) + list(draft_dir.glob(f"*--{local_id}.md"))
    if not overwrite and (md_path.exists() or json_path.exists() or existing):
        return False

    xhs_unit = None
    xhs_cards_for_record: list[str] = []
    if platform == "xiaohongshu":
        units = xhs_units_for_asset(asset)
        xhs_unit = units[min(index - 1, len(units) - 1)] if units else None
        xhs_cards_for_record = xhs_cards(title, xhs_unit or {})
        note_brief = xhs_note_brief(title, asset, xhs_unit or {})
    else:
        note_brief = {}
    record = {
        "platform": platform,
        "status": "draft",
        "intended_publish_at": publish_date,
        "local_id": local_id,
        "source_platform": "douyin",
        "source_asset_id": asset["asset_id"],
        "source_content_id": source_id,
        "source_url": asset.get("source_url") or "",
        "source_published_at": asset.get("published_at") or "",
        "draft_index": index,
        "source_content_type": asset.get("content_type") or "",
        "source_transcript_json": asset.get("transcript_json") or "",
        "source_transcript_md": asset.get("transcript_md") or "",
        "source_organized_transcript_json": asset.get("organized_transcript_json") or "",
        "source_organized_transcript_md": asset.get("organized_transcript_md") or "",
        "source_transcript_chars": asset.get("transcript_chars") or 0,
        "source_organized_transcript_chars": asset.get("organized_transcript_chars") or 0,
        "xhs_count_for_asset": xhs_count_for_asset(asset) if platform == "xiaohongshu" else None,
        "source_unit_title": (xhs_unit or {}).get("unit_title") if xhs_unit else None,
        "source_unit_start_s": (xhs_unit or {}).get("start_s") if xhs_unit else None,
        "source_unit_end_s": (xhs_unit or {}).get("end_s") if xhs_unit else None,
        "source_excerpt": (xhs_unit or {}).get("text") if xhs_unit else None,
        "note_brief": note_brief if platform == "xiaohongshu" else None,
        "image_cards": xhs_cards_for_record if platform == "xiaohongshu" else [],
        "xhs_workflow_version": "search-card-v1" if platform == "xiaohongshu" else None,
        "title": title,
        "body": body,
        "generated_at": now_iso(),
        "review_required": True,
    }
    json_path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(
        "\n".join(
            [
                "---",
                f"platform: {platform}",
                "status: draft",
                f"intended_publish_at: {publish_date}",
                f"local_id: {local_id}",
                "source_platform: douyin",
                f"source_content_id: {source_id}",
                f"source_url: {asset.get('source_url') or ''}",
                "review_required: true",
                "---",
                "",
                f"# {title}",
                "",
                "## 发布正文",
                "",
                body,
                "",
                *(
                    [
                        "## 图文卡片文案",
                        "",
                        *[f"{card_index}. {card}" for card_index, card in enumerate(xhs_cards_for_record, start=1)],
                        "",
                        "## 来源片段",
                        "",
                        (xhs_unit or {}).get("text", ""),
                        "",
                    ]
                    if platform == "xiaohongshu"
                    else []
                ),
            ]
        ),
        encoding="utf-8",
    )
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate cross-platform drafts from sent Douyin assets.")
    parser.add_argument("--platform", choices=TARGET_PLATFORMS, action="append")
    parser.add_argument("--source-content-id", action="append", default=[])
    parser.add_argument("--date", default=today())
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    assets = json.loads(ASSETS.read_text(encoding="utf-8"))
    if args.source_content_id:
        wanted = set(args.source_content_id)
        assets = [asset for asset in assets if str(asset.get("source_content_id") or "") in wanted]
    platforms = json.loads(PLATFORMS.read_text(encoding="utf-8"))["platforms"]
    ratios = {row["id"]: float(row["target_ratio_per_asset"]) for row in platforms}
    target_platforms = args.platform or TARGET_PLATFORMS

    created = 0
    skipped = 0
    for platform in target_platforms:
        target = count_for_platform(len(assets), ratios[platform])
        candidates = selected_assets(assets, platform, target)
        if platform != "xiaohongshu":
            candidates = candidates[:target]
        for asset, index in candidates:
            if write_draft(platform, asset, index, args.date, args.overwrite):
                created += 1
            else:
                skipped += 1

    print(f"created={created}")
    print(f"skipped_existing={skipped}")


if __name__ == "__main__":
    main()
