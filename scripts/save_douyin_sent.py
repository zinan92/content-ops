#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen


ROOT = Path("/Users/wendy")
OUT = ROOT / "park-io/outbox"
DOUYIN_SENT = OUT / "sent/douyin"
PROFILE_LIST = DOUYIN_SENT / "102174692353/profile-aweme-list.json"


def today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def slugify(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value[:48] or "douyin-video"


def resolve_url(url: str) -> str:
    if "v.douyin.com" not in url:
        return url
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=15) as response:
        return response.geturl()


def extract_aweme_id(url: str) -> str:
    match = re.search(r"(?:/video/|/share/video/)(\d+)", url)
    if match:
        return match.group(1)
    match = re.search(r"\b(\d{15,25})\b", url)
    if match:
        return match.group(1)
    raise SystemExit(f"Could not extract Douyin aweme id from URL: {url}")


def profile_record(aweme_id: str) -> dict:
    if not PROFILE_LIST.exists():
        return {}
    try:
        records = json.loads(PROFILE_LIST.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    for item in records:
        if str(item.get("aweme_id") or "") == aweme_id:
            return item
    return {}


def write_records(record: dict, slug: str) -> tuple[Path, Path]:
    date = record["published_at"]
    aweme_id = record["platform_id"]
    base = f"{date}--{slug}--{aweme_id}"
    json_path = DOUYIN_SENT / f"{base}.json"
    md_path = DOUYIN_SENT / f"{base}.md"
    DOUYIN_SENT.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(
        "\n".join(
            [
                "---",
                f"platform: {record['platform']}",
                f"status: {record['status']}",
                f"published_at: {record['published_at']}",
                f"platform_id: {record['platform_id']}",
                f"source_url: {record['source_url']}",
                f"repurpose_status: {record['repurpose_status']}",
                "---",
                "",
                f"# {record['title'] or slug}",
                "",
                record["description"],
                "",
            ]
        ),
        encoding="utf-8",
    )
    return json_path, md_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Save a mature published Douyin video into Park-IO outbox.")
    parser.add_argument("url", help="Douyin video URL or v.douyin.com share URL.")
    parser.add_argument("--date", default=today(), help="Actual publish date, YYYY-MM-DD.")
    parser.add_argument("--title", default="")
    parser.add_argument("--slug", default="")
    args = parser.parse_args()

    resolved = resolve_url(args.url)
    aweme_id = extract_aweme_id(resolved)
    known = profile_record(aweme_id)
    desc = known.get("desc") or args.title
    title = args.title or str(desc).splitlines()[0][:120]
    slug = args.slug or slugify(title or aweme_id)

    record = {
        "platform": "douyin",
        "status": "sent",
        "published_at": args.date,
        "source_url": f"https://www.douyin.com/video/{aweme_id}",
        "platform_id": aweme_id,
        "account": "Park的AI世界",
        "title": title,
        "description": desc,
        "tags": [],
        "repurpose_status": "not_started",
    }
    json_path, md_path = write_records(record, slug)
    print(f"wrote={json_path}")
    print(f"wrote={md_path}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
