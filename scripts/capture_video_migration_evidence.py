#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright


ROOT = Path("/Users/wendy")
OUTBOX = ROOT / "park-io/outbox"
BILIBILI_ACCOUNT = ROOT / "content-toolkit/capabilities/publish/cookies/bilibili_creator.json"
WECHAT_CHANNELS_ACCOUNT = ROOT / "content-toolkit/capabilities/publish/cookies/tencent_uploader/account.json"
URLS = {
    "wechat_channels": "https://channels.weixin.qq.com/platform/post/list",
    "bilibili": "https://member.bilibili.com/platform/upload-manager/article",
}


def emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    raise SystemExit(0 if payload.get("ok") else 2)


def load_biliup_cookies(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    raw_cookies = (data.get("cookie_info") or {}).get("cookies") or []
    expires = int(time.time() + 3600 * 24 * 30)
    cookies = []
    for item in raw_cookies:
        name = str(item.get("name") or "")
        value = str(item.get("value") or "")
        if not name or not value:
            continue
        cookies.append(
            {
                "name": name,
                "value": value,
                "domain": ".bilibili.com",
                "path": "/",
                "expires": expires,
                "httpOnly": False,
                "secure": True,
                "sameSite": "Lax",
            }
        )
    return cookies


async def main_async(args: argparse.Namespace) -> dict[str, Any]:
    output = Path(args.output).expanduser()
    output.parent.mkdir(parents=True, exist_ok=True)
    url = args.url or URLS.get(args.platform) or ""
    if not url:
        return {"ok": False, "status": "missing_url", "message": "没有可截图 URL。"}

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        try:
            if args.platform == "wechat_channels" and WECHAT_CHANNELS_ACCOUNT.exists():
                context = await browser.new_context(storage_state=str(WECHAT_CHANNELS_ACCOUNT), viewport={"width": 1440, "height": 1000})
            else:
                context = await browser.new_context(viewport={"width": 1440, "height": 1000})
            if args.platform == "bilibili" and BILIBILI_ACCOUNT.exists():
                await context.add_cookies(load_biliup_cookies(BILIBILI_ACCOUNT))
            page = await context.new_page()
            page.set_default_timeout(args.timeout * 1000)
            await page.goto(url, wait_until="domcontentloaded", timeout=args.timeout * 1000)
            await page.wait_for_timeout(args.wait * 1000)
            if args.title:
                try:
                    await page.get_by_text(args.title[:30], exact=False).first.scroll_into_view_if_needed(timeout=5000)
                    await page.wait_for_timeout(1200)
                except Exception:
                    pass
            await page.screenshot(path=str(output), full_page=False)
            text = "\n".join(await page.locator("body").all_inner_texts())
            title_found = bool(args.title and args.title[:30] in text)
            return {
                "ok": True,
                "status": "screenshot_saved",
                "platform": args.platform,
                "url": page.url,
                "output": str(output),
                "title_found": title_found,
                "message": "已保存发布结果截图。",
            }
        finally:
            await browser.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture platform evidence screenshot for Park-IO video migration.")
    parser.add_argument("--platform", required=True, choices=["wechat_channels", "bilibili", "youtube"])
    parser.add_argument("--source-content-id", required=True)
    parser.add_argument("--title", default="")
    parser.add_argument("--url", default="")
    parser.add_argument("--output", required=True)
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--wait", type=int, default=8)
    emit(asyncio.run(main_async(parser.parse_args())))


if __name__ == "__main__":
    main()
