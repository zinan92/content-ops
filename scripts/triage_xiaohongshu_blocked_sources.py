#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path


ROOT = Path("/Users/wendy")
DRAFT_DIR = ROOT / "park-io/outbox/drafts/xiaohongshu"
ASSETS_PATH = ROOT / "park-io/outbox/.system/data/assets.json"
AUDIT_PATH = ROOT / "work/content-ops/.runs/reports/xiaohongshu-workflow-audit.json"
REPORT_JSON = ROOT / "work/content-ops/.runs/reports/xiaohongshu-blocked-source-triage.json"
REPORT_MD = ROOT / "work/content-ops/.runs/reports/xiaohongshu-blocked-source-triage.md"


def load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {} if path.suffix == ".json" else []


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def chinese_len(text: str) -> int:
    return len(re.sub(r"\s+", "", text or ""))


def load_assets_by_source_id() -> dict[str, dict]:
    rows = load_json(ASSETS_PATH)
    if not isinstance(rows, list):
        return {}
    return {str(row.get("source_content_id") or ""): row for row in rows}


def load_audit_items() -> list[dict]:
    audit = load_json(AUDIT_PATH)
    if isinstance(audit, dict) and isinstance(audit.get("items"), list):
        return audit["items"]
    return []


def draft_path_for_item(item: dict) -> Path:
    raw_path = str(item.get("path") or "")
    if raw_path:
        return Path(raw_path)
    return DRAFT_DIR / str(item.get("filename") or "")


def asset_counts(asset: dict) -> tuple[int, int, int, int]:
    media_count = len(asset.get("media_files") or [])
    cover_count = len(asset.get("cover_files") or [])
    transcript_chars = int(asset.get("transcript_chars") or 0)
    organized_chars = int(asset.get("organized_chars") or asset.get("organized_transcript_chars") or transcript_chars or 0)
    return media_count, cover_count, transcript_chars, organized_chars


def classify(item: dict, record: dict, asset: dict, min_chars: int) -> tuple[str, str, str]:
    source_chars = int(item.get("source_excerpt_chars") or chinese_len(str(record.get("source_excerpt") or "")))
    media_count, _cover_count, transcript_chars, organized_chars = asset_counts(asset)
    has_long_source = max(transcript_chars, organized_chars) >= min_chars

    if source_chars >= min_chars:
        return (
            "stale_quality_recheck",
            "source excerpt 已经足够长，但质量结果仍 blocked；重新跑 quality/polish/render。",
            f"python3 /Users/wendy/work/content-ops/scripts/quality_xiaohongshu_drafts.py '{draft_path_for_item(item)}' --force",
        )
    if media_count == 0 and not has_long_source:
        return (
            "skip_or_reingest",
            "本地没有视频/转录，当前只有标题或短描述；不要从标题硬编。",
            "如果这条确实要做小红书，先重新下载/转录该抖音；否则保留 blocked 或删除这条 draft。",
        )
    if has_long_source and source_chars >= min_chars * 0.75:
        return (
            "near_threshold_review",
            "源视频有长转录，但当前主题片段略短；可以人工判断是否合并相邻片段。",
            f"python3 /Users/wendy/work/content-ops/scripts/repair_xiaohongshu_source_excerpts.py '{draft_path_for_item(item)}' --min-chars {min_chars} --force",
        )
    if has_long_source:
        return (
            "merge_or_drop_unit",
            "源视频有长转录，但这个拆条单元太短；应该回到 topic plan 合并主题或丢弃该单元。",
            "回看 source_unit_title/source_excerpt，决定合并到主选题，或保持 blocked 不发布。",
        )
    return (
        "unknown_source_gap",
        "缺口类型不明确；需要检查 asset manifest 和 draft source fields。",
        f"python3 /Users/wendy/work/content-ops/scripts/audit_xiaohongshu_workflow.py '{draft_path_for_item(item)}'",
    )


def triage(min_chars: int) -> dict:
    assets = load_assets_by_source_id()
    rows: list[dict] = []
    for item in load_audit_items():
        if item.get("status") != "blocked_source":
            continue
        path = draft_path_for_item(item)
        record = load_json(path)
        source_id = str(item.get("source_content_id") or record.get("source_content_id") or "")
        asset = assets.get(source_id, {})
        media_count, cover_count, transcript_chars, organized_chars = asset_counts(asset)
        bucket, reason, next_action = classify(item, record, asset, min_chars)
        rows.append(
            {
                "bucket": bucket,
                "reason": reason,
                "next_action": next_action,
                "filename": path.name,
                "path": str(path),
                "source_content_id": source_id,
                "source_title": asset.get("title") or record.get("source_title") or "",
                "draft_title": record.get("title") or item.get("title") or "",
                "source_unit_title": record.get("source_unit_title") or "",
                "source_excerpt_chars": int(item.get("source_excerpt_chars") or chinese_len(str(record.get("source_excerpt") or ""))),
                "media_count": media_count,
                "cover_count": cover_count,
                "transcript_chars": transcript_chars,
                "organized_chars": organized_chars,
                "issues": item.get("issues") or [],
                "quality_warnings": item.get("quality_warnings") or [],
            }
        )
    counts = Counter(row["bucket"] for row in rows)
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "min_chars": min_chars,
        "blocked_count": len(rows),
        "bucket_counts": dict(counts),
        "items": rows,
    }


def write_markdown(path: Path, report: dict) -> None:
    lines = [
        "# Xiaohongshu Blocked Source Triage",
        "",
        f"Generated: {report.get('generated_at')}",
        f"Minimum source chars: {report.get('min_chars')}",
        f"Blocked drafts: {report.get('blocked_count')}",
        "",
        "## Bucket Counts",
        "",
    ]
    for bucket, count in sorted((report.get("bucket_counts") or {}).items()):
        lines.append(f"- `{bucket}`: {count}")
    lines.extend(["", "## Items", ""])
    for item in report.get("items") or []:
        lines.extend(
            [
                f"### {item['draft_title'] or item['filename']}",
                "",
                f"- Bucket: `{item['bucket']}`",
                f"- Reason: {item['reason']}",
                f"- Source: `{item['source_content_id']}` {item['source_title']}",
                f"- Unit: {item['source_unit_title'] or '(none)'}",
                f"- Source excerpt chars: {item['source_excerpt_chars']}",
                f"- Local media/transcript: {item['media_count']} media, {item['cover_count']} cover, {item['transcript_chars']} raw chars, {item['organized_chars']} organized chars",
                f"- Draft: `{item['path']}`",
                f"- Next action: {item['next_action']}",
                "",
            ]
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Triage Xiaohongshu blocked_source drafts into actionable buckets.")
    parser.add_argument("--min-chars", type=int, default=400)
    args = parser.parse_args()

    report = triage(args.min_chars)
    write_json(REPORT_JSON, report)
    write_markdown(REPORT_MD, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"json_report={REPORT_JSON}")
    print(f"markdown_report={REPORT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
