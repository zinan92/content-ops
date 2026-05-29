#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import types
import time
from datetime import datetime
from pathlib import Path


ROOT = Path("/Users/wendy")
PUBLISH_ROOT = ROOT / "content-toolkit/capabilities/publish"
DEFAULT_ACCOUNT_FILE = PUBLISH_ROOT / "cookies/tencent_uploader/account.json"


def install_publish_conf(headless: bool) -> None:
    chrome_path = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    conf = types.ModuleType("conf")
    conf.BASE_DIR = PUBLISH_ROOT
    conf.XHS_SERVER = "http://127.0.0.1:11901"
    conf.LOCAL_CHROME_PATH = str(chrome_path) if chrome_path.exists() else ""
    conf.LOCAL_CHROME_HEADLESS = headless
    conf.DEBUG_MODE = True
    sys.modules["conf"] = conf
    if str(PUBLISH_ROOT) not in sys.path:
        sys.path.insert(0, str(PUBLISH_ROOT))


def extract_tags(text: str) -> list[str]:
    tags = []
    for match in re.findall(r"#([\w\u4e00-\u9fff]+)", text or ""):
        if match and match not in tags:
            tags.append(match[:20])
    return tags[:8]


async def push(args: argparse.Namespace) -> dict:
    install_publish_conf(headless=args.headless)
    from uploader.tencent_uploader.main import TencentVideo, cookie_auth, weixin_setup
    from utils.constant import TencentZoneTypes

    account_file = Path(args.account_file or DEFAULT_ACCOUNT_FILE)
    if args.check_only:
        if not account_file.exists():
            return {
                "ok": False,
                "status": "cookie_missing",
                "account_file": str(account_file),
                "checked_at": datetime.now().isoformat(timespec="seconds"),
            }
        ready = await weixin_setup(account_file, handle=False)
        return {
            "ok": bool(ready),
            "status": "cookie_valid" if ready else "cookie_invalid",
            "account_file": str(account_file),
            "checked_at": datetime.now().isoformat(timespec="seconds"),
        }
    if args.login_only:
        ready = await login_wechat_channels(account_file, headless=args.headless, timeout_seconds=args.login_timeout)
        if not ready and account_file.exists():
            account_file.unlink()
        return {
            "ok": bool(ready and account_file.exists()),
            "status": "cookie_saved" if ready and account_file.exists() else "cookie_login_failed",
            "account_file": str(account_file),
            "saved_at": datetime.now().isoformat(timespec="seconds"),
        }

    video = Path(args.video)
    if not video.exists():
        return {"ok": False, "status": "video_missing", "message": str(video)}
    if not account_file.exists() and not args.login:
        return {
            "ok": False,
            "status": "cookie_missing",
            "message": f"视频号 cookie 不存在：{account_file}。先运行带 --login 的手动登录流程。",
            "account_file": str(account_file),
        }
    ready = await weixin_setup(account_file, handle=args.login)
    if not ready:
        return {
            "ok": False,
            "status": "cookie_invalid",
            "message": "视频号 cookie 不存在或失效。请先完成登录。",
            "account_file": str(account_file),
        }
    app = TencentVideo(
        title=args.title[:64],
        file_path=video,
        tags=extract_tags(args.description),
        publish_date=0,
        account_file=account_file,
        category=TencentZoneTypes.TECHNOLOGY.value,
        is_draft=not args.publish,
    )
    await app.main()
    status = "published" if args.publish else "draft_saved_in_platform"
    return {
        "ok": True,
        "status": status,
        "title": args.title,
        "video": str(video),
        "account_file": str(account_file),
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "message": "已提交公开视频号发布。" if args.publish else "已保存到视频号草稿箱。",
    }


async def login_wechat_channels(account_file: Path, headless: bool, timeout_seconds: int) -> bool:
    from playwright.async_api import async_playwright
    from uploader.tencent_uploader.main import cookie_auth
    from utils.base_social_media import set_init_script

    account_file.parent.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=headless, args=["--lang=zh-CN"])
        context = await browser.new_context()
        context = await set_init_script(context)
        page = await context.new_page()
        await page.goto("https://channels.weixin.qq.com/platform/post/create", wait_until="domcontentloaded")
        started = time.time()
        last_status = ""
        while time.time() - started < timeout_seconds:
            await page.wait_for_timeout(3000)
            body_text = ""
            try:
                body_text = (await page.locator("body").inner_text(timeout=2000))[:3000]
            except Exception:
                body_text = ""
            current_url = page.url
            if body_text != last_status:
                print(json.dumps({
                    "status": "waiting_login",
                    "url": current_url,
                    "hint": "请在打开的微信视频号页面扫码/确认登录；登录后脚本会自动保存 cookie。",
                }, ensure_ascii=False), flush=True)
                last_status = body_text
            login_markers = ["扫码", "登录", "微信小店"]
            has_login_marker = any(marker in body_text for marker in login_markers)
            if "channels.weixin.qq.com/platform" in current_url and not has_login_marker:
                await context.storage_state(path=str(account_file))
                await browser.close()
                return await cookie_auth(account_file)
        await context.storage_state(path=str(account_file))
        await browser.close()
        return await cookie_auth(account_file)


def main() -> None:
    parser = argparse.ArgumentParser(description="Push a local video into WeChat Channels.")
    parser.add_argument("--title", required=True)
    parser.add_argument("--description", default="")
    parser.add_argument("--video", required=not any(flag in sys.argv for flag in ("--login-only", "--check-only")))
    parser.add_argument("--account-file", default=str(DEFAULT_ACCOUNT_FILE))
    parser.add_argument("--login", action="store_true", help="Allow interactive login if cookie is missing.")
    parser.add_argument("--login-only", action="store_true", help="Only complete interactive login and save cookie; do not upload.")
    parser.add_argument("--login-timeout", type=int, default=240, help="Seconds to wait for interactive QR login.")
    parser.add_argument("--check-only", action="store_true", help="Only validate the saved WeChat Channels cookie; do not upload.")
    parser.add_argument("--publish", action="store_true", help="Publish publicly instead of saving as draft.")
    parser.add_argument("--headless", action="store_true", help="Run browser headless. Default is visible browser.")
    args = parser.parse_args()
    result = asyncio.run(push(args))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result.get("ok") else 2)


if __name__ == "__main__":
    main()
