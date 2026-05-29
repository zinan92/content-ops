#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path("/Users/wendy")
OUTBOX = ROOT / "park-io/outbox"
DATA = OUTBOX / ".system/data/assets.json"
DOWNLOAD_OUTPUT = ROOT / "content-toolkit/capabilities/download/output"
DEFAULT_COOKIES = ROOT / "park-io/secrets/content-ops/douyin-cookies.json"
REPORT_DIR = OUTBOX / ".system/reports"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run(command: list[str], timeout: int = 600) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
        return {
            "command": command,
            "returncode": completed.returncode,
            "stdout": completed.stdout[-8000:],
            "stderr": completed.stderr[-8000:],
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "command": command,
            "returncode": 124,
            "stdout": (exc.stdout or "")[-8000:] if isinstance(exc.stdout, str) else "",
            "stderr": ((exc.stderr or "")[-8000:] if isinstance(exc.stderr, str) else "") + f"\nTimed out after {timeout}s",
        }


def existing_download_dir(source_id: str) -> Path | None:
    candidates = sorted(DOWNLOAD_OUTPUT.glob(f"douyin/*/{source_id}"))
    for candidate in candidates:
        if (candidate / "media/video.mp4").exists():
            return candidate
    return None


def find_download_dir(root: Path, source_id: str) -> Path | None:
    candidates = sorted(root.glob(f"douyin/*/{source_id}"))
    for candidate in candidates:
        if (candidate / "media/video.mp4").exists():
            return candidate
    return None


def missing_assets() -> list[dict[str, Any]]:
    assets = read_json(DATA)
    rows = []
    for asset in assets:
        media_files = [Path(path) for path in asset.get("media_files") or []]
        if any(path.exists() for path in media_files):
            continue
        rows.append(asset)
    return rows


def copy_media(download_dir: Path, content_dir: Path, dry_run: bool) -> list[dict[str, str]]:
    moves = []
    media_dir = content_dir / "media"
    sources = [
        (download_dir / "media/video.mp4", media_dir / "video.mp4"),
        (download_dir / "media/cover.jpg", media_dir / "cover.jpg"),
    ]
    for src, dst in sources:
        if not src.exists():
            continue
        moves.append({"from": str(src), "to": str(dst)})
        if not dry_run:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
    return moves


def repair_one(asset: dict[str, Any], cookies: Path, dry_run: bool, force_download: bool) -> dict[str, Any]:
    source_id = str(asset.get("source_content_id") or "")
    source_url = str(asset.get("source_url") or f"https://www.douyin.com/video/{source_id}")
    content_dir = Path(asset.get("content_dir") or "")
    result: dict[str, Any] = {
        "source_content_id": source_id,
        "title": asset.get("title") or "",
        "source_url": source_url,
        "content_dir": str(content_dir),
        "status": "pending",
    }
    if not source_id or not content_dir:
        result.update({"status": "invalid_asset"})
        return result

    download_dir = None if force_download else existing_download_dir(source_id)
    if download_dir:
        result["download_source"] = "existing_cache"
    else:
        if not cookies.exists():
            result.update({"status": "missing_cookies", "cookies": str(cookies)})
            return result
        with tempfile.TemporaryDirectory(prefix=f"park-douyin-{source_id}-") as tmp:
            tmp_path = Path(tmp)
            command = ["content", "download", source_url, "--cookies", str(cookies), "-o", str(tmp_path)]
            result["download_command"] = command
            if dry_run:
                result.update({"status": "dry_run_needs_download"})
                return result
            completed = run(command, timeout=900)
            result["download_result"] = completed
            if completed["returncode"] != 0:
                result.update({"status": "download_failed"})
                return result
            download_dir = find_download_dir(tmp_path, source_id)
            if not download_dir:
                result.update({"status": "download_missing_video"})
                return result
            result["download_source"] = "fresh_download"
            moves = copy_media(download_dir, content_dir, dry_run=False)
            result.update({"status": "repaired", "moves": moves})
            return result

    moves = copy_media(download_dir, content_dir, dry_run=dry_run)
    result.update({"status": "dry_run" if dry_run else "repaired", "download_dir": str(download_dir), "moves": moves})
    if not moves:
        result["status"] = "no_media_to_copy"
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Repair missing local Douyin videos in Park-IO outbox.")
    parser.add_argument("--cookies", default=str(DEFAULT_COOKIES))
    parser.add_argument("--source-content-id", action="append", default=[])
    parser.add_argument("--force-download", action="store_true")
    parser.add_argument("--apply", action="store_true", help="Actually copy/download media. Default is dry-run.")
    args = parser.parse_args()

    rows = missing_assets()
    if args.source_content_id:
        wanted = set(args.source_content_id)
        rows = [row for row in rows if str(row.get("source_content_id") or "") in wanted]

    report = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "dry_run": not args.apply,
        "cookies": str(Path(args.cookies)),
        "missing_count": len(rows),
        "items": [repair_one(row, Path(args.cookies), dry_run=not args.apply, force_download=args.force_download) for row in rows],
    }
    report_path = REPORT_DIR / "missing-douyin-video-repair.json"
    write_json(report_path, report)
    print(json.dumps({"report": str(report_path), **report}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
