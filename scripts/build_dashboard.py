#!/usr/bin/env python3
from __future__ import annotations

import html
import json
import os
from collections import Counter
from datetime import datetime
from pathlib import Path
from urllib.parse import quote


ROOT = Path("/Users/wendy")
MANIFESTS = [
    ROOT / "content-toolkit/capabilities/download/output/manifest.jsonl",
    ROOT / "park-io/outbox/.system/data/douyin-sent-manifest.jsonl",
]
PROFILE_AWEME_LISTS = [
    ROOT / "park-io/outbox/.system/data/douyin-profile-aweme-list.json",
]
OUT = ROOT / "park-io/outbox"
DATA_DIR = OUT / ".system/data"
REPORTS_DIR = ROOT / "work/content-ops/.runs/reports"
XHS_TRIAGE_REPORT = REPORTS_DIR / "xiaohongshu-blocked-source-triage.json"
ACTION_QUEUE_REPORT = REPORTS_DIR / "outbox-action-queue.json"
ACTION_QUEUE_MD = REPORTS_DIR / "outbox-action-queue.md"
PLATFORMS = Path(__file__).resolve().parents[1] / "platforms.json"
SOURCE_ACCOUNT_NAMES = {"Park的AI世界", "Park 的 AI 世界", "park 的 AI 世界"}
SENT_DOUYIN_RECORDS = OUT / "sent/douyin"
DEFAULT_FOCUS_SOURCE_ID = "7613803738997722394"
PLATFORM_ICONS = {
    "xiaohongshu": "📕",
    "wechat_mp": "📰",
    "wechat_channels": "▶",
    "x": "𝕏",
    "youtube": "▶",
    "bilibili": "B",
    "douyin": "♪",
}


def stable_asset_id(row: dict) -> str:
    platform = str(row.get("platform") or "douyin")
    content_id = str(row.get("content_id") or row.get("aweme_id") or "").strip()
    return f"{platform}_{content_id}"


def first_existing_path(paths: list[str], suffixes: tuple[str, ...]) -> list[str]:
    found = []
    for raw in paths:
        if raw.endswith(suffixes):
            found.append(str((ROOT / "park-io/library" / raw).resolve()))
    return found


def published_date_from_ts(raw: object) -> str:
    try:
        ts = int(raw or 0)
    except (TypeError, ValueError):
        return ""
    if ts <= 0:
        return ""
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")


def clean_douyin_dir(content_id: str) -> Path | None:
    matches = sorted(SENT_DOUYIN_RECORDS.glob(f"20*--*--{content_id}"))
    return matches[0] if matches else None


def enrich_with_clean_library(asset: dict, content_id: str) -> dict:
    clean_dir = clean_douyin_dir(content_id)
    if not clean_dir:
        return asset
    media_files = [str(path.resolve()) for path in sorted((clean_dir / "media").glob("*.mp4"))]
    cover_files = [str(path.resolve()) for path in sorted((clean_dir / "media").glob("cover.*"))]
    image_files = [
        str(path.resolve())
        for path in sorted((clean_dir / "media").glob("*"))
        if path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"} and not path.name.startswith("cover.")
    ]
    display_cover_files = cover_files or image_files[:1]
    transcript_md = clean_dir / "transcript/raw.md"
    transcript_json = clean_dir / "transcript/raw.json"
    if not transcript_md.exists():
        transcript_md = clean_dir / "transcript.md"
    if not transcript_json.exists():
        transcript_json = clean_dir / "transcript.json"
    organized_md = clean_dir / "transcript/organized.md"
    organized_json = clean_dir / "transcript/organized.json"
    content_package_json = clean_dir / "transcript/content-package.json"
    content_package_md = clean_dir / "transcript/content-package.md"
    if not organized_md.exists():
        organized_md = clean_dir / "organized_transcript.md"
    if not organized_json.exists():
        organized_json = clean_dir / "organized_transcript.json"
    source_json = clean_dir / "source.json"
    content_item = source_json if source_json.exists() else clean_dir / "content_item.json"
    content_type = ""
    if content_item.exists():
        try:
            content_type = json.loads(content_item.read_text(encoding="utf-8")).get("content_type") or ""
        except json.JSONDecodeError:
            content_type = ""
    asset["content_dir"] = str(clean_dir.resolve())
    asset["content_type"] = content_type
    if media_files:
        asset["media_files"] = media_files
    if image_files:
        asset["image_files"] = image_files
    if display_cover_files:
        asset["cover_files"] = display_cover_files
    if transcript_md.exists():
        asset["transcript_md"] = str(transcript_md.resolve())
    if transcript_json.exists():
        asset["transcript_json"] = str(transcript_json.resolve())
        try:
            transcript = json.loads(transcript_json.read_text(encoding="utf-8"))
            asset["transcript_chars"] = len(transcript.get("full_text") or "")
            asset["transcript_segments"] = len(transcript.get("segments") or [])
        except json.JSONDecodeError:
            pass
    if organized_md.exists():
        asset["organized_transcript_md"] = str(organized_md.resolve())
    if organized_json.exists():
        asset["organized_transcript_json"] = str(organized_json.resolve())
        try:
            organized = json.loads(organized_json.read_text(encoding="utf-8"))
            asset["organized_engine"] = organized.get("engine") or ""
            asset["organized_source_chars"] = organized.get("source_chars") or 0
            asset["organized_transcript_chars"] = organized.get("organized_chars") or 0
            asset["organized_retention_ratio"] = organized.get("retention_ratio") or 0
        except json.JSONDecodeError:
            pass
    if content_package_json.exists():
        asset["content_package_json"] = str(content_package_json.resolve())
        try:
            package = json.loads(content_package_json.read_text(encoding="utf-8"))
            asset["content_package_engine"] = package.get("engine") or ""
            asset["content_package_generated_at"] = package.get("generated_at") or ""
            asset["content_package_approved"] = bool(package.get("approved"))
            asset["content_package_approved_at"] = package.get("approved_at") or ""
            asset["content_package_approved_by"] = package.get("approved_by") or ""
            asset["content_package_source_chars"] = package.get("source_chars") or 0
            asset["content_package_readable_chars"] = package.get("readable_chars") or 0
            asset["content_package_warnings"] = package.get("warnings") or []
            asset["content_package_text"] = str(package.get("readable_transcript") or "").strip()
            asset["content_package_topics"] = package.get("topics") or package.get("topic_groups") or []
            asset["content_package_fine_topics"] = package.get("fine_topics") or []
            asset["content_package_topic_groups"] = package.get("topic_groups") or package.get("topics") or []
            asset["content_package_topic_count"] = len(asset["content_package_topics"])
            asset["content_package_fine_topic_count"] = len(asset["content_package_fine_topics"])
            asset["content_package_topic_group_count"] = len(asset["content_package_topic_groups"])
            asset["content_package_clip_count"] = len(package.get("clip_candidates") or [])
        except json.JSONDecodeError:
            pass
    if content_package_md.exists():
        asset["content_package_md"] = str(content_package_md.resolve())
    return asset


def is_public_aweme(aweme: dict) -> bool:
    status = aweme.get("status") or {}
    return (
        not status.get("is_delete")
        and not status.get("in_reviewing")
        and not status.get("is_prohibited")
        and status.get("private_status", 0) == 0
        and status.get("part_see", 0) == 0
        and status.get("allow_share") is True
    )


def asset_from_aweme(aweme: dict, list_path: Path) -> dict | None:
    author = aweme.get("author") or {}
    if (author.get("nickname") or "") not in SOURCE_ACCOUNT_NAMES:
        return None
    if not is_public_aweme(aweme):
        return None

    content_id = str(aweme.get("aweme_id") or "").strip()
    if not content_id:
        return None

    author_id = str(author.get("uid") or list_path.parent.name or "")
    item_dir = list_path.parent / content_id
    media_files = [str(path.resolve()) for path in sorted((item_dir / "media").glob("*.mp4"))]
    cover_files = [str(path.resolve()) for path in sorted((item_dir / "media").glob("cover.*"))]
    desc = aweme.get("desc") or ""
    return enrich_with_clean_library({
        "asset_id": f"douyin_{content_id}",
        "source_platform": "douyin",
        "source_content_id": content_id,
        "source_account": author.get("nickname") or "",
        "published_at": published_date_from_ts(aweme.get("create_time")),
        "title": desc.splitlines()[0][:120],
        "description": desc,
        "tags": [],
        "media_files": media_files,
        "cover_files": cover_files,
        "source_url": f"https://www.douyin.com/video/{content_id}",
        "raw": aweme,
    }, content_id)


def asset_from_sent_record(record: dict, path: Path) -> dict | None:
    if record.get("platform") != "douyin" or record.get("status") != "sent":
        return None
    content_id = str(record.get("platform_id") or record.get("content_id") or "").strip()
    if not content_id:
        return None
    title = record.get("title") or record.get("description") or path.stem
    return enrich_with_clean_library({
        "asset_id": f"douyin_{content_id}",
        "source_platform": "douyin",
        "source_content_id": content_id,
        "source_account": record.get("account") or "Park的AI世界",
        "published_at": str(record.get("published_at") or "")[:10],
        "title": str(title).splitlines()[0][:120],
        "description": record.get("description") or record.get("title") or "",
        "tags": record.get("tags") or [],
        "media_files": record.get("media_files") or [],
        "cover_files": record.get("cover_files") or [],
        "source_url": record.get("source_url") or f"https://www.douyin.com/video/{content_id}",
        "raw": record,
    }, content_id)


def load_assets() -> list[dict]:
    assets: list[dict] = []
    seen: set[str] = set()
    for list_path in PROFILE_AWEME_LISTS:
        if not list_path.exists():
            continue
        for aweme in json.loads(list_path.read_text(encoding="utf-8")):
            asset = asset_from_aweme(aweme, list_path)
            if not asset or asset["asset_id"] in seen:
                continue
            seen.add(asset["asset_id"])
            assets.append(asset)

    for record_path in sorted(SENT_DOUYIN_RECORDS.glob("*.json")):
        record = json.loads(record_path.read_text(encoding="utf-8"))
        asset = asset_from_sent_record(record, record_path)
        if not asset or asset["asset_id"] in seen:
            continue
        seen.add(asset["asset_id"])
        assets.append(asset)

    for manifest in MANIFESTS:
        if not manifest.exists():
            continue
        for line in manifest.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if (row.get("author_name") or "") not in SOURCE_ACCOUNT_NAMES:
                continue
            asset_id = stable_asset_id(row)
            if asset_id in seen:
                continue
            seen.add(asset_id)
            content_id = str(row.get("content_id") or row.get("aweme_id") or "")
            item_dir = manifest.parent / "douyin" / str(row.get("author_id") or "") / content_id
            media_files = [str(path.resolve()) for path in sorted((item_dir / "media").glob("*.mp4"))]
            cover_files = [str(path.resolve()) for path in sorted((item_dir / "media").glob("cover.*"))]
            assets.append(
                enrich_with_clean_library({
                    "asset_id": asset_id,
                    "source_platform": row.get("platform") or "douyin",
                    "source_content_id": content_id,
                    "source_account": row.get("author_name") or "",
                    "published_at": (row.get("publish_time") or row.get("date") or "")[:10],
                    "title": (row.get("title") or row.get("desc") or "").splitlines()[0][:120],
                    "description": row.get("description") or row.get("desc") or row.get("title") or "",
                    "tags": row.get("tags") or [],
                    "media_files": media_files,
                    "cover_files": cover_files,
                    "source_url": row.get("source_url") or "",
                    "raw": row,
                }, content_id)
            )
    assets.sort(key=lambda item: item.get("published_at") or "", reverse=True)
    return assets


def load_platforms() -> list[dict]:
    platforms = json.loads(PLATFORMS.read_text(encoding="utf-8"))["platforms"]
    return [platform for platform in platforms if platform["id"] != "zhihu"]


def progress_bar(done: int, total: int, width: int = 24) -> str:
    if total <= 0:
        return "░" * width
    filled = round(width * min(done / total, 1))
    return "█" * filled + "░" * (width - filled)


def count_platform_records(state: str, platform_id: str) -> int:
    directory = OUT / state / platform_id
    if not directory.exists():
        return 0
    json_records = [path for path in directory.glob("*.json") if path.is_file()]
    if json_records:
        return len(json_records)
    return len([path for path in directory.glob("*.md") if path.is_file()])


def build_summary(assets: list[dict], platforms: list[dict]) -> list[dict]:
    source_count = len(assets)
    rows = []
    for platform in platforms:
        platform_id = platform["id"]
        if platform_id == "douyin":
            published = source_count
            target = source_count
            drafts = count_platform_records("drafts", platform_id)
        else:
            published = count_platform_records("sent", platform_id)
            drafts = count_platform_records("drafts", platform_id)
            target = max(1, round(source_count * float(platform["target_ratio_per_asset"])))
        rows.append(
            {
                "platform_id": platform_id,
                "label": platform["label"],
                "role": platform["role"],
                "publish_mode": platform["publish_mode"],
                "published": published,
                "drafts": drafts,
                "target": target,
                "gap": max(target - published - drafts, 0),
                "progress": progress_bar(published + drafts, target),
            }
        )
    return rows


def write_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_markdown(assets: list[dict], summary: list[dict]) -> None:
    latest = assets[:15]
    lines = [
        "# Social Media Progress",
        "",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## Platform Progress",
        "",
        "| Platform | Progress | Sent | Drafts | Target | Gap | Mode |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for row in summary:
        lines.append(
            f"| {row['label']} | `{row['progress']}` | {row['published']} | {row['drafts']} | {row['target']} | {row['gap']} | {row['publish_mode']} |"
        )
    lines.extend(
        [
            "",
            "## Source Asset Backlog",
            "",
            f"- Park的AI世界 Douyin sent assets indexed locally: {len(assets)}",
            "- Other platform drafts live under `outbox/drafts/<platform>/`.",
            "- Sent platform records live under `outbox/sent/<platform>/`.",
            "- Repurposing reads mature Douyin records from `outbox/sent/douyin/` only.",
            "",
            "## Latest Douyin Assets",
            "",
        ]
    )
    for asset in latest:
        title = asset["title"].replace("\n", " ")
        lines.append(f"- {asset['published_at']} · `{asset['source_content_id']}` · {title}")
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / "platform-progress.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def rel_href(path: Path | str | None) -> str:
    if not path:
        return ""
    candidate = Path(path)
    try:
        rel = candidate.relative_to(OUT)
    except ValueError:
        rel = candidate
    return quote(str(rel), safe="/:#?&=")


def resolve_local_path(path: Path | str | None, base: Path | None = None) -> Path | None:
    if not path:
        return None
    candidate = Path(path)
    if base and not candidate.is_absolute():
        candidate = base / candidate
    return candidate


def existing_href(path: Path | str | None, fallback: Path | str | None = None, base: Path | None = None) -> str:
    candidate = resolve_local_path(path or fallback, base)
    if candidate and candidate.exists():
        return rel_href(candidate)
    return ""


def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def load_xhs_triage() -> dict[str, dict]:
    report = read_json(XHS_TRIAGE_REPORT)
    rows = report.get("items") or []
    lookup: dict[str, dict] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        for key in (row.get("path"), row.get("filename")):
            if key:
                lookup[str(key)] = row
    return lookup


def load_action_queue() -> dict:
    queue = read_json(ACTION_QUEUE_REPORT)
    actions = queue.get("actions") or []
    if not isinstance(actions, list):
        actions = []
    return {
        "generated_at": queue.get("generated_at") or "",
        "total_actions": queue.get("total_actions") or len(actions),
        "resolved_count": queue.get("resolved_count") or 0,
        "lane_counts": queue.get("lane_counts") or {},
        "report_href": f"file://{ACTION_QUEUE_MD}",
        "actions": [
            {
                "priority": item.get("priority") or 0,
                "lane": item.get("lane") or "",
                "label": item.get("label") or "",
                "source_content_id": item.get("source_content_id") or "",
                "draft_title": item.get("draft_title") or "",
                "source_unit_title": item.get("source_unit_title") or "",
                "source_excerpt_chars": item.get("source_excerpt_chars") or 0,
                "reason": item.get("reason") or "",
                "draft_path": item.get("draft_path") or "",
                "command": item.get("command") or "",
            }
            for item in actions[:12]
        ],
        "resolved": [
            {
                "priority": item.get("priority") or 0,
                "source_content_id": item.get("source_content_id") or "",
                "draft_title": item.get("draft_title") or "",
                "source_unit_title": item.get("source_unit_title") or "",
                "draft_path": item.get("draft_path") or "",
                "decision": item.get("decision") or {},
            }
            for item in (queue.get("resolved") or [])[:12]
            if isinstance(item, dict)
        ],
    }


def file_exists(raw: str | None) -> bool:
    return bool(raw) and Path(raw).exists()


def package_dir_for(record: dict, json_path: Path) -> Path | None:
    rendered = record.get("rendered_package_dir")
    if rendered and Path(rendered).exists():
        return Path(rendered)
    candidate = json_path.with_suffix("")
    if candidate.exists() and candidate.is_dir():
        return candidate
    return None


def text_preview(value: str | None, limit: int = 260) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip("，。,. ") + "…"


def readable_organized_transcript(path: str | None, limit: int = 60000) -> str:
    if not path:
        return ""
    transcript_path = Path(path)
    if not transcript_path.exists():
        return ""
    text = transcript_path.read_text(encoding="utf-8", errors="replace").strip()
    marker = "## Organized Transcript"
    if marker in text:
        text = text.split(marker, 1)[1].strip()
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("- Source transcript:") or stripped.startswith("- Engine:") or stripped.startswith("- Retention ratio:") or stripped.startswith("- Organized at:"):
            continue
        lines.append(line.rstrip())
    text = "\n".join(lines).strip()
    return text[:limit].rstrip()


def draft_preview_text(record: dict) -> str:
    if (record.get("platform") or "") == "xiaohongshu":
        cards = [str(card).strip() for card in record.get("image_cards") or [] if str(card).strip()]
        body = str(record.get("body") or "").strip()
        if body:
            return text_preview(body, 360)
        if cards:
            return text_preview(" / ".join(cards[:3]), 360)
        return ""
    return text_preview(record.get("body") or record.get("caption") or record.get("description") or "")


def first_rendered_images(record: dict, package_dir: Path | None, limit: int = 10) -> list[str]:
    images = [image for image in record.get("rendered_images") or [] if file_exists(image)]
    if not images and package_dir:
        images = [str(path.resolve()) for path in sorted((package_dir / "images").glob("*.png"))]
    return images[:limit]


def topic_key(title: str, index: int) -> str:
    normalized = "-".join(str(title or f"topic-{index}").strip().lower().split())
    normalized = "".join(ch for ch in normalized if ch.isalnum() or ch in "-_")
    return normalized[:48] or f"topic-{index}"


def topic_priority(title: str, text: str, index: int) -> str:
    sample = f"{title} {text}"
    if len(text) < 360:
        return "secondary"
    if any(word in str(title) for word in ("Remotion", "remotion", "测试", "token")):
        return "secondary"
    if len(text) >= 700:
        return "main"
    if any(word in sample for word in ("交易", "决策", "判断", "影响", "样本")):
        return "main"
    return "secondary"


def topic_reason(title: str, text: str, priority: str) -> str:
    if priority == "discard":
        return "内容支撑不足，暂不生成独立图文。"
    if priority == "secondary":
        return "可以独立成稿，但不是当前视频的最高传播主线。"
    hooks = []
    sample = f"{title} {text}"
    if any(word in sample for word in ("但是", "不是", "反而", "偏偏", "为什么")):
        hooks.append("有认知反差")
    if len(text) >= 700:
        hooks.append("内容支撑充足")
    if any(word in sample for word in ("比如", "例子", "石油", "战争", "蚂蚁", "交易")):
        hooks.append("有具体场景")
    return "；".join(hooks[:3]) or "具备独立观点和读者收益。"


def load_draft_records() -> list[dict]:
    rows: list[dict] = []
    for path in sorted((OUT / "drafts").glob("*/*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        md_path = path.with_suffix(".md")
        platform = record.get("platform") or path.parent.name
        if record.get("status") in {"superseded", "archived"}:
            continue
        quality = record.get("xhs_quality") or {}
        show_rendered_assets = platform != "xiaohongshu" or bool(quality.get("passes_quality_gate"))
        package_dir = package_dir_for(record, path)
        images = record.get("rendered_images") or []
        existing_images = [image for image in images if file_exists(image)] if show_rendered_assets else []
        preview_images = first_rendered_images(record, package_dir) if show_rendered_assets else []
        rows.append(
            {
                "record": record,
                "platform": platform,
                "title": record.get("title") or path.stem,
                "body": record.get("body") or record.get("caption") or record.get("description") or "",
                "preview": draft_preview_text(record),
                "source_unit_title": record.get("source_unit_title") or "",
                "topic_index": record.get("topic_index"),
                "source_unit_start_s": record.get("source_unit_start_s"),
                "source_unit_end_s": record.get("source_unit_end_s"),
                "source_excerpt": record.get("source_excerpt") or "",
                "local_id": record.get("local_id") or path.stem,
                "source_content_id": record.get("source_content_id") or "",
                "intended_publish_at": record.get("intended_publish_at") or "",
                "json_path": path,
                "md_path": md_path if md_path.exists() else None,
                "package_dir": package_dir if show_rendered_assets else None,
                "package_dir_path": str(package_dir.resolve()) if package_dir and show_rendered_assets else "",
                "package_href": rel_href(package_dir) if package_dir and show_rendered_assets else "",
                "md_href": rel_href(md_path) if md_path.exists() else "",
                "html_href": existing_href(record.get("html_preview_path"), path.with_suffix(".html"), path.parent),
                "wechat_html_href": existing_href(record.get("wechat_html_path"), path.with_name(f"{path.stem}.wechat.html"), path.parent),
                "wechat_style": record.get("wechat_style") or "professional",
                "wechat_style_label": record.get("wechat_style_label") or "简洁专业",
                "style_variants": record.get("style_variants") or {},
                "json_href": rel_href(path),
                "json_path_str": str(path.resolve()),
                "rendered_image_count": len(existing_images),
                "preview_images": preview_images,
                "preview_image_hrefs": [rel_href(image) for image in preview_images],
                "latest_platform_draft": record.get("latest_platform_draft") or {},
                "last_push_status": record.get("last_push_status") or "",
                "last_push_message": record.get("last_push_message") or "",
                "last_pushed_at": record.get("last_pushed_at") or "",
                "xhs_quality": quality,
                "note_brief": record.get("note_brief") or {},
                "status": record.get("status") or "draft",
            }
        )
    rows.sort(key=lambda row: (row["intended_publish_at"], row["platform"], row["title"]), reverse=True)
    return rows


def load_sent_records(platforms: list[dict]) -> list[dict]:
    rows: list[dict] = []
    platform_ids = {platform["id"] for platform in platforms}
    for platform_id in platform_ids:
        sent_dir = OUT / "sent" / platform_id
        if not sent_dir.exists():
            continue
        for path in sorted(sent_dir.glob("*.json")):
            record = read_json(path)
            if not record:
                continue
            rows.append(
                {
                    "platform": record.get("platform") or platform_id,
                    "source_content_id": str(record.get("source_content_id") or record.get("source_platform_id") or ""),
                    "platform_id": str(record.get("platform_id") or record.get("content_id") or ""),
                    "title": record.get("title") or path.stem,
                    "path": path,
                    "href": rel_href(path),
                }
            )
        for path in sorted(sent_dir.glob("20*--*")):
            if path.is_file() or path.suffix == ".json":
                continue
            rows.append(
                {
                    "platform": platform_id,
                    "source_content_id": "",
                    "platform_id": path.name.rsplit("--", 1)[-1],
                    "title": path.name,
                    "path": path,
                    "href": rel_href(path),
                }
            )
    return rows


def status_label(status: str) -> str:
    return {
        "missing": "未生成",
        "missing_asset": "缺素材",
        "source_gallery": "图文源",
        "draft": "草稿",
        "review_needed": "待审核",
        "ready_to_package": "待打包",
        "packaged": "已打包",
        "sent": "已发布",
    }.get(status, status)


def next_action_for(platform_id: str, status: str, source_content_id: str) -> str:
    if status == "missing":
        return "生成草稿：python3 /Users/wendy/work/content-ops/scripts/generate_repurpose_drafts.py"
    if status == "missing_asset":
        return "补齐本地视频：确认 outbox/sent/douyin/<source>/media/video.mp4 存在后重新生成 dashboard"
    if status == "source_gallery":
        return "源内容是抖音图文/相册，不进入视频迁移队列；优先处理小红书、公众号、X"
    if platform_id == "xiaohongshu":
        if status == "review_needed":
            return f"质量检查：python3 /Users/wendy/work/content-ops/scripts/quality_xiaohongshu_drafts.py --source-content-id {source_content_id} --force"
        if status == "ready_to_package":
            return f"渲染图文：python3 /Users/wendy/work/content-ops/scripts/render_xiaohongshu_cards.py --source-content-id {source_content_id} --overwrite"
        if status == "packaged":
            return "人工检查图文包，然后用 xiaohongshu-skills 填入创作者后台"
    if platform_id in {"bilibili", "wechat_channels", "youtube"} and status == "draft":
        return "检查标题、简介、封面、原视频素材，然后手动或半自动迁移"
    if platform_id in {"wechat_mp", "x"} and status == "review_needed":
        return "打开草稿，补上下文、结构和平台语气后再发布"
    if status == "sent":
        return "已进入 sent，无需处理"
    return "人工复查"


def platform_status(
    platform_id: str,
    drafts: list[dict],
    sent: list[dict],
    source_content_id: str,
    has_video: bool = True,
    content_type: str = "",
) -> dict:
    if sent:
        return {
            "status": "sent",
            "label": status_label("sent"),
            "draft_count": len(drafts),
            "sent_count": len(sent),
            "primary_href": sent[0].get("href") or "",
            "primary_title": sent[0].get("title") or "",
            "primary_local_id": "",
            "next_action": next_action_for(platform_id, "sent", source_content_id),
        }
    if not drafts:
        return {
            "status": "missing",
            "label": status_label("missing"),
            "draft_count": 0,
            "sent_count": 0,
            "primary_href": "",
            "primary_title": "",
            "primary_local_id": "",
            "next_action": next_action_for(platform_id, "missing", source_content_id),
        }
    if platform_id == "xiaohongshu":
        current_drafts = [
            draft
            for draft in drafts
            if str((draft.get("record") or {}).get("xhs_workflow_version") or "") == "search-card-v4-atomic-topic"
            and (draft.get("record") or {}).get("xhs_argument_pack")
        ]
        packaged = [draft for draft in current_drafts if draft["package_dir"]]
        quality_checked = [draft for draft in current_drafts if draft["xhs_quality"]]
        quality_passed = [draft for draft in current_drafts if draft["xhs_quality"].get("passes_quality_gate")]
        if packaged:
            status = "packaged"
        elif quality_passed:
            status = "ready_to_package"
        elif quality_checked:
            status = "review_needed"
        elif current_drafts:
            status = "review_needed"
        else:
            status = "review_needed"
        primary = packaged[0] if packaged else (current_drafts[0] if current_drafts else drafts[0])
        return {
            "status": status,
            "label": status_label(status),
            "draft_count": len(drafts),
            "sent_count": 0,
            "primary_href": primary.get("package_href") or primary.get("md_href") or primary.get("json_href"),
            "primary_title": primary.get("title") or "",
            "primary_local_id": primary.get("local_id") or "",
            "quality_passed": len(quality_passed),
            "quality_checked": len(quality_checked),
            "packaged_count": len(packaged),
            "current_draft_count": len(current_drafts),
            "legacy_draft_count": max(0, len(drafts) - len(current_drafts)),
            "next_action": next_action_for(platform_id, status, source_content_id),
        }
    if platform_id in {"wechat_mp", "x"}:
        status = "review_needed"
    elif platform_id in {"wechat_channels", "bilibili", "youtube"} and content_type == "gallery":
        status = "source_gallery"
    elif platform_id in {"wechat_channels", "bilibili", "youtube"} and not has_video:
        status = "missing_asset"
    else:
        status = "draft"
    primary = drafts[0]
    return {
        "status": status,
        "label": status_label(status),
        "draft_count": len(drafts),
        "sent_count": 0,
        "primary_href": primary.get("md_href") or primary.get("json_href"),
        "primary_title": primary.get("title") or "",
        "primary_local_id": primary.get("local_id") or "",
        "next_action": next_action_for(platform_id, status, source_content_id),
    }


def _dbs_review_summary(dbs_review: dict | None) -> dict | None:
    if not isinstance(dbs_review, dict) or not dbs_review.get("scores"):
        return None
    scores = dbs_review.get("scores") or {}
    weak = sorted(
        (
            {"dimension": dim, "score": (node or {}).get("score") or 0,
             "reason": (node or {}).get("reason") or "",
             "structural": bool((node or {}).get("structural"))}
            for dim, node in scores.items()
        ),
        key=lambda row: row["score"],
    )[:3]
    return {
        "total": dbs_review.get("total"),
        "verdict": dbs_review.get("verdict") or "",
        "structural_blockers": dbs_review.get("structural_blockers") or [],
        "first_action": dbs_review.get("first_action") or "",
        "weakest_dimensions": weak,
        "model": dbs_review.get("model") or "",
        "reviewed_at": dbs_review.get("reviewed_at") or "",
    }


def draft_summary(draft: dict, platform_status_value: str, xhs_triage: dict[str, dict] | None = None) -> dict:
    note_brief = draft.get("note_brief") or {}
    quality = draft.get("xhs_quality") or {}
    source_excerpt_chars = len("".join(str(draft.get("source_excerpt") or "").split()))
    quality_warnings = quality.get("quality_warnings") or []
    workflow_status = "passed" if quality.get("passes_quality_gate") else "needs_work"
    if source_excerpt_chars < 400 or any("source_excerpt" in str(warning) for warning in quality_warnings):
        workflow_status = "blocked_source"
    json_path = str(draft.get("json_path_str") or draft.get("json_path") or "")
    filename = Path(json_path).name if json_path else Path(str(draft.get("json_href") or "")).name
    triage = (xhs_triage or {}).get(json_path) or (xhs_triage or {}).get(filename) or {}
    draft_json_path = draft.get("json_path")
    variant_base = draft_json_path.parent if isinstance(draft_json_path, Path) else None
    style_variants = {}
    for key, value in (draft.get("style_variants") or {}).items():
        if not isinstance(value, dict):
            continue
        image_hrefs = [
            href
            for href in (existing_href(path, base=variant_base) for path in (value.get("image_paths") or []))
            if href
        ]
        style_variants[key] = {
            **value,
            "html_preview_href": existing_href(value.get("html_preview_path"), base=variant_base),
            "wechat_html_href": existing_href(value.get("wechat_html_path"), base=variant_base),
            "cover_href": existing_href(value.get("cover_path"), base=variant_base),
            "image_hrefs": image_hrefs,
        }
    return {
        "title": draft.get("title") or "",
        "topic_index": draft.get("topic_index"),
        "preview": draft.get("preview") or "",
        "body": draft.get("body") or "",
        "source_unit_title": draft.get("source_unit_title") or "",
        "local_id": draft.get("local_id") or "",
        "status": draft.get("status") or platform_status_value,
        "status_label": status_label(draft.get("status") or platform_status_value),
        "md_href": draft.get("md_href") or "",
        "html_href": draft.get("html_href") or "",
        "wechat_html_href": draft.get("wechat_html_href") or "",
        "wechat_style": draft.get("wechat_style") or "professional",
        "wechat_style_label": draft.get("wechat_style_label") or "简洁专业",
        "xhs_workflow_version": draft.get("record", {}).get("xhs_workflow_version") or draft.get("xhs_workflow_version") or "",
        "is_current_xhs_workflow": bool(
            str(draft.get("record", {}).get("xhs_workflow_version") or draft.get("xhs_workflow_version") or "")
            == "search-card-v4-atomic-topic"
            and draft.get("record", {}).get("xhs_argument_pack")
        ),
        "style_variants": style_variants,
        "json_href": draft.get("json_href") or "",
        "package_href": draft.get("package_href") or "",
        "template_kind": draft.get("record", {}).get("template_kind") or draft.get("template_kind") or "",
        "xhs_format": draft.get("record", {}).get("xhs_format") or {},
        "xhs_argument_pack": draft.get("record", {}).get("xhs_argument_pack") or {},
        "card_plan": draft.get("record", {}).get("card_plan") or [],
        "note_brief": note_brief,
        "search_keywords": note_brief.get("search_keywords") or [],
        "core_claim": note_brief.get("core_claim") or "",
        "reader_payoff": note_brief.get("reader_payoff") or "",
        "format_rationale": note_brief.get("format_rationale") or "",
        "card_chain": note_brief.get("card_chain") or [],
        "quality_passed": bool(quality.get("passes_quality_gate")),
        "workflow_status": workflow_status,
        "triage_bucket": triage.get("bucket") or "",
        "triage_reason": triage.get("reason") or "",
        "triage_next_action": triage.get("next_action") or "",
        "quality_warnings": quality_warnings,
        "source_excerpt_chars": source_excerpt_chars,
        "recommended_title": quality.get("recommended_title") or "",
        "dbs_review": _dbs_review_summary(quality.get("dbs_review")),
        "image_count": draft.get("rendered_image_count") or 0,
        "preview_images": draft.get("preview_image_hrefs") or [],
        "latest_platform_draft": draft.get("latest_platform_draft") or {},
        "last_push_status": draft.get("last_push_status") or "",
        "last_push_message": draft.get("last_push_message") or "",
        "last_pushed_at": draft.get("last_pushed_at") or "",
    }


def topic_plan_for_asset(asset: dict, asset_drafts: list[dict]) -> dict:
    xhs_drafts = sorted(
        [draft for draft in asset_drafts if draft["platform"] == "xiaohongshu"],
        key=lambda draft: (
            draft.get("topic_index") if draft.get("topic_index") is not None else 999,
            draft.get("source_unit_start_s") is None,
            draft.get("source_unit_start_s") if draft.get("source_unit_start_s") is not None else 999999,
            draft.get("title") or "",
        ),
    )
    candidates: list[dict] = []
    seen: set[str] = set()
    for idx, draft in enumerate(xhs_drafts, start=1):
        unit_title = draft.get("source_unit_title") or draft.get("title") or f"主题 {idx}"
        text = draft.get("source_excerpt") or draft.get("body") or ""
        key = topic_key(unit_title, idx)
        if key in seen:
            key = f"{key}-{idx}"
        seen.add(key)
        priority = topic_priority(unit_title, text, idx)
        candidates.append(
            {
                "topic_id": key,
                "title": unit_title,
                "draft_title": draft.get("title") or "",
                "priority": priority,
                "recommended_platforms": ["xiaohongshu", "wechat_mp", "x"] if priority != "discard" else [],
                "evidence_chars": len(text),
                "reason": topic_reason(unit_title, text, priority),
                "draft_local_id": draft.get("local_id") or "",
                "topic_index": draft.get("topic_index"),
                "source_unit_start_s": draft.get("source_unit_start_s"),
                "source_unit_end_s": draft.get("source_unit_end_s"),
            }
        )
    candidates.sort(
        key=lambda item: (
            item.get("topic_index") if item.get("topic_index") is not None else 999,
            {"main": 0, "secondary": 1, "discard": 2}.get(item.get("priority"), 3),
            item.get("source_unit_start_s") is None,
            item.get("source_unit_start_s") if item.get("source_unit_start_s") is not None else 999999,
            item.get("draft_title") or item.get("title") or "",
        )
    )
    return {
        "source_content_id": str(asset.get("source_content_id") or ""),
        "source_title": asset.get("title") or "",
        "topic_count": len([item for item in candidates if item["priority"] != "discard"]),
        "main_topic_count": len([item for item in candidates if item["priority"] == "main"]),
        "topics": candidates,
        "decision_rules": [
            "每个主题必须有独立观点，不按章节机械拆条。",
            "每个主题需要足够展开成 700-1200 字或 7-10 张图文卡片。",
            "优先保留有认知反差、具体场景、读者收益的主题。",
            "工具过程、短灵感、支撑不足的片段只能作为 secondary 或丢弃。",
        ],
    }


def build_workbench_model(assets: list[dict], platforms: list[dict], summary: list[dict]) -> dict:
    drafts = load_draft_records()
    sent_records = load_sent_records(platforms)
    xhs_triage = load_xhs_triage()
    platform_lookup = {platform["id"]: platform for platform in platforms}
    distribution_platforms = [platform for platform in platforms if platform["id"] != "douyin"]
    review_platforms = {"xiaohongshu", "wechat_mp", "x"}
    migration_platforms = {"wechat_channels", "bilibili", "youtube"}
    source_rows = []
    review_queue = []
    migration_queue = []
    topic_plans = []

    for asset in assets:
        source_id = str(asset.get("source_content_id") or "")
        row_platforms = {}
        asset_drafts = [draft for draft in drafts if draft["source_content_id"] == source_id]
        topic_plan = topic_plan_for_asset(asset, asset_drafts)
        topic_plans.append(topic_plan)
        asset_sent = [
            item
            for item in sent_records
            if item["source_content_id"] == source_id or item["platform_id"] == source_id
        ]
        for platform in distribution_platforms:
            platform_id = platform["id"]
            platform_drafts = [draft for draft in asset_drafts if draft["platform"] == platform_id]
            if platform_id == "xiaohongshu":
                topic_order = {
                    topic["draft_local_id"]: index
                    for index, topic in enumerate(topic_plan.get("topics") or [])
                }
                platform_drafts.sort(
                    key=lambda draft: (
                        draft.get("topic_index") if draft.get("topic_index") is not None else topic_order.get(draft.get("local_id"), 999),
                        draft.get("source_unit_start_s") is None,
                        draft.get("source_unit_start_s") if draft.get("source_unit_start_s") is not None else 999999,
                    )
                )
            platform_sent = [item for item in asset_sent if item["platform"] == platform_id]
            state = platform_status(
                platform_id,
                platform_drafts,
                platform_sent,
                source_id,
                has_video=bool(asset.get("media_files") or []),
                content_type=str(asset.get("content_type") or ""),
            )
            state["drafts"] = [draft_summary(draft, state["status"], xhs_triage) for draft in platform_drafts]
            state["sent"] = [
                {
                    "title": item.get("title") or "",
                    "href": item.get("href") or "",
                }
                for item in platform_sent
            ]
            row_platforms[platform_id] = state
            if platform_id in review_platforms and platform_drafts and state["status"] != "sent":
                for draft in platform_drafts:
                    review_queue.append(
                        {
                            "platform_id": platform_id,
                            "platform_label": platform_lookup[platform_id]["label"],
                            "source_content_id": source_id,
                            "source_title": asset.get("title") or "",
                            "title": draft["title"],
                            "local_id": draft["local_id"],
                            "status": state["status"],
                            "status_label": status_label(state["status"]),
                            "md_href": draft.get("md_href") or draft.get("json_href"),
                            "package_href": draft.get("package_href") or "",
                            "quality_passed": bool(draft["xhs_quality"].get("passes_quality_gate")),
                            "image_count": draft["rendered_image_count"],
                        }
                    )
            if platform_id in migration_platforms and platform_drafts and state["status"] not in {"sent", "source_gallery"}:
                for draft in platform_drafts:
                    migration_queue.append(
                        {
                            "platform_id": platform_id,
                            "platform_label": platform_lookup[platform_id]["label"],
                            "source_content_id": source_id,
                            "source_title": asset.get("title") or "",
                            "title": draft["title"],
                            "local_id": draft["local_id"],
                            "status_label": status_label(state["status"]),
                            "status": state["status"],
                            "md_href": draft.get("md_href") or draft.get("json_href"),
                            "video_count": len(asset.get("media_files") or []),
                            "cover_count": len(asset.get("cover_files") or []),
                        }
                    )
        source_rows.append(
            {
                "source_content_id": source_id,
                "asset_id": asset.get("asset_id") or "",
                "published_at": asset.get("published_at") or "",
                "title": asset.get("title") or "",
                "source_url": asset.get("source_url") or "",
                "content_dir": asset.get("content_dir") or "",
                "content_dir_href": rel_href(asset.get("content_dir")),
                "cover_href": rel_href((asset.get("cover_files") or [""])[0]),
                "image_count": len(asset.get("image_files") or []),
                "media_href": rel_href((asset.get("media_files") or [""])[0]),
                "media_count": len(asset.get("media_files") or []),
                "cover_count": len(asset.get("cover_files") or []),
                "transcript_md": asset.get("transcript_md") or "",
                "transcript_href": rel_href(asset.get("transcript_md")),
                "transcript_chars": asset.get("transcript_chars") or 0,
                "organized_transcript_md": asset.get("organized_transcript_md") or "",
                "organized_href": rel_href(asset.get("organized_transcript_md")),
                "organized_text": readable_organized_transcript(asset.get("organized_transcript_md")),
                "organized_engine": asset.get("organized_engine") or "",
                "organized_source_chars": asset.get("organized_source_chars") or 0,
                "organized_chars": asset.get("organized_transcript_chars") or 0,
                "organized_retention_ratio": asset.get("organized_retention_ratio") or 0,
                "content_package_json": asset.get("content_package_json") or "",
                "content_package_href": rel_href(asset.get("content_package_md") or asset.get("content_package_json")),
                "content_package_engine": asset.get("content_package_engine") or "",
                "content_package_generated_at": asset.get("content_package_generated_at") or "",
                "content_package_approved": bool(asset.get("content_package_approved")),
                "content_package_approved_at": asset.get("content_package_approved_at") or "",
                "content_package_approved_by": asset.get("content_package_approved_by") or "",
                "content_package_source_chars": asset.get("content_package_source_chars") or 0,
                "content_package_readable_chars": asset.get("content_package_readable_chars") or 0,
                "content_package_text": asset.get("content_package_text") or "",
                "content_package_topics": asset.get("content_package_topics") or [],
                "content_package_fine_topics": asset.get("content_package_fine_topics") or [],
                "content_package_topic_groups": asset.get("content_package_topic_groups") or [],
                "content_package_topic_count": asset.get("content_package_fine_topic_count")
                or asset.get("content_package_topic_count")
                or 0,
                "content_package_fine_topic_count": asset.get("content_package_fine_topic_count") or 0,
                "content_package_topic_group_count": asset.get("content_package_topic_group_count") or 0,
                "content_package_clip_count": asset.get("content_package_clip_count") or 0,
                "content_package_warnings": asset.get("content_package_warnings") or [],
                "topic_plan": topic_plan,
                "platforms": row_platforms,
            }
        )
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    write_json(DATA_DIR / "topic-plans.json", topic_plans)
    source_id_set = {str(source.get("source_content_id") or "") for source in source_rows}
    scoped_drafts = [
        draft for draft in drafts if not source_id_set or str(draft.get("source_content_id") or "") in source_id_set
    ]
    xhs_drafts = [draft for draft in scoped_drafts if draft["platform"] == "xiaohongshu"]
    quality_issue_count = len(
        [
            draft
            for draft in xhs_drafts
            if not draft["xhs_quality"].get("passes_quality_gate")
            or int(draft.get("rendered_image_count") or 0) < 4
        ]
    )
    xhs_ready_count = len(
        [
            draft
            for draft in xhs_drafts
            if draft.get("package_dir") and draft["xhs_quality"].get("passes_quality_gate")
        ]
    )
    platform_sent_count = len(
        [
            item
            for item in sent_records
            if item["platform"] != "douyin"
            and (not source_id_set or str(item.get("source_content_id") or "") in source_id_set)
        ]
    )
    missing_asset_count = len([item for item in migration_queue if item["status"] == "missing_asset"])
    main_topic_count = sum(plan.get("main_topic_count") or 0 for plan in topic_plans)
    action_queue = load_action_queue()
    if source_id_set:
        action_queue = {
            **action_queue,
            "actions": [
                item
                for item in action_queue.get("actions") or []
                if str(item.get("source_content_id") or "") in source_id_set
            ],
            "resolved": [
                item
                for item in action_queue.get("resolved") or []
                if str(item.get("source_content_id") or "") in source_id_set
            ],
        }
        lane_counts = Counter(str(item.get("lane") or "") for item in action_queue.get("actions") or [])
        action_queue["lane_counts"] = dict(lane_counts)
        action_queue["total_actions"] = len(action_queue.get("actions") or [])
        action_queue["resolved_count"] = len(action_queue.get("resolved") or [])
    production = {
        "review_needed": len(review_queue),
        "ready_to_push": xhs_ready_count
        + len([item for item in review_queue if item["platform_id"] in {"wechat_mp", "x"}]),
        "quality_issues": quality_issue_count,
        "missing_assets": missing_asset_count,
        "sent": platform_sent_count,
        "main_topics": main_topic_count,
        "migration_ready": len([item for item in migration_queue if item["status"] == "draft"]),
    }
    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "summary": summary,
        "platforms": distribution_platforms,
        "sources": source_rows,
        "review_queue": review_queue,
        "migration_queue": migration_queue,
        "action_queue": action_queue,
        "production": production,
        "counts": {
            "sources": len(source_rows),
            "review_queue": len(review_queue),
            "migration_queue": len(migration_queue),
            "drafts": len(scoped_drafts),
        },
    }


def stage_status_for_source(source: dict) -> list[dict]:
    platforms = source.get("platforms") or {}

    def state(platform_id: str) -> dict:
        return platforms.get(platform_id) or {}

    migration_states = [state("wechat_channels"), state("bilibili"), state("youtube")]
    migration_done = all(item.get("status") in {"packaged", "sent"} for item in migration_states)
    migration_started = any(item.get("status") in {"draft", "packaged", "sent"} for item in migration_states)
    migration_missing = any(item.get("status") in {"missing", "missing_asset"} for item in migration_states)

    package_started = bool(source.get("content_package_text") or source.get("content_package_readable_chars"))
    package_done = bool(source.get("content_package_approved")) and package_started

    wechat = state("wechat_mp")
    wechat_drafts = wechat.get("drafts") or []
    wechat_has_preview = any(
        draft.get("html_href")
        or any(
            variant.get("html_preview_href")
            for variant in (draft.get("style_variants") or {}).values()
            if isinstance(variant, dict)
        )
        for draft in wechat_drafts
    )
    wechat_started = bool(wechat.get("draft_count") or wechat.get("sent_count"))
    wechat_done = bool(
        wechat.get("status") in {"draft", "review_needed", "packaged", "sent"}
        and (wechat.get("sent_count") or wechat_has_preview)
    )

    xhs = state("xiaohongshu")
    fine_topic_count = len(source.get("content_package_fine_topics") or [])
    xhs_draft_count = int(xhs.get("draft_count") or 0)
    xhs_current_draft_count = int(xhs.get("current_draft_count") or 0)
    xhs_current_drafts = [
        draft for draft in (xhs.get("drafts") or []) if draft.get("is_current_xhs_workflow")
    ]
    xhs_done = fine_topic_count > 0 and xhs_current_draft_count >= fine_topic_count and not any(
        not draft.get("quality_passed") for draft in xhs_current_drafts
    )
    xhs_done = xhs_done and xhs_current_draft_count > 0
    xhs_started = xhs_current_draft_count > 0 or fine_topic_count > 0

    x_state = state("x")
    x_done = x_state.get("status") == "sent"
    x_drafts = x_state.get("drafts") or []
    x_started = any(
        "Draft X post/thread" not in str((draft.get("body") or draft.get("preview") or ""))
        for draft in x_drafts
    )

    return [
        {
            "id": "migration",
            "label": "视频迁移",
            "status": "done" if migration_done else ("blocked" if migration_missing else ("doing" if migration_started else "todo")),
            "text": "已完成" if migration_done else ("缺素材" if migration_missing else ("进行中" if migration_started else "未开始")),
        },
        {
            "id": "content_package",
            "label": "内容包",
            "status": "done" if package_done else ("doing" if package_started else "todo"),
            "text": "已完成" if package_done else ("待审核" if package_started else "未开始"),
        },
        {
            "id": "wechat_mp",
            "label": "公众号文章",
            "status": "done" if wechat_done else ("doing" if wechat_started else "todo"),
            "text": "已完成" if wechat_done else ("进行中" if wechat_started else "未开始"),
        },
        {
            "id": "xiaohongshu",
            "label": "小红书文字稿",
            "status": "done" if xhs_done else ("doing" if xhs_started else "todo"),
            "text": "已完成" if xhs_done else ("进行中" if xhs_started else "未开始"),
        },
        {
            "id": "x",
            "label": "X",
            "status": "done" if x_done else ("doing" if x_started else "todo"),
            "text": "已完成" if x_done else ("进行中" if x_started else "未开始"),
        },
    ]


def write_overview_html(model: dict) -> None:
    rows = []
    for source in model.get("sources") or []:
        stages = stage_status_for_source(source)
        complete_count = sum(1 for item in stages if item["status"] == "done")
        active_count = sum(1 for item in stages if item["status"] in {"done", "doing"})
        percent = round((complete_count / len(stages)) * 100) if stages else 0
        cover = (
            f"""<img src="{html.escape(source.get("cover_href") or "")}" alt="">"""
            if source.get("cover_href")
            else """<span>抖音</span>"""
        )
        stage_items = "".join(
            f"""<span class="stage-chip {html.escape(item["status"])}"><b>{html.escape(item["label"])}</b>{html.escape(item["text"])}</span>"""
            for item in stages
        )
        bar_items = "".join(
            f"""<span class="{html.escape(item["status"])}" title="{html.escape(item["label"] + '：' + item["text"])}"></span>"""
            for item in stages
        )
        rows.append(
            f"""
            <article class="source-row">
              <a class="source-cover" href="workbench.html?source={html.escape(source.get("source_content_id") or "")}">{cover}</a>
              <div class="source-main">
                <div class="source-head">
                  <div>
                    <small>{html.escape(source.get("published_at") or "")} · {html.escape(source.get("source_content_id") or "")}</small>
                    <h2>{html.escape(source.get("title") or "")}</h2>
                  </div>
                  <a class="open-link" href="workbench.html?source={html.escape(source.get("source_content_id") or "")}">打开工作台</a>
                </div>
                <div class="progress-meta"><b>{percent}%</b><span>{complete_count} 已完成 · {active_count - complete_count} 进行中 · {len(stages) - active_count} 未开始</span></div>
                <div class="stage-bar">{bar_items}</div>
                <div class="stage-list">{stage_items}</div>
              </div>
            </article>
            """
        )
    page = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <link rel="icon" href="data:," />
  <title>Park-IO Outbox 总览</title>
  <style>
    :root {{ color-scheme: light; --bg:#f5f6f2; --ink:#1c2421; --muted:#66706b; --line:#d9dfd7; --panel:#fff; --done:#176b5d; --doing:#c9822b; --todo:#d6dcd8; --blocked:#b94632; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; background:var(--bg); color:var(--ink); }}
    header {{ padding:30px 36px 18px; border-bottom:1px solid var(--line); background:#fbfcf8; }}
    h1 {{ margin:0 0 8px; font-size:28px; }}
    p {{ margin:0; color:var(--muted); line-height:1.55; }}
    main {{ padding:22px 36px 48px; }}
    .overview-top {{ display:flex; justify-content:space-between; gap:18px; align-items:end; }}
    .source-list {{ display:grid; gap:12px; max-width:1280px; }}
    .source-row {{ display:grid; grid-template-columns:120px minmax(0,1fr); gap:16px; padding:14px; background:var(--panel); border:1px solid var(--line); border-radius:10px; }}
    .source-cover {{ display:flex; align-items:center; justify-content:center; width:120px; aspect-ratio:3/4; border-radius:8px; overflow:hidden; background:#edf1ec; color:var(--muted); text-decoration:none; }}
    .source-cover img {{ width:100%; height:100%; object-fit:cover; }}
    .source-head {{ display:flex; justify-content:space-between; gap:16px; align-items:start; }}
    .source-head small {{ display:block; color:var(--muted); margin-bottom:4px; }}
    .source-head h2 {{ margin:0; font-size:18px; line-height:1.35; }}
    .open-link {{ flex:0 0 auto; color:var(--done); text-decoration:none; border:1px solid #b8d2c8; padding:7px 10px; border-radius:7px; background:#f8fbf8; }}
    .progress-meta {{ display:flex; gap:10px; align-items:center; margin:14px 0 8px; color:var(--muted); }}
    .progress-meta b {{ color:var(--ink); font-variant-numeric:tabular-nums; }}
    .stage-bar {{ display:grid; grid-template-columns:repeat(5,1fr); gap:4px; height:10px; margin-bottom:10px; }}
    .stage-bar span {{ background:var(--todo); border-radius:999px; }}
    .stage-bar .done {{ background:var(--done); }}
    .stage-bar .doing {{ background:var(--doing); }}
    .stage-bar .blocked {{ background:var(--blocked); }}
    .stage-list {{ display:flex; flex-wrap:wrap; gap:8px; }}
    .stage-chip {{ display:inline-flex; gap:6px; align-items:center; padding:6px 9px; border-radius:999px; border:1px solid var(--line); color:var(--muted); background:#f8faf7; font-size:13px; }}
    .stage-chip b {{ color:var(--ink); }}
    .stage-chip.done {{ border-color:#b8d7c9; background:#e7f4ed; color:#176b42; }}
    .stage-chip.doing {{ border-color:#ead0a9; background:#fff4df; color:#835016; }}
    .stage-chip.blocked {{ border-color:#e5b8ae; background:#fff0ed; color:#933825; }}
    @media (max-width:720px) {{ header, main {{ padding-left:16px; padding-right:16px; }} .source-row {{ grid-template-columns:84px minmax(0,1fr); }} .source-cover {{ width:84px; }} .source-head {{ display:block; }} .open-link {{ display:inline-block; margin-top:10px; }} }}
  </style>
</head>
<body>
  <header>
    <div class="overview-top">
      <div>
        <h1>Park-IO Outbox 总览</h1>
        <p>{html.escape(str(model.get("counts", {}).get("sources") or 0))} 条内容 · 生成时间：{html.escape(model.get("generated_at") or "")}</p>
      </div>
      <p>总览只看进度；点开某条视频后进入详情工作台。</p>
    </div>
  </header>
  <main>
    <section class="source-list">
      {''.join(rows) or '<p>暂无 outbox 内容。</p>'}
    </section>
  </main>
</body>
</html>
"""
    (OUT / "dashboard.html").write_text(page, encoding="utf-8")


def write_html(assets: list[dict], summary: list[dict], output_name: str = "workbench.html") -> None:
    platforms = load_platforms()
    model = build_workbench_model(assets, platforms, summary)
    model_json = json.dumps(model, ensure_ascii=False).replace("</", "<\\/")
    production = model["production"]
    action_queue = model.get("action_queue") or {}
    action_cards = [
        {
            "label": "待审核",
            "value": production["review_needed"],
            "note": "小红书 / 公众号 / X 草稿",
            "icon": "✍",
            "tone": "warn",
            "filter": "",
        },
        {
            "label": "可推送",
            "value": production["ready_to_push"],
            "note": "已生成草稿或图文包",
            "icon": "↗",
            "tone": "ok",
            "filter": "xiaohongshu",
        },
        {
            "label": "质量问题",
            "value": production["quality_issues"],
            "note": "小红书未过质检或图片偏少",
            "icon": "!",
            "tone": "warn",
            "filter": "xiaohongshu",
        },
        {
            "label": "修复队列",
            "value": action_queue.get("total_actions", 0),
            "note": "blocked source 下一步",
            "icon": "↻",
            "tone": "bad" if action_queue.get("total_actions") else "done",
            "filter": "xiaohongshu",
        },
        {
            "label": "缺素材",
            "value": production["missing_assets"],
            "note": "视频迁移缺源视频",
            "icon": "□",
            "tone": "bad",
            "filter": "",
        },
        {
            "label": "可迁移",
            "value": production["migration_ready"],
            "note": "视频号 / Bilibili / YouTube",
            "icon": "▶",
            "tone": "ok",
            "filter": "wechat_channels",
        },
        {
            "label": "已发送",
            "value": production["sent"],
            "note": "非抖音平台 sent 记录",
            "icon": "✓",
            "tone": "done",
            "filter": "",
        },
    ]
    platform_cards = []
    for card in action_cards:
        platform_cards.append(
            f"""
            <button class="action-card {html.escape(card['tone'])}" type="button" data-focus-platform="{html.escape(card['filter'])}">
              <span class="action-card-icon">{html.escape(card['icon'])}</span>
              <span class="action-card-body">
                <span class="action-card-label">{html.escape(card['label'])}</span>
                <strong>{card['value']}</strong>
                <small>{html.escape(card['note'])}</small>
              </span>
            </button>
            """
        )
    lane_labels = {
        "auto_repair_candidate": "可自动修复",
        "auto_recheck_candidate": "可重跑质检",
        "manual_reingest_or_drop": "需重抓/跳过",
        "manual_merge_or_drop": "需合并/丢弃",
        "manual_investigate": "需人工检查",
    }
    lane_chips = "".join(
        f"""<span class="workflow-chip">{html.escape(lane_labels.get(lane, lane))} {count}</span>"""
        for lane, count in sorted((action_queue.get("lane_counts") or {}).items())
    )
    auto_repair_count = int((action_queue.get("lane_counts") or {}).get("auto_repair_candidate") or 0)
    auto_repair_disabled = "" if auto_repair_count else " disabled"
    action_queue_hint = (
        "有可自动修复项时，先 dry-run，再 apply；按钮只处理 auto_repair_candidate。"
        if auto_repair_count
        else "当前没有可自动修复项；剩余 blocked source 需要重抓、合并或丢弃。"
    )
    action_queue_rows = []
    for item in action_queue.get("actions") or []:
        lane = item.get("lane") or ""
        decision_buttons = ""
        if lane == "manual_reingest_or_drop":
            decision_buttons = f"""
              <div class="action-row compact">
                <button class="command" type="button" data-action="record-action-decision" data-decision="reingest" data-draft-path="{html.escape(item.get('draft_path') or '')}" data-source-id="{html.escape(str(item.get('source_content_id') or ''))}">标记重抓</button>
                <button class="command" type="button" data-action="record-action-decision" data-decision="skip" data-draft-path="{html.escape(item.get('draft_path') or '')}" data-source-id="{html.escape(str(item.get('source_content_id') or ''))}">标记跳过</button>
              </div>
            """
        elif lane == "manual_merge_or_drop":
            decision_buttons = f"""
              <div class="action-row compact">
                <button class="command" type="button" data-action="record-action-decision" data-decision="merge" data-draft-path="{html.escape(item.get('draft_path') or '')}" data-source-id="{html.escape(str(item.get('source_content_id') or ''))}">标记合并</button>
                <button class="command" type="button" data-action="record-action-decision" data-decision="drop" data-draft-path="{html.escape(item.get('draft_path') or '')}" data-source-id="{html.escape(str(item.get('source_content_id') or ''))}">标记丢弃</button>
              </div>
            """
        action_queue_rows.append(
            f"""
            <article class="action-queue-item">
              <div class="row"><code>#{html.escape(str(item.get('priority') or ''))}</code><span class="status review_needed">{html.escape(lane_labels.get(lane, lane))}</span></div>
              <strong>{html.escape(item.get('draft_title') or '')}</strong>
              <p>{html.escape(item.get('source_unit_title') or item.get('reason') or '')}</p>
              <small>{html.escape(str(item.get('source_content_id') or ''))} · {html.escape(str(item.get('source_excerpt_chars') or 0))} 字</small>
              {decision_buttons}
            </article>
            """
        )
    resolved_rows = []
    for item in action_queue.get("resolved") or []:
        decision = item.get("decision") or {}
        resolved_rows.append(
            f"""
            <article class="action-queue-item resolved">
              <div class="row"><code>#{html.escape(str(item.get('priority') or ''))}</code><span class="status sent">{html.escape(decision.get('label') or decision.get('decision') or '已决策')}</span></div>
              <strong>{html.escape(item.get('draft_title') or '')}</strong>
              <p>{html.escape(item.get('source_unit_title') or decision.get('reason') or '')}</p>
              <small>{html.escape(str(item.get('source_content_id') or ''))} · {html.escape(decision.get('reason') or '无备注')}</small>
              <div class="action-row compact">
                <button class="command" type="button" data-action="clear-action-decision" data-draft-path="{html.escape(item.get('draft_path') or '')}" data-source-id="{html.escape(str(item.get('source_content_id') or ''))}">撤回决策</button>
              </div>
            </article>
            """
        )
    action_queue_html = f"""
    <section class="panel action-queue-panel">
      <div class="action-queue-head">
        <div>
          <h2>下一步行动队列</h2>
          <p>{html.escape(action_queue_hint)}</p>
        </div>
        <div class="action-row">
          <button class="command" type="button" data-action="run-action-queue" data-mode="dry-run"{auto_repair_disabled}>预演自动修复</button>
          <button class="command" type="button" data-action="run-action-queue" data-mode="apply"{auto_repair_disabled}>执行自动修复</button>
          <a href="{html.escape(action_queue.get('report_href') or '')}" target="_blank" rel="noreferrer">打开队列报告</a>
        </div>
      </div>
      <div class="workflow-meta">{lane_chips or '<span class="workflow-chip">暂无 blocked source</span>'}</div>
      <p class="muted-line">已记录人工决策 {html.escape(str(action_queue.get('resolved_count') or 0))} 条。</p>
      <div class="action-queue-list">{''.join(action_queue_rows) or '<p>当前没有待处理行动。</p>'}</div>
      {f'<details class="resolved-queue"><summary>已决策项目</summary><div class="action-queue-list">{"".join(resolved_rows)}</div></details>' if resolved_rows else ''}
    </section>
    """
    platform_headers = "".join(f"<th>{html.escape(platform['label'])}</th>" for platform in model["platforms"])
    source_rows = []
    for source in model["sources"]:
        cells = []
        for platform in model["platforms"]:
            state = source["platforms"][platform["id"]]
            detail = ""
            if platform["id"] == "xiaohongshu" and state.get("draft_count"):
                detail = f"<small>{state.get('quality_passed', 0)} 质检 · {state.get('packaged_count', 0)} 包</small>"
            elif state.get("draft_count"):
                detail = f"<small>{state['draft_count']} draft</small>"
            link_start = f"<a href=\"{html.escape(state['primary_href'])}\">" if state.get("primary_href") else ""
            link_end = "</a>" if state.get("primary_href") else ""
            cells.append(
                f"""<td><span class="status {html.escape(state['status'])}">{link_start}{html.escape(state['label'])}{link_end}</span>{detail}</td>"""
            )
        source_rows.append(
            f"""
            <tr data-source-id="{html.escape(source['source_content_id'])}">
              <td>
                <button class="source-button" type="button" data-source-id="{html.escape(source['source_content_id'])}">
                  <span>{html.escape(source['published_at'])}</span>
                  <strong>{html.escape(source['title'])}</strong>
                  <code>{html.escape(source['source_content_id'])}</code>
                </button>
              </td>
              {''.join(cells)}
            </tr>
            """
        )
    source_cards = []
    for source in model["sources"]:
        platform_dots = "".join(
            f"""<span class="mini-status {html.escape(source["platforms"][platform["id"]]["status"])}" title="{html.escape(platform["label"])}">{html.escape(PLATFORM_ICONS.get(platform["id"], "•"))}</span>"""
            for platform in model["platforms"]
        )
        cover = (
            f"""<img src="{html.escape(source["cover_href"])}" alt="">"""
            if source.get("cover_href")
            else """<div class="source-thumb-fallback">抖音</div>"""
        )
        source_cards.append(
            f"""
            <button class="flow-source-card" type="button" data-source-id="{html.escape(source['source_content_id'])}">
              <span class="source-thumb">{cover}</span>
              <span class="source-card-body">
                <span class="source-date">{html.escape(source['published_at'])}</span>
                <strong>{html.escape(source['title'])}</strong>
                <span class="source-card-meta">{html.escape(source['source_content_id'])} · {source['media_count']} 视频 · {source['cover_count']} 封面</span>
                <span class="source-mini-statuses">{platform_dots}</span>
              </span>
            </button>
            """
        )
    page = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <link rel="icon" href="data:," />
  <title>Park-IO Outbox 工作台</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f5f6f2;
      --ink: #1c2421;
      --muted: #66706b;
      --line: #d9dfd7;
      --fill: #176b5d;
      --accent: #a94f2a;
      --panel: #ffffff;
      --soft: #eef3ed;
      --warn: #fff4dc;
      --warn-ink: #8a4b0f;
      --ok: #e4f4ed;
      --ok-ink: #176b42;
      --todo: #eef1f5;
      --todo-ink: #4b5563;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: var(--bg);
      color: var(--ink);
    }}
    header {{
      padding: 28px 36px 18px;
      border-bottom: 1px solid var(--line);
      background: #fbfcf8;
    }}
    h1 {{ margin: 0 0 8px; font-size: 28px; letter-spacing: 0; }}
    p {{ color: var(--muted); margin: 0; line-height: 1.5; }}
    main {{ padding: 22px 36px 48px; }}
    .topline {{
      display:flex;
      justify-content:space-between;
      gap:16px;
      align-items:end;
    }}
    .stats {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
      gap: 12px;
      margin-bottom: 18px;
    }}
    .platform-card, .panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
    }}
    .card-top {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: baseline;
      margin-bottom: 10px;
    }}
    h2 {{ font-size: 16px; margin: 0; letter-spacing: 0; }}
    h3 {{ font-size: 14px; margin: 0 0 10px; color: var(--muted); font-weight: 650; }}
    .card-top span {{ font-variant-numeric: tabular-nums; color: var(--accent); }}
    .action-card {{
      min-height: 104px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      padding: 12px;
      display: grid;
      grid-template-columns: 36px minmax(0, 1fr);
      gap: 10px;
      align-items: center;
      color: inherit;
      text-align: left;
      cursor: pointer;
    }}
    .action-card:hover {{
      border-color: #9fc4b4;
      box-shadow: 0 1px 0 rgba(20, 60, 45, .08);
    }}
    .action-card-icon {{
      width: 36px;
      height: 36px;
      border-radius: 8px;
      display: grid;
      place-items: center;
      background: #eef3ed;
      color: var(--fill);
      font-weight: 900;
      font-size: 18px;
    }}
    .action-card.warn .action-card-icon {{ color:#9a5d16; background:#fff3d8; }}
    .action-card.bad .action-card-icon {{ color:#9c3529; background:#fff0ec; }}
    .action-card.done .action-card-icon {{ color:#22664d; background:#e4f4ed; }}
    .action-card-body {{
      min-width:0;
      display:grid;
      gap:2px;
    }}
    .action-card-label {{
      color:var(--muted);
      font-size:12px;
      font-weight:750;
    }}
    .action-card strong {{
      font-size:28px;
      line-height:1;
      font-variant-numeric:tabular-nums;
    }}
    .action-card small {{
      line-height:1.3;
    }}
    .platform-icon {{
      width: 28px;
      height: 28px;
      border-radius: 8px;
      display: inline-grid;
      place-items: center;
      margin-right: 8px;
      background: #eef3ed;
      color: var(--fill);
      font-weight: 850;
    }}
    .bar {{
      height: 8px;
      border-radius: 999px;
      background: #e7e9e3;
      overflow: hidden;
      margin-bottom: 10px;
    }}
    .bar div {{ height: 100%; background: var(--fill); }}
    small {{ color: var(--muted); }}
    a {{ color: var(--fill); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    .layout {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) 390px;
      gap: 16px;
      align-items: start;
    }}
    .matrix-wrap {{
      overflow-x: auto;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      background: var(--panel);
    }}
    th, td {{
      padding: 9px 10px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      vertical-align: top;
      font-size: 13px;
    }}
    th {{ color: var(--muted); font-weight: 650; white-space: nowrap; background:#fbfcf8; position:sticky; top:0; }}
    tr.active td {{ background: #f5faf7; }}
    section.block {{ margin-top: 18px; }}
    .toolbar {{
      display: flex;
      align-items: center;
      gap: 10px;
      margin-bottom: 12px;
      flex-wrap: wrap;
    }}
    select, button.command, button.action {{
      border: 1px solid var(--line);
      border-radius: 6px;
      background: var(--panel);
      color: var(--ink);
      padding: 8px 10px;
      font: inherit;
      cursor: pointer;
    }}
    button.action.primary {{
      background: var(--fill);
      border-color: var(--fill);
      color: #fff;
      font-weight: 700;
    }}
    button.action.approve {{
      background:#e5f5ee;
      border-color:#9bcfba;
      color:#1f684e;
      font-weight:800;
    }}
    button.command:disabled, button.action:disabled {{
      cursor: not-allowed;
      opacity: .55;
    }}
    .action-row {{
      display:flex;
      gap:8px;
      flex-wrap:wrap;
      margin-top:8px;
    }}
    .action-row.compact button {{
      padding: 6px 8px;
      font-size: 12px;
    }}
    .muted-line {{
      margin: 8px 0 0;
      color: var(--muted);
      font-size: 13px;
    }}
    .resolved-queue {{
      margin-top: 12px;
      border-top: 1px solid var(--line);
      padding-top: 10px;
    }}
    .resolved-queue summary {{
      cursor: pointer;
      color: var(--muted);
      font-weight: 700;
    }}
    .notice {{
      margin: 0 0 18px;
      padding: 10px 12px;
      border: 1px solid #d7dfdb;
      border-radius: 8px;
      background: #f7faf8;
      color: var(--muted);
      display:flex;
      justify-content:space-between;
      gap:12px;
      align-items:center;
    }}
    .notice-actions {{ display:flex; gap:8px; flex-wrap:wrap; justify-content:flex-end; }}
    .usage-panel {{
      display:grid;
      grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
      gap:10px;
      margin:0 0 18px;
    }}
    .usage-step {{
      border:1px solid var(--line);
      border-radius:8px;
      background:var(--panel);
      padding:12px;
    }}
    .usage-step b {{ display:block; margin-bottom:5px; font-size:13px; }}
    .usage-step p {{ font-size:12px; line-height:1.45; }}
    .setup-grid {{
      display:grid;
      grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
      gap:10px;
      margin:0 0 18px;
    }}
    .setup-item {{
      border:1px solid var(--line);
      border-radius:8px;
      background:#fbfcf8;
      padding:12px;
    }}
    .setup-item header {{
      padding:0;
      border:0;
      background:transparent;
      display:flex;
      justify-content:space-between;
      gap:8px;
      align-items:center;
      margin-bottom:7px;
    }}
    .setup-item p {{ font-size:12px; line-height:1.45; }}
    .auth-helper {{
      display:grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap:10px;
      margin-top:12px;
    }}
    .auth-helper-card {{
      border:1px solid var(--line);
      border-radius:8px;
      background:#fff;
      padding:12px;
    }}
    .auth-helper-card h3 {{
      margin:0 0 8px;
      font-size:14px;
    }}
    .auth-helper-card ol {{
      margin:8px 0 0 18px;
      padding:0;
      color:var(--muted);
      font-size:12px;
      line-height:1.45;
    }}
    .auth-helper-card code {{
      display:block;
      margin-top:6px;
      white-space:normal;
      word-break:break-all;
    }}
    .admin-panel {{
      margin:0 0 18px;
      border:1px solid var(--line);
      border-radius:8px;
      background:#fbfcf8;
      padding:10px 12px;
    }}
    .admin-panel.debug-hidden {{
      display:none;
    }}
    .admin-panel summary {{
      cursor:pointer;
      font-weight:700;
      color:var(--ink);
    }}
    .admin-tools {{
      margin-top:12px;
      display:grid;
      gap:12px;
    }}
    .flow-workbench {{
      display:grid;
      grid-template-columns: minmax(0, 1fr);
      gap:16px;
      align-items:start;
    }}
    .single-workflow-shell {{
      max-width: 1180px;
      margin: 0 auto;
    }}
    .source-rail {{
      display:grid;
      gap:8px;
      max-height: calc(100vh - 190px);
      overflow:auto;
      padding-right:4px;
    }}
    .flow-source-card {{
      border:1px solid var(--line);
      border-radius:8px;
      background:var(--panel);
      padding:9px;
      display:grid;
      grid-template-columns:112px minmax(0,1fr);
      gap:12px;
      text-align:left;
      color:inherit;
      cursor:pointer;
    }}
    .flow-source-card.active {{
      border-color:#97c3ad;
      background:#f4fbf6;
      box-shadow: inset 3px 0 0 var(--fill);
    }}
    .source-thumb {{
      width:112px;
      aspect-ratio: 3 / 4;
      border-radius:6px;
      overflow:hidden;
      border:1px solid var(--line);
      background:#eef1ec;
      display:grid;
      place-items:center;
      flex:none;
    }}
    .source-thumb img {{
      width:100%;
      height:100%;
      object-fit:contain;
      display:block;
      background:#f5f6f2;
    }}
    .source-thumb-fallback {{
      color:var(--muted);
      font-weight:800;
      font-size:13px;
    }}
    .source-card-body {{
      min-width:0;
      display:grid;
      gap:4px;
    }}
    .source-date, .source-card-meta {{
      font-size:12px;
      color:var(--muted);
    }}
    .source-card-body strong {{
      font-size:13px;
      line-height:1.3;
      color:var(--ink);
      display:-webkit-box;
      -webkit-line-clamp:2;
      -webkit-box-orient:vertical;
      overflow:hidden;
    }}
    .source-mini-statuses {{
      display:flex;
      gap:4px;
      flex-wrap:wrap;
      margin-top:2px;
    }}
    .mini-status {{
      border:1px solid var(--line);
      border-radius:7px;
      width:24px;
      height:22px;
      display:inline-grid;
      place-items:center;
      font-size:12px;
      font-weight:800;
      color:var(--muted);
      background:#f8faf6;
    }}
    .mini-status.sent, .mini-status.packaged, .mini-status.ready_to_package {{ color:var(--ok-ink); background:var(--ok); border-color:#c9e8d8; }}
    .mini-status.review_needed {{ color:var(--warn-ink); background:var(--warn); border-color:#edd5a8; }}
    .mini-status.missing_asset {{ color:#8b2b20; background:#fff0ec; border-color:#f1c8bd; }}
    .flow-panel {{
      min-height:640px;
    }}
    .flow-detail {{
      display:grid;
      gap:14px;
    }}
    .source-node {{
      border:1px solid var(--line);
      border-radius:8px;
      background:#fbfcf8;
      padding:12px;
      display:grid;
      grid-template-columns:156px minmax(0,1fr);
      gap:14px;
    }}
    .source-node .source-thumb {{ width:156px; }}
    .source-node h2 {{
      font-size:18px;
      line-height:1.28;
      margin:0 0 6px;
    }}
    .source-links {{
      display:flex;
      gap:10px;
      flex-wrap:wrap;
      margin-top:8px;
      font-size:12px;
    }}
    .flow-lanes {{
      display:grid;
      gap:14px;
    }}
    .flow-lane {{
      display:grid;
      grid-template-columns:minmax(0,1fr);
      gap:10px;
      align-items:start;
    }}
    .flow-lane.review-lane {{
      border:1px solid var(--line);
      border-radius:8px;
      background:#fbfcf8;
      padding:12px;
    }}
    .review-lane-header {{
      display:flex;
      justify-content:space-between;
      gap:10px;
      align-items:center;
      margin-bottom:10px;
    }}
    .review-lane-title {{
      display:flex;
      gap:8px;
      align-items:center;
      font-weight:800;
    }}
    .migration-strip {{
      border-top:1px solid var(--line);
      padding-top:12px;
      display:grid;
      grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
      gap:8px;
    }}
    .workflow-step {{
      border:1px solid var(--line);
      border-radius:8px;
      background:#fff;
      padding:14px;
      display:grid;
      gap:12px;
    }}
    .workflow-step.is-done {{
      background:#eff8f2;
      border-color:#b9dfcb;
      box-shadow: inset 4px 0 0 #29885d;
    }}
    .workflow-step.is-current {{
      background:#fffaf0;
      border-color:#e4c27b;
      box-shadow: inset 4px 0 0 #c9891b;
    }}
    .workflow-step.is-warn {{
      background:#fff8e8;
      border-color:#ead6a8;
    }}
    .workflow-step.is-locked {{
      background:#f7f8f5;
      opacity:.82;
    }}
    .step-status {{
      display:flex;
      gap:8px;
      align-items:center;
      flex-wrap:wrap;
    }}
    .workflow-step header {{
      display:flex;
      justify-content:space-between;
      gap:12px;
      align-items:flex-start;
      padding:0;
      border:0;
      background:transparent;
    }}
    .workflow-step h2 {{
      margin:0 0 4px;
    }}
    .workflow-step p {{
      margin:0;
      color:var(--muted);
      font-size:13px;
      line-height:1.45;
    }}
    .migration-choice-grid {{
      display:grid;
      grid-template-columns:repeat(auto-fit, minmax(180px, 1fr));
      gap:10px;
    }}
    .migration-status-grid {{
      display:grid;
      grid-template-columns:repeat(auto-fit, minmax(180px, 1fr));
      gap:10px;
    }}
    .migration-status-item {{
      border:1px solid var(--line);
      border-radius:8px;
      padding:10px;
      background:#fbfcf8;
      display:grid;
      gap:8px;
    }}
    .migration-status-item.done {{
      background:#f3fbf6;
      border-color:#c9e8d8;
    }}
    .migration-status-item.failed {{
      background:#fff0ec;
      border-color:#f1c8bd;
    }}
    .migration-status-item.waiting {{
      background:#fff8e8;
      border-color:#ead6a8;
    }}
    .migration-status-top {{
      display:flex;
      justify-content:space-between;
      gap:10px;
      align-items:center;
    }}
    .migration-status-item p {{
      font-size:12px;
      color:var(--muted);
      margin:0;
    }}
    .migration-status-item .action-row {{
      margin-top:0;
    }}
    .evidence-shot {{
      margin-top:2px;
      border:1px solid var(--line);
      border-radius:8px;
      overflow:hidden;
      background:#fff;
      cursor:pointer;
      aspect-ratio:16 / 9;
    }}
    .evidence-shot img {{
      width:100%;
      height:100%;
      object-fit:cover;
      display:block;
    }}
    .migration-choice {{
      border:1px solid var(--line);
      border-radius:8px;
      padding:10px;
      background:#fbfcf8;
      display:grid;
      gap:8px;
    }}
    .migration-choice label {{
      display:flex;
      align-items:center;
      gap:8px;
      font-weight:800;
      cursor:pointer;
    }}
    .migration-choice input {{
      width:16px;
      height:16px;
    }}
    .migration-choice.is-disabled {{
      opacity:.55;
    }}
    .migration-choice small {{
      color:var(--muted);
      line-height:1.35;
    }}
    .content-package-grid {{
      display:grid;
      grid-template-columns:repeat(auto-fit, minmax(210px, 1fr));
      gap:10px;
    }}
    .content-package-card {{
      border:1px solid var(--line);
      border-radius:8px;
      background:#fbfcf8;
      padding:10px;
      display:grid;
      gap:6px;
    }}
    .content-package-card b {{
      font-size:18px;
    }}
    .content-package-card.warn {{
      background:#fff8e8;
      border-color:#ead6a8;
    }}
    .package-status-line {{
      display:flex;
      flex-wrap:wrap;
      gap:8px;
      align-items:center;
      font-size:12px;
      color:var(--muted);
    }}
    .transcript-reader {{
      max-height:420px;
      overflow:auto;
      border:1px solid var(--line);
      border-radius:8px;
      background:#fcfdf9;
      padding:16px 18px;
      color:#24312b;
      font-size:15px;
      line-height:1.85;
    }}
    .transcript-reader p {{
      margin:0 0 14px;
      color:#24312b;
      font-size:15px;
      line-height:1.85;
    }}
    .transcript-reader .empty {{
      color:var(--muted);
      margin:0;
    }}
    .migration-card {{
      border:1px solid var(--line);
      border-radius:8px;
      background:var(--panel);
      padding:9px;
      display:grid;
      gap:7px;
    }}
    .migration-card header {{
      padding:0;
      border:0;
      background:transparent;
      display:flex;
      justify-content:space-between;
      gap:8px;
      align-items:center;
    }}
    .migration-card .node-actions {{
      margin-top:0;
    }}
    .platform-node, .draft-node, .empty-node {{
      border:1px solid var(--line);
      border-radius:8px;
      background:var(--panel);
      padding:10px;
    }}
    .platform-node header, .draft-node header {{
      padding:0;
      border:0;
      background:transparent;
      display:flex;
      justify-content:space-between;
      gap:8px;
      align-items:center;
      margin-bottom:6px;
    }}
    .platform-node p, .draft-node p, .empty-node p {{
      font-size:12px;
      line-height:1.45;
      color:var(--muted);
      margin-top:5px;
    }}
    .flow-arrow {{
      position:relative;
      height:42px;
      margin-top:16px;
    }}
    .flow-arrow::before {{
      content:"";
      position:absolute;
      left:0;
      right:7px;
      top:20px;
      border-top:1px solid #b9c4bd;
    }}
    .flow-arrow::after {{
      content:"";
      position:absolute;
      right:0;
      top:15px;
      border-left:8px solid #b9c4bd;
      border-top:6px solid transparent;
      border-bottom:6px solid transparent;
    }}
    .draft-branch {{
      display:grid;
      gap:8px;
    }}
    .preview-grid {{
      display:grid;
      grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
      gap:10px;
    }}
    .topic-stack {{
      display:grid;
      grid-template-columns:1fr;
      gap:12px;
    }}
    .draft-preview {{
      border:1px solid var(--line);
      border-radius:8px;
      background:var(--panel);
      overflow:hidden;
    }}
    .draft-preview header {{
      padding:10px;
      border:0;
      border-bottom:1px solid var(--line);
      background:#fff;
      display:flex;
      gap:8px;
      justify-content:space-between;
      align-items:flex-start;
    }}
    .draft-preview h3 {{
      margin:0;
      color:var(--ink);
      font-size:14px;
      line-height:1.35;
    }}
    .draft-preview p {{
      padding:10px;
      font-size:12px;
      line-height:1.55;
      color:var(--muted);
      margin:0;
    }}
    .wechat-article-preview {{
      grid-column:1 / -1;
      background:#edf2ed;
    }}
    .wechat-preview-frame {{
      width:100%;
      height:760px;
      border:0;
      background:#fff;
      display:block;
    }}
    .wechat-style-bar {{
      display:flex;
      gap:10px;
      align-items:center;
      padding:10px;
      border-bottom:1px solid var(--line);
      background:#fbfcf8;
    }}
    .wechat-style-bar b {{
      font-size:12px;
      color:var(--muted);
      white-space:nowrap;
    }}
    .wechat-style-options {{
      display:flex;
      gap:8px;
      flex-wrap:wrap;
    }}
    .wechat-style-summary {{
      padding:10px;
      border-bottom:1px solid var(--line);
      background:#fff;
    }}
    .wechat-style-card {{
      display:none;
      gap:8px;
      align-items:flex-start;
    }}
    .wechat-style-card.active {{
      display:grid;
    }}
    .wechat-style-card strong {{
      color:var(--ink);
      font-size:13px;
      line-height:1.4;
    }}
    .wechat-style-card p {{
      padding:0;
      color:var(--muted);
      font-size:12px;
      line-height:1.55;
    }}
    .wechat-style-metrics {{
      display:flex;
      gap:6px;
      flex-wrap:wrap;
    }}
    .wechat-style-metrics span {{
      border:1px solid var(--line);
      background:#fbfcf8;
      color:var(--muted);
      border-radius:999px;
      padding:4px 8px;
      font-size:11px;
    }}
    .wechat-style-thumbs {{
      display:flex;
      gap:8px;
      overflow-x:auto;
      padding-top:4px;
    }}
    .wechat-style-thumbs img {{
      width:108px;
      height:66px;
      object-fit:cover;
      border:1px solid var(--line);
      border-radius:6px;
      background:#fff;
      cursor:pointer;
    }}
    .style-choice {{
      border:1px solid var(--line);
      background:#fff;
      color:var(--muted);
      border-radius:999px;
      padding:6px 10px;
      font-size:12px;
      cursor:pointer;
    }}
    .style-choice.active {{
      border-color:var(--accent);
      background:#e6f4ed;
      color:var(--accent-strong);
      font-weight:700;
    }}
    .wechat-style-frame {{
      display:none;
    }}
    .wechat-style-frame.active {{
      display:block;
    }}
    .wechat-preview-note {{
      padding:9px 10px;
      color:var(--muted);
      font-size:12px;
      border-top:1px solid var(--line);
      background:#fbfcf8;
    }}
    .empty-preview {{
      padding:18px;
      background:#fff;
      border-top:1px solid var(--line);
      color:var(--muted);
      line-height:1.65;
    }}
    .empty-preview strong {{
      display:block;
      color:var(--ink);
      margin-bottom:8px;
    }}
    .wechat-push-meta {{
      display:flex;
      align-items:center;
      gap:8px;
      flex-wrap:wrap;
      padding:9px 10px;
      border-top:1px solid var(--line);
      background:#fffef9;
    }}
    .wechat-push-meta code {{
      max-width:100%;
      overflow:hidden;
      text-overflow:ellipsis;
      white-space:nowrap;
      color:var(--muted);
      font-size:11px;
    }}
    .wechat-push-meta p {{
      padding:0;
      flex-basis:100%;
      font-size:11px;
    }}
    .wechat-evidence {{
      margin:10px;
      max-width:360px;
      aspect-ratio:3 / 4;
    }}
    .wechat-evidence-details {{
      margin:10px;
      border:1px solid var(--line);
      border-radius:8px;
      background:#fbfcf8;
    }}
    .wechat-evidence-details summary {{
      cursor:pointer;
      padding:8px 10px;
      font-size:12px;
      font-weight:700;
      color:var(--ink);
      display:flex;
      justify-content:space-between;
      gap:10px;
      align-items:center;
    }}
    .wechat-evidence-details summary span {{
      font-weight:500;
      color:var(--muted);
    }}
    .wechat-evidence-details .wechat-evidence {{
      margin:0 10px 10px;
    }}
    .workflow-meta {{
      padding:10px 10px 0;
      display:flex;
      flex-wrap:wrap;
      gap:6px;
    }}
    .workflow-chip {{
      border:1px solid #cfe2d6;
      border-radius:999px;
      background:#eff8f2;
      color:#1d6845;
      padding:3px 7px;
      font-size:11px;
      line-height:1.2;
      font-weight:700;
    }}
    .workflow-chip.warn {{
      border-color:#f1d2a8;
      background:#fff7e9;
      color:#8a4b00;
    }}
    .brief-line {{
      padding:6px 10px 0;
      color:var(--muted);
      font-size:11px;
      line-height:1.45;
    }}
    .brief-line.blocked {{
      color:#8a4b00;
      font-weight:700;
    }}
    .topic-pill {{
      border:1px solid var(--line);
      border-radius:8px;
      background:#fff;
      padding:14px;
      display:grid;
      gap:12px;
    }}
    .topic-framework {{
      width:100%;
      background:#fffdf8;
      border-color:#d8e4d6;
    }}
    .topic-framework header {{
      display:flex;
      justify-content:space-between;
      gap:12px;
      align-items:flex-start;
    }}
    .topic-pill b {{
      font-size:15px;
      line-height:1.35;
    }}
    .topic-pill p {{
      font-size:12px;
      line-height:1.45;
      color:var(--muted);
      margin:0;
    }}
    .topic-subtitle {{
      margin-top:4px !important;
      color:#6a756d !important;
    }}
    .topic-framework-grid {{
      display:grid;
      grid-template-columns:repeat(auto-fit, minmax(240px, 1fr));
      gap:10px;
    }}
    .topic-framework-grid section {{
      border:1px solid #dfe8dd;
      border-radius:8px;
      background:#fbfcf8;
      padding:10px;
      display:grid;
      gap:5px;
    }}
    .topic-framework-grid .reader-mirror-section {{
      background:#eef8f3;
      border-color:#bfe4d4;
    }}
    .reader-mirror,
    .reader-mirror-section p {{
      color:#1f4f40 !important;
      font-weight:700;
    }}
    .topic-framework-grid span,
    .topic-evidence-label {{
      font-size:11px;
      font-weight:800;
      color:#23735a;
      letter-spacing:0;
    }}
    .topic-points {{
      display:grid;
      gap:8px;
    }}
    .topic-point {{
      display:grid;
      grid-template-columns:28px 1fr;
      gap:10px;
      border:1px solid #e4e7df;
      border-radius:8px;
      background:#fff;
      padding:10px;
    }}
    .topic-point > span {{
      width:28px;
      height:28px;
      border-radius:999px;
      display:grid;
      place-items:center;
      background:#e2f3ec;
      color:#1b6d53;
      font-weight:900;
      font-size:12px;
    }}
    .topic-point div {{
      display:grid;
      gap:4px;
    }}
    .topic-point b {{
      font-size:13px;
    }}
    .topic-point strong {{
      color:#24362e;
    }}
    .topic-merge {{
      padding:8px 10px;
      border-radius:8px;
      background:#f7f8f5;
      color:#56645d !important;
    }}
    .topic-evidence {{
      margin:2px 0 0;
      padding:8px 10px 8px 18px;
      border-radius:8px;
      background:#f7f8f5;
      color:#3f4b45;
      font-size:12px;
      line-height:1.5;
    }}
    .topic-evidence li {{
      margin:0 0 4px;
    }}
    .topic-evidence-label {{
      margin-top:2px;
    }}
    .xhs-text-stack {{
      display:grid;
      gap:14px;
    }}
    .xhs-text-draft {{
      border:1px solid #d8e4d6;
      border-radius:10px;
      background:#fffdf8;
      padding:14px;
      display:grid;
      gap:12px;
    }}
    .xhs-text-draft header {{
      display:flex;
      justify-content:space-between;
      gap:12px;
      align-items:flex-start;
      border:0;
      padding:0 0 10px;
      border-bottom:1px solid #e5eadf;
      background:transparent;
    }}
    .xhs-text-draft h3 {{
      margin:0;
      color:var(--ink);
      font-size:17px;
      line-height:1.35;
    }}
    .xhs-text-body {{
      max-height:360px;
      overflow:auto;
      padding:12px;
      border-radius:8px;
      background:#fff;
      border:1px solid #e5eadf;
    }}
    .xhs-text-body p {{
      margin:0 0 12px;
      color:#25312b;
      font-size:14px;
      line-height:1.7;
    }}
    .xhs-structure-check {{
      border-top:1px solid #e5eadf;
      padding-top:8px;
    }}
    .xhs-structure-check summary {{
      cursor:pointer;
      color:#23735a;
      font-weight:800;
      font-size:12px;
    }}
    .xhs-check-grid {{
      display:grid;
      grid-template-columns:repeat(auto-fit, minmax(220px, 1fr));
      gap:8px;
      margin-top:8px;
    }}
    .xhs-check-grid section {{
      border:1px solid #dfe8dd;
      border-radius:8px;
      background:#fbfcf8;
      padding:9px;
    }}
    .xhs-check-grid span {{
      display:block;
      margin-bottom:4px;
      color:#23735a;
      font-size:11px;
      font-weight:800;
    }}
    .xhs-check-grid p {{
      padding:0;
      margin:0;
      color:var(--muted);
      font-size:12px;
      line-height:1.45;
    }}
    .xhs-image-strip {{
      display:flex;
      gap:6px;
      overflow-x:auto;
      padding:10px;
      background:#f6f8f4;
      border-bottom:1px solid var(--line);
    }}
    .xhs-image-strip img {{
      width:76px;
      aspect-ratio:3/4;
      object-fit:cover;
      border-radius:6px;
      border:1px solid var(--line);
      background:#fff;
      flex:0 0 auto;
      cursor: zoom-in;
    }}
    .lightbox {{
      position:fixed;
      inset:0;
      z-index:50;
      display:none;
      align-items:center;
      justify-content:center;
      background:rgba(14, 20, 18, .72);
      padding:28px;
    }}
    .lightbox.open {{ display:flex; }}
    .lightbox-panel {{
      width:min(92vw, 980px);
      max-height:92vh;
      display:grid;
      grid-template-rows:auto minmax(0, 1fr) auto;
      gap:10px;
    }}
    .lightbox-header {{
      display:flex;
      justify-content:space-between;
      gap:12px;
      align-items:center;
      color:#fff;
    }}
    .lightbox-header b {{
      font-size:14px;
      line-height:1.35;
    }}
    .lightbox-close {{
      border:0;
      background:rgba(255,255,255,.14);
      color:#fff;
      width:34px;
      height:34px;
      border-radius:8px;
      font-size:20px;
      cursor:pointer;
    }}
    .lightbox-stage {{
      position:relative;
      min-height:0;
      display:grid;
      place-items:center;
    }}
    .lightbox-stage img {{
      max-width:100%;
      max-height:78vh;
      object-fit:contain;
      border-radius:8px;
      background:#fff;
      box-shadow:0 20px 80px rgba(0,0,0,.32);
    }}
    .lightbox-nav {{
      position:absolute;
      top:50%;
      transform:translateY(-50%);
      width:42px;
      height:54px;
      border:0;
      border-radius:8px;
      background:rgba(255,255,255,.18);
      color:#fff;
      font-size:28px;
      cursor:pointer;
    }}
    .lightbox-nav.prev {{ left:10px; }}
    .lightbox-nav.next {{ right:10px; }}
    .lightbox-footer {{
      display:flex;
      justify-content:center;
      gap:6px;
    }}
    .lightbox-dot {{
      width:8px;
      height:8px;
      border-radius:999px;
      background:rgba(255,255,255,.35);
    }}
    .lightbox-dot.active {{ background:#fff; }}
    .draft-node.primary {{
      border-color:#bfd9cc;
      background:#f7fbf8;
    }}
    .node-actions {{
      display:flex;
      gap:7px;
      flex-wrap:wrap;
      margin-top:8px;
    }}
    .node-actions a, .node-actions button {{
      font-size:12px;
      padding:6px 8px;
    }}
    .secondary-actions {{
      margin-top:8px;
    }}
    .secondary-actions summary {{
      cursor:pointer;
      color:var(--muted);
      font-size:12px;
    }}
    .server-link {{
      font-weight:700;
    }}
    .source-button {{
      appearance: none;
      border: 0;
      background: transparent;
      padding: 0;
      text-align: left;
      color: inherit;
      width: 270px;
      cursor: pointer;
    }}
    .source-button span, .source-button code {{ display:block; }}
    .source-button strong {{
      display: block;
      margin: 3px 0;
      line-height: 1.28;
      font-size: 13px;
      color: var(--ink);
    }}
    .status {{
      display: inline-flex;
      align-items: center;
      border-radius: 999px;
      padding: 3px 8px;
      font-size: 12px;
      font-weight: 700;
      white-space: nowrap;
      color: var(--todo-ink);
      background: var(--todo);
      border: 1px solid #d7dde5;
    }}
    .status a {{ color: inherit; }}
    .status.sent, .status.packaged, .status.ready_to_package {{ color: var(--ok-ink); background: var(--ok); border-color:#c9e8d8; }}
    .status.review_needed {{ color: var(--warn-ink); background: var(--warn); border-color:#edd5a8; }}
    .status.missing_asset {{ color:#8b2b20; background:#fff0ec; border-color:#f1c8bd; }}
    .status.source_gallery {{ color:#35506b; background:#edf5ff; border-color:#c7d9ee; }}
    .status.missing {{ opacity: .72; }}
    td small {{ display:block; color:var(--muted); margin-top:4px; white-space: nowrap; }}
    .detail-title {{ font-size: 18px; line-height: 1.25; margin: 0 0 8px; }}
    .meta-grid {{ display:grid; grid-template-columns: 1fr 1fr; gap:8px; margin:12px 0; }}
    .meta {{ background: var(--soft); border:1px solid var(--line); border-radius:8px; padding:8px; }}
    .meta b {{ display:block; font-size:12px; color:var(--muted); margin-bottom:2px; }}
    .platform-list {{ display:grid; gap:8px; }}
    .platform-item {{ border:1px solid var(--line); border-radius:8px; padding:9px; background:#fbfcf8; }}
    .platform-item header {{ padding:0; border:0; background:transparent; display:flex; justify-content:space-between; gap:8px; align-items:center; }}
    .platform-item p {{ margin-top:7px; font-size:12px; }}
    .capability-note {{ display:block; margin-top:6px; color:var(--muted); line-height:1.45; }}
    .preflight-panel {{ display:none; margin:10px 0 12px; border:1px solid var(--line); border-radius:8px; padding:10px; background:#f8faf6; }}
    .preflight-panel h3 {{ margin:0 0 8px; font-size:14px; }}
    .preflight-grid {{ display:grid; gap:8px; }}
    .preflight-item {{ border:1px solid var(--line); border-radius:8px; padding:9px; background:var(--panel); }}
    .preflight-item header {{ padding:0; border:0; background:transparent; display:flex; justify-content:space-between; gap:8px; align-items:center; }}
    .preflight-checks {{ margin:7px 0 0; padding-left:18px; color:var(--muted); font-size:12px; line-height:1.45; }}
    .queue-grid {{ display:grid; grid-template-columns: 1fr 1fr; gap:16px; }}
    .queue-list {{ display:grid; gap:8px; max-height: 430px; overflow:auto; }}
    .queue-item {{ border:1px solid var(--line); border-radius:8px; padding:10px; background:var(--panel); }}
    .queue-item strong {{ display:block; font-size:13px; line-height:1.3; margin:4px 0; }}
    .queue-item .row {{ display:flex; justify-content:space-between; gap:8px; align-items:center; }}
    .channel-status-list {{ display:grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap:8px; }}
    .channel-status-item {{ border:1px solid var(--line); border-radius:8px; padding:10px; background:#fbfcf8; }}
    .channel-status-item header {{ padding:0; border:0; background:transparent; display:flex; justify-content:space-between; gap:8px; align-items:center; }}
    .channel-status-item p {{ margin-top:6px; font-size:12px; color:var(--muted); line-height:1.45; }}
    .auth-queue {{ display:grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap:10px; }}
    .auth-item {{ border:1px solid var(--line); border-radius:8px; padding:11px; background:#fbfcf8; }}
    .auth-item.ready {{ border-color:#c9e8d8; background:#f3fbf6; }}
    .auth-item.active {{ border-color:#d8b66d; background:#fffaf0; box-shadow: inset 3px 0 0 #c9891b; }}
    .auth-item header {{ padding:0; border:0; background:transparent; display:flex; justify-content:space-between; gap:8px; align-items:center; }}
    .auth-item p {{ margin-top:7px; font-size:12px; color:var(--muted); line-height:1.45; }}
    .auth-item code {{ display:block; margin-top:6px; }}
    .auth-qr {{ margin-top:10px; padding:9px; border:1px solid var(--line); background:#fff; border-radius:8px; }}
    .auth-qr img {{ display:block; width:148px; height:148px; object-fit:contain; border:1px solid var(--line); background:#fff; }}
    .auth-qr small {{ display:block; margin-top:6px; color:var(--muted); }}
    .auth-session {{ margin-top:10px; padding:9px; border:1px solid var(--line); background:#fbfcf8; border-radius:8px; }}
    .auth-session pre {{ margin-top:7px; white-space:pre-wrap; max-height:120px; overflow:auto; font-size:11px; color:#405048; }}
    .history-list {{ display:grid; gap:8px; max-height:260px; overflow:auto; }}
    .history-item {{ border:1px solid var(--line); border-radius:8px; padding:9px; background:#fbfcf8; }}
    .history-item header {{ padding:0; border:0; background:transparent; display:flex; justify-content:space-between; gap:10px; align-items:center; }}
    .history-item p {{ margin-top:5px; font-size:12px; color:var(--muted); line-height:1.45; }}
    .action-queue-panel {{
      margin-bottom:18px;
    }}
    .action-queue-head {{
      display:flex;
      justify-content:space-between;
      gap:14px;
      align-items:flex-start;
      margin-bottom:8px;
    }}
    .action-queue-head p {{
      font-size:12px;
      margin-top:4px;
    }}
    .action-queue-list {{
      display:grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap:8px;
      margin-top:10px;
    }}
    .action-queue-item {{
      border:1px solid var(--line);
      border-radius:8px;
      background:#fbfcf8;
      padding:10px;
      display:grid;
      gap:6px;
    }}
    .action-queue-item .row {{
      display:flex;
      justify-content:space-between;
      gap:8px;
      align-items:center;
    }}
    .action-queue-item strong {{
      font-size:13px;
      line-height:1.35;
    }}
    .action-queue-item p {{
      font-size:12px;
      line-height:1.45;
      margin:0;
    }}
    .action-queue-item small {{
      color:var(--muted);
      font-size:11px;
    }}
    .command-box {{ white-space:pre-wrap; margin-top:10px; padding:10px; border-radius:8px; background:#1c2421; color:#eef5ef; font-size:12px; overflow:auto; display:none; }}
    code {{
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 13px;
      color: var(--muted);
      overflow-wrap: anywhere;
    }}
    @media (max-width: 980px) {{
      .layout, .queue-grid, .flow-workbench {{ grid-template-columns: 1fr; }}
      .source-rail {{ max-height:none; }}
    }}
    @media (max-width: 720px) {{
      header, main {{ padding-left: 18px; padding-right: 18px; }}
      .topline {{ display:block; }}
      .source-node, .flow-source-card, .flow-lane {{ grid-template-columns: 1fr; }}
      .flow-arrow {{ display:none; }}
    }}
  </style>
</head>
<body>
  <header>
    <div class="topline">
      <div>
        <h1>Park-IO Outbox 工作台</h1>
        <p>单条内容详情 · 生成时间：{html.escape(model['generated_at'])}。</p>
      </div>
      <p><a href="dashboard.html">返回总览</a> · 搬运视频 → 内容包 → 公众号文章 → 主题判断 → 小红书 / X / clips。</p>
    </div>
  </header>
  <main>
    <div class="notice" id="runtime-notice">
      <span>正在检测本地动作服务。</span>
      <div class="notice-actions">
        <button class="command" type="button" data-command="python3 /Users/wendy/work/content-ops/scripts/workbench_server.py --port 8788\nopen http://127.0.0.1:8788/workbench.html">显示启动命令</button>
      </div>
    </div>
    <details class="admin-panel debug-hidden">
      <summary>Debug / 手动修复工具</summary>
      <div class="admin-tools">
        <div class="action-row">
          <button class="command" type="button" data-action="check-auth-artifacts">检查授权文件</button>
          <button class="command" type="button" data-action="wait-auth-artifacts">等待授权完成</button>
          <button class="command" type="button" data-action="prepare-next-auth">准备下一个授权</button>
          <button class="command" type="button" data-action="prepare-next-actionable-auth">跳过人工卡点继续</button>
          <button class="command" type="button" data-action="prepare-missing-channels">准备缺失通道</button>
          <button class="command" type="button" data-action="refresh-auth-prompts">刷新扫码/登录入口</button>
          <button class="command" type="button" data-action="repair-all-local-gaps">补齐全部本地缺口</button>
          <a href="file:///Users/wendy/work/content-ops/AUTH_RUNBOOK.md" target="_blank" rel="noreferrer">授权 Runbook</a>
        </div>
        <section class="setup-grid" aria-label="通道打通清单">
          <article class="setup-item">
            <header><b>小红书</b><span class="status review_needed">扫码 cookie</span></header>
            <p>登录后可以把图文卡片安全保存到小红书草稿箱。</p>
            <div class="action-row">
              <button class="command" type="button" data-action="prepare-channel" data-platform="xiaohongshu">准备通道</button>
              <button class="command" type="button" data-action="check-channel" data-platform="xiaohongshu">检查登录</button>
            </div>
          </article>
          <article class="setup-item">
            <header><b>视频号</b><span class="status review_needed">扫码 cookie</span></header>
            <p>登录后可保存视频号草稿。</p>
            <div class="action-row">
              <button class="command" type="button" data-action="prepare-channel" data-platform="wechat_channels">准备通道</button>
              <button class="command" type="button" data-action="check-channel" data-platform="wechat_channels">检查登录</button>
            </div>
          </article>
          <article class="setup-item">
            <header><b>Bilibili</b><span class="status review_needed">账号 cookie</span></header>
            <p>账号就绪后可上传为仅自己可见视频。</p>
            <div class="action-row">
              <button class="command" type="button" data-action="prepare-channel" data-platform="bilibili">准备通道</button>
              <button class="command" type="button" data-action="check-channel" data-platform="bilibili">检查登录</button>
            </div>
          </article>
          <article class="setup-item">
            <header><b>YouTube</b><span class="status review_needed">Private / OAuth</span></header>
            <p>OAuth 就绪后可上传为 private 视频。</p>
            <div class="action-row">
              <button class="command" type="button" data-action="prepare-channel" data-platform="youtube">准备 OAuth</button>
              <button class="command" type="button" data-action="check-channel" data-platform="youtube">检查 OAuth</button>
              <button class="command" type="button" data-action="choose-youtube-oauth-client">选择 OAuth JSON</button>
              <input id="youtube-oauth-file" type="file" accept="application/json,.json" hidden>
            </div>
          </article>
        </section>
        <section class="panel" id="auth-queue-panel">
          <h2>授权队列</h2>
          <p>绿色代表已经能继续，黄色代表当前最应该处理。</p>
          <div class="auth-queue" id="auth-queue"></div>
          <div id="auth-qr-panel"></div>
        </section>
        <div class="auth-helper" aria-label="授权助手">
        <article class="auth-helper-card">
          <h3>小红书</h3>
          <p>目标：保存图文到小红书草稿/暂存，不发布。</p>
          <code>/Users/wendy/content-toolkit/capabilities/publish/cookies/xiaohongshu_creator.json</code>
          <ol>
            <li>点“小红书 / 准备通道”。</li>
            <li>在弹出的登录窗口完成扫码。</li>
            <li>点“等待授权完成”，再点“检查全部通道”。</li>
          </ol>
        </article>
        <article class="auth-helper-card">
          <h3>视频号</h3>
          <p>目标：上传视频到视频号草稿箱，不发布。</p>
          <code>/Users/wendy/content-toolkit/capabilities/publish/cookies/tencent_uploader/account.json</code>
          <ol>
            <li>点“视频号 / 准备通道”。</li>
            <li>在弹出的视频号浏览器页面完成扫码/确认登录。</li>
            <li>点“等待授权完成”，确认 cookie 落盘。</li>
          </ol>
        </article>
        <article class="auth-helper-card">
          <h3>Bilibili</h3>
          <p>目标：上传为仅自己可见，不公开发布。</p>
          <code>/Users/wendy/content-toolkit/capabilities/publish/cookies/bilibili_creator.json</code>
          <ol>
            <li>点“Bilibili / 准备通道”。</li>
            <li>在 dashboard 打开二维码，用 Bilibili App 扫码。</li>
            <li>点“等待授权完成”，然后检查登录。</li>
          </ol>
        </article>
        <article class="auth-helper-card">
          <h3>YouTube</h3>
          <p>目标：上传为 private，不公开发布。</p>
          <code>/Users/wendy/.config/park/youtube-oauth.json</code>
          <code>/Users/wendy/.config/park/youtube-token.json</code>
          <ol>
            <li>先下载 Google OAuth Desktop client JSON。</li>
            <li>点“选择 OAuth JSON”直接安装，或把文件放到 Downloads 后点“安装 OAuth client”。</li>
            <li>点“YouTube / 准备 OAuth”。</li>
            <li>完成 Google 授权后点“等待授权完成”。</li>
          </ol>
        </article>
        </div>
      </div>
    </details>
    <div class="flow-workbench single-workflow-shell">
      <aside class="panel flow-panel" id="detail-panel"></aside>
    </div>
    <details class="admin-panel" open>
      <summary>运行日志</summary>
      <section class="block panel" id="channel-status-panel">
        <h2>通道状态</h2>
        <p>这里记录平台连接状态；正式生产动作会写入最近动作。</p>
        <div class="channel-status-list" id="channel-status-list"></div>
      </section>
      <section class="block panel" id="action-history-panel">
        <h2>最近动作</h2>
        <p>后续所有前端操作都会进入这里：内容包更新、主题调整、草稿推送、发送结果。</p>
        <div class="history-list" id="action-history-list"></div>
      </section>
    </details>
    <pre class="command-box" id="command-box"></pre>
    <div class="lightbox" id="image-lightbox" aria-hidden="true">
      <div class="lightbox-panel">
        <div class="lightbox-header">
          <b id="lightbox-title"></b>
          <button class="lightbox-close" type="button" data-lightbox-close aria-label="关闭">×</button>
        </div>
        <div class="lightbox-stage">
          <button class="lightbox-nav prev" type="button" data-lightbox-prev aria-label="上一张">‹</button>
          <img id="lightbox-image" alt="">
          <button class="lightbox-nav next" type="button" data-lightbox-next aria-label="下一张">›</button>
        </div>
        <div class="lightbox-footer" id="lightbox-dots"></div>
      </div>
    </div>
  </main>
  <script>
    const model = {model_json};
    const sourceById = new Map(model.sources.map(source => [source.source_content_id, source]));
    const platformIds = model.platforms.map(platform => platform.id);
    const platformLabels = new Map(model.platforms.map(platform => [platform.id, platform.label]));
    const platformIcons = {{
      xiaohongshu: '📕',
      wechat_mp: '📰',
      wechat_channels: '▶',
      x: '𝕏',
      youtube: '▶',
      bilibili: 'B'
    }};
    const reviewPlatformIds = ['xiaohongshu', 'wechat_mp', 'x'];
    const migrationPlatformIds = ['wechat_channels', 'bilibili', 'youtube'];
    const detail = document.getElementById('detail-panel');
    const commandBox = document.getElementById('command-box');
    const runtimeNotice = document.getElementById('runtime-notice');
    const channelStatusList = document.getElementById('channel-status-list');
    const actionHistoryList = document.getElementById('action-history-list');
    const authQueue = document.getElementById('auth-queue');
    const authQrPanel = document.getElementById('auth-qr-panel');
    const lightbox = document.getElementById('image-lightbox');
    const lightboxImage = document.getElementById('lightbox-image');
    const lightboxTitle = document.getElementById('lightbox-title');
    const lightboxDots = document.getElementById('lightbox-dots');
    let lightboxImages = [];
    let lightboxIndex = 0;
    let lightboxLabel = '';
    let capabilities = {{}};
    let migrationRuntime = {{}};
    let migrationPollTimer = null;
    const serverLaunchCommand = 'python3 /Users/wendy/work/content-ops/scripts/workbench_server.py --port 8788\\nopen http://127.0.0.1:8788/dashboard.html';
    const trueDraftPlatforms = new Set(['xiaohongshu', 'wechat_mp', 'wechat_channels']);
    const handoffPlatforms = new Set(['x']);
    const privateUploadPlatforms = new Set(['bilibili', 'youtube']);
    const authPlatforms = ['xiaohongshu', 'wechat_channels', 'bilibili', 'youtube'];
    const authMeta = {{
      xiaohongshu: {{
        target: '小红书图文草稿箱',
        credential: '/Users/wendy/content-toolkit/capabilities/publish/cookies/xiaohongshu_creator.json',
        action: '优先复用 Chrome 已登录的小红书账号；不成功再扫码登录。dashboard 用安全草稿模式保存图文，不会点击发布。',
        chromeImport: true
      }},
      wechat_channels: {{
        target: '视频号公开视频',
        credential: '/Users/wendy/content-toolkit/capabilities/publish/cookies/tencent_uploader/account.json',
        action: '用于一键视频搬运。未登录时系统会打开视频号后台登录页。',
        chromeImport: true
      }},
      bilibili: {{
        target: 'Bilibili 公开视频',
        credential: '/Users/wendy/content-toolkit/capabilities/publish/cookies/bilibili_creator.json',
        action: '用于一键视频搬运。未登录时系统会打开 Bilibili 登录流程。',
        chromeImport: true
      }},
      youtube: {{
        target: 'YouTube public video',
        credential: '/Users/wendy/.config/park/youtube-oauth.json + youtube-token.json',
        action: '用于一键视频搬运。未授权时系统会打开 OAuth 流程。',
        oauthInstall: true
      }}
    }};
    const platformHome = {{
      xiaohongshu: 'https://creator.xiaohongshu.com/publish/publish',
      wechat_mp: 'https://mp.weixin.qq.com/',
      wechat_channels: 'https://channels.weixin.qq.com/platform/post/create',
      bilibili: 'https://member.bilibili.com/platform/upload/video/frame',
      youtube: 'https://studio.youtube.com/',
      x: 'https://x.com/compose/post'
    }};

    function escapeHtml(value) {{
      return String(value ?? '').replace(/[&<>"']/g, char => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[char]));
    }}
    function link(label, href) {{
      if (!href) return `<span>${{escapeHtml(label)}}</span>`;
      return `<a href="${{escapeHtml(href)}}">${{escapeHtml(label)}}</a>`;
    }}
    function navLink(label, href, className = '') {{
      if (!href) return '';
      const cls = className ? ` class="${{escapeHtml(className)}}"` : '';
      return `<a${{cls}} href="${{escapeHtml(href)}}">${{escapeHtml(label)}}</a>`;
    }}
    function showCommand(command) {{
      commandBox.textContent = command || '没有下一步命令';
      commandBox.style.display = 'block';
    }}
    function openLightbox(images, index = 0, label = '') {{
      lightboxImages = images || [];
      lightboxIndex = Math.max(0, Math.min(index, lightboxImages.length - 1));
      lightboxLabel = label || '';
      updateLightbox();
      lightbox.classList.add('open');
      lightbox.setAttribute('aria-hidden', 'false');
    }}
    function closeLightbox() {{
      lightbox.classList.remove('open');
      lightbox.setAttribute('aria-hidden', 'true');
    }}
    function moveLightbox(delta) {{
      if (!lightboxImages.length) return;
      lightboxIndex = (lightboxIndex + delta + lightboxImages.length) % lightboxImages.length;
      updateLightbox();
    }}
    function updateLightbox() {{
      const src = lightboxImages[lightboxIndex] || '';
      lightboxImage.src = src;
      lightboxTitle.textContent = lightboxImages.length
        ? `${{lightboxLabel}} · ${{lightboxIndex + 1}}/${{lightboxImages.length}}`
        : lightboxLabel;
      lightboxDots.innerHTML = lightboxImages.map((_, index) => `<span class="lightbox-dot ${{index === lightboxIndex ? 'active' : ''}}"></span>`).join('');
    }}
    function channelStatusText(channel) {{
      if (channel.ok) return '可用';
      if (channel.status === 'bridge_not_ready') return 'Bridge 未就绪';
      if (channel.status === 'extension_host_permission_missing') return '扩展权限不足';
      if (channel.status === 'xhs_sau_cookie_missing_bridge_permission_missing') return '缺小红书登录';
      if (channel.status === 'cookie_missing') return '缺登录 cookie';
      if (channel.status === 'cookie_invalid') return 'cookie 失效';
      if (channel.status === 'cookie_valid') return 'cookie 可用';
      if (channel.status === 'missing_account') return '缺账号 cookie';
      if (channel.status === 'account_or_biliup_missing') return channel.biliup_exists ? '缺账号 cookie' : '缺 runtime/cookie';
      if (channel.status === 'oauth_missing' || channel.status === 'oauth_client_missing') return '缺 OAuth';
      if (channel.status === 'token_missing') return '缺 token';
      if (channel.status === 'token_invalid') return 'token 失效';
      if (channel.status === 'token_valid') return 'OAuth 可用';
      if (channel.status === 'login_unknown_check_timeout') return '登录状态未知';
      return channel.status || '待处理';
    }}
    function channelStatusDetail(channel) {{
      if (channel.platform === 'xiaohongshu') {{
        const bridge = channel.bridge || {{}};
        return channel.next_step || `Bridge server: ${{Boolean(bridge.server_running)}} · extension: ${{Boolean(bridge.extension_connected)}}`;
      }}
      if (channel.platform === 'wechat_mp') return channel.ok ? '公众号 bridge 和配置已就绪，可以创建草稿。' : '需要启动/修复 wechat-workflow bridge 或公众号配置。';
      if (channel.platform === 'wechat_channels') return channel.ok ? '视频号 cookie 已存在，可以尝试推送平台草稿箱。' : `需要登录保存 cookie：${{channel.account_file || ''}}`;
      if (channel.platform === 'bilibili') return channel.ok ? '账号 cookie 和 biliup runtime 已存在；可上传为仅自己可见视频。' : `biliup: ${{Boolean(channel.biliup_exists)}} · account: ${{Boolean(channel.account_exists)}}`;
      if (channel.platform === 'youtube') return channel.ok ? 'YouTube OAuth 已就绪；可上传 private 视频。' : (channel.next_step || '缺 YouTube OAuth client/token。');
      if (channel.platform === 'x') return '使用 X Web Intent 预填内容。';
      return channel.next_step || channel.safe_mode || '';
    }}
    function credentialLines(channel, meta = {{}}) {{
      const lines = [];
      const artifacts = channel.auth_artifacts || [];
      if (Array.isArray(artifacts) && artifacts.length) {{
        artifacts.forEach(item => lines.push(`${{item.exists ? '已存在' : '缺失'}}：${{item.label || '凭据'}}：${{item.path || ''}}`));
      }}
      if (!lines.length) {{
        if (channel.account_file) lines.push(`账号/cookie：${{channel.account_file}}`);
        if (channel.client_secret) lines.push(`OAuth client：${{channel.client_secret}}`);
        if (channel.token_file) lines.push(`Token：${{channel.token_file}}`);
        const candidates = channel.client_file_candidates || channel.credential_candidates || [];
        if (Array.isArray(candidates) && candidates.length) lines.push(`OAuth client 候选：${{candidates.join(' / ')}}`);
        if (!lines.length && meta.credential) lines.push(meta.credential);
      }}
      return lines;
    }}
    function renderAuthQueue(channels, nextAuth = {{}}) {{
      const byPlatform = new Map((channels || []).map(channel => [channel.platform, channel]));
      authQueue.innerHTML = authPlatforms.map(platformId => {{
        const channel = byPlatform.get(platformId) || {{platform: platformId, ok: false, status: 'unchecked'}};
        const meta = authMeta[platformId] || {{}};
        const label = platformLabels.get(platformId) || platformId;
        const isActive = nextAuth.platform === platformId || (!nextAuth.platform && !channel.ok);
        const statusClass = channel.ok ? 'sent' : 'review_needed';
        const itemClass = channel.ok ? 'ready' : isActive ? 'active' : '';
        const activeText = isActive && !channel.ok ? '<p><b>当前处理：</b>先把这个通道打通，再回到内容详情点推送/上传。</p>' : '';
        const commandLine = nextAuth.platform === platformId && nextAuth.manual_command
          ? `<code>${{escapeHtml(nextAuth.manual_command)}}</code>`
          : channel.setup_command
          ? `<code>${{escapeHtml(channel.setup_command)}}</code>`
          : '';
        const browserFix = nextAuth.platform === platformId && nextAuth.browser_fix
          ? `<p>${{escapeHtml(nextAuth.browser_fix)}}</p>`
          : '';
        const credentials = credentialLines(channel, meta);
        const credentialHtml = credentials.length
          ? credentials.map(line => `<p><b>凭据：</b>${{escapeHtml(line)}}</p>`).join('')
          : '';
        const importButton = meta.chromeImport
          ? `<button class="command" type="button" data-action="import-chrome-auth" data-platform="${{escapeHtml(platformId)}}">导入 Chrome 登录态</button>`
          : '';
        const oauthInstallButton = meta.oauthInstall
          ? `<button class="command" type="button" data-action="install-youtube-oauth-client">安装 OAuth client</button>`
          : '';
        return `<article class="auth-item ${{itemClass}}">
          <header>
            <b>${{escapeHtml(label)}}</b>
            <span class="status ${{statusClass}}">${{escapeHtml(channel.ok ? '已打通' : channelStatusText(channel))}}</span>
          </header>
          <p><b>目标：</b>${{escapeHtml(meta.target || '')}}</p>
          ${{credentialHtml}}
          <p>${{escapeHtml(meta.action || channelStatusDetail(channel))}}</p>
          ${{activeText}}
          ${{browserFix}}
          ${{commandLine}}
          <div class="action-row">
            <button class="command" type="button" data-action="check-channel" data-platform="${{escapeHtml(platformId)}}">重查</button>
            ${{importButton}}
            ${{oauthInstallButton}}
            <button class="command" type="button" data-action="prepare-channel" data-platform="${{escapeHtml(platformId)}}">准备通道</button>
            ${{platformHome[platformId] ? `<a href="${{escapeHtml(platformHome[platformId])}}" target="_blank" rel="noreferrer">打开后台</a>` : ''}}
          </div>
        </article>`;
      }}).join('');
    }}
    function renderAuthQrcodes(qrcodes = {{}}, sessions = {{}}) {{
      const entries = Object.entries(qrcodes).filter(([, item]) => item && item.exists);
      const sessionEntries = Object.entries(sessions || {{}}).filter(([, item]) => item);
      if (!entries.length && !sessionEntries.length) {{
        authQrPanel.innerHTML = '';
        return;
      }}
      const labels = {{
        xiaohongshu: '小红书扫码登录',
        bilibili: 'Bilibili 扫码登录'
      }};
      const qrHtml = entries.map(([platform, item]) => `
        <article class="auth-qr">
          <b>${{escapeHtml(labels[platform] || platform)}}</b>
          ${{item.possibly_expired ? '<span class="status missing">可能过期</span>' : '<span class="status review_needed">可扫码</span>'}}
          <a href="${{escapeHtml(item.href)}}" target="_blank" rel="noreferrer">
            <img src="${{escapeHtml(item.href)}}?t=${{encodeURIComponent(item.modified_at || '')}}" alt="${{escapeHtml(labels[platform] || platform)}}二维码">
          </a>
          <small>${{escapeHtml(item.modified_at || '')}}${{item.age_seconds ? ` · ${{Math.round(item.age_seconds / 60)}} 分钟前` : ''}}</small>
          <div class="action-row">
            <a href="${{escapeHtml(item.href)}}" target="_blank" rel="noreferrer">打开二维码</a>
            <button class="command" type="button" data-action="prepare-channel" data-platform="${{escapeHtml(platform)}}">重新生成</button>
            <button class="command" type="button" data-action="wait-auth-artifacts">扫码后等待授权</button>
          </div>
        </article>`).join('');
      const sessionLabels = {{
        xiaohongshu: '小红书登录会话',
        wechat_channels: '视频号登录会话',
        bilibili: 'Bilibili 登录会话'
      }};
      const sessionHtml = sessionEntries.map(([platform, item]) => {{
        const state = item.running
          ? item.waiting_for_user ? '等待扫码/确认' : '运行中'
          : '未运行';
        return `<article class="auth-session">
          <b>${{escapeHtml(sessionLabels[platform] || platform)}}</b>
          <span class="status ${{item.running ? 'review_needed' : 'missing'}}">${{escapeHtml(state)}}</span>
          <small>${{escapeHtml(item.session || '')}}</small>
          ${{item.tail ? `<pre>${{escapeHtml(item.tail.trim().slice(-900))}}</pre>` : ''}}
        </article>`;
      }}).join('');
      authQrPanel.innerHTML = `<div class="auth-queue">${{qrHtml}}${{sessionHtml}}</div>`;
    }}
    function renderChannelStatuses(data) {{
      const artifacts = data.auth_artifacts || {{}};
      const channels = (data.channels || []).map(channel => ({{
        ...channel,
        auth_artifacts: artifacts[channel.platform] || channel.auth_artifacts || []
      }}));
      renderAuthQueue(channels, data.next_auth || {{}});
      renderAuthQrcodes(data.auth_qrcodes || {{}}, data.login_sessions || {{}});
      channelStatusList.innerHTML = channels.map(channel => {{
        const label = platformLabels.get(channel.platform) || channel.platform;
        const commandLine = channel.setup_command ? `<p><code>${{escapeHtml(channel.setup_command)}}</code></p>` : '';
        return `<article class="channel-status-item">
          <header><b>${{escapeHtml(label)}}</b><span class="status ${{channel.ok ? 'sent' : 'review_needed'}}">${{escapeHtml(channelStatusText(channel))}}</span></header>
          <p>${{escapeHtml(channelStatusDetail(channel))}}</p>
          ${{commandLine}}
          <div class="action-row">
            <button class="command" type="button" data-action="check-channel" data-platform="${{escapeHtml(channel.platform)}}">重查</button>
            <button class="command" type="button" data-action="prepare-channel" data-platform="${{escapeHtml(channel.platform)}}">准备通道</button>
            ${{platformHome[channel.platform] ? `<a href="${{escapeHtml(platformHome[channel.platform])}}" target="_blank" rel="noreferrer">打开后台</a>` : ''}}
          </div>
        </article>`;
      }}).join('') || '<p>还没有检查结果。</p>';
    }}
    function formatChannelSummary(data) {{
      const lines = [
        `通道检查完成：${{data.ready_count ?? 0}} 个可用，${{data.needs_setup_count ?? 0}} 个需要处理。`,
        ''
      ];
      (data.channels || []).forEach(channel => {{
        const label = platformLabels.get(channel.platform) || channel.platform;
        const status = channel.ok ? '可用' : channelStatusText(channel);
        const detail = channelStatusDetail(channel);
        lines.push(`${{channel.ok ? 'OK' : 'TODO'}} · ${{label}}：${{status}}`);
        if (detail) lines.push(`  ${{detail}}`);
      }});
      lines.push('', '下一步：绿色平台可以直接从单条内容详情里“推送平台草稿箱/打开后台填稿”；黄色平台先点对应的“准备通道”。');
      return lines.join('\\n');
    }}
    function formatActionResult(data) {{
      const label = platformLabels.get(data.platform) || data.platform || '平台';
      const lines = [
        `${{data.ok ? '完成' : '未完成'}} · ${{label}} · ${{data.status || ''}}`,
        data.message || ''
      ].filter(Boolean);
      if (data.platform_url) lines.push(`后台：${{data.platform_url}}`);
      if (data.video) lines.push(`视频文件：${{data.video}}`);
      if (data.clipboard_chars) lines.push(`${{data.status === 'handoff_dry_run' ? '可写入剪贴板' : '已写入剪贴板'}}：${{data.clipboard_chars}} 字符`);
      if (data.draft_url) lines.push(`平台草稿：${{data.draft_url}}`);
      if (data.local_id) lines.push(`本地草稿：${{data.local_id}}`);
      if (!data.ok && data.next_step) lines.push(`下一步：${{data.next_step}}`);
      if (!data.ok && data.error) lines.push(`错误：${{data.error}}`);
      return lines.join('\\n');
    }}
    function renderActionHistory(data) {{
      const actions = data.actions || [];
      actionHistoryList.innerHTML = actions.map(item => {{
        const label = platformLabels.get(item.platform) || item.platform || 'system';
        const source = item.source_content_id ? ` · ${{item.source_content_id}}` : '';
        const local = item.local_id ? ` · ${{item.local_id}}` : '';
        const statusClass = item.ok ? 'sent' : 'review_needed';
        return `<article class="history-item">
          <header>
            <b>${{escapeHtml(item.action || 'action')}} · ${{escapeHtml(label)}}</b>
            <span class="status ${{statusClass}}">${{escapeHtml(item.status || (item.ok ? 'ok' : 'needs attention'))}}</span>
          </header>
          <p>${{escapeHtml(item.created_at || '')}}${{escapeHtml(source)}}${{escapeHtml(local)}}</p>
          <p>${{escapeHtml(item.message || '')}}</p>
        </article>`;
      }}).join('') || '<p>还没有动作记录。</p>';
    }}
    async function refreshActionHistory() {{
      if (!isActionServerAvailable()) {{
        actionHistoryList.innerHTML = '<p>file:// 模式不能读取本地动作记录。请用 workbench server 打开。</p>';
        return;
      }}
      try {{
        const res = await fetch('/api/actions/recent', {{cache: 'no-store'}});
        const data = await res.json();
        renderActionHistory(data);
      }} catch (error) {{
        actionHistoryList.innerHTML = '<p>读取动作记录失败。</p>';
      }}
    }}
    function isActionServerAvailable() {{
      return location.protocol === 'http:' || location.protocol === 'https:';
    }}
    function actionMode(platformId) {{
      if (trueDraftPlatforms.has(platformId)) return 'draft';
      if (privateUploadPlatforms.has(platformId)) return 'private_upload';
      if (handoffPlatforms.has(platformId)) return 'handoff';
      return 'check';
    }}
    function actionButtonText(platformId) {{
      if (actionMode(platformId) === 'draft') return '推送平台草稿箱';
      if (platformId === 'bilibili') return '上传仅自己可见';
      if (actionMode(platformId) === 'private_upload') return '上传 private 视频';
      if (actionMode(platformId) === 'handoff') return '打开后台填稿';
      return '检查通道';
    }}
    function actionHint(platformId) {{
      if (platformId === 'xiaohongshu') return '图文笔记';
      if (platformId === 'wechat_mp') return '长文草稿';
      if (platformId === 'wechat_channels') return '视频迁移';
      if (platformId === 'bilibili') return '视频迁移';
      if (platformId === 'youtube') return '视频迁移';
      if (platformId === 'x') return '短文/Thread';
      return '';
    }}
    function formatTranscriptText(text) {{
      const raw = String(text || '').trim();
      if (!raw) return '<p class="empty">这条内容还没有 AI 内容包；请先在后台批量生成，生产页面不展示 raw transcript。</p>';
      return raw
        .split(/\\n\\s*\\n+/)
        .map(part => part.trim())
        .filter(Boolean)
        .map(part => `<p>${{escapeHtml(part).replace(/\\n/g, '<br>')}}</p>`)
        .join('');
    }}
    function formatDraftText(text) {{
      const raw = String(text || '').trim();
      if (!raw) return '<p class="empty">这篇还没有文字稿。</p>';
      return raw
        .split(/\\n\\s*\\n+/)
        .map(part => part.trim())
        .filter(Boolean)
        .map(part => `<p>${{escapeHtml(part).replace(/\\n/g, '<br>')}}</p>`)
        .join('');
    }}
    function transcriptStatus(source) {{
      if (source.content_package_text) {{
        const warnings = source.content_package_warnings || [];
        const warningText = warnings.map(item => {{
          if (String(item).includes('明显过短')) return '这版手稿保留度偏低，需要二次整理后再进入小红书/公众号生产。';
          return String(item);
        }}).join('；');
        if (!source.content_package_approved) {{
          return {{
            label: warnings.length ? 'AI 内容包需复核' : '内容包待你审核',
            className: 'review_needed',
            note: warnings.length
              ? `已生成内容包，但有 ${{warnings.length}} 个质量提醒：${{warningText}}`
              : `已生成内容包，等待你点“✓ 通过”后才算完成。engine=${{source.content_package_engine || 'unknown'}}，生成时间=${{source.content_package_generated_at || 'unknown'}}。`
          }};
        }}
        return {{
          label: warnings.length ? 'AI 内容包需复核' : 'AI 内容包已生成',
          className: warnings.length ? 'review_needed' : 'sent',
          note: warnings.length
            ? `已生成内容包，但有 ${{warnings.length}} 个质量提醒：${{warningText}}`
            : `engine=${{source.content_package_engine || 'unknown'}}，生成时间=${{source.content_package_generated_at || 'unknown'}}。`
        }};
      }}
      const engine = source.organized_engine || '';
      const ratio = Number(source.organized_retention_ratio || 0);
      const sameLength = Math.abs(Number(source.organized_chars || 0) - Number(source.transcript_chars || 0)) <= 5;
      if (!source.organized_text) return {{label: '缺 transcript', className: 'review_needed', note: '还没有可读文本。'}};
      if (!engine || engine === 'local' || sameLength) {{
        return {{
          label: '未 AI 整理',
          className: 'review_needed',
          note: `当前只是 raw cleaned transcript；engine=${{engine || 'unknown'}}，保留率=${{ratio ? ratio.toFixed(2) : 'n/a'}}。`
        }};
      }}
      return {{label: 'AI 整理过', className: 'packaged', note: `engine=${{engine}}，保留率=${{ratio ? ratio.toFixed(2) : 'n/a'}}。`}};
    }}
    function packageTopics(source, topicPlan) {{
      const fineTopics = source.content_package_fine_topics || [];
      if (fineTopics.length) {{
        return fineTopics
          .filter(topic => topic.priority !== 'discard')
          .map((topic, index) => ({{
            topic_id: `content-package-atomic-${{index + 1}}`,
            topic_index: index + 1,
            title: topic.title || `原子选题 ${{index + 1}}`,
            draft_title: topic.title || `原子选题 ${{index + 1}}`,
            priority: topic.priority || 'secondary',
            reason: topic.claim || '',
            contrast: topic.cognitive_contrast || '',
            reader_mirror: topic.reader_mirror || '',
            why_it_matters: topic.why_it_matters || '',
            points: topic.points || [],
            boundary: topic.boundary || '',
            takeaway: topic.takeaway || '',
            examples: topic.supporting_examples || [],
            platform_fit: topic.platform_fit || []
          }}));
      }}
      const packageTopics = source.content_package_topics || [];
      if (packageTopics.length) {{
        return packageTopics
          .filter(topic => topic.priority !== 'discard')
          .map((topic, index) => ({{
            topic_id: `content-package-${{index + 1}}`,
            topic_index: index + 1,
            title: topic.title || `主题 ${{index + 1}}`,
            draft_title: topic.title || `主题 ${{index + 1}}`,
            priority: topic.priority || 'secondary',
            reason: topic.claim || '',
            contrast: topic.cognitive_contrast || '',
            reader_mirror: topic.reader_mirror || '',
            why_it_matters: topic.why_it_matters || '',
            points: topic.points || [],
            boundary: topic.boundary || '',
            takeaway: topic.takeaway || '',
            examples: topic.supporting_examples || [],
            platform_fit: topic.platform_fit || []
          }}));
      }}
      return (topicPlan.topics || []).filter(topic => topic.priority !== 'discard');
    }}
    async function refreshCapabilities() {{
      if (!isActionServerAvailable()) {{
        runtimeNotice.querySelector('span').textContent = '当前是 file:// 查看模式：可以看进度和打开本地文件，但不能执行平台动作。请用本地 workbench server 打开。';
        return;
      }}
      try {{
        const res = await fetch('/api/capabilities', {{cache: 'no-store'}});
        const data = await res.json();
        capabilities = data.platforms || {{}};
        runtimeNotice.querySelector('span').textContent = '本地动作服务已连接。';
      }} catch (error) {{
        runtimeNotice.querySelector('span').textContent = '没有连上本地动作服务：请启动 workbench server 后刷新页面。';
      }}
    }}
    function canPushDraft(platformId, state) {{
      if (!isActionServerAvailable()) return false;
      if (platformId === 'xiaohongshu') return state && state.status === 'packaged' && state.primary_local_id;
      if (platformId === 'wechat_mp') return state && state.status === 'review_needed' && state.primary_local_id;
      if (platformId === 'wechat_channels') return state && state.status === 'draft' && state.primary_local_id;
      if (['bilibili', 'youtube'].includes(platformId)) return state && state.status === 'draft' && state.primary_local_id;
      if (platformId === 'x') return state && state.status !== 'missing' && state.primary_local_id;
      return false;
    }}
    async function pushDraft(platformId, sourceContentId, localId, dryRun=false, options={{}}) {{
      if (!isActionServerAvailable()) {{
        showCommand('python3 /Users/wendy/work/content-ops/scripts/workbench_server.py --port 8788\\nopen http://127.0.0.1:8788/dashboard.html');
        return;
      }}
      const label = platformLabels.get(platformId) || platformId;
      const mode = actionMode(platformId);
      const confirmTitle = mode === 'draft'
        ? `把这条内容推送到${{label}}草稿箱？`
        : mode === 'private_upload'
        ? platformId === 'bilibili'
          ? `把这条内容上传为 Bilibili 仅自己可见视频？`
          : `把这条内容上传为 YouTube private 视频？`
        : `打开${{label}}后台并准备填稿材料？`;
      const confirmNote = mode === 'draft'
        ? '这会写入平台草稿箱，但不会最终发布。'
        : mode === 'private_upload'
        ? platformId === 'bilibili'
          ? '这会上传为 Bilibili 仅自己可见，不会公开发布；你仍需要在创作中心手动检查和发布。'
          : '这会调用 YouTube API 上传为 private，不会公开发布；你仍需要在 YouTube Studio 手动检查和发布。'
        : '这会打开平台后台，并把标题/正文/视频路径复制到剪贴板；你需要在平台页面里手动粘贴、校对、保存或发送。';
      if (!dryRun && !confirm(`${{confirmTitle}}\\n\\n${{confirmNote}}`)) return;
      const res = await fetch('/api/actions/push-draft', {{
        method: 'POST',
        headers: {{'content-type': 'application/json'}},
        body: JSON.stringify({{
          platform: platformId,
          source_content_id: sourceContentId,
          local_id: localId || '',
          wechat_style: options.wechatStyle || '',
          dry_run: dryRun,
          confirmed: !dryRun
        }})
      }});
      const data = await res.json();
      showCommand(formatActionResult(data));
      refreshActionHistory();
      if (data.ok && platformId === 'wechat_mp') setTimeout(() => location.reload(), 900);
      if (!data.ok && data.platform_url) window.open(data.platform_url, '_blank', 'noopener');
    }}
    async function handoffPlatform(platformId, sourceContentId, localId) {{
      if (!isActionServerAvailable()) {{
        showCommand('python3 /Users/wendy/work/content-ops/scripts/workbench_server.py --port 8788\\nopen http://127.0.0.1:8788/dashboard.html');
        return;
      }}
      const label = platformLabels.get(platformId) || platformId;
      if (!confirm(`打开${{label}}后台并准备手动填稿材料？\\n\\n这会把标题、正文、视频路径写入剪贴板，并打开平台后台；不会上传，也不会发布。`)) return;
      const res = await fetch('/api/actions/handoff-platform', {{
        method: 'POST',
        headers: {{'content-type': 'application/json'}},
        body: JSON.stringify({{
          platform: platformId,
          source_content_id: sourceContentId,
          local_id: localId || '',
          confirmed: true
        }})
      }});
      const data = await res.json();
      showCommand(formatActionResult(data));
      refreshActionHistory();
      if (data.platform_url) window.open(data.platform_url, '_blank', 'noopener');
    }}
    async function refreshChannelStatuses(showResult = false) {{
      if (!isActionServerAvailable()) {{
        showCommand('python3 /Users/wendy/work/content-ops/scripts/workbench_server.py --port 8788\\nopen http://127.0.0.1:8788/dashboard.html');
        return null;
      }}
      channelStatusList.innerHTML = '<p>正在检查全部通道。</p>';
      const res = await fetch('/api/actions/check-all-channels', {{
        method: 'POST',
        headers: {{'content-type': 'application/json'}},
        body: JSON.stringify({{}})
      }});
      const data = await res.json();
      renderChannelStatuses(data);
      if (showResult) {{
        showCommand(formatChannelSummary(data));
      }}
      refreshActionHistory();
      return data;
    }}
    async function checkChannel(platformId) {{
      if (!isActionServerAvailable()) {{
        showCommand('python3 /Users/wendy/work/content-ops/scripts/workbench_server.py --port 8788\\nopen http://127.0.0.1:8788/dashboard.html');
        return;
      }}
      const res = await fetch('/api/actions/check-channel', {{
        method: 'POST',
        headers: {{'content-type': 'application/json'}},
        body: JSON.stringify({{platform: platformId}})
      }});
      const data = await res.json();
      const label = platformLabels.get(platformId) || platformId;
      const detail = channelStatusDetail(data);
      showCommand(`${{label}} 通道检查：${{data.ok ? '可用' : channelStatusText(data)}}${{detail ? '\\n' + detail : ''}}`);
      await refreshChannelStatuses(false);
    }}
    async function checkAllChannels() {{
      await refreshChannelStatuses(true);
    }}
    function formatAuthArtifacts(data) {{
      const labels = {{
        xiaohongshu: '小红书',
        wechat_channels: '视频号',
        bilibili: 'Bilibili',
        youtube: 'YouTube'
      }};
      const lines = [
        `授权文件检查：${{data.existing_count || 0}} 已存在 · ${{data.missing_count || 0}} 缺失`,
        ''
      ];
      Object.entries(data.auth_artifacts || {{}}).forEach(([platform, items]) => {{
        lines.push(`${{labels[platform] || platform}}：${{data.platform_ready && data.platform_ready[platform] ? '授权产物齐全' : '未齐全'}}`);
        (items || []).forEach(item => {{
          const meta = item.exists && item.modified_at ? ` · ${{item.size || 0}} bytes · ${{item.modified_at}}` : '';
          lines.push(`- ${{item.exists ? '已存在' : '缺失'}}：${{item.label || '凭据'}}：${{item.path || ''}}${{meta}}`);
        }});
      }});
      if (data.next_step) {{
        lines.push('', data.next_step);
      }}
      return lines.join('\\n');
    }}
    async function checkAuthArtifacts() {{
      if (!isActionServerAvailable()) {{
        showCommand('python3 /Users/wendy/work/content-ops/scripts/workbench_server.py --port 8788\\nopen http://127.0.0.1:8788/dashboard.html');
        return;
      }}
      const res = await fetch('/api/actions/check-auth-artifacts', {{
        method: 'POST',
        headers: {{'content-type': 'application/json'}},
        body: JSON.stringify({{}})
      }});
      const data = await res.json();
      showCommand(formatAuthArtifacts(data));
      renderAuthQueue([], {{}});
      await refreshChannelStatuses(false);
      refreshActionHistory();
    }}
    async function waitAuthArtifacts() {{
      if (!isActionServerAvailable()) {{
        showCommand('python3 /Users/wendy/work/content-ops/scripts/workbench_server.py --port 8788\\nopen http://127.0.0.1:8788/dashboard.html');
        return;
      }}
      showCommand('正在等待授权文件落盘，最多 2 分钟。你可以在平台登录窗口完成扫码/OAuth。');
      const res = await fetch('/api/actions/wait-auth-artifacts', {{
        method: 'POST',
        headers: {{'content-type': 'application/json'}},
        body: JSON.stringify({{timeout_seconds: 120, interval_seconds: 2}})
      }});
      const data = await res.json();
      showCommand(formatAuthArtifacts(data));
      await refreshChannelStatuses(false);
      refreshActionHistory();
    }}
    async function importChromeAuth(platformId) {{
      if (!isActionServerAvailable()) {{
        showCommand('python3 /Users/wendy/work/content-ops/scripts/workbench_server.py --port 8788\\nopen http://127.0.0.1:8788/dashboard.html');
        return;
      }}
      const label = platformLabels.get(platformId) || platformId;
      if (!confirm(`从 Chrome 当前登录态导入 ${{label}} 授权？\\n\\n这会读取本机 Chrome cookie，转换成本地账号文件；不会打印 cookie 值，也不会发布内容。`)) return;
      showCommand(`正在尝试复用 Chrome 里的 ${{label}} 登录态。`);
      const res = await fetch('/api/actions/import-chrome-auth', {{
        method: 'POST',
        headers: {{'content-type': 'application/json'}},
        body: JSON.stringify({{platform: platformId}})
      }});
      const data = await res.json();
      const lines = [
        `${{label}} Chrome 登录态导入：${{data.ok ? '成功' : '未成功'}}`,
        data.status ? `状态：${{data.status}}` : '',
        data.message || '',
        data.account_file ? `账号文件：${{data.account_file}}` : ''
      ].filter(Boolean);
      const summary = data.import_summary && data.import_summary.summary ? data.import_summary.summary : data.import_summary;
      if (summary && summary.cookie_count !== undefined) {{
        lines.push(`Chrome cookie：${{summary.cookie_count}} 个`);
        if (summary.domains && summary.domains.length) lines.push(`域名：${{summary.domains.join(', ')}}`);
      }}
      if (data.invalid_file) lines.push(`无效文件已移走：${{data.invalid_file}}`);
      showCommand(lines.join('\\n'));
      await refreshChannelStatuses(false);
      refreshActionHistory();
    }}
    async function installYoutubeOauthClient(file = null) {{
      if (!isActionServerAvailable()) {{
        showCommand('python3 /Users/wendy/work/content-ops/scripts/workbench_server.py --port 8788\\nopen http://127.0.0.1:8788/dashboard.html');
        return;
      }}
      const payload = {{}};
      if (file) {{
        payload.filename = file.name;
        payload.content = await file.text();
        showCommand(`正在安装你选择的 YouTube OAuth client JSON：${{file.name}}`);
      }} else {{
        showCommand('正在扫描 Downloads / Desktop / Documents 里的 Google OAuth client JSON。');
      }}
      const res = await fetch('/api/actions/install-youtube-oauth-client', {{
        method: 'POST',
        headers: {{'content-type': 'application/json'}},
        body: JSON.stringify(payload)
      }});
      const data = await res.json();
      const lines = [
        `YouTube OAuth client 安装：${{data.ok ? '成功' : '未找到'}}`,
        data.message || data.next_step || '',
        data.source ? `来源：${{data.source}}` : '',
        data.target ? `目标：${{data.target}}` : ''
      ].filter(Boolean);
      const candidates = data.candidates || [];
      if (candidates.length) {{
        lines.push('', '扫描结果：');
        candidates.slice(0, 6).forEach(item => {{
          lines.push(`- ${{item.ok ? '可用' : '不可用'}}：${{item.path || ''}} (${{item.status || ''}})`);
        }});
      }}
      showCommand(lines.join('\\n'));
      await refreshChannelStatuses(false);
      refreshActionHistory();
    }}
    async function validateChannelRoutes() {{
      if (!isActionServerAvailable()) {{
        showCommand('python3 /Users/wendy/work/content-ops/scripts/check_platform_channels.py');
        return;
      }}
      channelStatusList.innerHTML = '<p>正在验收通道路由。</p>';
      const res = await fetch('/api/actions/validate-channel-routes', {{
        method: 'POST',
        headers: {{'content-type': 'application/json'}},
        body: JSON.stringify({{confirmed: true}})
      }});
      const data = await res.json();
      const summary = data.summary || {{}};
      const nextAuth = data.next_auth || {{}};
      const lines = [
        `通道路由验收：${{data.ok ? '通过' : '未通过'}}`,
        `Ready：${{summary.ready_count ?? 0}}`,
        `需授权：${{summary.needs_auth_count ?? 0}}`,
        `代码/runtime 缺口：${{summary.code_or_runtime_gap_count ?? 0}}`,
        `Dry-run 通过：${{summary.dry_run_ok_count ?? 0}}`,
        nextAuth.platform ? '' : '',
        nextAuth.platform ? `下一个授权：${{nextAuth.label || platformLabels.get(nextAuth.platform) || nextAuth.platform}} (${{nextAuth.status || ''}})` : '',
        nextAuth.prepare_button ? `Dashboard：${{nextAuth.prepare_button}}` : '',
        nextAuth.credential_file ? `凭据文件：${{nextAuth.credential_file}}` : '',
        nextAuth.manual_command ? `命令：${{nextAuth.manual_command}}` : '',
        nextAuth.browser_fix ? `浏览器处理：${{nextAuth.browser_fix}}` : '',
        '',
        'Dry-runs:',
        ...((data.dry_runs || []).map(item => `- ${{platformLabels.get(item.platform) || item.platform}}：${{item.ok ? 'ok' : 'fail'}} (${{item.status || ''}})`))
      ];
      showCommand(lines.join('\\n'));
      renderChannelStatuses({{ok: true, channels: data.channels || [], next_auth: data.next_auth || {{}}}});
      refreshActionHistory();
    }}
    async function prepareChannel(platformId, options = {{}}) {{
      if (!isActionServerAvailable()) {{
        showCommand('python3 /Users/wendy/work/content-ops/scripts/workbench_server.py --port 8788\\nopen http://127.0.0.1:8788/dashboard.html');
        return;
      }}
      const label = platformLabels.get(platformId) || platformId;
      if (!options.skipConfirm && !confirm(`准备 ${{label}} 通道？\\n\\n这可能会启动本地服务、打开登录页或安装本地 runtime，但不会发布内容。`)) return;
      showCommand(`正在打开 ${{label}} 登录/授权流程...`);
      try {{
        const res = await fetch('/api/actions/prepare-channel', {{
          method: 'POST',
          headers: {{'content-type': 'application/json'}},
          body: JSON.stringify({{platform: platformId}})
        }});
        const data = await res.json();
        showCommand(`${{label}} 通道准备动作已执行。正在重新检查全部通道。\\n${{data.next_step || data.message || data.status || ''}}`);
        if (data.auth_qrcodes || data.login_sessions) renderAuthQrcodes(data.auth_qrcodes || {{}}, data.login_sessions || {{}});
        refreshActionHistory();
        await refreshChannelStatuses(false);
      }} catch (error) {{
        showCommand(`${{label}} 登录/授权流程启动失败：${{error?.message || error}}`);
      }}
    }}
    async function prepareMissingChannels() {{
      if (!isActionServerAvailable()) {{
        showCommand('python3 /Users/wendy/work/content-ops/scripts/workbench_server.py --port 8788\\nopen http://127.0.0.1:8788/dashboard.html');
        return;
      }}
      if (!confirm('准备所有当前缺失通道？\\n\\n这可能会打开多个 Terminal 登录流程、本地 bridge 或平台后台。不会发布任何内容。')) return;
      const res = await fetch('/api/actions/prepare-missing-channels', {{
        method: 'POST',
        headers: {{'content-type': 'application/json'}},
        body: JSON.stringify({{confirmed: true}})
      }});
      const data = await res.json();
      showCommand(`缺失通道准备动作已执行：${{data.status || ''}}。正在重新检查全部通道。`);
      refreshActionHistory();
      await refreshChannelStatuses(false);
    }}
    async function refreshAuthPrompts() {{
      if (!isActionServerAvailable()) {{
        showCommand('python3 /Users/wendy/work/content-ops/scripts/workbench_server.py --port 8788\\nopen http://127.0.0.1:8788/dashboard.html');
        return;
      }}
      if (!confirm('刷新当前未打通平台的扫码/登录入口？\\n\\n这会重启小红书、视频号、Bilibili 的登录会话，并重新生成可扫码入口；YouTube 会继续走 OAuth client/OAuth 准备流程。不会发布内容。')) return;
      showCommand('正在刷新扫码/登录入口。新二维码出现后请扫码，然后点“等待授权完成”。');
      const res = await fetch('/api/actions/refresh-auth-prompts', {{
        method: 'POST',
        headers: {{'content-type': 'application/json'}},
        body: JSON.stringify({{confirmed: true}})
      }});
      const data = await res.json();
      renderAuthQrcodes(data.auth_qrcodes || {{}}, data.login_sessions || {{}});
      showCommand(`${{data.message || data.status || ''}}\\n\\n已处理：${{(data.actions || []).map(item => platformLabels.get(item.platform) || item.platform).join('、')}}`);
      refreshActionHistory();
      await refreshChannelStatuses(false);
    }}
    async function prepareNextAuth(skipManualBlockers = false) {{
      if (!isActionServerAvailable()) {{
        showCommand('python3 /Users/wendy/work/content-ops/scripts/workbench_server.py --port 8788\\nopen http://127.0.0.1:8788/dashboard.html');
        return;
      }}
      const prompt = skipManualBlockers
        ? '跳过当前必须人工处理的授权卡点，准备下一个可启动授权？\\n\\n这会跳过例如 Chrome 扩展站点权限这种必须你手动处理的项目，继续拉起后续平台登录流程。不会发布内容。'
        : '准备下一个未授权平台？\\n\\n顺序：小红书 -> 视频号 -> Bilibili -> YouTube。每次只拉起一个登录/OAuth 流程，不会发布内容。';
      if (!confirm(prompt)) return;
      const res = await fetch('/api/actions/prepare-next-auth', {{
        method: 'POST',
        headers: {{'content-type': 'application/json'}},
        body: JSON.stringify({{confirmed: true, skip_manual_blockers: skipManualBlockers}})
      }});
      const data = await res.json();
      const platformLabel = data.platform ? (platformLabels.get(data.platform) || data.platform) : '';
      const lines = [
        data.message || data.status || '',
        platformLabel ? `平台：${{platformLabel}}` : '',
        data.before_status ? `原状态：${{data.before_status}}` : '',
        data.result && data.result.next_step ? `下一步：${{data.result.next_step}}` : '',
        data.skipped && data.skipped.length ? `已跳过：${{data.skipped.map(item => `${{platformLabels.get(item.platform) || item.platform}}(${{item.status}})`).join('、')}}` : '',
        data.remaining && data.remaining.length ? `之后还剩：${{data.remaining.map(item => platformLabels.get(item) || item).join('、')}}` : ''
      ].filter(Boolean);
      showCommand(lines.join('\\n'));
      refreshActionHistory();
      await refreshChannelStatuses(false);
    }}
    async function preflightSource(sourceContentId, platforms = null) {{
      if (!isActionServerAvailable()) {{
        showCommand('python3 /Users/wendy/work/content-ops/scripts/workbench_server.py --port 8788\\nopen http://127.0.0.1:8788/dashboard.html');
        return;
      }}
      const res = await fetch('/api/actions/preflight-source', {{
        method: 'POST',
        headers: {{'content-type': 'application/json'}},
        body: JSON.stringify({{source_content_id: sourceContentId, platforms}})
      }});
      const data = await res.json();
      showCommand(JSON.stringify(data, null, 2));
      renderPreflightResult(data);
      refreshActionHistory();
    }}
    function preflightNextStep(item) {{
      if (item.ready) {{
        return item.mode === 'draft_push' ? '可以尝试推送平台草稿箱。' : '可以打开后台填稿。';
      }}
      const failed = (item.checks || []).filter(check => !check.ok).map(check => check.name);
      if (failed.includes('local_draft')) return '先生成或修复这个平台的本地草稿。';
      if (failed.includes('source_video')) return '先补齐原视频；图文源不进入视频迁移。';
      if (failed.includes('xhs_rendered_package')) return '先完成小红书质量检查和图文卡片渲染。';
      if (failed.includes('markdown')) return '先补齐公众号 Markdown 草稿。';
      if (failed.includes('channel_ready')) return '先检查登录或准备通道。';
      if (failed.includes('handoff_available')) return '先确认后台交接入口。';
      return '需要人工检查。';
    }}
    function renderPreflightResult(data) {{
      const panel = document.getElementById('preflight-result');
      if (!panel) return;
      if (!data.ok) {{
        panel.style.display = 'block';
        panel.innerHTML = `<h3>预检失败</h3><p>${{escapeHtml(data.message || data.status || 'unknown error')}}</p>`;
        return;
      }}
      const rows = (data.platforms || []).map(item => {{
        const failedChecks = (item.checks || []).filter(check => !check.ok).map(check => check.name);
        const checks = (item.checks || []).map(check => {{
          const mark = check.ok ? 'OK' : '缺';
          const message = check.message ? `：${{check.message}}` : '';
          return `<li>${{escapeHtml(mark)}} · ${{escapeHtml(check.name)}}${{escapeHtml(message)}}</li>`;
        }}).join('');
        const repairButton = (!item.ready && item.platform === 'xiaohongshu' && failedChecks.includes('xhs_rendered_package'))
          ? `<div class="action-row"><button class="command" type="button" data-action="prepare-local-asset" data-platform="${{escapeHtml(item.platform)}}" data-source-id="${{escapeHtml(data.source_content_id)}}">生成小红书图文包</button></div>`
          : '';
        const draftButton = (!item.ready && failedChecks.includes('local_draft'))
          ? `<div class="action-row"><button class="command" type="button" data-action="generate-local-draft" data-platform="${{escapeHtml(item.platform)}}" data-source-id="${{escapeHtml(data.source_content_id)}}">生成本地草稿</button></div>`
          : '';
        const videoRepairButton = (!item.ready && ['wechat_channels', 'bilibili', 'youtube'].includes(item.platform) && failedChecks.includes('source_video') && data.content_type !== 'gallery')
          ? `<div class="action-row"><button class="command" type="button" data-action="repair-source-video" data-source-id="${{escapeHtml(data.source_content_id)}}">修复这条原视频</button></div>`
          : '';
        return `<article class="preflight-item">
          <header>
            <b>${{escapeHtml(item.label || item.platform)}}</b>
            <span class="status ${{item.ready ? 'sent' : 'review_needed'}}">${{item.ready ? '可继续' : '需处理'}}</span>
          </header>
          <p>${{escapeHtml(preflightNextStep(item))}}</p>
          <ul class="preflight-checks">${{checks}}</ul>
          ${{draftButton}}
          ${{repairButton}}
          ${{videoRepairButton}}
        </article>`;
      }}).join('');
      panel.style.display = 'block';
      const hasLocalGaps = (data.platforms || []).some(item => (item.checks || []).some(check => !check.ok && ['local_draft', 'xhs_rendered_package', 'markdown'].includes(check.name)));
      const bulkRepair = hasLocalGaps
        ? `<div class="action-row"><button class="command" type="button" data-action="repair-local-gaps" data-source-id="${{escapeHtml(data.source_content_id)}}">补齐本地缺口</button></div>`
        : '';
      panel.innerHTML = `<h3>预检结果：${{data.ready_count || 0}} 可继续 · ${{data.needs_work_count || 0}} 需处理</h3>${{bulkRepair}}<div class="preflight-grid">${{rows}}</div>`;
    }}
    async function prepareLocalAsset(platformId, sourceContentId) {{
      if (!isActionServerAvailable()) {{
        showCommand('python3 /Users/wendy/work/content-ops/scripts/workbench_server.py --port 8788\\nopen http://127.0.0.1:8788/dashboard.html');
        return;
      }}
      const label = platformLabels.get(platformId) || platformId;
      if (!confirm(`生成${{label}}本地素材包？\\n\\n这会根据已通过的主题生成笔记、运行质量检查并渲染图文卡片，不会打开平台后台，也不会发布。`)) return;
      const res = await fetch('/api/actions/prepare-local-asset', {{
        method: 'POST',
        headers: {{'content-type': 'application/json'}},
        body: JSON.stringify({{
          platform: platformId,
          source_content_id: sourceContentId,
          confirmed: true
        }})
      }});
      const data = await res.json();
      showCommand(JSON.stringify(data, null, 2));
      refreshActionHistory();
      preflightSource(sourceContentId);
      if (data.ok) setTimeout(() => location.reload(), 900);
    }}
    async function generateLocalDraft(platformId, sourceContentId) {{
      if (!isActionServerAvailable()) {{
        showCommand('python3 /Users/wendy/work/content-ops/scripts/workbench_server.py --port 8788\\nopen http://127.0.0.1:8788/dashboard.html');
        return;
      }}
      const label = platformLabels.get(platformId) || platformId;
      if (!confirm(`生成${{label}}本地草稿？\\n\\n这只会在 outbox/drafts/${{platformId}} 写入本地 Markdown/JSON，不会打开平台后台，也不会发布。`)) return;
      const res = await fetch('/api/actions/generate-local-draft', {{
        method: 'POST',
        headers: {{'content-type': 'application/json'}},
        body: JSON.stringify({{
          platform: platformId,
          source_content_id: sourceContentId,
          confirmed: true
        }})
      }});
      const data = await res.json();
      showCommand(JSON.stringify(data, null, 2));
      refreshActionHistory();
      preflightSource(sourceContentId);
    }}
    async function repairLocalGaps(sourceContentId) {{
      if (!isActionServerAvailable()) {{
        showCommand('python3 /Users/wendy/work/content-ops/scripts/workbench_server.py --port 8788\\nopen http://127.0.0.1:8788/dashboard.html');
        return;
      }}
      if (!confirm('补齐这条内容的本地缺口？\\n\\n这会生成缺失平台草稿，并补齐小红书图文包。不会下载视频、不会打开平台后台，也不会发布。')) return;
      const res = await fetch('/api/actions/repair-local-gaps', {{
        method: 'POST',
        headers: {{'content-type': 'application/json'}},
        body: JSON.stringify({{
          source_content_id: sourceContentId,
          confirmed: true
        }})
      }});
      const data = await res.json();
      showCommand(JSON.stringify(data, null, 2));
      refreshActionHistory();
      preflightSource(sourceContentId);
    }}
    async function repairAllLocalGaps() {{
      if (!isActionServerAvailable()) {{
        showCommand('python3 /Users/wendy/work/content-ops/scripts/workbench_server.py --port 8788\\nopen http://127.0.0.1:8788/dashboard.html');
        return;
      }}
      if (!confirm('补齐全部源内容的本地缺口？\\n\\n这会批量生成缺失的平台草稿，并补齐小红书图文包。不会打开平台后台，也不会发布。')) return;
      const res = await fetch('/api/actions/repair-all-local-gaps', {{
        method: 'POST',
        headers: {{'content-type': 'application/json'}},
        body: JSON.stringify({{confirmed: true}})
      }});
      const data = await res.json();
      showCommand(JSON.stringify({{
        ok: data.ok,
        status: data.status,
        source_count: data.source_count,
        ok_count: data.ok_count,
        failure_count: data.failure_count,
        failures: data.failures || []
      }}, null, 2));
      refreshActionHistory();
      if (data.ok) setTimeout(() => location.reload(), 900);
    }}
    async function runActionQueue(apply=false) {{
      if (!isActionServerAvailable()) {{
        showCommand('python3 /Users/wendy/work/content-ops/scripts/workbench_server.py --port 8788\\nopen http://127.0.0.1:8788/dashboard.html');
        return;
      }}
      if (apply && !confirm('执行自动修复队列？\\n\\n这只会处理 auto_repair_candidate lane，会修改本地小红书草稿并刷新 workflow；不会推送平台草稿箱，也不会发布。')) return;
      showCommand(apply ? '正在执行自动修复队列，并在完成后刷新 workflow。' : '正在 dry-run 自动修复队列。');
      const res = await fetch('/api/actions/run-action-queue', {{
        method: 'POST',
        headers: {{'content-type': 'application/json'}},
        body: JSON.stringify({{
          lane: 'auto_repair_candidate',
          apply,
          confirmed: apply
        }})
      }});
      const data = await res.json();
      showCommand(JSON.stringify(data, null, 2));
      refreshActionHistory();
      if (apply && data.ok) setTimeout(() => location.reload(), 1000);
    }}
    async function recordActionDecision(decision, draftPath, sourceContentId) {{
      if (!isActionServerAvailable()) {{
        showCommand('python3 /Users/wendy/work/content-ops/scripts/workbench_server.py --port 8788\\nopen http://127.0.0.1:8788/dashboard.html');
        return;
      }}
      const labels = {{
        reingest: '重抓/转录',
        skip: '跳过',
        merge: '合并',
        drop: '丢弃'
      }};
      const label = labels[decision] || decision;
      let reason = prompt(`记录人工决策：${{label}}\\n\\n这只会更新本地 outbox 决策记录，并刷新行动队列；不会删除文件、不会发布。\\n\\n可填写原因：`, '');
      if (reason === null) return;
      let mergeTarget = '';
      if (decision === 'merge') {{
        mergeTarget = prompt('要合并到哪一篇/哪个主题？可以先留空，后续人工处理。', '') || '';
      }}
      const res = await fetch('/api/actions/record-action-decision', {{
        method: 'POST',
        headers: {{'content-type': 'application/json'}},
        body: JSON.stringify({{
          decision,
          draft_path: draftPath,
          source_content_id: sourceContentId,
          reason,
          merge_target: mergeTarget
        }})
      }});
      const data = await res.json();
      showCommand(JSON.stringify(data, null, 2));
      refreshActionHistory();
      if (data.ok) setTimeout(() => location.reload(), 900);
    }}
    async function clearActionDecision(draftPath, sourceContentId) {{
      if (!isActionServerAvailable()) {{
        showCommand('python3 /Users/wendy/work/content-ops/scripts/workbench_server.py --port 8788\\nopen http://127.0.0.1:8788/dashboard.html');
        return;
      }}
      if (!confirm('撤回这条人工决策？\\n\\n这只会移除本地 action decision，并刷新队列；不会删除文件、不会发布。')) return;
      const res = await fetch('/api/actions/record-action-decision', {{
        method: 'POST',
        headers: {{'content-type': 'application/json'}},
        body: JSON.stringify({{
          clear: true,
          draft_path: draftPath,
          source_content_id: sourceContentId
        }})
      }});
      const data = await res.json();
      showCommand(JSON.stringify(data, null, 2));
      refreshActionHistory();
      if (data.ok) setTimeout(() => location.reload(), 900);
    }}
    async function repairSourceVideo(sourceContentId) {{
      if (!isActionServerAvailable()) {{
        showCommand('python3 /Users/wendy/work/content-ops/scripts/workbench_server.py --port 8788\\nopen http://127.0.0.1:8788/dashboard.html');
        return;
      }}
      if (!confirm('修复这条抖音原视频？\\n\\n这会使用本地 Douyin cookies 重新下载或复制这一条视频到 outbox/sent/douyin。不会发布任何平台内容。')) return;
      const res = await fetch('/api/actions/repair-missing-videos', {{
        method: 'POST',
        headers: {{'content-type': 'application/json'}},
        body: JSON.stringify({{
          source_content_ids: [sourceContentId],
          dry_run: false,
          confirmed: true
        }})
      }});
      const data = await res.json();
      showCommand(JSON.stringify(data, null, 2));
      refreshActionHistory();
      preflightSource(sourceContentId);
    }}
    async function markSent(platformId, sourceContentId, localId, title) {{
      if (!isActionServerAvailable()) {{
        showCommand('python3 /Users/wendy/work/content-ops/scripts/workbench_server.py --port 8788\\nopen http://127.0.0.1:8788/dashboard.html');
        return;
      }}
      const label = platformLabels.get(platformId) || platformId;
      if (!confirm(`确认已经在${{label}}后台发送/保存完成？\\n\\n${{title || sourceContentId}}\\n\\n这只会把本地 outbox 草稿移到 sent，不会调用平台发布。`)) return;
      const res = await fetch('/api/actions/mark-sent', {{
        method: 'POST',
        headers: {{'content-type': 'application/json'}},
        body: JSON.stringify({{
          platform: platformId,
          source_content_id: sourceContentId,
          local_id: localId || '',
          confirmed: true
        }})
      }});
      const data = await res.json();
      showCommand(JSON.stringify(data, null, 2));
      refreshActionHistory();
      if (data.ok) setTimeout(() => location.reload(), 700);
    }}
    async function repairMissingVideos(apply=false) {{
      if (!isActionServerAvailable()) {{
        showCommand('python3 /Users/wendy/work/content-ops/scripts/workbench_server.py --port 8788\\nopen http://127.0.0.1:8788/dashboard.html');
        return;
      }}
      if (apply && !confirm('修复缺视频素材？\\n\\n这会使用本地 Douyin cookies 重新下载缺失视频，并复制到 outbox/sent/douyin。不会发布任何平台内容。')) return;
      const res = await fetch('/api/actions/repair-missing-videos', {{
        method: 'POST',
        headers: {{'content-type': 'application/json'}},
        body: JSON.stringify({{
          dry_run: !apply,
          confirmed: apply
        }})
      }});
      const data = await res.json();
      showCommand(JSON.stringify(data, null, 2));
      refreshActionHistory();
      if (apply && data.ok) setTimeout(() => location.reload(), 900);
    }}
    async function generateLocalDraftSilent(platformId, sourceContentId) {{
      const res = await fetch('/api/actions/generate-local-draft', {{
        method: 'POST',
        headers: {{'content-type': 'application/json'}},
        body: JSON.stringify({{
          platform: platformId,
          source_content_id: sourceContentId,
          confirmed: true
        }})
      }});
      return await res.json();
    }}
    async function pushDraftSilent(platformId, sourceContentId, localId) {{
      const res = await fetch('/api/actions/push-draft', {{
        method: 'POST',
        headers: {{'content-type': 'application/json'}},
        body: JSON.stringify({{
          platform: platformId,
          source_content_id: sourceContentId,
          local_id: localId || '',
          confirmed: true
        }})
      }});
      return await res.json();
    }}
    function migrationStageLabel(item) {{
      const stage = item?.stage || item?.status || 'unchecked';
      const map = {{
        connected: '已连接',
        needs_login: '需要登录',
        waiting_auth: '等待登录',
        publishing: '发布中',
        published: '已公开发布',
        submitted_review: '已提交审核',
        verified_public: '已公开视频',
        public_uploaded: '已公开上传',
        found_in_manager: '已找到稿件',
        web_login_valid: '已连接',
        login_required: '需要登录',
        declaration_required: '需声明',
        upload_timeout: '上传超时',
        submit_not_confirmed: '提交未确认',
        public_unavailable: '公开视频不可用',
        public_unverified: '公开视频待验证',
        blocked: '不可搬运',
        failed: '失败',
        checking: '检查中'
      }};
      if (item?.ok && stage === 'connected') return '已连接';
      return map[stage] || item?.status || stage;
    }}
    function migrationStageClass(item) {{
      const stage = item?.stage || item?.status || '';
      if (item?.ok || ['published', 'connected', 'submitted_review', 'verified_public', 'public_uploaded', 'found_in_manager'].includes(stage)) return 'sent';
      if (['failed', 'blocked', 'login_required', 'declaration_required', 'upload_timeout', 'submit_not_confirmed', 'public_unavailable'].includes(stage)) return 'missing_asset';
      if (stage === 'waiting_auth' || stage === 'needs_login' || stage === 'checking' || stage === 'publishing') return 'review_needed';
      return 'draft';
    }}
    function platformResultUrl(item) {{
      return item?.platform_url || item?.result?.platform_url || item?.result?.url || '';
    }}
    function mergeMigrationRuntime(sourceContentId, data) {{
      if (!data) return;
      migrationRuntime[sourceContentId] = data;
      const source = sourceById.get(sourceContentId);
      if (source) renderDetail(source);
    }}
    async function refreshVideoMigrationStatus(sourceContentId, silent = true) {{
      if (!isActionServerAvailable()) {{
        mergeMigrationRuntime(sourceContentId, {{
          ok: false,
          status: 'server_required',
          platforms: migrationPlatformIds.map(platform => ({{
            platform,
            label: platformLabels.get(platform) || platform,
            stage: 'blocked',
            status: 'server_required',
            message: '需要用本地 workbench server 打开页面后才能执行搬运。'
          }}))
        }});
        if (!silent) showCommand(serverLaunchCommand);
        return null;
      }}
      try {{
        const res = await fetch(`/api/actions/video-migration/status?source_content_id=${{encodeURIComponent(sourceContentId)}}`, {{cache: 'no-store'}});
        const data = await res.json();
        mergeMigrationRuntime(sourceContentId, data);
        return data;
      }} catch (error) {{
        const data = {{
          ok: false,
          status: 'status_check_failed',
          platforms: migrationPlatformIds.map(platform => ({{
            platform,
            label: platformLabels.get(platform) || platform,
            stage: 'failed',
            status: 'status_check_failed',
            message: '读取平台状态失败。'
          }}))
        }};
        mergeMigrationRuntime(sourceContentId, data);
        return data;
      }}
    }}
    function startMigrationAuthPolling(sourceContentId) {{
      if (migrationPollTimer) clearInterval(migrationPollTimer);
      migrationPollTimer = setInterval(async () => {{
        const data = await refreshVideoMigrationStatus(sourceContentId, true);
        if (data && data.ok) {{
          clearInterval(migrationPollTimer);
          migrationPollTimer = null;
          await batchMigrateVideo(sourceContentId, {{skipConfirm: true}});
        }}
      }}, 5000);
    }}
    async function generateContentPackage(sourceContentId) {{
      if (!isActionServerAvailable()) {{
        showCommand('python3 /Users/wendy/work/content-ops/scripts/workbench_server.py --port 8788\\nopen http://127.0.0.1:8788/dashboard.html');
        return;
      }}
      if (!confirm('生成这条视频的 AI 内容包？\\n\\n这一步会读取 raw transcript，生成可读长文和主题判断。不会生成平台草稿，也不会发布。')) return;
      showCommand('正在生成 AI 内容包。这一步可能需要几分钟，请等待。');
      const res = await fetch('/api/actions/generate-content-package', {{
        method: 'POST',
        headers: {{'content-type': 'application/json'}},
        body: JSON.stringify({{
          source_content_id: sourceContentId,
          confirmed: true
        }})
      }});
      const data = await res.json();
      showCommand(JSON.stringify(data, null, 2));
      refreshActionHistory();
      if (data.ok || data.status === 'content_package_with_warnings') setTimeout(() => location.reload(), 900);
    }}
    async function approveContentPackage(sourceContentId) {{
      if (!isActionServerAvailable()) {{
        showCommand(serverLaunchCommand);
        return;
      }}
      if (!confirm('确认通过这一步内容包？\\n\\n通过后第二步会变成绿色，后续公众号 / 主题拆分都视为基于已审核内容包继续。')) return;
      const res = await fetch('/api/actions/approve-content-package', {{
        method: 'POST',
        headers: {{'content-type': 'application/json'}},
        body: JSON.stringify({{
          source_content_id: sourceContentId,
          confirmed: true
        }})
      }});
      const data = await res.json();
      showCommand(formatActionResult(data));
      refreshActionHistory();
      if (data.ok) setTimeout(() => location.reload(), 500);
    }}
    async function batchMigrateVideo(sourceContentId, options = {{}}) {{
      if (!isActionServerAvailable()) {{
        showCommand(serverLaunchCommand);
        return;
      }}
      if (!options.skipConfirm && !confirm('确认公开发布到 视频号 / Bilibili / YouTube？\\n\\n这是公开发布动作，不是保存草稿。若有平台未登录，本次不会开始上传，页面会显示需要先登录的平台。')) return;
      const running = {{
        ok: false,
        status: 'publishing',
        platforms: migrationPlatformIds.map(platform => ({{
          platform,
          label: platformLabels.get(platform) || platform,
          stage: 'publishing',
          status: 'publishing',
          message: '正在检查并发布。'
        }}))
      }};
      mergeMigrationRuntime(sourceContentId, running);
      try {{
        const res = await fetch('/api/actions/video-migration/run', {{
          method: 'POST',
          headers: {{'content-type': 'application/json'}},
          body: JSON.stringify({{
            source_content_id: sourceContentId,
            publish_mode: 'public',
            confirmed: true
          }})
        }});
        const data = await res.json();
        mergeMigrationRuntime(sourceContentId, data);
        const needsLogin = (data.platforms || []).filter(item => item && item.stage === 'needs_login');
        let autoPreparedLogin = false;
        if (data.status === 'waiting_auth') startMigrationAuthPolling(sourceContentId);
        if (data.status === 'needs_login' && needsLogin.length) {{
          showCommand(formatActionResult(data) + `\\n\\n正在打开 ${{platformLabels.get(needsLogin[0].platform) || needsLogin[0].platform}} 登录流程...`);
          await prepareChannel(needsLogin[0].platform, {{skipConfirm: true}});
          autoPreparedLogin = true;
        }}
        if (!autoPreparedLogin) showCommand(formatActionResult(data));
        refreshActionHistory();
      }} catch (error) {{
        const data = {{
          ok: false,
          status: 'request_failed',
          source_content_id: sourceContentId,
          message: `一键搬运请求失败：${{error?.message || error}}`,
          platforms: migrationPlatformIds.map(platform => ({{
            platform,
            label: platformLabels.get(platform) || platform,
            ok: false,
            stage: 'failed',
            status: 'request_failed',
            message: `请求没有成功返回：${{error?.message || error}}`
          }}))
        }};
        mergeMigrationRuntime(sourceContentId, data);
        showCommand(formatActionResult(data));
        refreshActionHistory();
      }}
    }}
    function renderDetail(source) {{
      const sourceCover = source.cover_href
        ? `<span class="source-thumb"><img src="${{escapeHtml(source.cover_href)}}" alt=""></span>`
        : `<span class="source-thumb"><span class="source-thumb-fallback">抖音</span></span>`;
      const selectedPlatform = document.getElementById('platform-filter')?.value || '';
      const topicPlan = source.topic_plan || {{topics: []}};
      const topics = packageTopics(source, topicPlan);
      const transcriptState = transcriptStatus(source);
      const contentPackageText = source.content_package_text || '';
      const readableChars = source.content_package_readable_chars || source.organized_chars || 0;
      const topicCount = source.content_package_topic_count || topicPlan.topic_count || 0;
      const productionTopicCount = (source.content_package_topic_groups || []).length || topicCount;
      const mainTopicCount = (source.content_package_topic_groups || []).length
        ? (source.content_package_topic_groups || []).filter(topic => topic.priority === 'main').length
        : (source.content_package_topics || []).length
        ? (source.content_package_topics || []).filter(topic => topic.priority === 'main').length
        : (topicPlan.main_topic_count || 0);
      const topicHtml = topics.length ? topics.map((topic, index) => {{
        const points = (topic.points || []).slice(0, 3);
        const pointHtml = points.length ? `
          <div class="topic-points">
            ${{points.map((point, pointIndex) => `
              <article class="topic-point">
                <span>${{pointIndex + 1}}</span>
                <div>
                  <b>${{escapeHtml(point.title || `要点 ${{pointIndex + 1}}`)}}</b>
                  ${{point.reader_mirror ? `<p class="reader-mirror"><strong>如果你也：</strong>${{escapeHtml(point.reader_mirror)}}</p>` : ''}}
                  ${{point.judgment ? `<p><strong>判断：</strong>${{escapeHtml(point.judgment)}}</p>` : ''}}
                  ${{point.explanation ? `<p><strong>解释：</strong>${{escapeHtml(point.explanation)}}</p>` : ''}}
                  ${{point.evidence ? `<p><strong>例子：</strong>${{escapeHtml(point.evidence)}}</p>` : ''}}
                </div>
              </article>`).join('')}}
          </div>` : '';
        return `
        <article class="topic-pill topic-framework">
          <header>
            <div>
              <b>${{index + 1}}. ${{escapeHtml(topic.draft_title || topic.title)}}</b>
              <p class="topic-subtitle">主题 = 一个可被卖出去的观点</p>
            </div>
            <span class="status ${{topic.priority === 'main' ? 'packaged' : 'missing'}}">${{escapeHtml(topic.priority === 'main' ? '主选题' : '备选')}}</span>
          </header>
          <div class="topic-framework-grid">
            ${{topic.reader_mirror || topic.contrast ? `<section class="reader-mirror-section"><span>用户视角</span><p>${{escapeHtml(topic.reader_mirror || topic.contrast || '')}}</p></section>` : ''}}
            <section><span>反对结论</span><p>${{escapeHtml(topic.reason || '')}}</p></section>
            ${{topic.why_it_matters ? `<section><span>论证与支持</span><p>${{escapeHtml(topic.why_it_matters)}}</p></section>` : ''}}
          </div>
          ${{pointHtml}}
          <div class="topic-framework-grid">
            ${{topic.boundary ? `<section><span>Boundary / 边界</span><p>${{escapeHtml(topic.boundary)}}</p></section>` : ''}}
            ${{topic.takeaway ? `<section><span>Takeaway / 总结</span><p>${{escapeHtml(topic.takeaway)}}</p></section>` : ''}}
          </div>
          ${{(topic.merged_topic_titles || []).length ? `<p class="topic-merge"><b>合并自：</b>${{escapeHtml(topic.merged_topic_titles.join(' / '))}}</p>` : ''}}
          ${{topic.merge_reason ? `<p class="topic-merge"><b>合并逻辑：</b>${{escapeHtml(topic.merge_reason)}}</p>` : ''}}
        </article>`;
      }}).join('') : '<p>还没有主题计划。</p>';
      const migrationStates = migrationPlatformIds.map(platformId => source.platforms[platformId]).filter(Boolean);
      const runtimeMigration = migrationRuntime[source.source_content_id] || null;
      const runtimePlatforms = new Map((runtimeMigration?.platforms || []).map(item => [item.platform, item]));
      const migrationDone = runtimeMigration?.status === 'published' || (runtimeMigration?.platforms || []).length === migrationPlatformIds.length && (runtimeMigration?.platforms || []).every(item => item.ok && ['published', 'submitted_review', 'verified_public', 'public_uploaded', 'found_in_manager'].includes(item.stage || item.status)) || (migrationStates.length > 0 && migrationStates.every(state => ['sent', 'packaged'].includes(state.status)));
      const migrationReady = source.media_count > 0 && migrationStates.some(state => !['sent', 'source_gallery', 'missing_asset'].includes(state.status));
      const migrationWaiting = runtimeMigration?.status === 'waiting_auth';
      const migrationFailed = runtimeMigration?.status === 'partial_failed';
      const migrationPublishing = runtimeMigration?.status === 'publishing';
      const migrationButtonLabel = migrationDone ? '已完成三平台搬运' : isActionServerAvailable() ? '一键公开发布到 3 个平台' : '需要启动本地服务';
      const packageDone = Boolean(source.content_package_text) && Boolean(source.content_package_approved) && !(source.content_package_warnings || []).length;
      const packageWarn = Boolean(source.content_package_text) && (source.content_package_warnings || []).length > 0;
      const packageApproved = Boolean(source.content_package_approved);
      const wechatState = source.platforms.wechat_mp || {{}};
      const wechatDrafts = wechatState.drafts || [];
      const wechatHasPreview = wechatDrafts.some(draft => draft.html_href || Object.values(draft.style_variants || {{}}).some(variant => variant && variant.html_preview_href));
      const wechatHasDrafts = wechatDrafts.length > 0 || (wechatState.sent || []).length > 0;
      const wechatReady = Boolean((wechatState.sent || []).length) || wechatHasPreview;
      const topicDone = Boolean(source.content_package_text) && topics.length > 0;
      const downstreamReviewIds = ['xiaohongshu', 'x'];
      const currentXhsDrafts = (source.platforms.xiaohongshu?.drafts || []).filter(draft => draft.is_current_xhs_workflow);
      const legacyXhsDrafts = (source.platforms.xiaohongshu?.drafts || []).filter(draft => !draft.is_current_xhs_workflow);
      const reviewHasDrafts = currentXhsDrafts.length > 0 || downstreamReviewIds.filter(platformId => platformId !== 'xiaohongshu').some(platformId => (source.platforms[platformId]?.drafts || []).length > 0);
      const reviewDone = downstreamReviewIds.every(platformId => ['sent'].includes(source.platforms[platformId]?.status));
      const migrationStepClass = migrationDone ? 'is-done' : migrationFailed || migrationWaiting ? 'is-current is-warn' : 'is-current';
      const packageStepClass = packageDone ? 'is-done' : packageWarn || source.content_package_text ? 'is-current is-warn' : migrationDone ? 'is-current' : 'is-locked';
      const wechatStepClass = wechatReady ? 'is-done' : wechatHasDrafts ? 'is-current is-warn' : source.content_package_text ? 'is-current' : 'is-locked';
      const topicStepClass = topicDone && packageApproved && !packageWarn ? 'is-done' : topicDone ? 'is-current is-warn' : 'is-locked';
      const reviewStepClass = reviewDone ? 'is-done' : currentXhsDrafts.length ? 'is-current' : legacyXhsDrafts.length ? 'is-current is-warn' : topicDone ? 'is-current' : 'is-locked';
      const migrationStatusItems = migrationPlatformIds.map(platformId => {{
        const state = source.platforms[platformId];
        const runtimeState = runtimePlatforms.get(platformId);
        const label = platformLabels.get(platformId) || platformId;
        const done = runtimeState ? ['published', 'submitted_review', 'verified_public', 'public_uploaded', 'found_in_manager'].includes(runtimeState.stage || runtimeState.status) || runtimeState.ok : ['sent', 'packaged'].includes(state.status);
        const failed = runtimeState && ['failed', 'blocked'].includes(runtimeState.stage);
        const waiting = runtimeState && ['needs_login', 'waiting_auth', 'publishing', 'checking'].includes(runtimeState.stage);
        const message = runtimeState?.message || (done ? '已完成。' : state.next_action || '等待执行。');
        const resultUrl = platformResultUrl(runtimeState);
        const evidenceHref = runtimeState?.evidence_screenshot_href || runtimeState?.result?.evidence_screenshot_href || '';
        const evidence = evidenceHref
          ? `<div class="evidence-shot"><img src="${{escapeHtml(evidenceHref)}}" alt="${{escapeHtml(label)}} 发布截图" data-lightbox-images="${{encodeURIComponent(JSON.stringify([evidenceHref]))}}" data-lightbox-index="0" data-lightbox-label="${{escapeHtml(label + ' 发布截图')}}"></div>`
          : '';
        const retryButton = failed
          ? `<button class="action" type="button" data-action="batch-migrate-video" data-source-id="${{escapeHtml(source.source_content_id)}}">重试</button>`
          : '';
        const loginButton = runtimeState && (runtimeState.stage === 'needs_login' || runtimeState.status === 'login_required' || runtimeState.status === 'cookie_missing' || runtimeState.status === 'cookie_invalid')
          ? `<button class="action" type="button" data-action="prepare-channel" data-platform="${{escapeHtml(platformId)}}">登录${{escapeHtml(label)}}</button>`
          : '';
        return `<article class="migration-status-item ${{done ? 'done' : failed ? 'failed' : waiting ? 'waiting' : ''}}">
          <div class="migration-status-top">
            <strong><span class="platform-icon">${{escapeHtml(platformIcons[platformId] || '•')}}</span>${{escapeHtml(label)}}</strong>
            <span class="status ${{escapeHtml(migrationStageClass(runtimeState || state))}}">${{escapeHtml(runtimeState ? migrationStageLabel(runtimeState) : state.label)}}</span>
          </div>
          <p>${{escapeHtml(message)}}</p>
          ${{evidence}}
          <div class="action-row">
            ${{resultUrl ? navLink('打开结果', resultUrl) : ''}}
            ${{loginButton}}
            ${{retryButton}}
          </div>
        </article>`;
      }}).join('');
      function draftPreviewCard(platformId, state, draft, index) {{
        const draftHref = draft.package_href || draft.md_href || draft.json_href || state.primary_href;
        if (platformId === 'wechat_mp') {{
          const pushLocalId = draft.local_id || state.primary_local_id || '';
          const latest = draft.latest_platform_draft || {{}};
          const pushed = Boolean(latest.draft_id);
          const variants = draft.style_variants || {{}};
          const usableVariantEntries = Object.entries(variants).filter(([, variant]) => variant && (variant.html_preview_href || draft.html_href));
          const variantEntries = usableVariantEntries.length
            ? usableVariantEntries
            : (draft.html_href ? [['professional', {{id: 'professional', label: '简洁专业', description: '当前默认版本', html_preview_href: draft.html_href, wechat_html_href: draft.wechat_html_href}}]] : []);
          const defaultStyle = draft.wechat_style || 'professional';
          if (!variantEntries.length) {{
            return `<article class="draft-preview wechat-article-preview missing-preview">
              <header>
                <h3>${{escapeHtml(draft.title || state.primary_title || '公众号文章')}}</h3>
                <span class="status review_needed">缺 HTML 预览</span>
              </header>
              <div class="empty-preview">
                <strong>这条是旧占位草稿，还没有生成公众号 HTML 预览。</strong>
                <p>${{escapeHtml(draft.preview || draft.body || '需要先重新生成公众号文章，生成后这里才会显示排版、封面和插图。')}}</p>
              </div>
            </article>`;
          }}
          const styleButtons = variantEntries.map(([styleId, variant]) => `
            <button class="style-choice ${{styleId === defaultStyle ? 'active' : ''}}" type="button"
              data-action="wechat-style-preview"
              data-style-id="${{escapeHtml(styleId)}}"
              data-local-id="${{escapeHtml(pushLocalId)}}"
              title="${{escapeHtml(variant.description || '')}}">${{escapeHtml(variant.label || styleId)}}</button>
          `).join('');
          const styleSummaries = variantEntries.map(([styleId, variant]) => {{
            const thumbs = (variant.image_hrefs || []).map((src, imageIndex) => `<img src="${{escapeHtml(src)}}" alt="${{escapeHtml((variant.label || styleId) + ' 插图')}}" data-lightbox-images="${{encodeURIComponent(JSON.stringify(variant.image_hrefs || []))}}" data-lightbox-index="${{imageIndex}}" data-lightbox-label="${{escapeHtml(variant.label || styleId)}}">`).join('');
            const imageNames = (variant.image_keys || []).join(' / ');
            return `<div class="wechat-style-card ${{styleId === defaultStyle ? 'active' : ''}}" data-style-id="${{escapeHtml(styleId)}}" data-local-id="${{escapeHtml(pushLocalId)}}">
              <strong>${{escapeHtml(variant.label || styleId)}}：${{escapeHtml(variant.description || '')}}</strong>
              <div class="wechat-style-metrics">
                <span>${{Math.round((variant.body_chars || 0) / 100) / 10}}k 字符</span>
                <span>${{(variant.image_hrefs || []).length}} 张图</span>
                ${{imageNames ? `<span>${{escapeHtml(imageNames)}}</span>` : ''}}
              </div>
              ${{thumbs ? `<div class="wechat-style-thumbs">${{thumbs}}</div>` : ''}}
            </div>`;
          }}).join('');
          const styleFrames = variantEntries.map(([styleId, variant]) => `
            <iframe class="wechat-preview-frame wechat-style-frame ${{styleId === defaultStyle ? 'active' : ''}}"
              data-style-id="${{escapeHtml(styleId)}}"
              data-local-id="${{escapeHtml(pushLocalId)}}"
              src="${{escapeHtml((variant.html_preview_href || draft.html_href) + '?v=' + encodeURIComponent(String(variant.body_chars || styleId)))}}"
              title="公众号文章预览 - ${{escapeHtml(variant.label || styleId)}}"></iframe>
          `).join('');
          const evidence = latest.evidence_screenshot_href
            ? `<details class="wechat-evidence-details">
                <summary>公众号草稿截图证据 <span>点击展开</span></summary>
                <div class="evidence-shot wechat-evidence"><img src="${{escapeHtml(latest.evidence_screenshot_href)}}" alt="公众号草稿证据截图" data-lightbox-images="${{encodeURIComponent(JSON.stringify([latest.evidence_screenshot_href]))}}" data-lightbox-index="0" data-lightbox-label="公众号草稿证据截图"></div>
              </details>`
            : '';
          const pushMeta = pushed
            ? `<div class="wechat-push-meta"><span class="status sent">已推送草稿箱</span><span>${{escapeHtml(latest.style_label || '简洁专业')}}</span><code>${{escapeHtml(latest.draft_id || '')}}</code><p>${{escapeHtml(latest.pushed_at || '')}}</p></div>`
            : `<div class="wechat-push-meta"><span class="status review_needed">待推送草稿箱</span></div>`;
          return `<article class="draft-preview wechat-article-preview">
            <header>
              <h3>${{escapeHtml(draft.title || state.primary_title || '公众号文章')}}</h3>
              <span class="status ${{pushed ? 'sent' : escapeHtml(state.status)}}">${{pushed ? '草稿箱已生成' : '长文预览'}}</span>
            </header>
            <div class="wechat-style-bar">
              <b>风格</b>
              <div class="wechat-style-options">${{styleButtons}}</div>
            </div>
            <div class="wechat-style-summary">${{styleSummaries}}</div>
            <div class="wechat-style-frames">${{styleFrames}}</div>
            <div class="wechat-preview-note">先切换风格预览；推送时会使用当前选中的风格，并自动上传封面和正文图片。默认版“简洁专业”已保留。</div>
            ${{pushMeta}}
            ${{evidence}}
            <div class="node-actions">
              <button class="action primary" type="button" data-action="push-draft" data-platform="wechat_mp" data-source-id="${{escapeHtml(source.source_content_id)}}" data-local-id="${{escapeHtml(pushLocalId)}}" data-wechat-style="${{escapeHtml(defaultStyle)}}">${{pushed ? '重新推送到公众号草稿箱' : '推送到公众号草稿箱'}}</button>
            </div>
          </article>`;
        }}
        const groupId = `${{platformId}}-${{source.source_content_id}}-${{draft.local_id || index}}`;
        const encodedImages = encodeURIComponent(JSON.stringify(draft.preview_images || []));
        const images = (draft.preview_images || []).map((src, imageIndex) => `<img src="${{escapeHtml(src)}}" alt="" data-lightbox-images="${{encodedImages}}" data-lightbox-index="${{imageIndex}}" data-lightbox-label="${{escapeHtml(draft.title || state.primary_title || state.label)}}" data-lightbox-group="${{escapeHtml(groupId)}}">`).join('');
        const imageStrip = images ? `<div class="xhs-image-strip">${{images}}</div>` : '';
        const label = platformId === 'xiaohongshu' ? `笔记 ${{index + 1}}` : state.label;
        if (platformId === 'xiaohongshu' && !draft.is_current_xhs_workflow) {{
          return `<article class="draft-preview legacy-draft">
            <header>
              <h3>${{escapeHtml(draft.title || state.primary_title || state.label)}}</h3>
              <span class="status review_needed">旧格式</span>
            </header>
            <div class="empty-preview">
              <strong>这是旧流程生成的图文包，不算当前小红书 SOP 的产物。</strong>
              <p>需要重新从“第四步：小红书文字稿”生成当前版本，再进入图文预览。</p>
            </div>
            <div class="node-actions">
              ${{draftHref ? navLink('打开旧草稿', draftHref) : ''}}
            </div>
          </article>`;
        }}
        const workflowStatusLabel = draft.workflow_status === 'blocked_source'
          ? '源不足'
          : (draft.quality_passed ? '质检通过' : '待修');
        const triageLabels = {{
          skip_or_reingest: '需重抓/跳过',
          near_threshold_review: '可合并修复',
          merge_or_drop_unit: '合并/丢弃',
          stale_quality_recheck: '重跑质检'
        }};
        const triageLabel = triageLabels[draft.triage_bucket] || '';
        const triageLine = draft.workflow_status === 'blocked_source'
          ? `<div class="brief-line blocked">${{escapeHtml(draft.triage_reason || '源片段不足，不能从标题硬编成稿。')}}</div>`
          : '';
        const dbsReview = draft.dbs_review;
        const dbsChip = dbsReview
          ? `<span class="workflow-chip ${{dbsReview.verdict === 'keep' ? '' : 'warn'}}">DBS ${{dbsReview.total || 0}}/90 · ${{escapeHtml(dbsReview.verdict || 'pending')}}</span>`
          : '<span class="workflow-chip warn">DBS 未评分</span>';
        const dbsStructuralChip = dbsReview && (dbsReview.structural_blockers || []).length
          ? `<span class="workflow-chip warn">结构锁: ${{escapeHtml((dbsReview.structural_blockers || []).join(','))}}</span>`
          : '';
        const dbsActionLine = dbsReview && dbsReview.verdict && dbsReview.verdict !== 'keep' && dbsReview.first_action
          ? `<div class="brief-line warn"><strong>下一步:</strong> ${{escapeHtml(dbsReview.first_action)}}</div>`
          : '';
        const dbsWeakLine = dbsReview && (dbsReview.weakest_dimensions || []).length
          ? `<div class="brief-line">${{escapeHtml((dbsReview.weakest_dimensions || []).map(w => `${{w.dimension}} ${{w.score}}/10`).join(' · '))}}</div>`
          : '';
        const workflowMeta = platformId === 'xiaohongshu'
          ? `<div class="workflow-meta">
              <span class="workflow-chip">${{escapeHtml(draft.template_kind || 'workflow')}}</span>
              <span class="workflow-chip ${{draft.quality_passed ? '' : 'warn'}}">${{escapeHtml(workflowStatusLabel)}}</span>
              ${{dbsChip}}
              ${{dbsStructuralChip}}
              ${{triageLabel ? `<span class="workflow-chip warn">${{escapeHtml(triageLabel)}}</span>` : ''}}
              <span class="workflow-chip ${{draft.image_count ? '' : 'warn'}}">${{draft.image_count || 0}} 张图</span>
            </div>
            <div class="brief-line">${{escapeHtml((draft.search_keywords || []).slice(0, 4).join(' / '))}}</div>
            ${{dbsWeakLine}}
            ${{dbsActionLine}}
            ${{triageLine}}`
          : '';
        return `<article class="draft-preview">
          <header>
            <h3>${{escapeHtml(draft.title || state.primary_title || state.label)}}</h3>
            <span class="status ${{escapeHtml(state.status)}}">${{escapeHtml(label)}}</span>
          </header>
          ${{imageStrip}}
          ${{workflowMeta}}
          ${{platformId === 'xiaohongshu' ? '' : `<p>${{escapeHtml(draft.preview || actionHint(platformId))}}</p>`}}
          <div class="node-actions">
            ${{draftHref ? navLink('打开草稿', draftHref) : ''}}
          </div>
        </article>`;
      }}
      const visibleWechatIds = selectedPlatform && selectedPlatform !== 'wechat_mp' ? [] : ['wechat_mp'];
      const wechatItems = visibleWechatIds.map(platformId => {{
        const state = source.platforms[platformId] || {{}};
        const label = platformLabels.get(platformId) || platformId;
        const drafts = state.drafts || [];
        const hasPreview = drafts.some(draft => draft.html_href || Object.values(draft.style_variants || {{}}).some(variant => variant && variant.html_preview_href));
        const laneStatusClass = hasPreview || state.status === 'sent' ? 'sent' : drafts.length ? 'review_needed' : 'missing';
        const laneStatusLabel = hasPreview || state.status === 'sent' ? '可预览' : drafts.length ? '旧占位草稿' : '待生成';
        let cards = '';
        if (state.status === 'sent') {{
          cards = (state.sent || []).map(item => `<article class="draft-preview">
            <header><h3>${{escapeHtml(item.title || source.title)}}</h3><span class="status sent">已发布</span></header>
            <p>${{link('打开 sent 记录', item.href)}}</p>
          </article>`).join('');
        }} else if (drafts.length) {{
          cards = drafts.map((draft, index) => draftPreviewCard(platformId, state, draft, index)).join('');
        }} else {{
          cards = `<article class="empty-node">
            <header><b>${{escapeHtml(state.label || '待生成公众号文章')}}</b></header>
            <p>还没有公众号长文草稿。</p>
          </article>`;
        }}
        return `<section class="flow-lane review-lane">
          <div class="review-lane-header">
            <span class="review-lane-title"><span class="platform-icon">${{escapeHtml(platformIcons[platformId] || '•')}}</span>${{escapeHtml(label)}}</span>
            <span class="status ${{escapeHtml(laneStatusClass)}}">${{escapeHtml(laneStatusLabel)}}</span>
          </div>
          <div class="preview-grid">${{cards}}</div>
        </section>`;
      }}).join('');
      const visibleReviewIds = selectedPlatform ? ['xiaohongshu'].filter(platformId => platformId === selectedPlatform) : ['xiaohongshu'];
      const reviewItems = visibleReviewIds.map(platformId => {{
        const state = source.platforms[platformId];
        const label = platformLabels.get(platformId) || platformId;
        const drafts = state.drafts || [];
        let cards = '';
        if (state.status === 'sent') {{
          cards = (state.sent || []).map(item => `<article class="draft-preview">
            <header><h3>${{escapeHtml(item.title || source.title)}}</h3><span class="status sent">已发布</span></header>
            <p>${{link('打开 sent 记录', item.href)}}</p>
          </article>`).join('');
        }} else if (drafts.length) {{
          cards = drafts.map((draft, index) => draftPreviewCard(platformId, state, draft, index)).join('');
        }} else {{
          cards = `<article class="empty-node">
            <header><b>${{escapeHtml(state.label)}}</b></header>
            <p>还没有这个平台的改写草稿。</p>
          </article>`;
        }}
        return `<section class="flow-lane review-lane">
          <div class="review-lane-header">
            <span class="review-lane-title"><span class="platform-icon">${{escapeHtml(platformIcons[platformId] || '•')}}</span>${{escapeHtml(label)}}</span>
            <span class="status ${{escapeHtml(state.status)}}">${{escapeHtml(state.label)}}</span>
          </div>
          <div class="preview-grid">${{cards}}</div>
        </section>`;
      }}).join('');
      const xhsTextDrafts = source.platforms.xiaohongshu?.drafts || [];
      const topicsByIndex = new Map(topics.map((topic, index) => [Number(topic.topic_index || index + 1), topic]));
      const xhsTextItems = xhsTextDrafts.length ? xhsTextDrafts.map((draft, index) => {{
        const topicIndex = Number(draft.topic_index || index + 1);
        const topic = topicsByIndex.get(topicIndex) || {{}};
        const pack = draft.xhs_argument_pack || {{}};
        const noteBrief = draft.note_brief || {{}};
        const qualityStatus = !draft.is_current_xhs_workflow ? '旧格式' : (draft.quality_passed ? '质检通过' : '需要修改');
        const draftHref = draft.md_href || draft.json_href || draft.package_href || '';
        const body = draft.body || draft.preview || '';
        const checkSections = [
          ['用户视角', pack.reader_entry || noteBrief.reader_mirror || topic.reader_mirror || topic.contrast || ''],
          ['反对结论', pack.one_sentence_claim || noteBrief.core_claim || topic.reason || ''],
          ['论证支撑', pack.why_it_holds || noteBrief.why_it_matters || topic.why_it_matters || ''],
          ['边界', pack.boundary || topic.boundary || ''],
          ['读者行动', pack.reader_action || noteBrief.takeaway || topic.takeaway || '']
        ].filter(([, value]) => String(value || '').trim());
        const checkHtml = checkSections.length ? `
          <details class="xhs-structure-check">
            <summary>查看结构检查</summary>
            <div class="xhs-check-grid">
              ${{checkSections.map(([label, value]) => `<section><span>${{escapeHtml(label)}}</span><p>${{escapeHtml(value)}}</p></section>`).join('')}}
            </div>
          </details>` : '';
        return `<article class="xhs-text-draft">
          <header>
            <div>
              <h3>${{topicIndex}}. ${{escapeHtml(draft.title || topic.draft_title || topic.title || `小红书文字稿 ${{topicIndex}}`)}}</h3>
              <p class="topic-subtitle">${{escapeHtml(!draft.is_current_xhs_workflow ? '旧流程占位稿：仅保留作历史参考，不算当前可审核文字稿。' : (draft.source_unit_title || topic.title || ''))}}</p>
            </div>
            <span class="status ${{draft.is_current_xhs_workflow && draft.quality_passed ? 'packaged' : 'review_needed'}}">${{escapeHtml(qualityStatus)}}</span>
          </header>
          <div class="xhs-text-body">${{formatDraftText(body)}}</div>
          ${{checkHtml}}
          <div class="node-actions">
            ${{draftHref ? navLink('打开草稿', draftHref) : ''}}
          </div>
        </article>`;
      }}).join('') : '<p>还没有小红书文字稿。</p>';
      const xhsDraftCount = (source.platforms.xiaohongshu?.drafts || []).length;
      const currentXhsCount = currentXhsDrafts.length;
      const legacyXhsCount = legacyXhsDrafts.length;
      const reviewDraftLabel = currentXhsCount
        ? `${{currentXhsCount}} 篇当前图文`
        : legacyXhsCount
        ? `旧图文 ${{legacyXhsCount}} 篇`
        : '待生成';
      detail.innerHTML = `<div class="flow-detail">
        <article class="source-node">
          ${{sourceCover}}
          <div>
            <h2>${{escapeHtml(source.title)}}</h2>
            <p>${{escapeHtml(source.published_at)}} · <code>${{escapeHtml(source.source_content_id)}}</code></p>
            <div class="meta-grid">
              <div class="meta"><b>视频</b>${{source.media_count}}</div>
              <div class="meta"><b>封面</b>${{source.cover_count}}</div>
              <div class="meta"><b>生产主题</b>${{productionTopicCount}}</div>
              <div class="meta"><b>主选题</b>${{mainTopicCount}}</div>
            </div>
            <details class="secondary-actions">
              <summary>源内容 / 本地工具</summary>
              <div class="source-links">
                ${{link('打开抖音', source.source_url)}}
                ${{link('源内容目录', source.content_dir_href)}}
                ${{link('organized transcript', source.organized_href)}}
                ${{source.media_href ? link('源视频', source.media_href) : ''}}
              </div>
              <div class="node-actions">
                <button class="command" type="button" data-action="preflight-source" data-source-id="${{escapeHtml(source.source_content_id)}}">预检</button>
                <button class="command" type="button" data-action="repair-local-gaps" data-source-id="${{escapeHtml(source.source_content_id)}}">补齐缺口</button>
              </div>
            </details>
          </div>
        </article>
        <section class="workflow-step ${{migrationStepClass}}">
          <header>
            <div>
              <h2>第一步：视频搬运</h2>
              <p>只处理视频号、Bilibili、YouTube。默认公开发布；未登录的平台会先显示为需要登录，不会静默上传。</p>
            </div>
            <div class="step-status">
              <span class="status ${{migrationDone ? 'sent' : migrationFailed ? 'missing_asset' : 'review_needed'}}">${{migrationDone ? '已完成' : migrationPublishing ? '发布中' : migrationWaiting ? '等待登录' : migrationFailed ? '部分失败' : '下一步'}}</span>
              ${{migrationReady ? `<button class="action primary" type="button" data-action="batch-migrate-video" data-source-id="${{escapeHtml(source.source_content_id)}}" ${{migrationPublishing || migrationDone ? 'disabled' : ''}}>${{migrationButtonLabel}}</button>` : ''}}
            </div>
          </header>
          <div class="migration-status-grid">${{migrationStatusItems}}</div>
          <div class="node-actions">
            ${{source.media_href ? link('源视频', source.media_href) : '<span class="status missing_asset">缺源视频</span>'}}
          </div>
        </section>
        <section class="workflow-step ${{packageStepClass}}">
          <header>
            <div>
              <h2>第二步：内容包</h2>
              <p>先把口播转录变成真正可读的内容包，再决定小红书、公众号、X、clips 怎么生产。</p>
            </div>
            <span class="status ${{packageApproved ? 'sent' : escapeHtml(transcriptState.className)}}">${{packageApproved ? '内容包已通过' : escapeHtml(transcriptState.label)}}</span>
          </header>
          <div class="content-package-grid">
            <article class="content-package-card ${{transcriptState.className === 'review_needed' ? 'warn' : ''}}"><span>内容包手稿字数</span><b>${{readableChars}}</b></article>
            <article class="content-package-card"><span>生产主题</span><b>${{productionTopicCount}}</b></article>
            <article class="content-package-card"><span>主选题</span><b>${{mainTopicCount}}</b></article>
            <article class="content-package-card"><span>Clip 候选</span><b>${{source.content_package_clip_count || 0}}</b></article>
          </div>
          <div class="package-status-line">
            <span class="status ${{packageApproved ? 'sent' : escapeHtml(transcriptState.className)}}">${{packageApproved ? '已通过' : escapeHtml(transcriptState.label)}}</span>
            <span>${{escapeHtml(packageApproved ? `你已审核通过内容包。${{source.content_package_approved_at ? '通过时间：' + source.content_package_approved_at : ''}}` : transcriptState.note)}}</span>
            ${{source.content_package_text && !packageApproved ? `<button class="action approve" type="button" data-action="approve-content-package" data-source-id="${{escapeHtml(source.source_content_id)}}" title="通过内容包">✓ 通过</button>` : ''}}
            ${{source.content_package_href ? navLink('打开内容包', source.content_package_href) : ''}}
          </div>
          <div class="transcript-reader">${{formatTranscriptText(contentPackageText)}}</div>
        </section>
        <section class="workflow-step ${{wechatStepClass}}">
          <header>
            <div>
              <h2>第三步：公众号文章</h2>
              <p>公众号先承接完整内容包，整理成一篇可审核的长文；它不需要先拆主题。</p>
            </div>
            <span class="status ${{wechatReady ? 'sent' : wechatHasDrafts ? 'review_needed' : 'missing'}}">${{wechatReady ? '已有可预览长文' : wechatHasDrafts ? '旧占位草稿' : '待生成'}}</span>
          </header>
          <div class="flow-lanes">${{wechatItems}}</div>
        </section>
        <section class="workflow-step ${{topicStepClass}}">
          <header>
            <div>
              <h2>第四步：小红书文字稿</h2>
              <p>这里审核每篇小红书的标题和正文；用户视角、反对结论、边界等结构检查默认折叠在后台。</p>
            </div>
            <button class="action" type="button" data-action="prepare-local-asset" data-platform="xiaohongshu" data-source-id="${{escapeHtml(source.source_content_id)}}">生成小红书笔记</button>
          </header>
          <div class="xhs-text-stack">${{xhsTextItems}}</div>
        </section>
        <section class="workflow-step ${{reviewStepClass}}">
          <header>
            <div>
              <h2>第五步：小红书图文预览</h2>
              <p>文字已在第四步审核；这里仅看最终图片、素材包和草稿入口。</p>
            </div>
            <span class="status ${{reviewHasDrafts ? 'review_needed' : 'missing'}}">${{reviewDraftLabel}}</span>
          </header>
          <div class="flow-lanes">${{reviewItems}}</div>
        </section>
      </div>`;
      return;
      const visiblePlatformIds = selectedPlatform ? [selectedPlatform] : platformIds;
      const platformItems = visiblePlatformIds.map(platformId => {{
        const state = source.platforms[platformId];
        const label = platformLabels.get(platformId) || platformId;
        const platformUrl = platformHome[platformId] || '';
        const platformActions = `
          <div class="node-actions">
            ${{platformUrl ? navLink('打开后台', platformUrl, 'action primary') : ''}}
          </div>
          <details class="secondary-actions">
            <summary>通道工具</summary>
            <div class="node-actions">
              <button class="command" type="button" data-action="check-channel" data-platform="${{escapeHtml(platformId)}}">检查通道</button>
              <button class="command" type="button" data-action="prepare-channel" data-platform="${{escapeHtml(platformId)}}">准备通道</button>
            </div>
          </details>`;
        const drafts = state.drafts || [];
        let branch = '';
        if (state.status === 'sent') {{
          const sent = (state.sent || []).map(item => `<article class="draft-node primary">
            <header><b>${{escapeHtml(item.title || source.title)}}</b><span class="status sent">已发布</span></header>
            <p>${{link('打开 sent 记录', item.href)}}</p>
          </article>`).join('');
          branch = sent || `<article class="draft-node primary"><header><b>已发布</b><span class="status sent">已发布</span></header><p>这条内容已经进入 sent。</p></article>`;
        }} else if (drafts.length) {{
          branch = drafts.map((draft, index) => {{
            const draftHref = draft.package_href || draft.md_href || draft.json_href || state.primary_href;
            const quality = platformId === 'xiaohongshu'
              ? `${{draft.workflow_status === 'blocked_source' ? '源不足' : (draft.quality_passed ? '质检通过' : '待修')}} · ${{draft.image_count || 0}} 张图`
              : actionHint(platformId);
            const pushEnabled = canPushDraft(platformId, state) && !['missing_asset', 'source_gallery'].includes(state.status);
            const pushButton = pushEnabled
              ? `<button class="action primary" type="button" data-action="push-draft" data-platform="${{escapeHtml(platformId)}}" data-source-id="${{escapeHtml(source.source_content_id)}}" data-local-id="${{escapeHtml(draft.local_id || state.primary_local_id || '')}}">${{escapeHtml(actionButtonText(platformId))}}</button>`
              : `<button class="action" type="button" data-action="push-draft" data-platform="${{escapeHtml(platformId)}}" data-source-id="${{escapeHtml(source.source_content_id)}}" data-local-id="${{escapeHtml(draft.local_id || state.primary_local_id || '')}}">检查并推送</button>`;
            const handoffButton = ['bilibili', 'youtube'].includes(platformId) && !['source_gallery', 'missing_asset'].includes(state.status)
              ? `<button class="command" type="button" data-action="handoff-platform" data-platform="${{escapeHtml(platformId)}}" data-source-id="${{escapeHtml(source.source_content_id)}}" data-local-id="${{escapeHtml(draft.local_id || '')}}">交接后台</button>`
              : '';
            return `<article class="draft-node ${{index === 0 ? 'primary' : ''}}">
              <header><b>${{escapeHtml(draft.title || state.primary_title || state.label)}}</b><span class="status ${{escapeHtml(state.status)}}">${{escapeHtml(platformId === 'xiaohongshu' ? '笔记 ' + (index + 1) : state.label)}}</span></header>
              <p>${{escapeHtml(quality)}}</p>
              <div class="node-actions">
                ${{pushButton}}
              </div>
              <details class="secondary-actions">
                <summary>查看素材 / 完成后标记</summary>
                <div class="node-actions">
                  ${{draftHref ? navLink('打开素材', draftHref) : ''}}
                  ${{handoffButton}}
                  <button class="command" type="button" data-action="mark-sent" data-platform="${{escapeHtml(platformId)}}" data-source-id="${{escapeHtml(source.source_content_id)}}" data-local-id="${{escapeHtml(draft.local_id || '')}}" data-title="${{escapeHtml(draft.title || state.primary_title || source.title || '')}}">标记已发送</button>
                </div>
              </details>
            </article>`;
          }}).join('');
        }} else {{
          const missingAction = state.status === 'missing_asset'
            ? `<button class="command" type="button" data-action="repair-source-video" data-source-id="${{escapeHtml(source.source_content_id)}}">补视频素材</button>`
            : `<button class="command" type="button" data-action="generate-local-draft" data-platform="${{escapeHtml(platformId)}}" data-source-id="${{escapeHtml(source.source_content_id)}}">生成本地草稿</button>`;
          branch = `<article class="empty-node">
            <header><b>${{escapeHtml(state.label)}}</b></header>
            <p>${{escapeHtml(state.next_action || '暂无可操作草稿。')}}</p>
            <div class="node-actions">${{missingAction}}</div>
          </article>`;
        }}
        return `<section class="flow-lane">
          <article class="platform-node">
            <header><b>${{escapeHtml(label)}}</b><span class="status ${{escapeHtml(state.status)}}">${{escapeHtml(state.label)}}</span></header>
            <p>${{escapeHtml(actionHint(platformId))}}</p>
            ${{platformActions}}
          </article>
          <span class="flow-arrow" aria-hidden="true"></span>
          <div class="draft-branch">${{branch}}</div>
        </section>`;
      }}).join('');
      detail.innerHTML = `<div class="flow-detail">
        <article class="source-node">
          ${{sourceCover}}
          <div>
            <h2>${{escapeHtml(source.title)}}</h2>
            <p>${{escapeHtml(source.published_at)}} · <code>${{escapeHtml(source.source_content_id)}}</code></p>
            <div class="meta-grid">
              <div class="meta"><b>视频</b>${{source.media_count}}</div>
              <div class="meta"><b>封面</b>${{source.cover_count}}</div>
              <div class="meta"><b>Raw transcript</b>${{source.transcript_chars || 0}}</div>
              <div class="meta"><b>Organized</b>${{source.organized_chars || 0}}</div>
            </div>
            <details class="secondary-actions">
              <summary>源内容 / 本地工具</summary>
              <div class="source-links">
                ${{link('打开抖音', source.source_url)}}
                ${{link('源内容目录', source.content_dir_href)}}
                ${{link('raw transcript', source.transcript_href)}}
                ${{link('organized transcript', source.organized_href)}}
                ${{source.media_href ? link('源视频', source.media_href) : ''}}
              </div>
              <div class="node-actions">
                <button class="command" type="button" data-action="preflight-source" data-source-id="${{escapeHtml(source.source_content_id)}}">预检这条内容</button>
                <button class="command" type="button" data-action="repair-local-gaps" data-source-id="${{escapeHtml(source.source_content_id)}}">补齐本地缺口</button>
              </div>
            </details>
          </div>
        </article>
        <div class="preflight-panel" id="preflight-result"></div>
        <div class="flow-lanes">
          ${{platformItems}}
        </div>
      </div>`;
    }}
    function selectSource(sourceId) {{
      const source = sourceById.get(sourceId);
      if (!source) return;
      document.querySelectorAll('.flow-source-card').forEach(row => row.classList.toggle('active', row.dataset.sourceId === sourceId));
      renderDetail(source);
      refreshVideoMigrationStatus(sourceId, true);
    }}
    function renderQueue(containerId, rows) {{
      const container = document.getElementById(containerId);
      if (!container) return;
      container.innerHTML = rows.map(row => `<article class="queue-item">
        <div class="row"><code>${{escapeHtml(row.platform_label)}}</code><span class="status ${{escapeHtml(row.status || '')}}">${{escapeHtml(row.status_label || '')}}</span></div>
        <strong>${{link(row.title, row.package_href || row.md_href)}}</strong>
        <p>${{escapeHtml(row.source_title)}}</p>
        <small>${{escapeHtml(row.source_content_id)}}${{row.image_count ? ' · ' + row.image_count + ' images' : ''}}${{row.video_count ? ' · ' + row.video_count + ' videos' : ''}}</small>
        <div class="action-row">
          ${{row.status === 'missing_asset'
            ? '<button class="action" type="button" disabled>缺本地视频</button>'
            : row.status === 'source_gallery'
            ? '<button class="action" type="button" disabled>图文源</button>'
            : `<button class="action" type="button" data-action="push-draft" data-platform="${{escapeHtml(row.platform_id)}}" data-source-id="${{escapeHtml(row.source_content_id)}}" data-local-id="${{escapeHtml(row.local_id || '')}}">${{actionButtonText(row.platform_id)}}</button>`}}
          <button class="command" type="button" data-action="mark-sent" data-platform="${{escapeHtml(row.platform_id)}}" data-source-id="${{escapeHtml(row.source_content_id)}}" data-local-id="${{escapeHtml(row.local_id || '')}}" data-title="${{escapeHtml(row.title || '')}}">标记已发送</button>
          ${{['bilibili', 'youtube'].includes(row.platform_id) && !['source_gallery', 'missing_asset'].includes(row.status) ? `<button class="command" type="button" data-action="handoff-platform" data-platform="${{escapeHtml(row.platform_id)}}" data-source-id="${{escapeHtml(row.source_content_id)}}" data-local-id="${{escapeHtml(row.local_id || '')}}">手动交接到后台</button>` : ''}}
          ${{platformHome[row.platform_id] ? `<a href="${{escapeHtml(platformHome[row.platform_id])}}" target="_blank" rel="noreferrer">打开后台</a>` : ''}}
        </div>
      </article>`).join('') || '<p>当前没有待处理项目。</p>';
    }}
    document.querySelectorAll('[data-focus-platform]').forEach(button => {{
      button.addEventListener('click', () => {{
        const platformId = button.dataset.focusPlatform || '';
        const filter = document.getElementById('platform-filter');
        if (filter) {{
          filter.value = platformId;
          filter.dispatchEvent(new Event('change'));
        }}
        document.querySelector('.flow-workbench')?.scrollIntoView({{behavior:'smooth', block:'start'}});
      }});
    }});
    document.addEventListener('click', event => {{
      const button = event.target.closest('button[data-command]');
      if (button) showCommand(button.dataset.command);
      const lightboxImageTarget = event.target.closest('img[data-lightbox-images]');
      if (lightboxImageTarget) {{
        try {{
          const images = JSON.parse(decodeURIComponent(lightboxImageTarget.dataset.lightboxImages || '[]'));
          openLightbox(images, Number(lightboxImageTarget.dataset.lightboxIndex || 0), lightboxImageTarget.dataset.lightboxLabel || '');
        }} catch (error) {{
          openLightbox([lightboxImageTarget.src], 0, lightboxImageTarget.dataset.lightboxLabel || '');
        }}
      }}
      const actionButton = event.target.closest('button[data-action="push-draft"]');
      if (actionButton) {{
        pushDraft(actionButton.dataset.platform, actionButton.dataset.sourceId, actionButton.dataset.localId, false, {{
          wechatStyle: actionButton.dataset.wechatStyle || ''
        }});
      }}
      const styleButton = event.target.closest('button[data-action="wechat-style-preview"]');
      if (styleButton) {{
        const localId = styleButton.dataset.localId || '';
        const styleId = styleButton.dataset.styleId || 'professional';
        document.querySelectorAll(`.style-choice[data-local-id="${{CSS.escape(localId)}}"]`).forEach(node => node.classList.toggle('active', node.dataset.styleId === styleId));
        document.querySelectorAll(`.wechat-style-frame[data-local-id="${{CSS.escape(localId)}}"]`).forEach(node => node.classList.toggle('active', node.dataset.styleId === styleId));
        document.querySelectorAll(`.wechat-style-card[data-local-id="${{CSS.escape(localId)}}"]`).forEach(node => node.classList.toggle('active', node.dataset.styleId === styleId));
        document.querySelectorAll(`button[data-action="push-draft"][data-local-id="${{CSS.escape(localId)}}"][data-platform="wechat_mp"]`).forEach(node => node.dataset.wechatStyle = styleId);
      }}
      const handoffButton = event.target.closest('button[data-action="handoff-platform"]');
      if (handoffButton) {{
        handoffPlatform(handoffButton.dataset.platform, handoffButton.dataset.sourceId, handoffButton.dataset.localId);
      }}
      const checkButton = event.target.closest('button[data-action="check-channel"]');
      if (checkButton) {{
        checkChannel(checkButton.dataset.platform);
      }}
      const checkAllButton = event.target.closest('button[data-action="check-all-channels"]');
      if (checkAllButton) {{
        checkAllChannels();
      }}
      const checkAuthArtifactsButton = event.target.closest('button[data-action="check-auth-artifacts"]');
      if (checkAuthArtifactsButton) {{
        checkAuthArtifacts();
      }}
      const waitAuthArtifactsButton = event.target.closest('button[data-action="wait-auth-artifacts"]');
      if (waitAuthArtifactsButton) {{
        waitAuthArtifacts();
      }}
      const importChromeAuthButton = event.target.closest('button[data-action="import-chrome-auth"]');
      if (importChromeAuthButton) {{
        importChromeAuth(importChromeAuthButton.dataset.platform);
      }}
      const installYoutubeOauthButton = event.target.closest('button[data-action="install-youtube-oauth-client"]');
      if (installYoutubeOauthButton) {{
        installYoutubeOauthClient();
      }}
      const chooseYoutubeOauthButton = event.target.closest('button[data-action="choose-youtube-oauth-client"]');
      if (chooseYoutubeOauthButton) {{
        document.getElementById('youtube-oauth-file')?.click();
      }}
      const validateRoutesButton = event.target.closest('button[data-action="validate-channel-routes"]');
      if (validateRoutesButton) {{
        validateChannelRoutes();
      }}
      const prepareNextAuthButton = event.target.closest('button[data-action="prepare-next-auth"]');
      if (prepareNextAuthButton) {{
        prepareNextAuth();
      }}
      const prepareNextActionableAuthButton = event.target.closest('button[data-action="prepare-next-actionable-auth"]');
      if (prepareNextActionableAuthButton) {{
        prepareNextAuth(true);
      }}
      const prepareMissingButton = event.target.closest('button[data-action="prepare-missing-channels"]');
      if (prepareMissingButton) {{
        prepareMissingChannels();
      }}
      const refreshAuthPromptsButton = event.target.closest('button[data-action="refresh-auth-prompts"]');
      if (refreshAuthPromptsButton) {{
        refreshAuthPrompts();
      }}
      const preflightButton = event.target.closest('button[data-action="preflight-source"]');
      if (preflightButton) {{
        const platforms = preflightButton.dataset.platforms ? preflightButton.dataset.platforms.split(',').filter(Boolean) : null;
        preflightSource(preflightButton.dataset.sourceId, platforms);
      }}
      const prepareLocalAssetButton = event.target.closest('button[data-action="prepare-local-asset"]');
      if (prepareLocalAssetButton) {{
        prepareLocalAsset(prepareLocalAssetButton.dataset.platform, prepareLocalAssetButton.dataset.sourceId);
      }}
      const generateLocalDraftButton = event.target.closest('button[data-action="generate-local-draft"]');
      if (generateLocalDraftButton) {{
        generateLocalDraft(generateLocalDraftButton.dataset.platform, generateLocalDraftButton.dataset.sourceId);
      }}
      const generateContentPackageButton = event.target.closest('button[data-action="generate-content-package"]');
      if (generateContentPackageButton) {{
        generateContentPackage(generateContentPackageButton.dataset.sourceId);
      }}
      const approveContentPackageButton = event.target.closest('button[data-action="approve-content-package"]');
      if (approveContentPackageButton) {{
        approveContentPackage(approveContentPackageButton.dataset.sourceId);
      }}
      const repairLocalGapsButton = event.target.closest('button[data-action="repair-local-gaps"]');
      if (repairLocalGapsButton) {{
        repairLocalGaps(repairLocalGapsButton.dataset.sourceId);
      }}
      const repairAllLocalGapsButton = event.target.closest('button[data-action="repair-all-local-gaps"]');
      if (repairAllLocalGapsButton) {{
        repairAllLocalGaps();
      }}
      const runActionQueueButton = event.target.closest('button[data-action="run-action-queue"]');
      if (runActionQueueButton) {{
        runActionQueue(runActionQueueButton.dataset.mode === 'apply');
      }}
      const recordDecisionButton = event.target.closest('button[data-action="record-action-decision"]');
      if (recordDecisionButton) {{
        recordActionDecision(recordDecisionButton.dataset.decision, recordDecisionButton.dataset.draftPath, recordDecisionButton.dataset.sourceId);
      }}
      const clearDecisionButton = event.target.closest('button[data-action="clear-action-decision"]');
      if (clearDecisionButton) {{
        clearActionDecision(clearDecisionButton.dataset.draftPath, clearDecisionButton.dataset.sourceId);
      }}
      const repairSourceVideoButton = event.target.closest('button[data-action="repair-source-video"]');
      if (repairSourceVideoButton) {{
        repairSourceVideo(repairSourceVideoButton.dataset.sourceId);
      }}
      const prepareButton = event.target.closest('button[data-action="prepare-channel"]');
      if (prepareButton) {{
        prepareChannel(prepareButton.dataset.platform);
      }}
      const markSentButton = event.target.closest('button[data-action="mark-sent"]');
      if (markSentButton) {{
        markSent(markSentButton.dataset.platform, markSentButton.dataset.sourceId, markSentButton.dataset.localId, markSentButton.dataset.title);
      }}
      const repairButton = event.target.closest('button[data-action="repair-missing-videos"]');
      if (repairButton) {{
        repairMissingVideos(repairButton.dataset.mode === 'apply');
      }}
      const batchMigrateButton = event.target.closest('button[data-action="batch-migrate-video"]');
      if (batchMigrateButton) {{
        batchMigrateVideo(batchMigrateButton.dataset.sourceId);
      }}
    }});
    document.getElementById('youtube-oauth-file')?.addEventListener('change', (event) => {{
      const file = event.target.files && event.target.files[0];
      if (!file) return;
      installYoutubeOauthClient(file);
      event.target.value = '';
    }});
    document.querySelector('[data-lightbox-close]')?.addEventListener('click', closeLightbox);
    document.querySelector('[data-lightbox-prev]')?.addEventListener('click', () => moveLightbox(-1));
    document.querySelector('[data-lightbox-next]')?.addEventListener('click', () => moveLightbox(1));
    lightbox?.addEventListener('click', event => {{
      if (event.target === lightbox) closeLightbox();
    }});
    document.addEventListener('keydown', event => {{
      if (!lightbox?.classList.contains('open')) return;
      if (event.key === 'Escape') closeLightbox();
      if (event.key === 'ArrowLeft') moveLightbox(-1);
      if (event.key === 'ArrowRight') moveLightbox(1);
    }});
    document.getElementById('platform-filter')?.addEventListener('change', event => {{
      const selected = event.target.value;
      document.querySelectorAll('.source-mini-statuses .mini-status').forEach(node => {{
        const visible = !selected || node.textContent === (platformIcons[selected] || selected);
        node.style.display = visible ? '' : 'none';
      }});
      const currentId = document.querySelector('.flow-source-card.active')?.dataset.sourceId || model.sources[0]?.source_content_id;
      if (currentId) selectSource(currentId);
    }});
    renderQueue('review-queue', model.review_queue);
    renderQueue('migration-queue', model.migration_queue);
    renderAuthQueue([], {{}});
    refreshCapabilities();
    refreshActionHistory();
    const params = new URLSearchParams(window.location.search);
    const requestedSource = params.get('source');
    const initialSource = requestedSource && model.sources.some(source => source.source_content_id === requestedSource)
      ? requestedSource
      : model.sources[0]?.source_content_id;
    if (initialSource) selectSource(initialSource);
  </script>
</body>
</html>
"""
    (OUT / output_name).write_text(page, encoding="utf-8")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    assets = load_assets()
    platforms = load_platforms()
    all_summary = build_summary(assets, platforms)
    all_model = build_workbench_model(assets, platforms, all_summary)
    focus_source_id = os.environ.get("PARK_OUTBOX_FOCUS_SOURCE_ID", DEFAULT_FOCUS_SOURCE_ID).strip()
    workbench_assets = assets
    if focus_source_id and focus_source_id.lower() not in {"all", "*"}:
        focused = [asset for asset in assets if str(asset.get("source_content_id") or "") == focus_source_id]
        if focused:
            workbench_assets = focused
    summary = build_summary(workbench_assets, platforms)
    write_json(DATA_DIR / "assets.json", assets)
    write_json(DATA_DIR / "platform-summary.json", all_summary)
    write_markdown(workbench_assets, summary)
    write_overview_html(all_model)
    write_html(assets, all_summary, output_name="workbench.html")
    print(f"indexed_assets={len(assets)}")
    print(f"dashboard_assets={len(assets)}")
    print(f"wrote={OUT / 'dashboard.html'}")
    print(f"wrote={OUT / 'workbench.html'}")


if __name__ == "__main__":
    main()
