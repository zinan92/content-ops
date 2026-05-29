#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path


ROOT = Path("/Users/wendy")
OUT = ROOT / "park-io/outbox"
XHS_DRAFTS = OUT / "drafts/xiaohongshu"
ASSETS = OUT / ".system/data/assets.json"


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def clean_source_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    return text


def clean_claim_text(text: str) -> str:
    text = re.sub(r"#[^\s#]+", "", text or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def tags_from_source(text: str) -> list[str]:
    tags = re.findall(r"#([A-Za-z0-9_\-\u4e00-\u9fff]+)", text or "")
    defaults = ["AI", "自媒体", "个人成长", "效率工具"]
    out: list[str] = []
    seen: set[str] = set()
    for tag in tags + defaults:
        if tag in {"内", "容", "一"}:
            continue
        if tag.startswith("一") or "软件订阅" in tag:
            continue
        if len(tag) > 12:
            continue
        if len(tag) == 1 and not tag.isascii():
            continue
        if tag and tag not in seen:
            seen.add(tag)
            out.append(tag)
    return out[:6]


def infer_angle(record: dict) -> str:
    title = record.get("title") or ""
    if "方法版" in title:
        return "method"
    if "争议版" in title:
        return "debate"
    return "viewpoint"


def title_for_xhs(record: dict, source_text: str) -> str:
    title = (record.get("title") or "").strip()
    title = title.replace("｜观点版", "").replace("｜方法版", "").replace("｜争议版", "")
    title = re.sub(r"#[^\s#]+", "", title).strip()
    if title:
        return title[:20]
    source_text = re.sub(r"#[^\s#]+", "", source_text).strip()
    return (source_text[:20] or "这件事值得认真想想").rstrip("，。,. ")


def render_xhs_copy(record: dict) -> tuple[str, str, list[str]]:
    raw_body = clean_source_text(record.get("body") or "")
    transcript_match = re.search(
        r"原始转录片段：\s*(.*?)\s*(?:小红书改写要求：|$)",
        raw_body,
        re.S,
    )
    source_text = clean_source_text(transcript_match.group(1) if transcript_match else "")
    if not source_text:
        source_text = clean_source_text(record.get("source_description") or record.get("source_title") or "")
    if not source_text:
        source_match = re.search(r"原始抖音观点：\s*(.*?)\s*(?:小红书改写要求：|$)", raw_body, re.S)
        source_text = clean_source_text(source_match.group(1) if source_match else raw_body)
    source_claim = clean_claim_text(source_text)
    if not source_claim:
        source_claim = source_text
    title = title_for_xhs(record, source_text)
    angle = infer_angle(record)
    tags = tags_from_source(source_text)

    if angle == "method":
        body = f"""这条可以拆成一个“方法/路径”笔记。

核心原话：
{source_claim}

可以改写成小红书正文时，保留这几个层次：

1. 先说这个方法解决什么问题
2. 再说为什么普通人容易误解
3. 最后给一个可以执行的判断标准

这一条还需要人工把口播语气改成更短的段落，不要删掉原论证里的例子。"""
    elif angle == "debate":
        body = f"""这条可以拆成一个“争议/反直觉”笔记。

核心原话：
{source_claim}

适合小红书的处理方式：

1. 第一屏放最反直觉的一句话
2. 第二段解释为什么这不是标题党
3. 中间保留原视频里的关键推理
4. 结尾抛一个能引发评论的问题

这一条还不是最终发布稿，需要下一步做口语化重写。"""
    else:
        body = f"""这条可以拆成一个“观点判断”笔记。

核心原话：
{source_claim}

小红书正文应该围绕这一个判断展开，而不是泛泛总结。

建议结构：

1. 结论先行
2. 保留原视频里的推理链
3. 把长句拆成 3-5 个短段落
4. 用一个具体问题收尾

这一条已经基于 transcript 选段，但还不是最终人工可发布稿。"""

    return title, body, tags


def load_asset_map() -> dict[str, dict]:
    if not ASSETS.exists():
        return {}
    try:
        assets = json.loads(ASSETS.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return {str(asset.get("source_content_id") or ""): asset for asset in assets}


def write_markdown(path: Path, record: dict) -> None:
    tag_line = " ".join(f"#{tag}" for tag in record["tags"])
    lines = [
        "---",
        f"platform: {record['platform']}",
        f"status: {record['status']}",
        f"intended_publish_at: {record['intended_publish_at']}",
        f"local_id: {record['local_id']}",
        "source_platform: douyin",
        f"source_content_id: {record['source_content_id']}",
        f"source_url: {record.get('source_url') or ''}",
        "review_required: true",
        "---",
        "",
        f"# {record['title']}",
        "",
        record["body"],
        "",
        tag_line,
        "",
        "---",
        "封面建议：大字标题 + 高对比背景。第一屏只放一个判断，不堆信息。",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def upgrade_one(json_path: Path, overwrite: bool, asset_map: dict[str, dict]) -> bool:
    record = json.loads(json_path.read_text(encoding="utf-8"))
    if record.get("platform") != "xiaohongshu":
        return False
    if record.get("status") == "draft_ready" and not overwrite:
        return False

    source_asset = asset_map.get(str(record.get("source_content_id") or ""))
    if source_asset:
        record["source_title"] = source_asset.get("title") or ""
        record["source_description"] = source_asset.get("description") or source_asset.get("title") or ""
        record["source_transcript_json"] = source_asset.get("transcript_json") or record.get("source_transcript_json") or ""
        record["source_transcript_md"] = source_asset.get("transcript_md") or record.get("source_transcript_md") or ""
        record["source_transcript_chars"] = source_asset.get("transcript_chars") or record.get("source_transcript_chars") or 0

    title, body, tags = render_xhs_copy(record)
    record.update(
        {
            "status": "draft_ready",
            "title": title,
            "body": body,
            "tags": tags,
            "upgraded_at": now_iso(),
            "copy_level": "publish_review",
            "review_required": True,
        }
    )
    json_path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_markdown(json_path.with_suffix(".md"), record)
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Upgrade Xiaohongshu direction drafts into reviewable copy.")
    parser.add_argument("--limit", type=int, default=0, help="0 means all.")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    paths = sorted(XHS_DRAFTS.glob("*.json"))
    if args.limit > 0:
        paths = paths[: args.limit]

    upgraded = 0
    skipped = 0
    asset_map = load_asset_map()
    for path in paths:
        if upgrade_one(path, args.overwrite, asset_map):
            upgraded += 1
        else:
            skipped += 1
    print(f"upgraded={upgraded}")
    print(f"skipped={skipped}")


if __name__ == "__main__":
    main()
