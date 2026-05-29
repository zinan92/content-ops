#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path


ROOT = Path("/Users/wendy")
OUT = ROOT / "park-io/outbox"
DOUYIN_SENT = OUT / "sent/douyin"
PROFILE_LIST = OUT / ".system/data/douyin-profile-aweme-list.json"
COOKIE_FILE = ROOT / "park-io/secrets/content-ops/douyin-cookies.json"
DOWNLOAD_CLI = ROOT / "content-toolkit/capabilities/download/.venv/bin/content-downloader"
EXTRACT_CLI = ROOT / "content-toolkit/capabilities/extract/.venv/bin/content-extractor"
RUNS = ROOT / "work/content-ops/.runs"
DOWNLOAD_CACHE = RUNS / "cache/douyin-downloads"


def published_date(raw: object) -> str:
    try:
        ts = int(raw or 0)
    except (TypeError, ValueError):
        return datetime.now().strftime("%Y-%m-%d")
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")


def title_text(aweme: dict) -> str:
    raw = aweme.get("desc") or aweme.get("item_title") or str(aweme.get("aweme_id"))
    raw = re.sub(r"\s+", " ", raw).strip()
    raw = re.sub(r"\s*#[^\s#]+", "", raw).strip()
    return raw or str(aweme.get("aweme_id"))


def safe_name(text: str, limit: int = 72) -> str:
    text = text.replace("/", "／").replace(":", "：")
    text = re.sub(r"[\0\r\n\t]+", " ", text)
    text = re.sub(r"[<>\"|?*]+", "", text)
    text = re.sub(r"\s+", " ", text).strip(" .")
    return text[:limit].strip(" .") or "untitled"


def dir_name(aweme: dict) -> str:
    date = published_date(aweme.get("create_time"))
    title = safe_name(title_text(aweme))
    aweme_id = str(aweme["aweme_id"])
    return f"{date}--{title}--{aweme_id}"


def existing_sources(aweme_id: str) -> list[Path]:
    candidates = [
        RUNS / "cache/douyin-profile-102174692353" / aweme_id,
        ROOT / "content-toolkit/capabilities/download/output/douyin/102174692353" / aweme_id,
        DOWNLOAD_CACHE / "douyin/102174692353" / aweme_id,
    ]
    return [path for path in candidates if path.exists()]


def copy_tree_contents(src: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for child in src.iterdir():
        target = dest / child.name
        if child.is_dir():
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(child, target)
        else:
            shutil.copy2(child, target)


def run(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=str(cwd) if cwd else None, text=True, capture_output=True)


def download_aweme(aweme: dict) -> Path | None:
    url = f"https://www.douyin.com/video/{aweme['aweme_id']}"
    cmd = [
        str(DOWNLOAD_CLI),
        "download",
        url,
        "--output-dir",
        str(DOWNLOAD_CACHE),
        "--cookies",
        str(COOKIE_FILE),
        "--limit",
        "1",
    ]
    result = run(cmd, cwd=DOWNLOAD_CLI.parent.parent)
    if result.returncode != 0:
        print(f"download_failed={aweme['aweme_id']}")
        print((result.stdout or "").strip())
        print((result.stderr or "").strip())
        return None
    return DOWNLOAD_CACHE / "douyin/102174692353" / str(aweme["aweme_id"])


def ensure_content_item(dest: Path, aweme: dict) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    content_item = dest / "content_item.json"
    media_files = []
    video = dest / "media/video.mp4"
    if video.exists():
        media_files.append("media/video.mp4")
    item = {}
    if content_item.exists():
        try:
            item = json.loads(content_item.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            item = {}
    defaults = {
        "platform": "douyin",
        "content_id": str(aweme["aweme_id"]),
        "content_type": "video" if video.exists() else item.get("content_type", "unknown"),
        "title": title_text(aweme),
        "description": aweme.get("desc") or title_text(aweme),
        "author_id": "102174692353",
        "author_name": "Park的AI世界",
        "publish_time": datetime.fromtimestamp(int(aweme.get("create_time") or 0)).isoformat(),
        "downloaded_at": datetime.now().isoformat(),
        "source_url": f"https://www.douyin.com/video/{aweme['aweme_id']}",
        "media_files": media_files or item.get("media_files", []),
        "cover_file": "media/cover.jpg" if (dest / "media/cover.jpg").exists() else item.get("cover_file"),
    }
    for key, value in defaults.items():
        if key not in item or item[key] in (None, "", []):
            item[key] = value
    content_item.write_text(json.dumps(item, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def mmss(seconds: float | int | None) -> str:
    if seconds is None:
        return "00:00"
    total = int(float(seconds))
    return f"{total // 60:02d}:{total % 60:02d}"


def write_transcript_md(dest: Path, aweme: dict) -> None:
    transcript_json = dest / "transcript.json"
    if not transcript_json.exists():
        return
    data = json.loads(transcript_json.read_text(encoding="utf-8"))
    segments = data.get("segments") or []
    lines = [
        f"# {title_text(aweme)}",
        "",
        f"- Douyin ID: `{aweme['aweme_id']}`",
        f"- Source: https://www.douyin.com/video/{aweme['aweme_id']}",
        "",
        "## Transcript",
        "",
    ]
    if segments:
        for segment in segments:
            text = re.sub(r"\s+", " ", segment.get("text") or "").strip()
            if text:
                lines.append(f"[{mmss(segment.get('start'))}] {text}")
    else:
        full = data.get("full_text") or ""
        for paragraph in re.split(r"(?<=[。！？!?])\s*", full):
            paragraph = paragraph.strip()
            if paragraph:
                lines.append(paragraph)
    (dest / "transcript.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def extract_transcript(dest: Path, aweme: dict, force: bool) -> bool:
    if (dest / "transcript.json").exists() and not force:
        write_transcript_md(dest, aweme)
        return True
    if not (dest / "media/video.mp4").exists():
        return False
    cmd = [str(EXTRACT_CLI), "extract", str(dest), "--force"]
    result = run(cmd, cwd=EXTRACT_CLI.parent.parent)
    if result.returncode != 0:
        print(f"extract_failed={aweme['aweme_id']}")
        print((result.stdout or "").strip())
        print((result.stderr or "").strip())
        return False
    write_transcript_md(dest, aweme)
    return True


def sync_one(aweme: dict, download: bool, transcribe: bool, force_transcribe: bool) -> dict:
    aweme_id = str(aweme["aweme_id"])
    dest = DOUYIN_SENT / dir_name(aweme)
    sources = existing_sources(aweme_id)
    if not sources and download:
        downloaded = download_aweme(aweme)
        if downloaded and downloaded.exists():
            sources = [downloaded]
    if sources:
        copy_tree_contents(sources[0], dest)
    ensure_content_item(dest, aweme)
    ok_video = (dest / "media/video.mp4").exists()
    ok_transcript = False
    if transcribe:
        ok_transcript = extract_transcript(dest, aweme, force=force_transcribe)
    else:
        ok_transcript = (dest / "transcript.json").exists()
        if ok_transcript:
            write_transcript_md(dest, aweme)
    return {
        "aweme_id": aweme_id,
        "title": title_text(aweme),
        "directory": str(dest),
        "video": ok_video,
        "transcript": ok_transcript,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a clean Douyin video + transcript library under Park-IO outbox.")
    parser.add_argument("--no-download", action="store_true")
    parser.add_argument("--transcribe", action="store_true")
    parser.add_argument("--force-transcribe", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    awemes = json.loads(PROFILE_LIST.read_text(encoding="utf-8"))
    if args.limit > 0:
        awemes = awemes[: args.limit]

    report = []
    for aweme in awemes:
        row = sync_one(
            aweme,
            download=not args.no_download,
            transcribe=args.transcribe,
            force_transcribe=args.force_transcribe,
        )
        report.append(row)
        print(
            f"{row['aweme_id']} video={row['video']} transcript={row['transcript']} dir={row['directory']}"
        )

    report_path = RUNS / "reports/douyin-library-report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote={report_path}")


if __name__ == "__main__":
    main()
