#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime
from pathlib import Path


ROOT = Path("/Users/wendy")
DOUYIN_SENT = ROOT / "park-io/outbox/sent/douyin"


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def move_if_exists(src: Path, dest: Path, dry_run: bool) -> bool:
    if not src.exists():
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        if src.is_file() and dest.is_file() and src.read_bytes() == dest.read_bytes():
            if not dry_run:
                src.unlink()
            return True
        stem = dest.stem
        suffix = dest.suffix
        dest = dest.with_name(f"{stem}-{datetime.now().strftime('%Y%m%d%H%M%S')}{suffix}")
    if not dry_run:
        shutil.move(str(src), str(dest))
    return True


def copy_if_exists(src: Path, dest: Path, dry_run: bool) -> bool:
    if not src.exists():
        return False
    if src.resolve() == dest.resolve():
        return True
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dry_run:
        shutil.copy2(src, dest)
    return True


def title_from_dir(path: Path) -> str:
    parts = path.name.split("--")
    if len(parts) >= 3:
        return "--".join(parts[1:-1]).strip()
    return path.name


def aweme_id_from_dir(path: Path) -> str:
    return path.name.rsplit("--", 1)[-1]


def build_source_json(item_dir: Path) -> dict:
    content_item = load_json(item_dir / "content_item.json") or load_json(item_dir / "_raw/content_item.json")
    metadata = load_json(item_dir / "metadata.json") or load_json(item_dir / "_raw/douyin-metadata.json")
    text_path = item_dir / "text.txt"
    raw_text_path = item_dir / "_raw/text.txt"
    text = ""
    if text_path.exists():
        text = text_path.read_text(encoding="utf-8").strip()
    elif raw_text_path.exists():
        text = raw_text_path.read_text(encoding="utf-8").strip()

    aweme_id = str(content_item.get("content_id") or metadata.get("aweme_id") or aweme_id_from_dir(item_dir))
    stats = metadata.get("statistics") or {}
    source = {
        "platform": "douyin",
        "content_id": aweme_id,
        "content_type": content_item.get("content_type") or ("video" if (item_dir / "media/video.mp4").exists() else "gallery"),
        "title": content_item.get("title") or metadata.get("desc") or title_from_dir(item_dir),
        "description": content_item.get("description") or text or metadata.get("desc") or "",
        "author_id": content_item.get("author_id") or "102174692353",
        "author_name": content_item.get("author_name") or "Park的AI世界",
        "publish_time": content_item.get("publish_time") or "",
        "source_url": content_item.get("source_url") or f"https://www.douyin.com/video/{aweme_id}",
        "media_files": sorted(str(path.relative_to(item_dir)) for path in (item_dir / "media").glob("*") if path.is_file()),
        "stats": {
            "likes": content_item.get("likes") or stats.get("digg_count") or 0,
            "comments": content_item.get("comments") or stats.get("comment_count") or 0,
            "shares": content_item.get("shares") or stats.get("share_count") or 0,
            "collects": content_item.get("collects") or stats.get("collect_count") or 0,
            "views": content_item.get("views") or stats.get("play_count") or 0,
        },
        "raw_files": {
            "metadata": "_raw/douyin-metadata.json" if (item_dir / "_raw/douyin-metadata.json").exists() or (item_dir / "metadata.json").exists() else "",
            "content_item": "_raw/content_item.json" if (item_dir / "_raw/content_item.json").exists() or (item_dir / "content_item.json").exists() else "",
            "text": "_raw/text.txt" if (item_dir / "_raw/text.txt").exists() or (item_dir / "text.txt").exists() else "",
        },
        "layout_version": "2026-05-20",
    }
    return source


def migrate_item(item_dir: Path, dry_run: bool) -> dict:
    changes: list[str] = []
    transcript_dir = item_dir / "transcript"
    raw_dir = item_dir / "_raw"

    source = build_source_json(item_dir)
    if not dry_run:
        write_json(item_dir / "source.json", source)
    changes.append("source.json")

    moves = [
        ("transcript.md", "transcript/raw.md"),
        ("transcript.json", "transcript/raw.json"),
        ("organized_transcript.md", "transcript/organized.md"),
        ("organized_transcript.json", "transcript/organized.json"),
        ("mlx_result.json", "_raw/mlx_result.json"),
        ("metadata.json", "_raw/douyin-metadata.json"),
        ("content_item.json", "_raw/content_item.json"),
        ("text.txt", "_raw/text.txt"),
        ("analysis.json", "_raw/extractor/analysis.json"),
        ("extraction_status.json", "_raw/extractor/extraction_status.json"),
        ("extractor_output.json", "_raw/extractor/extractor_output.json"),
        ("structured_text.md", "_raw/extractor/structured_text.md"),
        (".extraction_complete", "_raw/extractor/.extraction_complete"),
        ("mlx-transcribe", "_raw/mlx-transcribe"),
    ]
    for src_name, dest_name in moves:
        if move_if_exists(item_dir / src_name, item_dir / dest_name, dry_run):
            changes.append(f"{src_name}->{dest_name}")

    # Backfill old new-layout files if a previous run only copied them.
    copy_if_exists(item_dir / "transcript/raw.json", transcript_dir / "raw.json", dry_run)
    copy_if_exists(item_dir / "transcript/raw.md", transcript_dir / "raw.md", dry_run)
    copy_if_exists(item_dir / "transcript/organized.json", transcript_dir / "organized.json", dry_run)
    copy_if_exists(item_dir / "transcript/organized.md", transcript_dir / "organized.md", dry_run)

    return {
        "directory": str(item_dir),
        "changes": changes,
        "has_media": (item_dir / "media").exists(),
        "has_source": (item_dir / "source.json").exists() or not dry_run,
        "has_raw_transcript": (transcript_dir / "raw.json").exists() or (item_dir / "transcript.json").exists(),
        "has_organized_transcript": (transcript_dir / "organized.md").exists() or (item_dir / "organized_transcript.md").exists(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Collapse Douyin item folders into media/source/transcript layout.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    dirs = sorted(DOUYIN_SENT.glob("20*--*--*"))
    if args.limit:
        dirs = dirs[: args.limit]
    report = [migrate_item(item_dir, args.dry_run) for item_dir in dirs]
    report_path = Path("/Users/wendy/work/content-ops/.runs/reports/douyin-layout-cleanup-report.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    if not args.dry_run:
        write_json(report_path, {"generated_at": datetime.now().isoformat(timespec="seconds"), "items": report})
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not args.dry_run:
        print(f"wrote={report_path}")


if __name__ == "__main__":
    main()
