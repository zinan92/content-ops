#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path


ROOT = Path("/Users/wendy")
DOWNLOAD_CAPABILITY = ROOT / "content-toolkit/capabilities/download"
DEFAULT_SEC_UID = "MS4wLjABAAAALENnZndjA2wTx4aRk6lDxxtshwA2W_OJIXtu0jDdCkY"
DEFAULT_COOKIE_FILE = ROOT / "park-io/secrets/content-ops/douyin-cookies.json"
DEFAULT_OUTPUT = (
    ROOT
    / "park-io/outbox/.system/data/douyin-profile-aweme-list.json"
)

sys.path.insert(0, str(DOWNLOAD_CAPABILITY))

from content_downloader.adapters.douyin.api_client import DouyinAPIClient  # noqa: E402


async def fetch_awemes(sec_uid: str, cookies: dict[str, str], limit: int) -> list[dict]:
    items: list[dict] = []
    seen: set[str] = set()
    max_cursor = 0

    async with DouyinAPIClient(cookies=cookies) as client:
        for _page in range(50):
            page = await asyncio.wait_for(client.get_user_post(sec_uid, max_cursor, 20), timeout=25)
            awemes = page.get("aweme_list") or []
            if not awemes:
                break

            for aweme in awemes:
                aweme_id = str(aweme.get("aweme_id") or "")
                if not aweme_id or aweme_id in seen:
                    continue
                seen.add(aweme_id)
                items.append(aweme)
                if limit > 0 and len(items) >= limit:
                    return items

            next_cursor = int(page.get("max_cursor") or 0)
            if not page.get("has_more") or next_cursor == max_cursor:
                break
            max_cursor = next_cursor

    return items


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest Park's Douyin profile metadata.")
    parser.add_argument("--sec-uid", default=DEFAULT_SEC_UID)
    parser.add_argument("--cookies", type=Path, default=DEFAULT_COOKIE_FILE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--limit", type=int, default=0, help="0 means no explicit limit.")
    args = parser.parse_args()

    cookies = json.loads(args.cookies.read_text(encoding="utf-8"))
    awemes = asyncio.run(fetch_awemes(args.sec_uid, cookies, args.limit))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(awemes, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"indexed_profile_awemes={len(awemes)}")
    print(f"wrote={args.output}")


if __name__ == "__main__":
    main()
