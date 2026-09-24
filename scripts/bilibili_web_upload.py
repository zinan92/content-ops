#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright


ROOT = Path("/Users/wendy")
DEFAULT_ACCOUNT_FILE = ROOT / "content-toolkit/capabilities/publish/cookies/bilibili_creator.json"
UPLOAD_URL = "https://member.bilibili.com/platform/upload/video/frame"
MANAGER_URL = "https://member.bilibili.com/platform/upload-manager/article"


def emit(payload: dict[str, Any], exit_code: int | None = None) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    raise SystemExit(exit_code if exit_code is not None else (0 if payload.get("ok") else 2))


def load_biliup_cookies(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    raw_cookies = (data.get("cookie_info") or {}).get("cookies") or []
    if not raw_cookies:
        raise ValueError(f"Bilibili cookie 文件没有 cookie_info.cookies：{path}")
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


async def click_text(page, label: str, *, exact: bool = True, timeout: int = 1500) -> bool:
    locator = page.get_by_text(label, exact=exact)
    if await locator.count() == 0:
        return False
    try:
        await locator.first.click(timeout=timeout)
        return True
    except Exception:
        return False


async def page_text(page) -> str:
    return "\n".join(await page.locator("body").all_inner_texts())


async def check(args: argparse.Namespace) -> dict[str, Any]:
    account_file = Path(args.account_file).expanduser()
    if not account_file.exists():
        return {
            "ok": False,
            "status": "cookie_missing",
            "account_file": str(account_file),
            "message": "缺少 Bilibili cookie 文件，请先登录 Bilibili。",
        }
    cookies = load_biliup_cookies(account_file)
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context()
        await context.add_cookies(cookies)
        page = await context.new_page()
        try:
            await page.goto(UPLOAD_URL, wait_until="domcontentloaded", timeout=args.page_timeout * 1000)
            await page.wait_for_timeout(5000)
            text = await page_text(page)
            logged_in = "扫码登录" not in text and "密码登录" not in text and "投稿" in text
            return {
                "ok": logged_in,
                "status": "web_login_valid" if logged_in else "web_login_invalid",
                "account_file": str(account_file),
                "url": page.url,
                "message": "Bilibili 网页投稿登录态可用。" if logged_in else "Bilibili 登录态不可用，请重新登录。",
            }
        finally:
            await browser.close()


async def verify(args: argparse.Namespace) -> dict[str, Any]:
    account_file = Path(args.account_file).expanduser()
    cookies = load_biliup_cookies(account_file)
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context()
        await context.add_cookies(cookies)
        page = await context.new_page()
        try:
            await page.goto(MANAGER_URL, wait_until="domcontentloaded", timeout=args.page_timeout * 1000)
            await page.wait_for_timeout(8000)
            text = await page_text(page)
            title = str(args.title or "").strip()
            found = bool(title and title in text)
            status_fragments = []
            for marker in ["转码中", "审核中", "已通过", "稿件投递成功", "未通过"]:
                if marker in text:
                    status_fragments.append(marker)
            return {
                "ok": found,
                "status": "found_in_manager" if found else "not_found_in_manager",
                "title": title,
                "url": page.url,
                "platform_url": MANAGER_URL,
                "review_status": " / ".join(status_fragments[:3]) if status_fragments else "",
                "message": "Bilibili 稿件管理页已找到该标题。" if found else "Bilibili 稿件管理页没有找到该标题，请检查是否提交成功。",
            }
        finally:
            await browser.close()


async def set_cover(page, cover: Path) -> dict[str, Any] | None:
    """打开「封面制作」，勾「双比例同步改动」（4:3 的图同时用在 16:9），上传，点完成。

    返回 None 表示设好了；否则是说明哪一步没成的结果，调用方在投稿前停下。
    """
    await page.locator(".cover-empty, .cover-main .cover-slot").first.click()
    dialog = page.locator(".bcc-dialog").filter(has_text="封面制作").first
    await dialog.wait_for(state="visible", timeout=15000)
    sync = dialog.locator(".sync.ratio_4_3 .sync-checkbox").first
    if await sync.count() and "bcc-checkbox-checked" not in (await sync.get_attribute("class") or ""):
        await sync.click()
        await page.wait_for_timeout(500)
    await dialog.locator('input[type=file][accept*="image"]').first.set_input_files(str(cover))
    await page.wait_for_timeout(5000)
    await dialog.get_by_text("完成", exact=True).last.click()
    await page.wait_for_timeout(3000)
    has_image = await page.evaluate(
        "() => { const img = document.querySelector('.cover-main .cover-img'); return !!img && /url\\(/.test(img.style.backgroundImage || ''); }"
    )
    if not has_image:
        return {"ok": False, "status": "cover_not_set", "message": "封面没设上，没有投稿。可以重试，或者在 B 站后台手动投稿。"}
    return None


async def upload(args: argparse.Namespace) -> dict[str, Any]:
    account_file = Path(args.account_file).expanduser()
    video = Path(args.video).expanduser()
    if not account_file.exists():
        return {"ok": False, "status": "cookie_missing", "account_file": str(account_file), "message": "缺少 Bilibili cookie 文件。"}
    if not video.exists():
        return {"ok": False, "status": "video_missing", "video": str(video), "message": "缺少本地视频文件。"}
    cover = Path(args.cover).expanduser() if getattr(args, "cover", None) else None
    if cover is not None and (not cover.is_file() or cover.suffix.lower() not in (".jpg", ".jpeg", ".png")):
        return {"ok": False, "status": "cover_missing", "cover": str(cover), "message": "封面要是本地的 jpg 或 png。"}
    cookies = load_biliup_cookies(account_file)
    tags = [tag.strip().lstrip("#") for tag in (args.tags or "").split(",") if tag.strip()]
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=args.headless)
        context = await browser.new_context(viewport={"width": 1440, "height": 1000})
        await context.add_cookies(cookies)
        page = await context.new_page()
        try:
            page.set_default_timeout(args.page_timeout * 1000)
            await page.goto(UPLOAD_URL, wait_until="domcontentloaded", timeout=args.page_timeout * 1000)
            await page.wait_for_timeout(3000)
            if "login" in page.url:
                return {
                    "ok": False,
                    "status": "login_required",
                    "platform_url": "https://passport.bilibili.com/login",
                    "message": "Bilibili 网页投稿登录态失效，请在 dashboard 里重新登录 Bilibili。",
                }
            file_inputs = page.locator('input[type="file"]')
            # 投稿页是单页应用，上传控件要 4–5 秒才渲染出来；固定等 3 秒会误报「没有上传控件」。
            try:
                await file_inputs.first.wait_for(state="attached", timeout=args.page_timeout * 1000)
            except PlaywrightTimeoutError:
                pass
            if await file_inputs.count() == 0:
                text = (await page_text(page))[:1200]
                return {"ok": False, "status": "upload_input_missing", "url": page.url, "message": "Bilibili 投稿页没有找到上传控件。", "page_excerpt": text}
            await file_inputs.first.set_input_files(str(video))
            await page.wait_for_selector('input[placeholder="请输入稿件标题"]', timeout=args.form_timeout * 1000)
            await page.locator('input[placeholder="请输入稿件标题"]').first.fill(args.title[:80])
            if cover is not None:
                failed = await set_cover(page, cover)
                if failed:
                    return failed

            declaration = page.locator('input[placeholder="请选择符合您视频内容的创作声明"]').first
            if await declaration.count():
                await declaration.click()
                await page.wait_for_timeout(800)
                declaration_selected = False
                for label in ["内容无需标注", "内容为自制"]:
                    if await click_text(page, label, exact=True):
                        declaration_selected = True
                        break
                if not declaration_selected:
                    return {
                        "ok": False,
                        "status": "declaration_required",
                        "message": "Bilibili 要求选择创作声明，但页面没有找到可自动选择的声明项。",
                    }

            tag_input = page.locator('input[placeholder="按回车键Enter创建标签"]').first
            for tag in tags[:6]:
                await tag_input.fill(tag)
                await page.keyboard.press("Enter")
                await page.wait_for_timeout(300)

            editors = page.locator(".ql-editor")
            if await editors.count():
                await editors.first.click()
                await page.keyboard.type(args.description[:2000])

            deadline = time.time() + args.upload_timeout
            last_progress = ""
            while True:
                text = await page_text(page)
                if "上传完成" in text and "上传中" not in text:
                    break
                if "已经上传" in text:
                    start = text.find("已经上传")
                    last_progress = text[start : start + 140]
                if time.time() > deadline:
                    return {
                        "ok": False,
                        "status": "upload_timeout",
                        "message": "Bilibili 视频上传超时。",
                        "last_progress": last_progress,
                    }
                await page.wait_for_timeout(5000)

            await page.get_by_text("立即投稿", exact=True).first.click()
            await page.wait_for_timeout(3000)
            for _ in range(6):
                clicked = False
                for label, exact in [
                    ("内容无需标注", True),
                    ("去声明", False),
                    ("确定", True),
                    ("确认", True),
                    ("知道了", False),
                    ("我知道了", False),
                ]:
                    if await click_text(page, label, exact=exact):
                        clicked = True
                        await page.wait_for_timeout(2500)
                if not clicked:
                    break

            await page.wait_for_timeout(12000)
            text = await page_text(page)
            submitted = "稿件投递成功" in text or "查看进度" in text or "再投一个" in text
            if not submitted:
                if "发布前请添加创作声明" in text:
                    return {
                        "ok": False,
                        "status": "declaration_required",
                        "message": "Bilibili 拦截了提交：发布前请添加创作声明。",
                        "page_excerpt": text[-1500:],
                    }
                return {
                    "ok": False,
                    "status": "submit_not_confirmed",
                    "message": "Bilibili 没有确认投稿成功，请检查页面提示。",
                    "page_excerpt": text[-1800:],
                }

            verify_result = await verify(args)
            ok = bool(verify_result.get("ok"))
            return {
                "ok": ok,
                "status": "submitted_review" if ok else "submitted_unverified",
                "title": args.title,
                "video": str(video),
                "platform_url": MANAGER_URL,
                "verification": verify_result,
                "message": "已提交 Bilibili，当前进入转码/审核流程。" if ok else "Bilibili 页面提示已投递，但稿件管理页暂未验证到标题。",
                "submitted_at": datetime.now().isoformat(timespec="seconds"),
            }
        except PlaywrightTimeoutError as exc:
            return {"ok": False, "status": "page_timeout", "message": f"Bilibili 页面等待超时：{exc}"[:800]}
        finally:
            await browser.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Park-IO Bilibili web uploader.")
    parser.add_argument("--account-file", default=str(DEFAULT_ACCOUNT_FILE))
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--page-timeout", type=int, default=60)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("check")

    verify_parser = sub.add_parser("verify")
    verify_parser.add_argument("--title", required=True)

    upload_parser = sub.add_parser("upload")
    upload_parser.add_argument("--video", required=True)
    upload_parser.add_argument("--title", required=True)
    upload_parser.add_argument("--description", default="")
    upload_parser.add_argument("--tags", default="")
    upload_parser.add_argument("--cover", default="", help="横版封面 jpg/png；同一张图同时用在 4:3 和 16:9")
    upload_parser.add_argument("--upload-timeout", type=int, default=900)
    upload_parser.add_argument("--form-timeout", type=int, default=120)

    args = parser.parse_args()
    if args.command == "check":
        emit(asyncio.run(check(args)))
    if args.command == "verify":
        emit(asyncio.run(verify(args)))
    if args.command == "upload":
        emit(asyncio.run(upload(args)))
    emit({"ok": False, "status": "unknown_command"})


if __name__ == "__main__":
    main()
