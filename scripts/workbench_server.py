#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import time
from datetime import datetime
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, urlparse
from urllib.request import Request, urlopen


ROOT = Path("/Users/wendy")
OUTBOX = ROOT / "park-io/outbox"
DRAFTS = OUTBOX / "drafts"
SENT = OUTBOX / "sent"
ACTION_DIR = OUTBOX / ".system/actions"
ACTION_LOG = ACTION_DIR / "action-log.jsonl"
VIDEO_MIGRATION_STATE = ACTION_DIR / "video-migration-state.json"
EVIDENCE_DIR = OUTBOX / ".system/evidence"
AUTH_QR_DIR = OUTBOX / ".system/auth-qrcodes"
XHS_SKILL = ROOT / ".agents/skills/xiaohongshu-skills"
XHS_CLI = XHS_SKILL / "scripts/cli.py"
WECHAT_WORKFLOW = ROOT / "wechat-workflow"
WECHAT_CHANNELS_PUSH = ROOT / "work/content-ops/scripts/push_wechat_channels_draft.py"
REPAIR_DOUYIN_VIDEOS = ROOT / "work/content-ops/scripts/repair_missing_douyin_videos.py"
RUN_OUTBOX_ACTION_QUEUE = ROOT / "work/content-ops/scripts/run_outbox_action_queue.py"
RUN_OUTBOX_WORKFLOW = ROOT / "work/content-ops/scripts/run_outbox_workflow.py"
RECORD_OUTBOX_ACTION_DECISION = ROOT / "work/content-ops/scripts/record_outbox_action_decision.py"
GENERATE_REPURPOSE_DRAFTS = ROOT / "work/content-ops/scripts/generate_repurpose_drafts.py"
GENERATE_CONTENT_PACKAGE = ROOT / "work/content-ops/scripts/generate_content_package.py"
GENERATE_XHS_FROM_CONTENT_PACKAGE = ROOT / "work/content-ops/scripts/generate_xiaohongshu_from_content_package.py"
BUILD_DASHBOARD = ROOT / "work/content-ops/scripts/build_dashboard.py"
QUALITY_XHS_DRAFTS = ROOT / "work/content-ops/scripts/quality_xiaohongshu_drafts.py"
RENDER_XHS_CARDS = ROOT / "work/content-ops/scripts/render_xiaohongshu_cards.py"
CHECK_PLATFORM_CHANNELS = ROOT / "work/content-ops/scripts/check_platform_channels.py"
YOUTUBE_CHANNEL = ROOT / "work/content-ops/scripts/youtube_channel.py"
BILIBILI_WEB_UPLOAD = ROOT / "work/content-ops/scripts/bilibili_web_upload.py"
CAPTURE_VIDEO_MIGRATION_EVIDENCE = ROOT / "work/content-ops/scripts/capture_video_migration_evidence.py"
IMPORT_CHROME_COOKIES = ROOT / "work/content-ops/scripts/import_chrome_cookies.py"
CONTENT_OPS_PYTHON = ROOT / "work/content-ops/.venv/bin/python"
PUBLISH_ROOT = ROOT / "content-toolkit/capabilities/publish"
PUBLISH_PYTHON = PUBLISH_ROOT / ".venv/bin/python"
FFMPEG = shutil.which("ffmpeg") or str(ROOT / "bin/ffmpeg")
FFPROBE = shutil.which("ffprobe") or str(ROOT / "bin/ffprobe")
TMUX = shutil.which("tmux") or "/opt/homebrew/bin/tmux"
BILIBILI_ACCOUNT = PUBLISH_ROOT / "cookies/bilibili_creator.json"
XHS_SAU_ACCOUNT = PUBLISH_ROOT / "cookies/xiaohongshu_creator.json"
WECHAT_CHANNELS_ACCOUNT = PUBLISH_ROOT / "cookies/tencent_uploader/account.json"
BILIBILI_DEFAULT_TID = 231
PLATFORM_URLS = {
    "xiaohongshu": "https://creator.xiaohongshu.com/publish/publish",
    "wechat_mp": "https://mp.weixin.qq.com/",
    "wechat_channels": "https://channels.weixin.qq.com/platform/post/create",
    "bilibili": "https://member.bilibili.com/platform/upload/video/frame",
    "youtube": "https://studio.youtube.com/",
    "zhihu": "https://www.zhihu.com/creator",
    "x": "https://x.com/compose/post",
}
WECHAT_BRIDGE_URL = "http://127.0.0.1:5174"
XHS_EXTENSION_URL = "chrome://extensions/?id=djmopoijialkhicdddlneckfmfoagcki"
YOUTUBE_CLIENT_CANDIDATES = [
    ROOT / ".config/park/youtube-oauth.json",
    ROOT / ".credentials/youtube.json",
]
YOUTUBE_TOKEN = ROOT / ".config/park/youtube-token.json"
YOUTUBE_OAUTH_SEARCH_DIRS = [
    ROOT / "Downloads",
    ROOT / "Desktop",
    ROOT / "Documents",
]


CAPABILITIES = {
    "xiaohongshu": {
        "label": "小红书",
        "status": "draft_push_ready",
        "mode": "content_toolkit_safe_draft",
        "mutates_platform": True,
        "final_publish": False,
        "tool": str(PUBLISH_ROOT / "sau_cli.py"),
        "notes": "优先使用 content-toolkit/social-auto-upload 图文上传并点击暂存离开保存草稿；xiaohongshu-skills Bridge 只作为备用。",
    },
    "wechat_mp": {
        "label": "公众号",
        "status": "draft_push_ready",
        "mode": "wechat_draft_api",
        "mutates_platform": True,
        "final_publish": False,
        "tool": str(WECHAT_WORKFLOW / "bridge/server.js"),
        "notes": "使用 wechat-workflow bridge 创建公众号草稿；不会群发或发布。",
    },
    "wechat_channels": {
        "label": "视频号",
        "status": "public_publish_ready_needs_cookie",
        "mode": "video_public_publish",
        "mutates_platform": True,
        "final_publish": True,
        "tool": str(WECHAT_CHANNELS_PUSH),
        "notes": "使用 social-auto-upload TencentVideo 公开视频发布；需要有效 cookie。",
    },
    "bilibili": {
        "label": "Bilibili",
        "status": "public_upload_ready_needs_cookie",
        "mode": "bilibili_public_upload",
        "mutates_platform": True,
        "final_publish": True,
        "tool": str(ROOT / "content-toolkit/capabilities/publish/uploader/bilibili_uploader/runtime.py"),
        "notes": "账号 cookie 就绪后可公开视频投稿。",
    },
    "youtube": {
        "label": "YouTube",
        "status": "public_upload_ready_needs_oauth",
        "mode": "youtube_api_public_upload",
        "mutates_platform": True,
        "final_publish": True,
        "tool": str(YOUTUBE_CHANNEL),
        "notes": "Google OAuth 就绪后可公开视频上传。",
    },
    "zhihu": {
        "label": "知乎",
        "status": "handoff_ready",
        "mode": "open_editor_with_clipboard_payload",
        "mutates_platform": True,
        "final_publish": False,
        "tool": "macOS open + clipboard",
        "notes": "先打开知乎写作页并复制标题/正文；不点击发布。",
    },
    "x": {
        "label": "X",
        "status": "handoff_ready",
        "mode": "open_composer_with_prefilled_text",
        "mutates_platform": True,
        "final_publish": False,
        "tool": str(ROOT / ".local/bin/twitter"),
        "notes": "使用 X compose intent 预填正文；不调用 twitter CLI post。",
    },
}

CHANNELS = ["xiaohongshu", "wechat_mp", "wechat_channels", "bilibili", "youtube", "x", "zhihu"]
PREPARABLE_CHANNELS = {"xiaohongshu", "wechat_mp", "wechat_channels", "bilibili", "youtube"}
VIDEO_MIGRATION_CHANNELS = {"wechat_channels", "bilibili", "youtube"}
VIDEO_MIGRATION_ORDER = ["wechat_channels", "bilibili", "youtube"]
AUTH_PREP_ORDER = ["xiaohongshu", "wechat_channels", "bilibili", "youtube"]
MANUAL_AUTH_BLOCKERS = {"extension_host_permission_missing"}
XHS_BRIDGE_SESSION = "park-xhs-bridge"
XHS_LOGIN_SESSION = "park-xhs-login"
BILIBILI_LOGIN_SESSION = "park-bilibili-login"
WECHAT_CHANNELS_LOGIN_SESSION = "park-wechat-channels-login"


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def compact_for_log(value: Any) -> Any:
    if isinstance(value, dict):
        compacted: dict[str, Any] = {}
        for key, item in value.items():
            if key in {"html", "markdown", "body"} and isinstance(item, str):
                compacted[f"{key}_chars"] = len(item)
                compacted[f"{key}_preview"] = item[:160]
            elif key == "payload" and isinstance(item, dict):
                payload = compact_for_log(item)
                if isinstance(payload, dict):
                    compacted[key] = payload
                else:
                    compacted[key] = payload
            else:
                compacted[key] = compact_for_log(item)
        return compacted
    if isinstance(value, list):
        return [compact_for_log(item) for item in value[:30]]
    return value


def write_log(entry: dict[str, Any]) -> None:
    ACTION_DIR.mkdir(parents=True, exist_ok=True)
    entry = compact_for_log({"created_at": now_iso(), **entry})
    with ACTION_LOG.open("a", encoding="utf-8") as file_obj:
        file_obj.write(json.dumps(entry, ensure_ascii=False) + "\n")


def load_video_migration_state() -> dict[str, Any]:
    if not VIDEO_MIGRATION_STATE.exists():
        return {}
    try:
        data = json.loads(VIDEO_MIGRATION_STATE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_video_migration_state(state: dict[str, Any]) -> None:
    ACTION_DIR.mkdir(parents=True, exist_ok=True)
    tmp = VIDEO_MIGRATION_STATE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(VIDEO_MIGRATION_STATE)


def persisted_video_migration_platform(source_content_id: str, platform: str) -> dict[str, Any]:
    item = (load_video_migration_state().get(source_content_id) or {}).get(platform)
    return item if isinstance(item, dict) else {}


def update_video_migration_state(source_content_id: str, platform: str, result: dict[str, Any]) -> None:
    stage = "published" if result.get("ok") else "failed"
    if result.get("ok") and result.get("status") in {"submitted_review", "found_in_manager"}:
        stage = "submitted_review"
    elif result.get("ok") and result.get("status") in {"verified_public", "public_uploaded"}:
        stage = "published"
    state = load_video_migration_state()
    source_state = state.setdefault(source_content_id, {})
    source_state[platform] = {
        "updated_at": now_iso(),
        "platform": platform,
        "label": platform_label(platform),
        "ok": bool(result.get("ok")),
        "stage": stage,
        "status": result.get("status") or ("published" if result.get("ok") else "failed"),
        "message": result.get("message") or "",
        "platform_url": result.get("platform_url") or result.get("url") or "",
        "video_id": result.get("video_id") or "",
        "evidence_screenshot": result.get("evidence_screenshot") or "",
        "evidence_screenshot_href": result.get("evidence_screenshot_href") or "",
        "result": result,
    }
    save_video_migration_state(state)


def evidence_href(path: str | Path) -> str:
    evidence_path = Path(path)
    try:
        relative = evidence_path.relative_to(OUTBOX)
        return "/" + quote(str(relative))
    except ValueError:
        return "file://" + quote(str(evidence_path))


def capture_video_migration_evidence(source_content_id: str, platform: str, result: dict[str, Any]) -> dict[str, Any]:
    if not result.get("ok") or not CAPTURE_VIDEO_MIGRATION_EVIDENCE.exists():
        return result
    asset = find_source_asset(source_content_id)
    title = str((asset or {}).get("title") or "")
    url = str(result.get("platform_url") or result.get("url") or "")
    if platform == "youtube" and result.get("video_id"):
        url = f"https://www.youtube.com/watch?v={quote(str(result.get('video_id')))}"
    output = EVIDENCE_DIR / source_content_id / f"{platform}.png"
    python_bin = CONTENT_OPS_PYTHON if CONTENT_OPS_PYTHON.exists() else Path(sys.executable)
    command = [
        str(python_bin),
        str(CAPTURE_VIDEO_MIGRATION_EVIDENCE),
        "--platform",
        platform,
        "--source-content-id",
        source_content_id,
        "--title",
        title,
        "--output",
        str(output),
    ]
    if url:
        command.extend(["--url", url])
    completed = run_command(command, cwd=CAPTURE_VIDEO_MIGRATION_EVIDENCE.parent, timeout=120)
    try:
        parsed = json.loads(completed.get("stdout") or "{}")
    except json.JSONDecodeError:
        parsed = {}
    enriched = {**result, "evidence_result": parsed or scrub_command_result(completed)}
    if completed.get("returncode") == 0 and parsed.get("ok") and output.exists():
        enriched["evidence_screenshot"] = str(output)
        enriched["evidence_screenshot_href"] = evidence_href(output)
    return enriched


def compact_action(entry: dict[str, Any]) -> dict[str, Any]:
    result = entry.get("result") or {}
    request = entry.get("request") or {}
    platform = entry.get("platform") or result.get("platform") or request.get("platform") or ""
    source_content_id = result.get("source_content_id") or request.get("source_content_id") or ""
    local_id = result.get("local_id") or request.get("local_id") or ""
    summary = {
        "created_at": entry.get("created_at") or "",
        "action": entry.get("action") or "",
        "platform": platform,
        "source_content_id": source_content_id,
        "local_id": local_id,
        "ok": bool(result.get("ok")),
        "status": result.get("status") or "",
        "message": result.get("message") or result.get("next_step") or "",
    }
    if entry.get("action") == "check_all_channels":
        summary["message"] = f"{result.get('ready_count', 0)} ready · {result.get('needs_setup_count', 0)} need setup"
    elif entry.get("action") == "preflight_source":
        summary["message"] = f"{result.get('ready_count', 0)} ready · {result.get('needs_work_count', 0)} need work"
    elif entry.get("action") == "repair_local_gaps":
        summary["message"] = result.get("message") or f"{len(result.get('actions') or [])} local actions"
    elif entry.get("action") == "prepare_missing_channels":
        summary["message"] = result.get("message") or f"{result.get('prepared_count', 0)} prepare actions requested"
    elif result.get("summary"):
        summary["message"] = json.dumps(result.get("summary"), ensure_ascii=False)
    return summary


def recent_actions(limit: int = 30) -> dict[str, Any]:
    if not ACTION_LOG.exists():
        return {"ok": True, "actions": []}
    lines = ACTION_LOG.read_text(encoding="utf-8", errors="replace").splitlines()
    actions = []
    for line in reversed(lines[-max(limit * 3, limit):]):
        try:
            actions.append(compact_action(json.loads(line)))
        except json.JSONDecodeError:
            continue
        if len(actions) >= limit:
            break
    return {"ok": True, "actions_log": str(ACTION_LOG), "actions": actions}


def read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def file_artifact(path: Path, label: str) -> dict[str, Any]:
    exists = path.exists()
    artifact: dict[str, Any] = {
        "label": label,
        "path": str(path),
        "exists": exists,
    }
    if exists:
        try:
            stat = path.stat()
            artifact.update(
                {
                    "size": stat.st_size,
                    "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
                }
            )
        except OSError:
            pass
    return artifact


def auth_artifacts() -> dict[str, list[dict[str, Any]]]:
    wechat_html_path = Path(str(record.get("wechat_html_path") or "")) if record.get("wechat_html_path") else None
    if wechat_html_path and wechat_html_path.exists():
        html_path = wechat_html_path
        content_html = html_path.read_text(encoding="utf-8")
    return {
        "xiaohongshu": [file_artifact(XHS_SAU_ACCOUNT, "小红书账号 cookie")],
        "wechat_channels": [file_artifact(WECHAT_CHANNELS_ACCOUNT, "视频号账号 cookie")],
        "bilibili": [file_artifact(BILIBILI_ACCOUNT, "Bilibili 账号 cookie")],
        "youtube": [
            *[file_artifact(path, "YouTube OAuth client") for path in YOUTUBE_CLIENT_CANDIDATES],
            file_artifact(YOUTUBE_TOKEN, "YouTube OAuth token"),
        ],
    }


def check_auth_artifacts() -> dict[str, Any]:
    artifacts = auth_artifacts()
    flat = [item for items in artifacts.values() for item in items]
    existing = [item for item in flat if item.get("exists")]
    missing = [item for item in flat if not item.get("exists")]
    platform_ready = {
        platform: any(item.get("exists") for item in items)
        for platform, items in artifacts.items()
    }
    if "youtube" in platform_ready:
        youtube_items = artifacts.get("youtube") or []
        has_client = any(item.get("exists") and item.get("label") == "YouTube OAuth client" for item in youtube_items)
        has_token = any(item.get("exists") and item.get("label") == "YouTube OAuth token" for item in youtube_items)
        platform_ready["youtube"] = has_client and has_token
    return {
        "ok": True,
        "status": "checked",
        "checked_at": now_iso(),
        "platform_ready": platform_ready,
        "existing_count": len(existing),
        "missing_count": len(missing),
        "auth_artifacts": artifacts,
        "next_step": "如果某个平台仍显示缺失，先点该平台“准备通道”完成扫码/OAuth，再重查授权文件。",
    }


def wait_auth_artifacts(payload: dict[str, Any]) -> dict[str, Any]:
    timeout_seconds = min(max(int(payload.get("timeout_seconds") or 120), 5), 600)
    interval_seconds = min(max(float(payload.get("interval_seconds") or 2), 0.5), 10)
    started = time.time()
    initial = check_auth_artifacts()
    initial_existing = int(initial.get("existing_count") or 0)
    final = initial
    while time.time() - started < timeout_seconds:
        time.sleep(interval_seconds)
        final = check_auth_artifacts()
        if int(final.get("existing_count") or 0) > initial_existing or int(final.get("missing_count") or 0) == 0:
            break
    changed = int(final.get("existing_count") or 0) > initial_existing
    timed_out = not changed and int(final.get("missing_count") or 0) > 0
    return {
        **final,
        "status": "auth_artifact_detected" if changed else ("timeout" if timed_out else "complete"),
        "changed": changed,
        "timed_out": timed_out,
        "waited_seconds": round(time.time() - started, 1),
        "initial_existing_count": initial_existing,
        "timeout_seconds": timeout_seconds,
        "next_step": "检测到新的授权文件，正在重查通道。" if changed else "等待期间没有新的授权文件出现；请确认扫码/OAuth 是否已经完成，或继续等待后再检查。",
    }


def latest_file(paths: list[Path]) -> Path | None:
    existing = [path for path in paths if path.exists()]
    if not existing:
        return None
    return max(existing, key=lambda path: path.stat().st_mtime)


def collect_auth_qrcodes() -> dict[str, dict[str, Any]]:
    AUTH_QR_DIR.mkdir(parents=True, exist_ok=True)
    sources = {
        "xiaohongshu": latest_file(sorted((PUBLISH_ROOT / "cookies").glob("xiaohongshu_creator_xhs_login_qrcode_*.png"))),
        "bilibili": latest_file([PUBLISH_ROOT / "qrcode.png"]),
    }
    qrcodes: dict[str, dict[str, Any]] = {}
    for platform, source in sources.items():
        target = AUTH_QR_DIR / f"{platform}.png"
        if source:
            try:
                shutil.copy2(source, target)
            except OSError:
                pass
        item: dict[str, Any] = {
            "platform": platform,
            "exists": target.exists(),
            "path": str(target),
            "href": f"/.system/auth-qrcodes/{platform}.png",
        }
        if target.exists():
            stat = target.stat()
            age_seconds = max(0, int(time.time() - stat.st_mtime))
            item.update(
                {
                    "size": stat.st_size,
                    "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
                    "age_seconds": age_seconds,
                    "possibly_expired": age_seconds > 180,
                }
            )
        if source:
            item["source_path"] = str(source)
        qrcodes[platform] = item
    return qrcodes


def capture_tmux_tail(session: str, lines: int = 30) -> dict[str, Any]:
    has_session = run_command([TMUX, "has-session", "-t", session], timeout=5)
    if has_session["returncode"] != 0:
        return {"running": False, "session": session, "tail": ""}
    capture = run_command([TMUX, "capture-pane", "-t", session, "-p", "-S", f"-{lines}"], timeout=5)
    return {
        "running": capture["returncode"] == 0,
        "session": session,
        "tail": (capture.get("stdout") or "")[-3000:],
    }


def login_sessions_status() -> dict[str, dict[str, Any]]:
    sessions = {
        "xiaohongshu": XHS_LOGIN_SESSION,
        "wechat_channels": WECHAT_CHANNELS_LOGIN_SESSION,
        "bilibili": BILIBILI_LOGIN_SESSION,
    }
    result: dict[str, dict[str, Any]] = {}
    for platform, session in sessions.items():
        status = capture_tmux_tail(session)
        tail = status.get("tail") or ""
        waiting_markers = ["请扫码", "waiting_login", "扫码", "scan", "qrcode", "二维码"]
        success_markers = ["cookie有效", "cookie_saved", "login completed", "登录成功", "success"]
        failure_markers = ["cookie_login_failed", " failed", " error", "Traceback", "登录失败"]
        status["platform"] = platform
        status["waiting_for_user"] = bool(status.get("running") and any(marker.lower() in tail.lower() for marker in waiting_markers))
        status["looks_successful"] = any(marker.lower() in tail.lower() for marker in success_markers)
        status["looks_failed"] = any(marker.lower() in tail.lower() for marker in failure_markers)
        result[platform] = status
    return result


def restart_auth_prompts(payload: dict[str, Any]) -> dict[str, Any]:
    if not bool(payload.get("confirmed")):
        return {
            "ok": False,
            "status": "confirmation_required",
            "message": "这是会重启扫码/登录/OAuth 入口的动作，需要 confirmed=true。",
        }
    checks = check_all_channels()
    channels_by_platform = {str(item.get("platform") or ""): item for item in checks.get("channels") or []}
    sessions = {
        "xiaohongshu": XHS_LOGIN_SESSION,
        "wechat_channels": WECHAT_CHANNELS_LOGIN_SESSION,
        "bilibili": BILIBILI_LOGIN_SESSION,
    }
    qr_targets = {
        "xiaohongshu": [AUTH_QR_DIR / "xiaohongshu.png"],
        "bilibili": [AUTH_QR_DIR / "bilibili.png", PUBLISH_ROOT / "qrcode.png"],
    }
    actions: list[dict[str, Any]] = []
    for platform in AUTH_PREP_ORDER:
        channel = channels_by_platform.get(platform) or {}
        if channel.get("ok"):
            actions.append({"platform": platform, "status": "already_ready"})
            continue
        session = sessions.get(platform)
        if session:
            kill = run_command([TMUX, "kill-session", "-t", session], timeout=5)
        else:
            kill = {"returncode": 0, "stdout": "", "stderr": ""}
        removed = []
        for path in qr_targets.get(platform, []):
            if path.exists():
                try:
                    path.unlink()
                    removed.append(str(path))
                except OSError:
                    pass
        actions.append(
            {
                "platform": platform,
                "before_status": channel.get("status") or "",
                "killed_session": bool(session),
                "kill_result": kill,
                "removed": removed,
                "result": prepare_channel(platform),
            }
        )
    return {
        "ok": True,
        "status": "auth_prompts_restarted",
        "actions": actions,
        "auth_qrcodes": collect_auth_qrcodes(),
        "login_sessions": login_sessions_status(),
        "message": "已重启当前未打通平台的扫码/登录/OAuth 入口；不会发布任何内容。请在 dashboard 扫码/授权后点“等待授权完成”。",
    }


def validate_youtube_oauth_client(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "path": str(path), "status": "invalid_json", "message": str(exc)}
    result = validate_youtube_oauth_data(data)
    result["path"] = str(path)
    return result


def validate_youtube_oauth_data(data: dict[str, Any]) -> dict[str, Any]:
    config = data.get("installed") or data.get("web") or {}
    required = {"client_id", "client_secret", "auth_uri", "token_uri"}
    missing = sorted(required - set(config))
    if missing:
        return {
            "ok": False,
            "status": "not_google_oauth_client",
            "missing": missing,
        }
    return {
        "ok": True,
        "status": "valid_google_oauth_client",
        "client_type": "installed" if data.get("installed") else "web",
        "client_id_suffix": str(config.get("client_id") or "")[-18:],
    }


def find_youtube_oauth_client_candidates() -> list[dict[str, Any]]:
    patterns = ["*client_secret*.json", "*oauth*.json", "credentials*.json"]
    paths: list[Path] = []
    for directory in YOUTUBE_OAUTH_SEARCH_DIRS:
        if not directory.exists():
            continue
        for pattern in patterns:
            paths.extend(directory.glob(pattern))
            paths.extend(directory.glob(f"**/{pattern}"))
    seen = set()
    candidates = []
    for path in sorted(paths, key=lambda item: item.stat().st_mtime if item.exists() else 0, reverse=True):
        key = str(path.resolve())
        if key in seen or not path.is_file():
            continue
        seen.add(key)
        check = validate_youtube_oauth_client(path)
        try:
            stat = path.stat()
            check.update({"modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"), "size": stat.st_size})
        except OSError:
            pass
        candidates.append(check)
    return candidates[:20]


def install_youtube_oauth_client(payload: dict[str, Any]) -> dict[str, Any]:
    explicit = str(payload.get("path") or "").strip()
    inline_content = str(payload.get("content") or "").strip()
    filename = str(payload.get("filename") or "uploaded-oauth-client.json").strip()
    if inline_content:
        try:
            data = json.loads(inline_content)
        except json.JSONDecodeError as exc:
            return {
                "ok": False,
                "status": "invalid_uploaded_json",
                "filename": filename,
                "message": f"不是有效 JSON：{exc}",
            }
        validation = validate_youtube_oauth_data(data)
        if not validation.get("ok"):
            return {
                "ok": False,
                "status": "uploaded_file_not_oauth_client",
                "filename": filename,
                "client": validation,
                "target": str(YOUTUBE_CLIENT_CANDIDATES[0]),
                "message": "这个 JSON 不是 Google OAuth client 文件；需要 Google Cloud 下载的 Desktop client JSON。",
            }
        target = YOUTUBE_CLIENT_CANDIDATES[0]
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            backup = target.with_suffix(target.suffix + f".backup-{datetime.now().strftime('%Y%m%d%H%M%S')}")
            shutil.copy2(target, backup)
        else:
            backup = None
        target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        target.chmod(0o600)
        checked = check_channel("youtube")
        return {
            "ok": True,
            "status": "oauth_client_installed",
            "source": f"browser-upload:{filename}",
            "target": str(target),
            "backup": str(backup) if backup else "",
            "client": validation,
            "check_result": checked,
            "next_step": "OAuth client 已安装。现在点 YouTube / 准备 OAuth 完成 Google 授权，生成 youtube-token.json。",
        }
    if explicit:
        candidates = [validate_youtube_oauth_client(Path(explicit).expanduser())]
    else:
        candidates = find_youtube_oauth_client_candidates()
    valid = [item for item in candidates if item.get("ok")]
    if not valid:
        return {
            "ok": False,
            "status": "no_valid_oauth_client_found",
            "search_dirs": [str(path) for path in YOUTUBE_OAUTH_SEARCH_DIRS],
            "candidates": candidates,
            "target": str(YOUTUBE_CLIENT_CANDIDATES[0]),
            "message": "没有找到可安装的 Google OAuth client JSON。请从 Google Cloud 下载 Desktop client JSON 到 Downloads 后重试。",
        }
    source = Path(str(valid[0]["path"]))
    target = YOUTUBE_CLIENT_CANDIDATES[0]
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        backup = target.with_suffix(target.suffix + f".backup-{datetime.now().strftime('%Y%m%d%H%M%S')}")
        shutil.copy2(target, backup)
    else:
        backup = None
    shutil.copy2(source, target)
    target.chmod(0o600)
    checked = check_channel("youtube")
    return {
        "ok": True,
        "status": "oauth_client_installed",
        "source": str(source),
        "target": str(target),
        "backup": str(backup) if backup else "",
        "client": valid[0],
        "check_result": checked,
        "next_step": "OAuth client 已安装。现在点 YouTube / 准备 OAuth 完成 Google 授权，生成 youtube-token.json。",
    }


def start_tmux_session(session: str, command: str, cwd: Path) -> dict[str, Any]:
    if not Path(TMUX).exists():
        return {"ok": False, "status": "tmux_missing", "session": session, "tmux": TMUX}
    has_session = run_command([TMUX, "has-session", "-t", session], timeout=5)
    if has_session["returncode"] == 0:
        return {"ok": True, "status": "session_exists", "session": session}
    shell_command = f"cd {shlex.quote(str(cwd))} && {command}"
    result = run_command([TMUX, "new-session", "-d", "-s", session, shell_command], timeout=10)
    return {
        "ok": result["returncode"] == 0,
        "status": "session_started" if result["returncode"] == 0 else "session_start_failed",
        "session": session,
        "command": shell_command,
        "result": result,
    }


def start_xhs_login_session() -> dict[str, Any]:
    existing_session = run_command([TMUX, "has-session", "-t", XHS_LOGIN_SESSION], timeout=5)
    if existing_session["returncode"] == 0:
        qrcodes = collect_auth_qrcodes()
        return {
            "ok": True,
            "status": "session_exists",
            "session": XHS_LOGIN_SESSION,
            "qrcode": qrcodes.get("xiaohongshu", {}),
            "next_step": "小红书登录会话已经在等待扫码。请在 dashboard 的授权队列里打开二维码，用小红书 App 扫码。扫码完成后点“等待授权完成”。",
        }
    for stale_qrcode in (PUBLISH_ROOT / "cookies").glob("xiaohongshu_creator_xhs_login_qrcode_*.png"):
        try:
            stale_qrcode.unlink()
        except OSError:
            pass
    stale_dashboard_qrcode = AUTH_QR_DIR / "xiaohongshu.png"
    if stale_dashboard_qrcode.exists():
        try:
            stale_dashboard_qrcode.unlink()
        except OSError:
            pass
    command = (
        f"{shlex.quote(str(PUBLISH_PYTHON))} sau_cli.py xiaohongshu login "
        "--account creator --headed"
    )
    result = start_tmux_session(XHS_LOGIN_SESSION, command, PUBLISH_ROOT)
    qrcodes = collect_auth_qrcodes()
    deadline = time.time() + 12
    while time.time() < deadline and not qrcodes.get("xiaohongshu", {}).get("exists"):
        time.sleep(1)
        qrcodes = collect_auth_qrcodes()
    return {
        **result,
        "qrcode": qrcodes.get("xiaohongshu", {}),
        "next_step": "请在 dashboard 的授权队列里打开小红书二维码，用小红书 App 扫码。扫码完成后点“等待授权完成”。",
    }


def start_bilibili_login_session() -> dict[str, Any]:
    command = f"{shlex.quote(str(PUBLISH_PYTHON))} sau_cli.py bilibili login --account creator"
    result = start_tmux_session(BILIBILI_LOGIN_SESSION, command, PUBLISH_ROOT)
    if result.get("status") == "session_started":
        time.sleep(2)
        run_command([TMUX, "send-keys", "-t", BILIBILI_LOGIN_SESSION, "Down", "Enter"], timeout=5)
    qrcodes = collect_auth_qrcodes()
    deadline = time.time() + 12
    while time.time() < deadline and not qrcodes.get("bilibili", {}).get("exists"):
        time.sleep(1)
        qrcodes = collect_auth_qrcodes()
    return {
        **result,
        "qrcode": qrcodes.get("bilibili", {}),
        "next_step": "请在 dashboard 的授权队列里打开 Bilibili 二维码，用 Bilibili App 扫码。扫码完成后点“等待授权完成”。",
    }


def start_wechat_channels_login_session() -> dict[str, Any]:
    command = [
        str(PUBLISH_PYTHON if PUBLISH_PYTHON.exists() else Path(sys.executable)),
        str(WECHAT_CHANNELS_PUSH),
        "--title",
        "login-only",
        "--login-only",
        "--login-timeout",
        "300",
    ]
    terminal_result = run_in_terminal(command, cwd=WECHAT_CHANNELS_PUSH.parent)
    return {
        "ok": bool(terminal_result.get("ok")),
        "status": "login_terminal_opened" if terminal_result.get("ok") else "login_terminal_failed",
        "session": WECHAT_CHANNELS_LOGIN_SESSION,
        "command": " ".join(shlex.quote(part) for part in command),
        "result": terminal_result,
        "next_step": "已启动视频号登录流程。请在弹出的视频号浏览器页面扫码/确认登录；脚本会自动保存 cookie，完成后点“等待授权完成”。",
    }


def scrub_command_result(result: dict[str, Any]) -> dict[str, Any]:
    scrubbed = dict(result)
    for key in ("stdout", "stderr"):
        if scrubbed.get(key):
            scrubbed[key] = "[redacted]"
    return scrubbed


def import_chrome_auth(payload: dict[str, Any]) -> dict[str, Any]:
    platform = str(payload.get("platform") or "").strip()
    if platform not in {"xiaohongshu", "wechat_channels", "bilibili"}:
        return {
            "ok": False,
            "platform": platform,
            "status": "unsupported_platform",
            "message": "当前只支持把 Chrome 登录态转换成小红书/视频号/Bilibili 使用的账号文件。",
        }
    if not IMPORT_CHROME_COOKIES.exists():
        return {"ok": False, "platform": platform, "status": "import_script_missing", "script": str(IMPORT_CHROME_COOKIES)}

    output = XHS_SAU_ACCOUNT if platform == "xiaohongshu" else WECHAT_CHANNELS_ACCOUNT if platform == "wechat_channels" else BILIBILI_ACCOUNT
    backup = None
    if output.exists():
        backup = output.with_suffix(output.suffix + f".backup-{datetime.now().strftime('%Y%m%d%H%M%S')}")
        shutil.copy2(output, backup)

    python_bin = CONTENT_OPS_PYTHON if CONTENT_OPS_PYTHON.exists() else Path(sys.executable)
    import_result = run_command(
        [
            str(python_bin),
            str(IMPORT_CHROME_COOKIES),
            "--platform",
            platform,
            "--output",
            str(output),
            "--force",
        ],
        cwd=ROOT / "work/content-ops",
        timeout=90,
    )
    try:
        parsed = json.loads(import_result.get("stdout") or "{}")
    except json.JSONDecodeError:
        parsed = {}

    result: dict[str, Any] = {
        "ok": False,
        "platform": platform,
        "status": "chrome_auth_import_failed",
        "account_file": str(output),
        "backup_file": str(backup) if backup else "",
        "import_result": import_result,
        "import_summary": parsed,
    }
    if import_result["returncode"] != 0 or not parsed.get("ok"):
        if backup and backup.exists():
            shutil.copy2(backup, output)
            result["restored_backup"] = True
        elif output.exists():
            output.unlink()
            result["removed_invalid_file"] = True
        result["message"] = parsed.get("message") or "没有可用的 Chrome 登录态，或缺少必要 cookie。"
        return result

    checked = check_channel(platform)
    result["check_result"] = checked
    if checked.get("ok"):
        result.update(
            {
                "ok": True,
                "status": "chrome_auth_imported_and_valid",
                "message": "已复用 Chrome 登录态并通过通道校验；现在可以从内容卡片继续平台动作。",
            }
        )
        return result

    if backup and backup.exists():
        shutil.copy2(backup, output)
        result["restored_backup"] = True
    elif output.exists():
        output.unlink()
        result["removed_invalid_file"] = True
    result.update(
        {
            "status": "chrome_auth_imported_but_invalid",
            "message": "Chrome cookie 已转换，但平台校验没有通过；已避免保留无效账号文件。请使用“准备通道”扫码登录。",
        }
    )
    return result


def run_command(command: list[str], cwd: Path | None = None, timeout: int = 900) -> dict[str, Any]:
    started = time.time()
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
        return {
            "command": command,
            "cwd": str(cwd) if cwd else "",
            "returncode": completed.returncode,
            "stdout": completed.stdout[-8000:],
            "stderr": completed.stderr[-8000:],
            "duration_seconds": round(time.time() - started, 2),
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "command": command,
            "cwd": str(cwd) if cwd else "",
            "returncode": 124,
            "stdout": (exc.stdout or "")[-8000:] if isinstance(exc.stdout, str) else "",
            "stderr": ((exc.stderr or "")[-8000:] if isinstance(exc.stderr, str) else "") + f"\nTimed out after {timeout}s",
            "duration_seconds": round(time.time() - started, 2),
        }


def run_detached(command: list[str]) -> dict[str, Any]:
    try:
        subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
        return {"ok": True, "command": command}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "command": command, "message": str(exc)}


def run_in_terminal(command: list[str], cwd: Path | None = None) -> dict[str, Any]:
    shell_command = " ".join(shlex.quote(part) for part in command)
    if cwd:
        shell_command = f"cd {shlex.quote(str(cwd))} && {shell_command}"
    applescript = f'tell application "Terminal" to do script {json.dumps(shell_command)}'
    return run_detached(["osascript", "-e", applescript])


def ensure_xhs_bridge_server() -> dict[str, Any]:
    bridge_script = XHS_SKILL / "scripts/bridge_server.py"
    if not bridge_script.exists():
        return {"ok": False, "status": "missing_bridge_server", "script": str(bridge_script)}
    has_session = run_command([TMUX, "has-session", "-t", XHS_BRIDGE_SESSION], timeout=5)
    if has_session["returncode"] == 0:
        return {"ok": True, "status": "bridge_session_exists", "session": XHS_BRIDGE_SESSION}
    command = [
        TMUX,
        "new-session",
        "-d",
        "-s",
        XHS_BRIDGE_SESSION,
        f"cd {shlex.quote(str(XHS_SKILL / 'scripts'))} && {shlex.quote(sys.executable)} {shlex.quote(str(bridge_script))}",
    ]
    started = run_command(command, timeout=10)
    return {
        "ok": started["returncode"] == 0,
        "status": "bridge_session_started" if started["returncode"] == 0 else "bridge_session_failed",
        "session": XHS_BRIDGE_SESSION,
        "result": started,
    }


def copy_to_clipboard(text: str) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            ["pbcopy"],
            input=text,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )
        return {
            "ok": completed.returncode == 0,
            "returncode": completed.returncode,
            "stderr": completed.stderr[-1000:],
            "chars": len(text),
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "message": str(exc), "chars": len(text)}


def setup_command_for(platform: str) -> str:
    if platform == "xiaohongshu":
        if PUBLISH_PYTHON.exists() and (PUBLISH_ROOT / "sau_cli.py").exists():
            return (
                f"cd {shlex.quote(str(PUBLISH_ROOT))} && "
                f"{shlex.quote(str(PUBLISH_PYTHON))} sau_cli.py xiaohongshu login --account creator --headed"
            )
        return f"cd {shlex.quote(str(XHS_SKILL / 'scripts'))} && {shlex.quote(sys.executable)} {shlex.quote(str(XHS_CLI))} login"
    if platform == "wechat_mp":
        return f"cd {shlex.quote(str(WECHAT_WORKFLOW))} && npm run bridge:start"
    if platform == "wechat_channels":
        return (
            f"cd {shlex.quote(str(WECHAT_CHANNELS_PUSH.parent))} && "
            f"{shlex.quote(str(PUBLISH_PYTHON if PUBLISH_PYTHON.exists() else Path(sys.executable)))} {shlex.quote(str(WECHAT_CHANNELS_PUSH))} "
            "--title login-only --login-only"
        )
    if platform == "bilibili":
        return (
            f"cd {shlex.quote(str(PUBLISH_ROOT))} && "
            f"{shlex.quote(str(PUBLISH_PYTHON))} sau_cli.py bilibili login --account creator"
        )
    if platform == "youtube":
        return (
            f"cd {shlex.quote(str(ROOT / 'work/content-ops'))} && "
            f"{shlex.quote(str(CONTENT_OPS_PYTHON if CONTENT_OPS_PYTHON.exists() else Path(sys.executable)))} "
            f"{shlex.quote(str(YOUTUBE_CHANNEL))} auth"
        )
    if platform == "x":
        return "open https://x.com/compose/post"
    if platform == "zhihu":
        return "open https://www.zhihu.com/creator"
    return ""


def find_draft_record(platform: str, source_content_id: str, local_id: str = "") -> dict[str, Any] | None:
    platform_dir = DRAFTS / platform
    if not platform_dir.exists():
        return None
    matches: list[dict[str, Any]] = []
    for json_path in sorted(platform_dir.glob("*.json")):
        record = read_json(json_path)
        if not record:
            continue
        if str(record.get("source_content_id") or "") != source_content_id:
            continue
        record_local_id = str(record.get("local_id") or json_path.stem)
        if local_id and local_id not in {record_local_id, json_path.stem}:
            continue
        package_dir = Path(record.get("rendered_package_dir") or json_path.with_suffix(""))
        html_path = Path(record.get("html_preview_path") or json_path.with_suffix(".html"))
        preview_html_path = html_path
        if platform == "wechat_mp":
            wechat_html_path = Path(str(record.get("wechat_html_path") or "")) if record.get("wechat_html_path") else None
            if wechat_html_path and wechat_html_path.exists():
                html_path = wechat_html_path
            else:
                candidate = json_path.with_suffix(".wechat.html")
                if candidate.exists():
                    html_path = candidate
        matches.append(
            {
                "record": record,
                "json_path": json_path,
                "md_path": json_path.with_suffix(".md"),
                "html_path": html_path,
                "preview_html_path": preview_html_path,
                "package_dir": package_dir if package_dir.exists() else None,
                "local_id": record_local_id,
            }
        )
    if not matches:
        return None
    matches.sort(key=lambda item: (item["package_dir"] is not None, item["json_path"].name), reverse=True)
    return matches[0]


def unique_destination(path: Path) -> Path:
    if not path.exists():
        return path
    counter = 2
    while True:
        candidate = path.with_name(f"{path.stem}--{counter}{path.suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


def mark_sent(payload: dict[str, Any]) -> dict[str, Any]:
    platform = str(payload.get("platform") or "")
    source_content_id = str(payload.get("source_content_id") or "")
    local_id = str(payload.get("local_id") or "")
    dry_run = bool(payload.get("dry_run"))
    confirmed = bool(payload.get("confirmed"))
    if platform not in CHANNELS:
        return {"ok": False, "status": "unknown_platform", "platform": platform}
    if not source_content_id:
        raise ValueError("缺少 source_content_id。")
    if not dry_run and not confirmed:
        return {
            "ok": False,
            "status": "confirmation_required",
            "platform": platform,
            "message": "这是本地 outbox 状态变更，会把草稿移到 sent，需要 confirmed=true。",
        }
    draft = find_draft_record(platform, source_content_id, local_id)
    if not draft:
        raise ValueError(f"没有找到对应的 {platform} 草稿 JSON。")
    sent_dir = SENT / platform
    paths: list[Path] = [draft["json_path"]]
    md_path = draft.get("md_path")
    if md_path and md_path.exists():
        paths.append(md_path)
    package_dir = draft.get("package_dir")
    if package_dir and package_dir.exists() and package_dir not in paths:
        paths.append(package_dir)
    moves = []
    for path in paths:
        dest = unique_destination(sent_dir / path.name)
        moves.append({"from": str(path), "to": str(dest), "type": "dir" if path.is_dir() else "file"})
    result = {
        "ok": True,
        "status": "dry_run" if dry_run else "marked_sent",
        "platform": platform,
        "source_content_id": source_content_id,
        "local_id": draft["local_id"],
        "moves": moves,
        "dry_run": dry_run,
        "message": "只更新本地 outbox 状态，不会调用平台发布。",
    }
    if dry_run:
        return result
    sent_dir.mkdir(parents=True, exist_ok=True)
    for move in moves:
        src = Path(move["from"])
        dst = Path(move["to"])
        shutil.move(str(src), str(dst))
    return result


def find_source_asset(source_content_id: str) -> dict[str, Any]:
    assets_path = OUTBOX / ".system/data/assets.json"
    try:
        assets = json.loads(assets_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    for asset in assets:
        if str(asset.get("source_content_id") or "") == source_content_id:
            return asset
    return {}


def platform_label(platform: str) -> str:
    return str((CAPABILITIES.get(platform) or {}).get("label") or platform)


def first_existing(paths: list[str]) -> str:
    for raw in paths:
        path = Path(raw)
        if path.exists():
            return str(path)
    return ""


def ffprobe_media(path: str) -> dict[str, Any]:
    if not FFPROBE or not Path(FFPROBE).exists():
        return {"ok": False, "status": "ffprobe_missing", "message": "找不到 ffprobe。"}
    result = run_command([FFPROBE, "-v", "error", "-show_streams", "-show_format", "-of", "json", path], timeout=60)
    if result["returncode"] != 0:
        return {"ok": False, "status": "ffprobe_failed", "result": scrub_command_result(result)}
    try:
        data = json.loads(result.get("stdout") or "{}")
    except json.JSONDecodeError:
        return {"ok": False, "status": "ffprobe_json_failed", "result": scrub_command_result(result)}
    return {"ok": True, "status": "probed", "data": data}


def is_wechat_compatible_probe(probe: dict[str, Any]) -> tuple[bool, str]:
    streams = ((probe.get("data") or {}).get("streams") or []) if probe.get("ok") else []
    video = next((stream for stream in streams if stream.get("codec_type") == "video"), {})
    audio = next((stream for stream in streams if stream.get("codec_type") == "audio"), {})
    if video.get("codec_name") != "h264":
        return False, f"视频编码是 {video.get('codec_name') or 'unknown'}，需要 H.264。"
    if video.get("pix_fmt") != "yuv420p":
        return False, f"像素格式是 {video.get('pix_fmt') or 'unknown'}，需要 yuv420p。"
    if int(video.get("level") or 0) > 42:
        return False, f"H.264 level 是 {video.get('level')}，视频号网页上传更稳的是 4.2 以内。"
    audio_profile = str(audio.get("profile") or "")
    if audio.get("codec_name") != "aac" or "HE-AAC" in audio_profile:
        return False, f"音频是 {audio.get('codec_name') or 'unknown'} {audio_profile}，需要 AAC-LC。"
    return True, "视频号兼容。"


def ensure_wechat_compatible_video(video: str, source_content_id: str) -> dict[str, Any]:
    source = Path(video)
    if not source.exists():
        return {"ok": False, "status": "source_video_missing", "message": str(source)}
    target = source.with_name("video-wechat-h264-aac.mp4")
    if target.exists() and target.stat().st_mtime >= source.stat().st_mtime:
        probe = ffprobe_media(str(target))
        compatible, reason = is_wechat_compatible_probe(probe)
        if compatible:
            return {"ok": True, "status": "compatible_cached", "video": str(target), "source_video": str(source), "probe": probe, "message": "已使用视频号兼容缓存文件。"}
    source_probe = ffprobe_media(str(source))
    compatible, reason = is_wechat_compatible_probe(source_probe)
    if compatible:
        return {"ok": True, "status": "source_compatible", "video": str(source), "source_video": str(source), "probe": source_probe, "message": reason}
    if not FFMPEG or not Path(FFMPEG).exists():
        return {"ok": False, "status": "ffmpeg_missing", "message": "找不到 ffmpeg，不能生成视频号兼容文件。", "reason": reason}
    tmp = target.with_suffix(".tmp.mp4")
    command = [
        FFMPEG,
        "-y",
        "-i",
        str(source),
        "-map",
        "0:v:0",
        "-map",
        "0:a:0?",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "23",
        "-profile:v",
        "high",
        "-level:v",
        "4.1",
        "-pix_fmt",
        "yuv420p",
        "-r",
        "30",
        "-c:a",
        "aac",
        "-profile:a",
        "aac_low",
        "-b:a",
        "128k",
        "-movflags",
        "+faststart",
        str(tmp),
    ]
    completed = run_command(command, cwd=source.parent, timeout=7200)
    if completed["returncode"] != 0 or not tmp.exists():
        return {
            "ok": False,
            "status": "wechat_transcode_failed",
            "message": "生成视频号兼容文件失败。",
            "reason": reason,
            "run_result": scrub_command_result(completed),
        }
    tmp.replace(target)
    final_probe = ffprobe_media(str(target))
    final_ok, final_reason = is_wechat_compatible_probe(final_probe)
    return {
        "ok": final_ok,
        "status": "compatible_transcoded" if final_ok else "transcoded_but_still_incompatible",
        "video": str(target),
        "source_video": str(source),
        "source_content_id": source_content_id,
        "reason": reason,
        "message": "已生成视频号兼容文件。" if final_ok else final_reason,
        "run_result": scrub_command_result(completed),
        "probe": final_probe,
    }


def xhs_package_from_draft(draft: dict[str, Any]) -> dict[str, Any]:
    package_dir = draft.get("package_dir")
    if not package_dir:
        raise ValueError("这条小红书草稿还没有渲染图文包，不能推送到小红书草稿箱。")
    manifest_path = package_dir / "manifest.json"
    manifest = read_json(manifest_path)
    title_file = Path(manifest.get("title_file") or package_dir / "title.txt")
    content_file = Path(manifest.get("content_file") or package_dir / "content.txt")
    images = [Path(path) for path in manifest.get("images") or sorted((package_dir / "images").glob("*.png"))]
    missing = [path for path in [title_file, content_file, *images] if not path.exists()]
    if missing:
        raise ValueError("小红书图文包缺少文件：" + ", ".join(str(path) for path in missing))
    if not images:
        raise ValueError("小红书图文包没有图片。")
    return {
        "package_dir": package_dir,
        "title_file": title_file,
        "content_file": content_file,
        "images": images,
        "manifest_path": manifest_path,
    }


def push_xhs_draft(payload: dict[str, Any]) -> dict[str, Any]:
    source_content_id = str(payload.get("source_content_id") or "")
    local_id = str(payload.get("local_id") or "")
    dry_run = bool(payload.get("dry_run"))
    if not source_content_id:
        raise ValueError("缺少 source_content_id。")
    if not XHS_CLI.exists():
        raise ValueError(f"找不到 xiaohongshu-skills CLI：{XHS_CLI}")
    draft = find_draft_record("xiaohongshu", source_content_id, local_id)
    if not draft:
        raise ValueError("没有找到对应的小红书草稿 JSON。")
    package = xhs_package_from_draft(draft)
    title = package["title_file"].read_text(encoding="utf-8").strip()
    content = package["content_file"].read_text(encoding="utf-8").strip()
    sau_cmd = [
        str(PUBLISH_PYTHON if PUBLISH_PYTHON.exists() else Path(sys.executable)),
        "sau_cli.py",
        "xiaohongshu",
        "upload-note",
        "--account",
        "creator",
        "--images",
        *[str(path) for path in package["images"]],
        "--title",
        title,
        "--note",
        content,
        "--draft",
    ]
    fill_cmd = [
        sys.executable,
        str(XHS_CLI),
        "fill-publish",
        "--title-file",
        str(package["title_file"]),
        "--content-file",
        str(package["content_file"]),
        "--images",
        *[str(path) for path in package["images"]],
    ]
    save_cmd = [sys.executable, str(XHS_CLI), "save-draft"]
    result = {
        "platform": "xiaohongshu",
        "source_content_id": source_content_id,
        "local_id": draft["local_id"],
        "package_dir": str(package["package_dir"]),
        "commands": [sau_cmd, fill_cmd, save_cmd],
        "dry_run": dry_run,
    }
    if dry_run:
        return {"ok": True, "status": "dry_run", **result}
    if XHS_SAU_ACCOUNT.exists():
        sau_check = run_command(
            [str(PUBLISH_PYTHON if PUBLISH_PYTHON.exists() else Path(sys.executable)), "sau_cli.py", "xiaohongshu", "check", "--account", "creator"],
            cwd=PUBLISH_ROOT,
            timeout=60,
        )
        result["sau_check_result"] = scrub_command_result(sau_check)
        if sau_check["returncode"] == 0:
            sau_upload = run_command(sau_cmd, cwd=PUBLISH_ROOT, timeout=900)
            result["sau_upload_result"] = scrub_command_result(sau_upload)
            if sau_upload["returncode"] == 0:
                return {
                    "ok": True,
                    "status": "draft_saved_in_platform",
                    "safe_channel": "content_toolkit_xiaohongshu_draft",
                    "message": "已通过 content-toolkit 小红书安全草稿模式保存到草稿箱；未点击发布。",
                    **result,
                }
            return {"ok": False, "status": "sau_xhs_draft_failed", **result}
    fill = run_command(fill_cmd, cwd=XHS_SKILL / "scripts")
    result["fill_result"] = fill
    if fill["returncode"] != 0:
        return {"ok": False, "status": "fill_failed", **result}
    save = run_command(save_cmd, cwd=XHS_SKILL / "scripts")
    result["save_result"] = save
    if save["returncode"] != 0:
        return {"ok": False, "status": "save_draft_failed", **result}
    return {"ok": True, "status": "draft_saved_in_platform", **result}


def http_json(method: str, url: str, payload: dict[str, Any] | None = None, timeout: int = 30) -> dict[str, Any]:
    data = None
    headers = {"accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["content-type"] = "application/json"
    request = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - localhost only
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            parsed = {"ok": False, "message": body.strip() or str(exc)}
        parsed.setdefault("ok", False)
        parsed.setdefault("http_status", exc.code)
        return parsed


def ensure_wechat_bridge(dry_run: bool) -> dict[str, Any]:
    health_url = f"{WECHAT_BRIDGE_URL}/api/health"
    try:
        return {"ok": True, "started": False, "health": http_json("GET", health_url, timeout=3)}
    except Exception as first_error:  # noqa: BLE001
        if dry_run:
            return {"ok": False, "started": False, "message": str(first_error)}
        start = run_command(["npm", "run", "bridge:start"], cwd=WECHAT_WORKFLOW, timeout=30)
        deadline = time.time() + 12
        last_error: Exception | None = None
        while time.time() < deadline:
            try:
                return {
                    "ok": True,
                    "started": True,
                    "start_result": start,
                    "health": http_json("GET", health_url, timeout=3),
                }
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                time.sleep(0.5)
        return {
            "ok": False,
            "started": True,
            "start_result": start,
            "message": str(last_error or first_error),
        }


def wechat_payload_from_draft(draft: dict[str, Any], source_content_id: str, style_id: str = "") -> dict[str, Any]:
    record = draft["record"]
    md_path = draft.get("md_path")
    html_path = draft.get("html_path")
    selected_style = style_id or str(record.get("wechat_style") or "professional")
    style_variants = record.get("style_variants") if isinstance(record.get("style_variants"), dict) else {}
    variant = style_variants.get(selected_style) if isinstance(style_variants.get(selected_style), dict) else {}
    variant_html_path = Path(str(variant.get("wechat_html_path") or "")) if variant.get("wechat_html_path") else None
    if variant_html_path and variant_html_path.exists():
        html_path = variant_html_path
    variant_label = str(variant.get("label") or record.get("wechat_style_label") or "简洁专业")
    markdown = ""
    if md_path and md_path.exists():
        markdown = md_path.read_text(encoding="utf-8")
    if not markdown.strip():
        markdown = str(record.get("body") or "")
    content_html = ""
    if html_path and html_path.exists():
        content_html = html_path.read_text(encoding="utf-8")
    title = str(record.get("title") or draft["json_path"].stem).strip()[:64]
    digest = str(record.get("digest") or record.get("summary") or "").strip()
    if not digest:
        digest = "由 Park-IO Outbox 从成熟抖音内容整理生成，待 Wendy 在公众号后台人工审核。"
    asset = find_source_asset(source_content_id)
    record_cover_path = Path(str(variant.get("cover_path") or record.get("cover_path") or "")) if (variant.get("cover_path") or record.get("cover_path")) else None
    cover_path = record_cover_path if record_cover_path and record_cover_path.exists() else first_existing(asset.get("cover_files") or [])
    # Body image src values are relative to the HTML file directory, e.g.
    # "<draft-package>/article-spine.png" from drafts/wechat_mp/.
    # Using rendered_package_dir here duplicates the path segment.
    asset_base_dir = html_path.parent if html_path else None
    return {
        "taskId": f"park-outbox-{draft['local_id']}",
        "title": title,
        "digest": digest[:120],
        "markdown": markdown,
        "html": content_html,
        "htmlPath": str(html_path) if html_path else "",
        "htmlBaseDir": str(html_path.parent) if html_path else "",
        "assetBaseDir": str(asset_base_dir) if asset_base_dir else "",
        "theme": variant_label,
        "wechatStyle": selected_style,
        "coverStyle": "default",
        "coverTitle": title,
        "coverPath": str(cover_path) if cover_path else "",
        "author": "Wendy",
    }


def human_wechat_error(response: dict[str, Any]) -> str:
    kind = str(response.get("kind") or response.get("status") or "")
    message = str(response.get("message") or "")
    mapping = {
        "missing_wechat_config": "公众号 AppID/Secret 配置不完整。",
        "access_token_failed": "公众号 access_token 获取失败。通常是 AppID/Secret、IP 白名单或 VPN 出口 IP 问题。",
        "cover_missing": "本地封面文件不存在或无法读取。",
        "cover_upload_failed": "封面上传到微信素材库失败。",
        "body_image_upload_failed": "正文图片上传到微信素材库失败。通常是本地图片路径不对或图片文件不存在。",
        "draft_create_failed": "微信草稿创建失败。通常是正文 HTML、标题长度、封面素材或微信接口限制问题。",
        "empty_content": "公众号正文为空，没有可推送内容。",
    }
    prefix = mapping.get(kind)
    if prefix and message:
        return f"{prefix}原始错误：{message}"
    return prefix or message or "公众号草稿推送失败。"


def capture_wechat_mp_preview_evidence(draft: dict[str, Any], source_content_id: str, html_path: Path | None = None, style_id: str = "") -> dict[str, Any]:
    html_path = html_path or draft.get("html_path")
    if not (html_path and html_path.exists()):
        return {"ok": False, "message": "缺少公众号 HTML 证据源。"}
    evidence_dir = EVIDENCE_DIR / source_content_id
    evidence_dir.mkdir(parents=True, exist_ok=True)
    suffix = f"_{style_id}" if style_id else ""
    output = evidence_dir / f"wechat_mp_draft_payload{suffix}_{datetime.now().strftime('%Y%m%d-%H%M%S')}.png"
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 900, "height": 1200}, device_scale_factor=1)
            page.goto(html_path.resolve().as_uri(), wait_until="networkidle")
            page.screenshot(path=str(output), full_page=True)
            browser.close()
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "message": str(exc)}
    return {"ok": True, "path": str(output), "href": evidence_href(output)}


def update_wechat_draft_push_record(
    draft: dict[str, Any],
    source_content_id: str,
    response: dict[str, Any],
    evidence: dict[str, Any],
    style_id: str = "professional",
    style_label: str = "简洁专业",
) -> None:
    json_path = draft.get("json_path")
    if not (json_path and json_path.exists()):
        return
    record = read_json(json_path) or {}
    pushed_at = response.get("publishedAt") or now_iso()
    record["status"] = "draft_pushed"
    record["latest_platform_draft"] = {
        "platform": "wechat_mp",
        "draft_id": response.get("draftId") or "",
        "pushed_at": pushed_at,
        "title": (response.get("debug") or {}).get("titleApplied") or record.get("title") or "",
        "style_id": style_id,
        "style_label": style_label,
        "thumb_media_id": (response.get("debug") or {}).get("thumbMediaId") or "",
        "uploaded_media_urls": (response.get("debug") or {}).get("uploadedMediaUrls") or [],
        "evidence_screenshot": evidence.get("path") or "",
        "evidence_screenshot_href": evidence.get("href") or "",
    }
    history = record.get("platform_draft_history")
    if not isinstance(history, list):
        history = []
    history.append(record["latest_platform_draft"])
    record["platform_draft_history"] = history[-10:]
    record["last_push_status"] = "ok"
    record["last_push_message"] = response.get("message") or "已推送到公众号草稿箱。"
    record["last_pushed_at"] = pushed_at
    json_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")


def push_wechat_mp_draft(payload: dict[str, Any]) -> dict[str, Any]:
    source_content_id = str(payload.get("source_content_id") or "")
    local_id = str(payload.get("local_id") or "")
    style_id = str(payload.get("wechat_style") or payload.get("style_id") or "professional")
    dry_run = bool(payload.get("dry_run"))
    if not source_content_id:
        raise ValueError("缺少 source_content_id。")
    draft = find_draft_record("wechat_mp", source_content_id, local_id)
    if not draft:
        raise ValueError("没有找到对应的公众号草稿 JSON。")
    wechat_payload = wechat_payload_from_draft(draft, source_content_id, style_id)
    pushed_html_path = Path(wechat_payload["htmlPath"]) if wechat_payload.get("htmlPath") else draft.get("html_path")
    result = {
        "platform": "wechat_mp",
        "source_content_id": source_content_id,
        "local_id": draft["local_id"],
        "bridge_url": f"{WECHAT_BRIDGE_URL}/api/publish/wechat-draft",
        "payload": {key: value for key, value in wechat_payload.items() if key != "markdown"},
        "markdown_chars": len(wechat_payload.get("markdown") or ""),
        "dry_run": dry_run,
    }
    if dry_run:
        bridge = ensure_wechat_bridge(dry_run=True)
        return {"ok": True, "status": "dry_run", "bridge": bridge, **result}
    bridge = ensure_wechat_bridge(dry_run=False)
    result["bridge"] = bridge
    if not bridge.get("ok"):
        return {"ok": False, "status": "wechat_bridge_unavailable", **result}
    try:
        response = http_json("POST", f"{WECHAT_BRIDGE_URL}/api/publish/wechat-draft", wechat_payload, timeout=180)
    except URLError as exc:
        return {"ok": False, "status": "wechat_bridge_request_failed", "message": str(exc), **result}
    result["wechat_response"] = response
    if not response.get("ok"):
        return {
            "ok": False,
            "status": response.get("kind") or "wechat_draft_failed",
            "message": human_wechat_error(response),
            **result,
        }
    evidence = capture_wechat_mp_preview_evidence(draft, source_content_id, pushed_html_path, style_id)
    result["evidence"] = evidence
    update_wechat_draft_push_record(draft, source_content_id, response, evidence, style_id, str(wechat_payload.get("theme") or "简洁专业"))
    return {"ok": True, "status": "draft_saved_in_platform", "message": response.get("message") or "已推送到公众号草稿箱。", **result}



def push_wechat_channels_draft(payload: dict[str, Any]) -> dict[str, Any]:
    source_content_id = str(payload.get("source_content_id") or "")
    local_id = str(payload.get("local_id") or "")
    dry_run = bool(payload.get("dry_run"))
    publish_mode = str(payload.get("publish_mode") or "draft")
    if not source_content_id:
        raise ValueError("缺少 source_content_id。")
    draft = find_draft_record("wechat_channels", source_content_id, local_id)
    if not draft:
        raise ValueError("没有找到对应的视频号草稿 JSON。")
    record = draft["record"]
    asset = find_source_asset(source_content_id)
    video = first_existing(asset.get("media_files") or [])
    if not video:
        raise ValueError("没有找到对应的原视频文件。")
    video_prepare: dict[str, Any] | None = None
    if publish_mode == "public":
        video_prepare = ensure_wechat_compatible_video(video, source_content_id)
        if not video_prepare.get("ok"):
            return {
                "ok": False,
                "status": video_prepare.get("status") or "wechat_video_prepare_failed",
                "platform": "wechat_channels",
                "source_content_id": source_content_id,
                "local_id": draft["local_id"],
                "video": video,
                "video_prepare": video_prepare,
                "message": video_prepare.get("message") or "视频号兼容视频准备失败。",
            }
        video = str(video_prepare.get("video") or video)
    title = str(record.get("title") or draft["json_path"].stem).strip()
    description = str(record.get("body") or record.get("description") or "")
    command = [
        str(PUBLISH_PYTHON if PUBLISH_PYTHON.exists() else Path(sys.executable)),
        str(WECHAT_CHANNELS_PUSH),
        "--title",
        title,
        "--description",
        description,
        "--video",
        video,
    ]
    if publish_mode == "public":
        command.append("--publish")
    result = {
        "platform": "wechat_channels",
        "source_content_id": source_content_id,
        "local_id": draft["local_id"],
        "video": video,
        "source_video": str((video_prepare or {}).get("source_video") or video),
        "video_prepare": video_prepare,
        "command": command,
        "dry_run": dry_run,
        "publish_mode": publish_mode,
    }
    if dry_run:
        return {"ok": True, "status": "dry_run", **result}
    completed = run_command(command, cwd=WECHAT_CHANNELS_PUSH.parent, timeout=1800)
    result["run_result"] = completed
    if completed["returncode"] != 0:
        combined = f"{completed.get('stdout') or ''}\n{completed.get('stderr') or ''}".strip()
        if "不支持此视频格式" in combined or "H.264" in combined:
            status = "wechat_video_format_rejected"
            message = "视频号拒绝当前视频格式，需要 H.264/AAC 兼容文件；系统会优先使用 media/video-wechat-h264-aac.mp4。"
        elif "登录" in combined or "cookie" in combined.lower():
            status = "wechat_channels_login_required"
            message = "视频号登录态失效，请重新扫码登录后重试。"
        else:
            status = "wechat_channels_publish_failed" if publish_mode == "public" else "wechat_channels_draft_failed"
            message = "视频号发布失败，请查看错误详情。"
        return {"ok": False, "status": status, "message": message, **result}
    return {
        "ok": True,
        "status": "published" if publish_mode == "public" else "draft_saved_in_platform",
        "message": "已提交公开视频号发布。" if publish_mode == "public" else "已保存到视频号草稿箱。",
        **result,
    }


def platform_handoff_text(platform: str, draft: dict[str, Any], source_content_id: str) -> str:
    record = draft["record"]
    asset = find_source_asset(source_content_id)
    title = str(record.get("title") or draft["json_path"].stem).strip()
    body = str(record.get("body") or record.get("description") or "").strip()
    video = first_existing(asset.get("media_files") or [])
    source_url = str(record.get("source_url") or asset.get("source_url") or "")
    if platform in {"bilibili", "youtube"}:
        return "\n".join(
            [
                f"标题：{title}",
                "",
                "简介：",
                body,
                "",
                f"视频文件：{video}",
                f"来源抖音：{source_url}",
                "",
                "注意：当前工作台只准备填稿材料，不点击发布。",
            ]
        )
    if platform == "x":
        text = body or title
        text = text.replace("标题：", "").strip()
        if len(text) > 260:
            text = text[:257].rstrip() + "..."
        return text
    if platform == "zhihu":
        return "\n".join(
            [
                f"# {title}",
                "",
                body,
                "",
                f"来源抖音：{source_url}",
                "",
                "注意：当前工作台只准备知乎草稿材料，不点击发布。",
            ]
        )
    return body or title


def handoff_video_file(platform: str, source_content_id: str) -> str:
    if platform not in {"bilibili", "youtube"}:
        return ""
    asset = find_source_asset(source_content_id)
    return first_existing(asset.get("media_files") or [])


def verify_youtube_public_video(video_id: str, title: str = "") -> dict[str, Any]:
    url = f"https://www.youtube.com/watch?v={quote(video_id)}"
    last_error = ""
    for _ in range(6):
        try:
            request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urlopen(request, timeout=20) as response:
                html = response.read(700_000).decode("utf-8", errors="replace")
            unavailable = "Video unavailable" in html or "This video isn't available" in html
            too_long = "video is too long" in html.lower() or "too long" in html.lower()
            title_ok = bool(title and title[:60] in html) or bool(video_id and video_id in html)
            if unavailable or too_long:
                return {
                    "ok": False,
                    "status": "youtube_too_long" if too_long else "youtube_unavailable",
                    "url": url,
                    "message": "YouTube 已上传但公开视频不可用，可能仍受长视频权限、处理或版权限制影响。",
                }
            if title_ok:
                return {"ok": True, "status": "verified_public", "url": url, "message": "YouTube 公开视频页已验证。"}
            last_error = "公开视频页已打开，但没有验证到标题。"
        except URLError as exc:
            last_error = str(exc)
        except OSError as exc:
            last_error = str(exc)
        time.sleep(10)
    return {"ok": False, "status": "public_unverified", "url": url, "message": last_error or "YouTube 公开视频暂未验证成功。"}


def preflight_platform(platform: str, source_content_id: str) -> dict[str, Any]:
    asset = find_source_asset(source_content_id)
    draft = find_draft_record(platform, source_content_id)
    media_file = first_existing(asset.get("media_files") or [])
    cover_file = first_existing(asset.get("cover_files") or [])
    channel = check_channel(platform)
    checks: list[dict[str, Any]] = []
    checks.append({"name": "local_draft", "ok": bool(draft), "message": "找到本地草稿" if draft else "缺本地草稿"})
    if platform in VIDEO_MIGRATION_CHANNELS:
        content_type = str(asset.get("content_type") or "")
        if content_type == "gallery":
            checks.append({"name": "source_video", "ok": False, "message": "源内容是图文，不适合视频迁移"})
        else:
            checks.append({"name": "source_video", "ok": bool(media_file), "message": media_file or "缺原视频文件"})
    if platform == "xiaohongshu" and draft:
        try:
            package = xhs_package_from_draft(draft)
            checks.append(
                {
                    "name": "xhs_rendered_package",
                    "ok": True,
                    "message": str(package["package_dir"]),
                    "image_count": len(package["images"]),
                }
            )
        except Exception as exc:  # noqa: BLE001
            checks.append({"name": "xhs_rendered_package", "ok": False, "message": str(exc)})
    if platform == "wechat_mp" and draft:
        md_path = draft.get("md_path")
        checks.append({"name": "markdown", "ok": bool(md_path and md_path.exists()), "message": str(md_path or "")})
    if platform == "bilibili":
        checks.append(
            {
                "name": "channel_ready",
                "ok": bool(channel.get("ok")),
                "message": channel.get("status") or "",
                "channel": channel,
            }
        )
    elif platform in {"x", "zhihu"}:
        checks.append(
            {
                "name": "handoff_available",
                "ok": True,
                "message": channel.get("safe_mode") or channel.get("status") or "handoff",
                "channel": channel,
            }
        )
    elif platform == "youtube":
        checks.append(
            {
                "name": "channel_ready",
                "ok": bool(channel.get("ok")),
                "message": channel.get("status") or "",
                "channel": channel,
            }
        )
    else:
        checks.append(
            {
                "name": "channel_ready",
                "ok": bool(channel.get("ok")),
                "message": channel.get("status") or "",
                "channel": channel,
            }
        )
    ready = all(item.get("ok") for item in checks)
    if platform in {"x", "zhihu"}:
        ready = bool(draft)
    mode = "draft_push" if platform in {"xiaohongshu", "wechat_mp", "wechat_channels"} else "self_only_upload" if platform == "bilibili" else "private_upload" if platform == "youtube" else "handoff"
    return {
        "platform": platform,
        "label": platform_label(platform),
        "ready": ready,
        "mode": mode,
        "local_id": draft["local_id"] if draft else "",
        "draft_json": str(draft["json_path"]) if draft else "",
        "draft_md": str(draft["md_path"]) if draft and draft.get("md_path") and draft["md_path"].exists() else "",
        "media_file": media_file,
        "cover_file": cover_file,
        "checks": checks,
    }


def preflight_source(payload: dict[str, Any]) -> dict[str, Any]:
    source_content_id = str(payload.get("source_content_id") or "")
    if not source_content_id:
        raise ValueError("缺少 source_content_id。")
    asset = find_source_asset(source_content_id)
    if not asset:
        raise ValueError(f"没有找到源内容：{source_content_id}")
    platforms = payload.get("platforms") or CHANNELS
    if isinstance(platforms, str):
        platforms = [platforms]
    items = [preflight_platform(str(platform), source_content_id) for platform in platforms if str(platform) in CHANNELS]
    return {
        "ok": True,
        "status": "preflight_checked",
        "source_content_id": source_content_id,
        "title": asset.get("title") or "",
        "content_type": asset.get("content_type") or "",
        "ready_count": sum(1 for item in items if item.get("ready")),
        "needs_work_count": sum(1 for item in items if not item.get("ready")),
        "platforms": items,
    }


def handoff_platform(payload: dict[str, Any]) -> dict[str, Any]:
    platform = str(payload.get("platform") or "")
    source_content_id = str(payload.get("source_content_id") or "")
    local_id = str(payload.get("local_id") or "")
    dry_run = bool(payload.get("dry_run"))
    if platform not in {"bilibili", "youtube", "x", "zhihu"}:
        return unsupported_platform_response(platform, payload)
    if not source_content_id:
        raise ValueError("缺少 source_content_id。")
    draft = find_draft_record(platform, source_content_id, local_id)
    if not draft:
        raise ValueError(f"没有找到对应的 {platform} 草稿 JSON。")
    video = handoff_video_file(platform, source_content_id)
    if platform in {"bilibili", "youtube"} and not video:
        return {
            "ok": False,
            "status": "source_video_missing",
            "platform": platform,
            "source_content_id": source_content_id,
            "local_id": draft["local_id"],
            "message": f"{platform} 是视频迁移平台，但这条源内容没有本地视频文件；请先补齐 sent/douyin 下的 media/video.mp4。",
            "platform_url": PLATFORM_URLS.get(platform, ""),
        }
    handoff_text = platform_handoff_text(platform, draft, source_content_id)
    url = PLATFORM_URLS.get(platform, "")
    if platform == "x":
        url = f"https://x.com/intent/tweet?text={quote(handoff_text)}"
    result = {
        "ok": True,
        "status": "handoff_dry_run" if dry_run else "handoff_prepared",
        "platform": platform,
        "source_content_id": source_content_id,
        "local_id": draft["local_id"],
        "platform_url": url,
        "video": video,
        "clipboard_chars": len(handoff_text),
        "message": "已准备平台填稿材料；不会最终发布。" if not dry_run else "dry-run: 可准备平台填稿材料。",
    }
    if dry_run:
        result["clipboard_preview"] = handoff_text[:1200]
        return result
    result["clipboard"] = copy_to_clipboard(handoff_text)
    result["open_result"] = run_detached(["open", url]) if url else {"ok": False, "message": "missing url"}
    if video:
        result["reveal_video_result"] = run_detached(["open", "-R", video])
    return result


def push_youtube_upload(payload: dict[str, Any]) -> dict[str, Any]:
    source_content_id = str(payload.get("source_content_id") or "")
    local_id = str(payload.get("local_id") or "")
    dry_run = bool(payload.get("dry_run"))
    privacy_status = str(payload.get("privacy_status") or payload.get("publish_mode") or "private")
    if privacy_status not in {"public", "private", "unlisted"}:
        privacy_status = "private"
    if not source_content_id:
        raise ValueError("缺少 source_content_id。")
    draft = find_draft_record("youtube", source_content_id, local_id)
    if not draft:
        raise ValueError("没有找到对应的 YouTube 草稿 JSON。")
    video = handoff_video_file("youtube", source_content_id)
    if not video:
        return {
            "ok": False,
            "status": "source_video_missing",
            "platform": "youtube",
            "source_content_id": source_content_id,
            "local_id": draft["local_id"],
            "message": "YouTube 是视频迁移平台，但这条源内容没有本地视频文件；请先补齐 sent/douyin 下的 media/video.mp4。",
            "platform_url": PLATFORM_URLS["youtube"],
        }
    python_bin = CONTENT_OPS_PYTHON if CONTENT_OPS_PYTHON.exists() else Path(sys.executable)
    command = [
        str(python_bin),
        str(YOUTUBE_CHANNEL),
        "upload",
        "--video",
        video,
        "--draft-json",
        str(draft["json_path"]),
        "--privacy-status",
        privacy_status,
    ]
    if dry_run:
        command.append("--dry-run")
    run = run_command(command, cwd=ROOT / "work/content-ops", timeout=1800)
    try:
        parsed = json.loads(run.get("stdout") or "{}")
    except json.JSONDecodeError:
        parsed = {}
    ok = run["returncode"] == 0 and bool(parsed.get("ok"))
    verified = None
    if ok and privacy_status == "public" and parsed.get("video_id"):
        verified = verify_youtube_public_video(str(parsed.get("video_id")), str((draft["record"].get("title") or "").strip()))
        if verified.get("ok"):
            parsed["status"] = "verified_public"
            parsed["url"] = verified.get("url") or parsed.get("url")
        elif verified.get("status") in {"youtube_unavailable", "youtube_too_long"}:
            ok = False
    result = {
        "ok": ok,
        "status": parsed.get("status") or (f"{privacy_status}_uploaded" if ok else "youtube_upload_failed"),
        "platform": "youtube",
        "source_content_id": source_content_id,
        "local_id": draft["local_id"],
        "video": video,
        "draft_json": str(draft["json_path"]),
        "result": parsed or run,
        "platform_url": parsed.get("url") or PLATFORM_URLS["youtube"],
        "message": parsed.get("message") or ("已公开发布到 YouTube。" if ok and privacy_status == "public" else f"YouTube {privacy_status} 上传未完成，请查看 result。"),
        "privacy_status": privacy_status,
    }
    if verified is not None:
        result["verification"] = verified
        if not ok:
            result["message"] = verified.get("message") or result["message"]
    if parsed.get("video_id"):
        result["video_id"] = parsed.get("video_id")
    return result


def push_youtube_private_upload(payload: dict[str, Any]) -> dict[str, Any]:
    payload = {**payload, "privacy_status": "private"}
    return push_youtube_upload(payload)


def push_bilibili_upload(payload: dict[str, Any]) -> dict[str, Any]:
    source_content_id = str(payload.get("source_content_id") or "")
    local_id = str(payload.get("local_id") or "")
    dry_run = bool(payload.get("dry_run"))
    publish_mode = str(payload.get("publish_mode") or "self_only")
    only_self = bool(payload.get("only_self")) or publish_mode != "public"
    if not source_content_id:
        raise ValueError("缺少 source_content_id。")
    draft = find_draft_record("bilibili", source_content_id, local_id)
    if not draft:
        raise ValueError("没有找到对应的 Bilibili 草稿 JSON。")
    asset = find_source_asset(source_content_id)
    video = first_existing(asset.get("media_files") or [])
    cover = first_existing(asset.get("cover_files") or [])
    if not video:
        return {
            "ok": False,
            "status": "source_video_missing",
            "platform": "bilibili",
            "source_content_id": source_content_id,
            "local_id": draft["local_id"],
            "message": "Bilibili 是视频迁移平台，但这条源内容没有本地视频文件；请先补齐 sent/douyin 下的 media/video.mp4。",
            "platform_url": PLATFORM_URLS["bilibili"],
        }
    record = draft["record"]
    title = str(record.get("title") or draft["json_path"].stem).strip()
    desc = str(record.get("body") or record.get("description") or "").strip()
    tags_value = record.get("tags") or ["AI", "人工智能", "一人公司"]
    if isinstance(tags_value, list):
        tags = ",".join(str(tag).strip().lstrip("#") for tag in tags_value if str(tag).strip())
    else:
        tags = str(tags_value)
    python_bin = PUBLISH_PYTHON if PUBLISH_PYTHON.exists() else Path(sys.executable)
    if only_self:
        command = [
            str(python_bin),
            "sau_cli.py",
            "bilibili",
            "upload-video",
            "--account",
            "creator",
            "--file",
            video,
            "--title",
            title,
            "--desc",
            desc,
            "--tid",
            str(int(record.get("tid") or BILIBILI_DEFAULT_TID)),
            "--tags",
            tags,
            "--only-self",
        ]
        if cover:
            command.extend(["--cover", cover])
    else:
        command = [
            str(python_bin),
            str(BILIBILI_WEB_UPLOAD),
            "--headless",
            "upload",
            "--video",
            video,
            "--title",
            title,
            "--description",
            desc,
            "--tags",
            tags,
        ]
    result = {
        "platform": "bilibili",
        "source_content_id": source_content_id,
        "local_id": draft["local_id"],
        "video": video,
        "cover": cover,
        "draft_json": str(draft["json_path"]),
        "command": command,
        "dry_run": dry_run,
        "publish_mode": "self_only" if only_self else "public",
        "platform_url": PLATFORM_URLS["bilibili"],
    }
    if dry_run:
        return {
            "ok": True,
            "status": "self_only_upload_dry_run" if only_self else "public_upload_dry_run",
            "message": "dry-run: 可上传为 Bilibili 公开投稿。" if not only_self else "dry-run: 可上传为 Bilibili 仅自己可见视频；不会公开发布。",
            **result,
        }
    completed = run_command(command, cwd=PUBLISH_ROOT if only_self else BILIBILI_WEB_UPLOAD.parent, timeout=3600)
    result["run_result"] = completed
    parsed: dict[str, Any] = {}
    try:
        parsed = json.loads(completed.get("stdout") or "{}")
    except json.JSONDecodeError:
        parsed = {}
    if completed["returncode"] != 0:
        status = parsed.get("status") or "bilibili_upload_failed"
        messages = {
            "login_required": "Bilibili 登录态失效，请重新登录后重试。",
            "cookie_missing": "缺少 Bilibili cookie 文件，请先登录 Bilibili。",
            "declaration_required": "Bilibili 要求选择创作声明，自动选择失败。",
            "upload_timeout": "Bilibili 上传超时，请检查网络或视频文件。",
            "submit_not_confirmed": "Bilibili 没有确认投稿成功，请查看页面提示。",
            "not_found_in_manager": "Bilibili 页面提示投递后，稿件管理页没有验证到标题。",
        }
        return {
            "ok": False,
            "status": status,
            "message": parsed.get("message") or messages.get(status, "Bilibili 上传失败。"),
            "parsed_result": parsed,
            **result,
        }
    if not only_self:
        ok = bool(parsed.get("ok"))
        return {
            **result,
            "ok": ok,
            "status": parsed.get("status") or ("submitted_review" if ok else "bilibili_upload_failed"),
            "message": parsed.get("message") or ("已提交 Bilibili，当前进入转码/审核流程。" if ok else "Bilibili 投稿未完成。"),
            "parsed_result": parsed,
            "platform_url": parsed.get("platform_url") or PLATFORM_URLS["bilibili"],
        }
    return {
        "ok": True,
        "status": "self_only_uploaded",
        "message": "已上传为 Bilibili 仅自己可见视频；请到创作中心检查后手动发布。",
        **result,
    }


def push_bilibili_self_only_upload(payload: dict[str, Any]) -> dict[str, Any]:
    payload = {**payload, "publish_mode": "self_only", "only_self": True}
    return push_bilibili_upload(payload)


def video_migration_platform_status(platform: str, source_content_id: str) -> dict[str, Any]:
    persisted = persisted_video_migration_platform(source_content_id, platform)
    if persisted.get("ok") and persisted.get("stage") in {"published", "submitted_review"}:
        return {
            **persisted,
            "platform": platform,
            "label": platform_label(platform),
            "message": persisted.get("message") or "已完成，下一次不会重复上传。",
        }
    asset = find_source_asset(source_content_id)
    if not asset:
        return {
            "platform": platform,
            "label": platform_label(platform),
            "ok": False,
            "stage": "failed",
            "status": "source_missing",
            "message": f"没有找到源内容：{source_content_id}",
        }
    media_file = first_existing(asset.get("media_files") or [])
    if str(asset.get("content_type") or "") == "gallery":
        return {
            "platform": platform,
            "label": platform_label(platform),
            "ok": False,
            "stage": "blocked",
            "status": "source_gallery",
            "message": "这条抖音是图文源，不进入视频搬运。",
        }
    if not media_file:
        return {
            "platform": platform,
            "label": platform_label(platform),
            "ok": False,
            "stage": "blocked",
            "status": "source_video_missing",
            "message": "缺少本地视频文件。",
        }
    video_prepare: dict[str, Any] | None = None
    if platform == "wechat_channels":
        video_prepare = ensure_wechat_compatible_video(media_file, source_content_id)
        if not video_prepare.get("ok"):
            return {
                "platform": platform,
                "label": platform_label(platform),
                "ok": False,
                "stage": "blocked",
                "status": video_prepare.get("status") or "wechat_video_prepare_failed",
                "message": video_prepare.get("message") or "视频号兼容视频准备失败。",
                "media_file": media_file,
                "video_prepare": video_prepare,
            }
        media_file = str(video_prepare.get("video") or media_file)
    channel = check_channel(platform)
    draft = find_draft_record(platform, source_content_id)
    return {
        "platform": platform,
        "label": platform_label(platform),
        "ok": bool(channel.get("ok")),
        "stage": "connected" if channel.get("ok") else "needs_login",
        "status": channel.get("status") or "unchecked",
        "message": "已连接，可以公开发布。" if channel.get("ok") else channel.get("next_step") or "需要登录或授权。",
        "channel": channel,
        "media_file": media_file,
        "video_prepare": video_prepare,
        "local_id": draft["local_id"] if draft else "",
    }


def video_migration_status(payload: dict[str, Any]) -> dict[str, Any]:
    source_content_id = str(payload.get("source_content_id") or "")
    if not source_content_id:
        return {"ok": False, "status": "missing_source_content_id", "message": "缺少 source_content_id。"}
    asset = find_source_asset(source_content_id)
    if not asset:
        return {"ok": False, "status": "source_missing", "source_content_id": source_content_id, "message": f"没有找到源内容：{source_content_id}"}
    platforms = [video_migration_platform_status(platform, source_content_id) for platform in VIDEO_MIGRATION_ORDER]
    blocked = [item for item in platforms if item.get("stage") == "blocked"]
    needs_login = [item for item in platforms if item.get("stage") == "needs_login"]
    done = [item for item in platforms if item.get("ok") and item.get("stage") in {"published", "submitted_review"}]
    return {
        "ok": not blocked and not needs_login,
        "status": "published" if len(done) == len(VIDEO_MIGRATION_ORDER) else "ready" if not blocked and not needs_login else "blocked" if blocked else "needs_login",
        "source_content_id": source_content_id,
        "title": asset.get("title") or "",
        "publish_mode": "public",
        "platforms": platforms,
    }


def ensure_video_migration_draft(platform: str, source_content_id: str) -> dict[str, Any]:
    draft = find_draft_record(platform, source_content_id)
    if draft:
        return {"ok": True, "status": "local_draft_ready", "local_id": draft["local_id"], "draft_json": str(draft["json_path"])}
    generated = generate_local_draft({"platform": platform, "source_content_id": source_content_id, "confirmed": True})
    draft = find_draft_record(platform, source_content_id)
    if draft:
        return {"ok": True, "status": "local_draft_generated", "local_id": draft["local_id"], "draft_json": str(draft["json_path"]), "generate_result": generated}
    return {"ok": False, "status": "local_draft_missing", "message": generated.get("message") or "本地草稿生成失败。", "generate_result": generated}


def push_video_migration_platform(platform: str, source_content_id: str, local_id: str) -> dict[str, Any]:
    payload = {
        "platform": platform,
        "source_content_id": source_content_id,
        "local_id": local_id,
        "confirmed": True,
        "publish_mode": "public",
    }
    if platform == "wechat_channels":
        return push_wechat_channels_draft(payload)
    if platform == "bilibili":
        return push_bilibili_upload(payload)
    if platform == "youtube":
        return push_youtube_upload({**payload, "privacy_status": "public"})
    return unsupported_platform_response(platform, payload)


def run_video_migration(payload: dict[str, Any]) -> dict[str, Any]:
    source_content_id = str(payload.get("source_content_id") or "")
    confirmed = bool(payload.get("confirmed"))
    if not source_content_id:
        return {"ok": False, "status": "missing_source_content_id", "message": "缺少 source_content_id。"}
    if not confirmed:
        return {
            "ok": False,
            "status": "confirmation_required",
            "source_content_id": source_content_id,
            "message": "这是公开发布到 视频号 / Bilibili / YouTube 的动作，需要 confirmed=true。",
        }
    status = video_migration_status({"source_content_id": source_content_id})
    results: list[dict[str, Any]] = []
    status_platforms = status.get("platforms") or []
    needs_login_states = [item for item in status_platforms if item.get("stage") == "needs_login"]
    blocked_states = [item for item in status_platforms if item.get("stage") == "blocked"]
    if needs_login_states or blocked_states:
        for platform_state in status_platforms:
            platform = str(platform_state.get("platform") or "")
            if platform_state.get("stage") == "needs_login":
                results.append(
                    {
                        **platform_state,
                        "ok": False,
                        "stage": "needs_login",
                        "status": platform_state.get("status") or "needs_login",
                        "message": platform_state.get("message") or f"需要先完成{platform_label(platform)}登录授权。",
                        "next_action": f"请先完成{platform_label(platform)}登录授权，然后重新点击一键公开发布。",
                    }
                )
            elif platform_state.get("stage") == "blocked":
                results.append({**platform_state, "ok": False, "stage": "blocked"})
            else:
                results.append(
                    {
                        **platform_state,
                        "stage": "connected",
                        "status": platform_state.get("status") or "connected",
                        "message": "已连接，等待其他平台登录完成后再统一公开发布。",
                    }
                )
        result = {
            "ok": False,
            "status": "needs_login" if needs_login_states else "blocked",
            "source_content_id": source_content_id,
            "publish_mode": "public",
            "platforms": results,
            "message": "需要先完成平台登录；为避免部分平台误发，本次没有开始上传。",
        }
        write_log({"action": "video_migration_batch", "request": payload, "result": result})
        return result

    waiting_auth = False
    for platform_state in status_platforms:
        platform = str(platform_state.get("platform") or "")
        if platform_state.get("ok") and platform_state.get("stage") in {"published", "submitted_review"}:
            results.append(
                {
                    **platform_state,
                    "stage": platform_state.get("stage") or "published",
                    "status": platform_state.get("status") or "published",
                    "message": platform_state.get("message") or "已完成，跳过重复上传。",
                }
            )
            continue
        if platform_state.get("stage") == "blocked":
            results.append({**platform_state, "ok": False, "stage": "blocked"})
            continue
        if platform_state.get("stage") == "needs_login":
            results.append(
                {
                    **platform_state,
                    "ok": False,
                    "stage": "needs_login",
                    "status": platform_state.get("status") or "needs_login",
                    "message": platform_state.get("message") or f"需要先完成{platform_label(platform)}登录授权。",
                    "next_action": f"请先完成{platform_label(platform)}登录授权，然后重新点击一键公开发布。",
                }
            )
            waiting_auth = True
            continue
        draft = ensure_video_migration_draft(platform, source_content_id)
        if not draft.get("ok"):
            results.append(
                {
                    **platform_state,
                    "ok": False,
                    "stage": "failed",
                    "status": draft.get("status") or "local_draft_failed",
                    "message": draft.get("message") or "本地草稿未生成。",
                    "draft_result": draft,
                }
            )
            continue
        try:
            published = push_video_migration_platform(platform, source_content_id, str(draft.get("local_id") or ""))
        except Exception as exc:  # noqa: BLE001
            published = {"ok": False, "status": "error", "platform": platform, "message": str(exc)}
        published = capture_video_migration_evidence(source_content_id, platform, published)
        update_video_migration_state(source_content_id, platform, published)
        results.append(
            {
                **platform_state,
                "ok": bool(published.get("ok")),
                "stage": "submitted_review" if published.get("ok") and published.get("status") in {"submitted_review", "found_in_manager"} else "published" if published.get("ok") else "failed",
                "status": published.get("status") or ("published" if published.get("ok") else "failed"),
                "message": published.get("message") or ("已公开发布。" if published.get("ok") else "发布失败。"),
                "local_id": draft.get("local_id") or "",
                "result": published,
                "platform_url": published.get("platform_url") or published.get("url") or PLATFORM_URLS.get(platform, ""),
                "video_id": published.get("video_id") or "",
            }
        )
    ok = bool(results) and all(item.get("ok") for item in results)
    final_status = "published" if ok else "waiting_auth" if waiting_auth else "partial_failed"
    result = {
        "ok": ok,
        "status": final_status,
        "source_content_id": source_content_id,
        "publish_mode": "public",
        "platforms": results,
        "message": "三个平台已提交；YouTube 为公开视频，视频号/Bilibili 可能处于审核或转码中。" if ok else "部分平台需要登录或发布失败，请看各平台卡片。",
    }
    write_log({"action": "video_migration_batch", "request": payload, "result": result})
    return result


def check_channel(platform: str) -> dict[str, Any]:
    capability = CAPABILITIES.get(platform)
    if not capability:
        return {"ok": False, "platform": platform, "status": "unknown_platform"}
    if platform == "xiaohongshu":
        if not XHS_CLI.exists():
            return {"ok": False, "platform": platform, "status": "missing_tool", "tool": str(XHS_CLI), "account_file": str(XHS_SAU_ACCOUNT)}
        sau_result = None
        if PUBLISH_PYTHON.exists() and (PUBLISH_ROOT / "sau_cli.py").exists():
            sau_result = run_command(
                [str(PUBLISH_PYTHON), "sau_cli.py", "xiaohongshu", "check", "--account", "creator"],
                cwd=PUBLISH_ROOT,
                timeout=60,
            )
            if sau_result["returncode"] == 0:
                return {
                    "ok": True,
                    "platform": platform,
                    "status": "sau_cookie_valid",
                    "account_file": str(XHS_SAU_ACCOUNT),
                    "result": sau_result,
                    "safe_mode": "content_toolkit_xiaohongshu_draft",
                    "next_step": "content-toolkit 小红书 cookie 已验证；dashboard 会用安全草稿模式保存图文，不会发布。",
                }
        bridge = {"server_running": False, "extension_connected": False}
        try:
            sys.path.insert(0, str(XHS_SKILL / "scripts"))
            from xhs.bridge import BridgePage  # type: ignore

            page = BridgePage("ws://localhost:9333")
            bridge = {
                "server_running": page.is_server_running(),
                "extension_connected": page.is_extension_connected(),
            }
        except Exception as exc:  # noqa: BLE001
            bridge["message"] = str(exc)
        if not bridge.get("server_running") or not bridge.get("extension_connected"):
            sau_missing = bool(sau_result and sau_result.get("returncode") != 0)
            return {
                "ok": False,
                "platform": platform,
                "status": "xhs_sau_cookie_missing_bridge_not_ready" if sau_missing else "bridge_not_ready",
                "account_file": str(XHS_SAU_ACCOUNT),
                "bridge": bridge,
                "sau_result": sau_result,
                "setup_command": setup_command_for(platform),
                "next_step": "优先点击“准备通道”完成 content-toolkit 小红书扫码登录，生成 xiaohongshu_creator.json；XHS Bridge 只是备用通道。",
            }
        result = run_command([sys.executable, str(XHS_CLI), "check-login"], cwd=XHS_SKILL / "scripts", timeout=12)
        timed_out = result["returncode"] == 124
        combined_output = f"{result.get('stdout') or ''}\n{result.get('stderr') or ''}"
        if "Cannot access contents of the page" in combined_output or "Extension manifest must request permission" in combined_output:
            sau_missing = bool(sau_result and sau_result.get("returncode") != 0)
            return {
                "ok": False,
                "platform": platform,
                "status": "xhs_sau_cookie_missing_bridge_permission_missing" if sau_missing else "extension_host_permission_missing",
                "account_file": str(XHS_SAU_ACCOUNT),
                "bridge": bridge,
                "sau_result": sau_result,
                "result": result,
                "setup_command": setup_command_for(platform),
                "next_step": "优先完成 content-toolkit 小红书扫码登录，生成 xiaohongshu_creator.json；备用的 XHS Bridge 扩展也仍缺站点访问权限。两条通道都只保存草稿，不会发布。",
            }
        return {
            "ok": result["returncode"] == 0,
            "platform": platform,
            "status": "login_ok" if result["returncode"] == 0 else ("login_unknown_check_timeout" if timed_out else "login_check_failed"),
            "account_file": str(XHS_SAU_ACCOUNT),
            "bridge": bridge,
            "result": result,
            "setup_command": setup_command_for(platform),
            "next_step": "如果状态未知，点击“准备通道”重新拉起登录流程；确认登录后再推送平台草稿箱。",
        }
    if platform == "wechat_mp":
        bridge = ensure_wechat_bridge(dry_run=True)
        health = bridge.get("health") or {}
        configured = bool((health.get("wechat") or {}).get("configured"))
        return {
            "ok": bool(bridge.get("ok") and configured),
            "platform": platform,
            "status": "ready" if bridge.get("ok") and configured else "bridge_or_secret_missing",
            "bridge": bridge,
            "setup_command": setup_command_for(platform),
        }
    if platform == "wechat_channels":
        if WECHAT_CHANNELS_ACCOUNT.exists():
            result = run_command(
                [
                    str(PUBLISH_PYTHON if PUBLISH_PYTHON.exists() else Path(sys.executable)),
                    str(WECHAT_CHANNELS_PUSH),
                    "--title",
                    "check-only",
                    "--check-only",
                    "--headless",
                ],
                cwd=WECHAT_CHANNELS_PUSH.parent,
                timeout=45,
            )
            check_ok = result["returncode"] == 0
            status = "cookie_valid" if check_ok else "cookie_invalid"
            try:
                parsed = json.loads(result.get("stdout") or "{}")
                status = str(parsed.get("status") or status)
                check_ok = bool(parsed.get("ok"))
            except json.JSONDecodeError:
                parsed = {}
            return {
                "ok": check_ok,
                "platform": platform,
                "status": status,
                "account_file": str(WECHAT_CHANNELS_ACCOUNT),
                "tool": str(WECHAT_CHANNELS_PUSH),
                "check_result": parsed or result,
                "setup_command": setup_command_for(platform),
                    "next_step": "视频号 cookie 有效；可以执行一键公开发布。" if check_ok else "视频号 cookie 存在但校验失败；需要重新登录。",
            }
        return {
            "ok": False,
            "platform": platform,
            "status": "cookie_missing",
            "account_file": str(WECHAT_CHANNELS_ACCOUNT),
            "tool": str(WECHAT_CHANNELS_PUSH),
            "setup_command": setup_command_for(platform),
            "next_step": "需要先登录视频号；本次不会开始上传。请完成登录后重新点击一键公开发布。",
        }
    if platform == "bilibili":
        runtime = ROOT / ".social-auto-upload/tools/biliup/macos-aarch64/biliup"
        base = {
            "platform": platform,
            "account_file": str(BILIBILI_ACCOUNT),
            "account_exists": BILIBILI_ACCOUNT.exists(),
            "biliup": str(runtime),
            "biliup_exists": runtime.exists(),
            "web_uploader": str(BILIBILI_WEB_UPLOAD),
            "web_uploader_exists": BILIBILI_WEB_UPLOAD.exists(),
            "python": str(PUBLISH_PYTHON),
            "python_exists": PUBLISH_PYTHON.exists(),
            "safe_mode": "web_public_upload",
            "setup_command": setup_command_for(platform),
        }
        if BILIBILI_ACCOUNT.exists() and BILIBILI_WEB_UPLOAD.exists() and PUBLISH_PYTHON.exists():
            result = run_command(
                [str(PUBLISH_PYTHON), str(BILIBILI_WEB_UPLOAD), "--headless", "check"],
                cwd=BILIBILI_WEB_UPLOAD.parent,
                timeout=90,
            )
            try:
                parsed = json.loads(result.get("stdout") or "{}")
            except json.JSONDecodeError:
                parsed = {}
            ok = result["returncode"] == 0 and bool(parsed.get("ok"))
            return {
                **base,
                "ok": ok,
                "status": "web_login_valid" if ok else (parsed.get("status") or "cookie_invalid"),
                "check_result": parsed or scrub_command_result(result),
                "next_step": "Bilibili 网页投稿登录态可用；可以执行一键公开发布。" if ok else "Bilibili 登录态不可用；请重新登录 Bilibili。",
            }
        missing_parts = []
        if not BILIBILI_ACCOUNT.exists():
            missing_parts.append("account")
        if not BILIBILI_WEB_UPLOAD.exists():
            missing_parts.append("web_uploader")
        if not PUBLISH_PYTHON.exists():
            missing_parts.append("python")
        return {
            **base,
            "ok": False,
            "status": "missing_" + "_".join(missing_parts) if missing_parts else "unknown_not_ready",
            "next_step": "需要登录 Bilibili；系统会打开登录流程，登录成功后继续发布。",
        }
    if platform == "youtube":
        python_bin = CONTENT_OPS_PYTHON if CONTENT_OPS_PYTHON.exists() else Path(sys.executable)
        result = run_command([str(python_bin), str(YOUTUBE_CHANNEL), "check"], cwd=ROOT / "work/content-ops", timeout=45)
        try:
            parsed = json.loads(result.get("stdout") or "{}")
        except json.JSONDecodeError:
            parsed = {}
        ok = result["returncode"] == 0 and bool(parsed.get("ok"))
        return {
            "ok": ok,
            "platform": platform,
            "status": parsed.get("status") or "youtube_check_failed",
            "check_result": parsed or result,
            "credential_candidates": parsed.get("credential_candidates") or [],
            "client_file_candidates": parsed.get("credential_candidates") or [],
            "client_secret": parsed.get("client_secret") or "",
            "token_file": parsed.get("token_file") or str(ROOT / ".config/park/youtube-token.json"),
            "safe_mode": "api_public_upload",
            "setup_command": setup_command_for(platform),
            "next_step": "YouTube OAuth 已就绪；可以执行一键公开发布。" if ok else (parsed.get("message") or "缺 YouTube OAuth client/token。"),
        }
    if platform == "x":
        return {
            "ok": True,
            "platform": platform,
            "status": "web_intent_available",
            "safe_mode": "compose_intent_only_no_api_post",
            "url": PLATFORM_URLS["x"],
            "setup_command": setup_command_for(platform),
        }
    if platform == "zhihu":
        return {
            "ok": True,
            "platform": platform,
            "status": "web_editor_handoff_only",
            "safe_mode": "no_confirmed_official_public_draft_api",
            "url": PLATFORM_URLS["zhihu"],
            "setup_command": setup_command_for(platform),
        }
    return {"ok": False, "platform": platform, "status": "not_implemented"}


def check_all_channels() -> dict[str, Any]:
    checks = []
    for platform in CHANNELS:
        checks.append(check_channel(platform))
    ready = [item for item in checks if item.get("ok")]
    needs_setup = [item for item in checks if not item.get("ok")]
    return {
        "ok": True,
        "status": "checked",
        "checked_at": now_iso(),
        "ready_count": len(ready),
        "needs_setup_count": len(needs_setup),
        "auth_artifacts": auth_artifacts(),
        "auth_qrcodes": collect_auth_qrcodes(),
        "login_sessions": login_sessions_status(),
        "channels": checks,
    }


def prepare_channel(platform: str) -> dict[str, Any]:
    if platform == "bilibili":
        if not PUBLISH_PYTHON.exists():
            return {"ok": False, "platform": platform, "status": "publish_venv_missing", "python": str(PUBLISH_PYTHON), "account_file": str(BILIBILI_ACCOUNT)}
        command = [
            str(PUBLISH_PYTHON),
            "-c",
            "from uploader.bilibili_uploader.runtime import ensure_biliup_binary; p=ensure_biliup_binary(force_check=False); print(p)",
        ]
        result = run_command(command, cwd=PUBLISH_ROOT, timeout=180)
        ready = result["returncode"] == 0 and (ROOT / ".social-auto-upload/tools/biliup/macos-aarch64/biliup").exists()
        if ready and BILIBILI_ACCOUNT.exists():
            checked = check_channel(platform)
            if checked.get("ok"):
                return {
                    "ok": True,
                    "platform": platform,
                    "status": "ready",
                    "result": result,
                    "check_result": checked,
                    "account_file": str(BILIBILI_ACCOUNT),
                    "next_step": "Bilibili runtime 和账号 cookie 都已验证；可以从具体内容卡片上传为仅自己可见视频。",
                }
        login_result = start_bilibili_login_session()
        return {
            "ok": ready,
            "platform": platform,
            "status": "biliup_ready" if ready else "biliup_prepare_failed",
            "account_file": str(BILIBILI_ACCOUNT),
            "result": result,
            "login_result": login_result,
            "auth_qrcodes": collect_auth_qrcodes(),
            "next_step": "已启动 Bilibili 登录流程。请在 dashboard 打开二维码，用 Bilibili App 扫码；登录成功后回到 dashboard 点“检查登录”。",
        }
    if platform == "wechat_mp":
        result = run_command(["npm", "run", "bridge:start"], cwd=WECHAT_WORKFLOW, timeout=30)
        return {"ok": result["returncode"] == 0, "platform": platform, "status": "bridge_start_requested", "result": result}
    if platform == "xiaohongshu":
        bridge = ensure_xhs_bridge_server()
        chrome = run_detached(["open", "-a", "Google Chrome", "https://www.xiaohongshu.com/explore"])
        sau_login_result = {}
        if PUBLISH_PYTHON.exists() and (PUBLISH_ROOT / "sau_cli.py").exists():
            sau_login_result = start_xhs_login_session()
        result = run_in_terminal([sys.executable, str(XHS_CLI), "login"], cwd=XHS_SKILL / "scripts")
        return {
            "ok": bool((sau_login_result or result).get("ok")),
            "platform": platform,
            "status": "login_started",
            "account_file": str(XHS_SAU_ACCOUNT),
            "bridge": bridge,
            "chrome": chrome,
            "sau_login_result": sau_login_result,
            "auth_qrcodes": collect_auth_qrcodes(),
            "result": result,
            "next_step": "已启动小红书登录流程。请在 dashboard 打开二维码，用小红书 App 扫码；成功后 dashboard 会用安全草稿模式保存图文，不会发布。XHS Bridge 仍可作为备用。",
        }
    if platform == "wechat_channels":
        if WECHAT_CHANNELS_ACCOUNT.exists():
            checked = check_channel(platform)
            if checked.get("ok"):
                return {
                    "ok": True,
                    "platform": platform,
                    "status": "cookie_valid",
                    "check_result": checked,
                    "account_file": str(WECHAT_CHANNELS_ACCOUNT),
                    "next_step": "视频号 cookie 已验证；可以从具体内容卡片点击“推送平台草稿箱”。",
                }
        login_result = start_wechat_channels_login_session()
        return {
            "ok": bool(login_result.get("ok")),
            "platform": platform,
            "status": "login_browser_opened" if login_result.get("ok") else "login_browser_failed",
            "account_file": str(WECHAT_CHANNELS_ACCOUNT),
            "session": WECHAT_CHANNELS_LOGIN_SESSION,
            "login_result": login_result,
            "next_step": "已启动视频号登录流程；请在弹出的浏览器页面扫码/确认登录。登录成功后回到 dashboard 点“检查登录”。",
        }
    if platform == "youtube":
        checked = check_channel(platform)
        status = str(checked.get("status") or "")
        if checked.get("ok"):
            return {
                "ok": True,
                "platform": platform,
                "status": "oauth_ready",
                "check_result": checked,
                "client_file_candidates": [str(path) for path in YOUTUBE_CLIENT_CANDIDATES],
                "token_file": str(YOUTUBE_TOKEN),
                "next_step": "YouTube OAuth 已就绪；可以从具体内容卡片点击“上传 private 视频”。",
            }
        if status in {"token_missing", "token_invalid"}:
            command = [str(CONTENT_OPS_PYTHON if CONTENT_OPS_PYTHON.exists() else Path(sys.executable)), str(YOUTUBE_CHANNEL), "auth"]
            result = run_in_terminal(command, cwd=ROOT / "work/content-ops")
            return {
                "ok": bool(result.get("ok")),
                "platform": platform,
                "status": "oauth_terminal_opened" if result.get("ok") else "oauth_terminal_failed",
                "check_result": checked,
                "result": result,
                "client_file_candidates": [str(path) for path in YOUTUBE_CLIENT_CANDIDATES],
                "token_file": str(YOUTUBE_TOKEN),
                "next_step": "已打开 Terminal 启动 YouTube OAuth；授权完成后回到 dashboard 点“检查 OAuth”。",
            }
        result = run_detached(["open", "https://console.cloud.google.com/apis/credentials"])
        return {
            "ok": bool(result.get("ok")),
            "platform": platform,
            "status": "oauth_client_missing",
            "check_result": checked,
            "result": result,
            "client_file_candidates": [str(path) for path in YOUTUBE_CLIENT_CANDIDATES],
            "token_file": str(YOUTUBE_TOKEN),
            "next_step": "缺 Google OAuth desktop client JSON；请创建 OAuth client 并保存到 /Users/wendy/.config/park/youtube-oauth.json，再点“准备通道”。",
        }
    if platform in {"x", "zhihu"}:
        result = run_detached(["open", PLATFORM_URLS[platform]])
        return {"ok": bool(result.get("ok")), "platform": platform, "status": "platform_opened", "result": result}
    return {"ok": False, "platform": platform, "status": "not_implemented"}


def prepare_missing_channels(payload: dict[str, Any]) -> dict[str, Any]:
    if not bool(payload.get("confirmed")):
        return {
            "ok": False,
            "status": "confirmation_required",
            "message": "这是会打开多个通道准备流程的动作，需要 confirmed=true。",
        }
    checks = check_all_channels()
    actions = []
    for channel in checks.get("channels", []):
        platform = str(channel.get("platform") or "")
        if channel.get("ok") or platform not in PREPARABLE_CHANNELS:
            continue
        actions.append(
            {
                "platform": platform,
                "before_status": channel.get("status"),
                "setup_command": setup_command_for(platform),
                "result": prepare_channel(platform),
            }
        )
    return {
        "ok": True,
        "status": "prepare_missing_requested",
        "checked_at": checks.get("checked_at"),
        "prepared_count": len(actions),
        "auth_artifacts": auth_artifacts(),
        "actions": actions,
        "message": "已为缺失通道发起准备动作；可能会打开 Terminal、平台后台或本地服务。不会发布任何内容。",
    }


def prepare_next_auth_channel(payload: dict[str, Any]) -> dict[str, Any]:
    if not bool(payload.get("confirmed")):
        return {
            "ok": False,
            "status": "confirmation_required",
            "message": "这是会打开登录/OAuth 准备流程的动作，需要 confirmed=true。",
        }
    checks = check_all_channels()
    channels_by_platform = {str(item.get("platform") or ""): item for item in checks.get("channels") or []}
    skip_manual_blockers = bool(payload.get("skip_manual_blockers"))
    skipped: list[dict[str, Any]] = []
    for platform in AUTH_PREP_ORDER:
        channel = channels_by_platform.get(platform) or {}
        if channel.get("ok"):
            continue
        if skip_manual_blockers and channel.get("status") in MANUAL_AUTH_BLOCKERS:
            skipped.append({"platform": platform, "status": channel.get("status") or ""})
            continue
        if platform == "xiaohongshu" and channel.get("status") == "extension_host_permission_missing":
            open_result = run_detached(["open", "-a", "Google Chrome", XHS_EXTENSION_URL])
            result = {
                "ok": bool(open_result.get("ok")),
                "platform": platform,
                "status": "extension_permission_page_opened" if open_result.get("ok") else "extension_permission_page_failed",
                "open_result": open_result,
                "next_step": "Chrome 已打开 XHS Bridge 扩展页；请 reload 扩展，并把 Site access 设置为允许访问 xiaohongshu.com。完成后回到 dashboard 点“检查全部通道”。",
            }
            return {
                "ok": bool(result.get("ok")),
                "status": "next_auth_prepare_requested",
                "platform": platform,
                "before_status": channel.get("status") or "",
                "result": result,
                "remaining": [
                    item.get("platform")
                    for item in checks.get("channels") or []
                    if item.get("platform") in AUTH_PREP_ORDER and not item.get("ok") and item.get("platform") != platform
                ],
                "skipped": skipped,
                "message": "已打开小红书 XHS Bridge 扩展权限页；请完成 reload/站点访问授权。",
            }
        result = prepare_channel(platform)
        return {
            "ok": bool(result.get("ok")),
            "status": "next_auth_prepare_requested",
            "platform": platform,
            "before_status": channel.get("status") or "",
            "result": result,
            "remaining": [
                item.get("platform")
                for item in checks.get("channels") or []
                if item.get("platform") in AUTH_PREP_ORDER and not item.get("ok") and item.get("platform") != platform
            ],
            "skipped": skipped,
            "message": f"已发起 {platform_label(platform)} 的授权准备流程；完成后请回到 dashboard 点“检查全部通道”。",
        }
    return {
        "ok": True,
        "status": "all_auth_channels_ready",
        "message": "小红书、视频号、Bilibili、YouTube 授权通道都已 ready。",
        "checks": checks,
    }


def validate_channel_routes(payload: dict[str, Any]) -> dict[str, Any]:
    command = [sys.executable, str(CHECK_PLATFORM_CHANNELS), "--json"]
    source_content_id = str(payload.get("source_content_id") or "")
    if source_content_id:
        command.extend(["--source-content-id", source_content_id])
    result = run_command(command, cwd=CHECK_PLATFORM_CHANNELS.parent, timeout=180)
    try:
        parsed = json.loads(result.get("stdout") or "{}")
    except json.JSONDecodeError:
        parsed = {}
    ok = result["returncode"] == 0 and bool(parsed.get("ok"))
    return {
        "ok": ok,
        "status": "channel_routes_validated" if ok else "channel_routes_validation_failed",
        "result": parsed or result,
        "summary": (parsed or {}).get("summary") or {},
        "next_auth": (parsed or {}).get("next_auth") or {},
        "source": (parsed or {}).get("source") or {},
        "dry_runs": (parsed or {}).get("dry_runs") or [],
        "channels": (parsed or {}).get("channels") or [],
    }


def repair_missing_videos(payload: dict[str, Any]) -> dict[str, Any]:
    dry_run = bool(payload.get("dry_run"))
    confirmed = bool(payload.get("confirmed"))
    if not REPAIR_DOUYIN_VIDEOS.exists():
        return {"ok": False, "status": "missing_tool", "tool": str(REPAIR_DOUYIN_VIDEOS)}
    if not dry_run and not confirmed:
        return {
            "ok": False,
            "status": "confirmation_required",
            "message": "这是会下载/复制本地视频素材的动作，需要 confirmed=true。",
        }
    command = [sys.executable, str(REPAIR_DOUYIN_VIDEOS)]
    if not dry_run:
        command.append("--apply")
    source_ids = payload.get("source_content_ids") or []
    if isinstance(source_ids, str):
        source_ids = [source_ids]
    for source_id in source_ids:
        command.extend(["--source-content-id", str(source_id)])
    result = run_command(command, cwd=REPAIR_DOUYIN_VIDEOS.parent, timeout=1200)
    parsed = {}
    try:
        parsed = json.loads(result.get("stdout") or "{}")
    except json.JSONDecodeError:
        parsed = {}
    return {
        "ok": result["returncode"] == 0,
        "status": "dry_run" if dry_run else "repair_finished",
        "dry_run": dry_run,
        "result": result,
        "report": parsed.get("report") or "",
        "summary": {
            "missing_count": parsed.get("missing_count"),
            "item_statuses": [
                [item.get("source_content_id"), item.get("status")]
                for item in parsed.get("items", [])
            ],
        },
    }


def prepare_local_asset(payload: dict[str, Any]) -> dict[str, Any]:
    platform = str(payload.get("platform") or "")
    source_content_id = str(payload.get("source_content_id") or "")
    confirmed = bool(payload.get("confirmed"))
    if not source_content_id:
        raise ValueError("缺少 source_content_id。")
    if not confirmed:
        return {
            "ok": False,
            "status": "confirmation_required",
            "platform": platform,
            "source_content_id": source_content_id,
            "message": "这是会改写/生成本地素材包的动作，需要 confirmed=true。",
        }
    if platform != "xiaohongshu":
        return {
            "ok": False,
            "status": "unsupported_local_asset_action",
            "platform": platform,
            "source_content_id": source_content_id,
            "message": "当前只支持从 dashboard 修复小红书本地图文包。",
        }
    generate = run_command(
        [
            sys.executable,
            str(GENERATE_XHS_FROM_CONTENT_PACKAGE),
            "--source-content-id",
            source_content_id,
            "--overwrite",
            "--engine",
            "auto",
            "--timeout",
            "240",
        ],
        cwd=GENERATE_XHS_FROM_CONTENT_PACKAGE.parent,
        timeout=3600,
    )
    quality = run_command(
        [sys.executable, str(QUALITY_XHS_DRAFTS), "--source-content-id", source_content_id, "--force"],
        cwd=QUALITY_XHS_DRAFTS.parent,
        timeout=900,
    )
    render = run_command(
        [sys.executable, str(RENDER_XHS_CARDS), "--source-content-id", source_content_id, "--style", "manual"],
        cwd=RENDER_XHS_CARDS.parent,
        timeout=900,
    )
    rebuild = run_command([sys.executable, str(BUILD_DASHBOARD)], cwd=BUILD_DASHBOARD.parent, timeout=120)
    draft = find_draft_record("xiaohongshu", source_content_id)
    if not draft:
        raise ValueError("没有找到对应的小红书草稿 JSON。")
    preflight = preflight_source({"source_content_id": source_content_id, "platforms": ["xiaohongshu"]})
    xhs_checks = ((preflight.get("platforms") or [{}])[0].get("checks") or [])
    package_ready = any(check.get("name") == "xhs_rendered_package" and check.get("ok") for check in xhs_checks)
    ok = generate["returncode"] == 0 and quality["returncode"] == 0 and render["returncode"] == 0 and rebuild["returncode"] == 0 and package_ready
    channel_ready = any(check.get("name") == "channel_ready" and check.get("ok") for check in xhs_checks)
    status = "local_asset_ready" if ok and channel_ready else "local_asset_ready_channel_pending" if ok else "local_asset_prepare_failed"
    return {
        "ok": ok,
        "status": status,
        "platform": platform,
        "source_content_id": source_content_id,
        "local_id": draft["local_id"],
        "generate_result": generate,
        "quality_result": quality,
        "render_result": render,
        "rebuild_dashboard": rebuild,
        "preflight": preflight,
        "message": (
            "小红书本地图文包已生成；还需要小红书 Bridge/登录就绪后才能推送平台草稿箱。"
            if ok and not channel_ready
            else "小红书本地图文包已生成，可以回到预检或推送平台草稿箱。"
            if ok
            else "小红书本地素材生成未完全通过，请查看 quality/render 输出。"
        ),
    }


def generate_local_draft(payload: dict[str, Any]) -> dict[str, Any]:
    platform = str(payload.get("platform") or "")
    source_content_id = str(payload.get("source_content_id") or "")
    confirmed = bool(payload.get("confirmed"))
    if platform not in CHANNELS:
        return {"ok": False, "status": "unknown_platform", "platform": platform}
    if not source_content_id:
        raise ValueError("缺少 source_content_id。")
    if not confirmed:
        return {
            "ok": False,
            "status": "confirmation_required",
            "platform": platform,
            "source_content_id": source_content_id,
            "message": "这是会生成本地平台草稿的动作，需要 confirmed=true。",
        }
    command = [
        sys.executable,
        str(GENERATE_REPURPOSE_DRAFTS),
        "--source-content-id",
        source_content_id,
        "--platform",
        platform,
    ]
    result = run_command(command, cwd=GENERATE_REPURPOSE_DRAFTS.parent, timeout=900)
    preflight = preflight_source({"source_content_id": source_content_id, "platforms": [platform]})
    platform_state = (preflight.get("platforms") or [{}])[0]
    has_draft = any(check.get("name") == "local_draft" and check.get("ok") for check in platform_state.get("checks") or [])
    return {
        "ok": result["returncode"] == 0 and has_draft,
        "status": "local_draft_ready" if result["returncode"] == 0 and has_draft else "local_draft_generate_failed",
        "platform": platform,
        "source_content_id": source_content_id,
        "result": result,
        "preflight": preflight,
        "message": "本地平台草稿已生成；请重新预检后继续。" if result["returncode"] == 0 and has_draft else "本地平台草稿生成失败，请查看输出。",
    }


def generate_content_package_action(payload: dict[str, Any]) -> dict[str, Any]:
    source_content_id = str(payload.get("source_content_id") or "")
    confirmed = bool(payload.get("confirmed"))
    if not source_content_id:
        raise ValueError("缺少 source_content_id。")
    if not confirmed:
        return {
            "ok": False,
            "status": "confirmation_required",
            "source_content_id": source_content_id,
            "message": "这是会调用 AI 生成本地内容包的动作，需要 confirmed=true。",
        }
    python_bin = CONTENT_OPS_PYTHON if CONTENT_OPS_PYTHON.exists() else Path(sys.executable)
    command = [str(python_bin), str(GENERATE_CONTENT_PACKAGE), "--source-content-id", source_content_id]
    result = run_command(command, cwd=GENERATE_CONTENT_PACKAGE.parent, timeout=1200)
    rebuild = None
    if result["returncode"] == 0:
        rebuild = run_command([str(python_bin), str(BUILD_DASHBOARD)], cwd=BUILD_DASHBOARD.parent, timeout=300)
    return {
        "ok": result["returncode"] == 0 and (not rebuild or rebuild["returncode"] == 0),
        "status": "content_package_ready" if result["returncode"] == 0 else "content_package_failed",
        "source_content_id": source_content_id,
        "result": result,
        "rebuild_dashboard": rebuild,
        "message": "AI 内容包已生成，dashboard 已刷新。" if result["returncode"] == 0 else "AI 内容包生成失败，请查看输出。",
    }


def content_package_path_for(source_content_id: str) -> Path:
    asset = find_source_asset(source_content_id)
    raw = asset.get("content_package_json") or ""
    if raw and Path(raw).exists():
        return Path(raw)
    candidates = list((OUTBOX / "sent/douyin").glob(f"*--{source_content_id}/transcript/content-package.json"))
    if candidates:
        return candidates[0]
    raise FileNotFoundError(f"没有找到内容包：{source_content_id}")


def approve_content_package_action(payload: dict[str, Any]) -> dict[str, Any]:
    source_content_id = str(payload.get("source_content_id") or "")
    confirmed = bool(payload.get("confirmed"))
    if not source_content_id:
        raise ValueError("缺少 source_content_id。")
    if not confirmed:
        return {
            "ok": False,
            "status": "confirmation_required",
            "source_content_id": source_content_id,
            "message": "这是会把内容包标记为已审核通过的动作，需要 confirmed=true。",
        }
    package_path = content_package_path_for(source_content_id)
    package = read_json(package_path)
    if not package:
        raise ValueError(f"内容包不是合法 JSON：{package_path}")
    package["approved"] = True
    package["approved_at"] = now_iso()
    package["approved_by"] = "dashboard"
    package_path.write_text(json.dumps(package, ensure_ascii=False, indent=2), encoding="utf-8")
    python_bin = CONTENT_OPS_PYTHON if CONTENT_OPS_PYTHON.exists() else Path(sys.executable)
    rebuild = run_command([str(python_bin), str(BUILD_DASHBOARD)], cwd=BUILD_DASHBOARD.parent, timeout=300)
    return {
        "ok": rebuild["returncode"] == 0,
        "status": "content_package_approved" if rebuild["returncode"] == 0 else "content_package_approved_dashboard_rebuild_failed",
        "source_content_id": source_content_id,
        "content_package": str(package_path),
        "approved_at": package["approved_at"],
        "rebuild_dashboard": rebuild,
        "message": "内容包已标记为通过，dashboard 已刷新。" if rebuild["returncode"] == 0 else "内容包已标记为通过，但 dashboard 重建失败。",
    }


def repair_local_gaps(payload: dict[str, Any]) -> dict[str, Any]:
    source_content_id = str(payload.get("source_content_id") or "")
    confirmed = bool(payload.get("confirmed"))
    if not source_content_id:
        raise ValueError("缺少 source_content_id。")
    if not confirmed:
        return {
            "ok": False,
            "status": "confirmation_required",
            "source_content_id": source_content_id,
            "message": "这是会生成本地草稿/图文包的动作，需要 confirmed=true。",
        }
    before = preflight_source({"source_content_id": source_content_id})
    actions: list[dict[str, Any]] = []
    for item in before.get("platforms") or []:
        platform = str(item.get("platform") or "")
        failed = [check.get("name") for check in item.get("checks") or [] if not check.get("ok")]
        if "local_draft" in failed:
            actions.append({"kind": "generate_local_draft", "platform": platform, "result": generate_local_draft({"platform": platform, "source_content_id": source_content_id, "confirmed": True})})
    after_drafts = preflight_source({"source_content_id": source_content_id})
    xhs_item = next((item for item in after_drafts.get("platforms") or [] if item.get("platform") == "xiaohongshu"), {})
    xhs_failed = [check.get("name") for check in xhs_item.get("checks") or [] if not check.get("ok")]
    if "xhs_rendered_package" in xhs_failed:
        actions.append({"kind": "prepare_local_asset", "platform": "xiaohongshu", "result": prepare_local_asset({"platform": "xiaohongshu", "source_content_id": source_content_id, "confirmed": True})})
    after = preflight_source({"source_content_id": source_content_id})
    local_failures = []
    for item in after.get("platforms") or []:
        for check in item.get("checks") or []:
            if check.get("name") in {"local_draft", "xhs_rendered_package", "markdown"} and not check.get("ok"):
                local_failures.append({"platform": item.get("platform"), "check": check.get("name"), "message": check.get("message")})
    return {
        "ok": not local_failures,
        "status": "local_gaps_repaired" if not local_failures else "local_gaps_remaining",
        "source_content_id": source_content_id,
        "actions": actions,
        "before": before,
        "after": after,
        "local_failures": local_failures,
        "message": "本地草稿和小红书图文包缺口已补齐；仍可能需要原视频或平台登录。" if not local_failures else "仍有本地缺口未修复，请查看 local_failures。",
    }


def repair_all_local_gaps(payload: dict[str, Any]) -> dict[str, Any]:
    confirmed = bool(payload.get("confirmed"))
    if not confirmed:
        return {
            "ok": False,
            "status": "confirmation_required",
            "message": "这是会批量生成本地草稿/图文包的动作，需要 confirmed=true。",
        }
    assets_path = OUTBOX / ".system/data/assets.json"
    try:
        assets = json.loads(assets_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "ok": False,
            "status": "assets_index_unavailable",
            "message": f"无法读取 assets index：{exc}",
            "assets_path": str(assets_path),
        }
    requested_ids = payload.get("source_content_ids") or []
    if requested_ids:
        wanted = {str(item) for item in requested_ids}
        assets = [asset for asset in assets if str(asset.get("source_content_id") or "") in wanted]
    results = []
    for asset in assets:
        source_content_id = str(asset.get("source_content_id") or "")
        if not source_content_id:
            continue
        try:
            result = repair_local_gaps({"source_content_id": source_content_id, "confirmed": True})
        except Exception as exc:  # noqa: BLE001
            result = {
                "ok": False,
                "status": "error",
                "source_content_id": source_content_id,
                "message": str(exc),
            }
        results.append(result)
    failures = [item for item in results if not item.get("ok")]
    return {
        "ok": not failures,
        "status": "all_local_gaps_repaired" if not failures else "all_local_gaps_remaining",
        "source_count": len(results),
        "ok_count": sum(1 for item in results if item.get("ok")),
        "failure_count": len(failures),
        "failures": failures,
        "results": results,
        "message": "全部源内容的本地草稿/图文包缺口已补齐；平台授权仍需单独检查。" if not failures else "仍有本地缺口未修复，请查看 failures。",
    }


def run_action_queue(payload: dict[str, Any]) -> dict[str, Any]:
    apply = bool(payload.get("apply"))
    confirmed = bool(payload.get("confirmed"))
    lane = str(payload.get("lane") or "auto_repair_candidate")
    if lane != "auto_repair_candidate":
        return {
            "ok": False,
            "status": "unsupported_lane",
            "lane": lane,
            "message": "dashboard 只允许执行 auto_repair_candidate；其他 lane 需要人工判断。",
        }
    if apply and not confirmed:
        return {
            "ok": False,
            "status": "confirmation_required",
            "message": "执行自动修复会修改本地草稿，需要 confirmed=true。",
        }
    python_bin = CONTENT_OPS_PYTHON if CONTENT_OPS_PYTHON.exists() else Path(sys.executable)
    command = [str(python_bin), str(RUN_OUTBOX_ACTION_QUEUE), "--lane", lane]
    if apply:
        command.append("--apply")
    result = run_command(command, cwd=ROOT / "work/content-ops", timeout=1800)
    workflow_result: dict[str, Any] | None = None
    if apply and result.get("returncode") == 0:
        workflow_result = run_command([str(python_bin), str(RUN_OUTBOX_WORKFLOW)], cwd=ROOT / "work/content-ops", timeout=900)
    ok = result.get("returncode") == 0 and (workflow_result is None or workflow_result.get("returncode") == 0)
    return {
        "ok": ok,
        "status": "action_queue_applied" if apply and ok else ("action_queue_dry_run" if not apply and ok else "action_queue_failed"),
        "mode": "apply" if apply else "dry_run",
        "lane": lane,
        "action_queue_result": scrub_command_result(result),
        "workflow_result": scrub_command_result(workflow_result) if workflow_result else None,
        "message": "自动修复队列已执行，并刷新 workflow。" if apply and ok else ("自动修复队列 dry-run 已完成。" if ok else "自动修复队列执行失败，请看输出。"),
    }


def record_action_decision(payload: dict[str, Any]) -> dict[str, Any]:
    decision = str(payload.get("decision") or "")
    clear = bool(payload.get("clear"))
    draft_path = str(payload.get("draft_path") or "")
    source_content_id = str(payload.get("source_content_id") or "")
    reason = str(payload.get("reason") or "")
    merge_target = str(payload.get("merge_target") or "")
    if not clear and decision not in {"reingest", "skip", "merge", "drop", "keep_blocked"}:
        return {"ok": False, "status": "invalid_decision", "decision": decision, "message": "decision 必须是 reingest/skip/merge/drop/keep_blocked。"}
    if not draft_path:
        return {"ok": False, "status": "missing_draft_path", "message": "缺少 draft_path。"}
    python_bin = CONTENT_OPS_PYTHON if CONTENT_OPS_PYTHON.exists() else Path(sys.executable)
    command = [
        str(python_bin),
        str(RECORD_OUTBOX_ACTION_DECISION),
        draft_path,
        "--source-content-id",
        source_content_id,
        "--operator",
        "dashboard",
    ]
    if clear:
        command.append("--clear")
    else:
        command.extend(["--decision", decision])
    if reason:
        command.extend(["--reason", reason])
    if merge_target:
        command.extend(["--merge-target", merge_target])
    result = run_command(command, cwd=ROOT / "work/content-ops", timeout=300)
    workflow_result: dict[str, Any] | None = None
    if result.get("returncode") == 0:
        workflow_result = run_command([str(python_bin), str(RUN_OUTBOX_WORKFLOW)], cwd=ROOT / "work/content-ops", timeout=900)
    ok = result.get("returncode") == 0 and (workflow_result is None or workflow_result.get("returncode") == 0)
    return {
        "ok": ok,
        "status": ("decision_cleared" if clear else "decision_recorded") if ok else "decision_failed",
        "decision": decision,
        "clear": clear,
        "draft_path": draft_path,
        "source_content_id": source_content_id,
        "decision_result": scrub_command_result(result),
        "workflow_result": scrub_command_result(workflow_result) if workflow_result else None,
        "message": ("人工决策已撤回，并刷新 workflow。" if clear else "人工决策已记录，并刷新 workflow。") if ok else "人工决策记录失败，请看输出。",
    }


def unsupported_platform_response(platform: str, payload: dict[str, Any]) -> dict[str, Any]:
    capability = CAPABILITIES.get(platform) or {}
    return {
        "ok": False,
        "status": capability.get("status") or "not_implemented",
        "platform": platform,
        "capability": capability,
        "message": capability.get("notes") or "这个平台还没有安全的草稿推送通道。",
        "platform_url": PLATFORM_URLS.get(platform, ""),
        "source_content_id": payload.get("source_content_id") or "",
        "local_id": payload.get("local_id") or "",
    }


def handle_push_draft(payload: dict[str, Any]) -> dict[str, Any]:
    platform = str(payload.get("platform") or "")
    dry_run = bool(payload.get("dry_run"))
    confirmed = bool(payload.get("confirmed"))
    if platform == "youtube":
        if not dry_run and not confirmed:
            result = {
                "ok": False,
                "status": "confirmation_required",
                "platform": platform,
                "message": "这是会上传 YouTube private 视频的动作，需要 confirmed=true；不会公开视频。",
            }
            write_log({"action": "youtube_private_upload", "platform": platform, "request": payload, "result": result})
            return result
        try:
            result = push_youtube_private_upload(payload)
        except Exception as exc:  # noqa: BLE001
            result = {"ok": False, "status": "error", "platform": platform, "message": str(exc)}
        write_log({"action": "youtube_private_upload", "platform": platform, "request": payload, "result": result})
        return result
    if platform == "bilibili":
        if not dry_run and not confirmed:
            result = {
                "ok": False,
                "status": "confirmation_required",
                "platform": platform,
                "message": "这是会上传 Bilibili 仅自己可见视频的动作，需要 confirmed=true；不会公开发布。",
            }
            write_log({"action": "bilibili_self_only_upload", "platform": platform, "request": payload, "result": result})
            return result
        try:
            result = push_bilibili_self_only_upload(payload)
        except Exception as exc:  # noqa: BLE001
            result = {"ok": False, "status": "error", "platform": platform, "message": str(exc)}
        write_log({"action": "bilibili_self_only_upload", "platform": platform, "request": payload, "result": result})
        return result
    if platform in {"x", "zhihu"}:
        if not dry_run and not confirmed:
            result = {
                "ok": False,
                "status": "confirmation_required",
                "platform": platform,
                "message": "这是会打开平台后台并写入系统剪贴板的动作，需要 confirmed=true。",
            }
            write_log({"action": "handoff", "platform": platform, "request": payload, "result": result})
            return result
        try:
            result = handoff_platform(payload)
        except Exception as exc:  # noqa: BLE001
            result = {"ok": False, "status": "error", "platform": platform, "message": str(exc)}
        write_log({"action": "handoff", "platform": platform, "request": payload, "result": result})
        return result
    if platform not in {"xiaohongshu", "wechat_mp", "wechat_channels"}:
        result = unsupported_platform_response(platform, payload)
        write_log({"action": "push_draft", "platform": platform, "request": payload, "result": result})
        return result
    if not dry_run and not confirmed:
        result = {
            "ok": False,
            "status": "confirmation_required",
            "platform": platform,
            "message": "这是会修改平台草稿箱的动作，需要 confirmed=true。",
        }
        write_log({"action": "push_draft", "platform": platform, "request": payload, "result": result})
        return result
    try:
        if platform == "xiaohongshu":
            result = push_xhs_draft(payload)
        elif platform == "wechat_mp":
            result = push_wechat_mp_draft(payload)
        else:
            result = push_wechat_channels_draft(payload)
    except Exception as exc:  # noqa: BLE001
        result = {
            "ok": False,
            "status": "error",
            "platform": platform,
            "message": str(exc),
        }
    write_log({"action": "push_draft", "platform": platform, "request": payload, "result": result})
    return result


class WorkbenchHandler(SimpleHTTPRequestHandler):
    server_version = "ParkIOWorkbench/1.0"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(OUTBOX), **kwargs)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        sys.stderr.write("[%s] %s\n" % (now_iso(), format % args))

    def send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("cache-control", "no-store")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("content-length") or "0")
        raw = self.rfile.read(length).decode("utf-8")
        return json.loads(raw) if raw else {}

    def do_GET(self) -> None:  # noqa: N802
        parsed_url = urlparse(self.path)
        route = parsed_url.path
        if route == "/api/health":
            self.send_json(
                {
                    "ok": True,
                    "service": "park-io-outbox-workbench",
                    "outbox": str(OUTBOX),
                    "actions_log": str(ACTION_LOG),
                    "platforms": CAPABILITIES,
                }
            )
            return
        if route == "/api/capabilities":
            self.send_json({"ok": True, "platforms": CAPABILITIES, "platform_urls": PLATFORM_URLS})
            return
        if route == "/api/actions/recent":
            self.send_json(recent_actions())
            return
        if route == "/api/actions/video-migration/status":
            query = parse_qs(parsed_url.query)
            source_content_id = (query.get("source_content_id") or [""])[0]
            self.send_json(video_migration_status({"source_content_id": source_content_id}))
            return
        if route == "/":
            self.send_response(HTTPStatus.FOUND)
            self.send_header("location", "/dashboard.html")
            self.end_headers()
            return
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        route = urlparse(self.path).path
        if route not in {
            "/api/actions/push-draft",
            "/api/actions/video-migration/run",
            "/api/actions/video-migration/status",
            "/api/actions/handoff-platform",
            "/api/actions/check-channel",
            "/api/actions/check-all-channels",
            "/api/actions/check-auth-artifacts",
            "/api/actions/wait-auth-artifacts",
            "/api/actions/auth-qrcodes",
            "/api/actions/login-sessions",
            "/api/actions/import-chrome-auth",
            "/api/actions/install-youtube-oauth-client",
            "/api/actions/validate-channel-routes",
            "/api/actions/prepare-channel",
            "/api/actions/prepare-next-auth",
            "/api/actions/prepare-missing-channels",
            "/api/actions/refresh-auth-prompts",
            "/api/actions/preflight-source",
            "/api/actions/prepare-local-asset",
            "/api/actions/generate-local-draft",
            "/api/actions/generate-content-package",
            "/api/actions/approve-content-package",
            "/api/actions/repair-local-gaps",
            "/api/actions/repair-all-local-gaps",
            "/api/actions/run-action-queue",
            "/api/actions/record-action-decision",
            "/api/actions/mark-sent",
            "/api/actions/repair-missing-videos",
        }:
            self.send_json({"ok": False, "message": "unknown endpoint"}, status=404)
            return
        try:
            payload = self.read_json_body()
        except json.JSONDecodeError:
            self.send_json({"ok": False, "message": "请求体不是合法 JSON"}, status=400)
            return
        if route == "/api/actions/check-channel":
            result = check_channel(str(payload.get("platform") or ""))
            write_log({"action": "check_channel", "platform": payload.get("platform") or "", "request": payload, "result": result})
        elif route == "/api/actions/video-migration/status":
            result = video_migration_status(payload)
            write_log({"action": "video_migration_status", "request": payload, "result": result})
        elif route == "/api/actions/video-migration/run":
            result = run_video_migration(payload)
        elif route == "/api/actions/handoff-platform":
            if not bool(payload.get("confirmed")) and not bool(payload.get("dry_run")):
                result = {
                    "ok": False,
                    "status": "confirmation_required",
                    "platform": payload.get("platform") or "",
                    "message": "这是会打开平台后台并写入系统剪贴板的动作，需要 confirmed=true。",
                }
            else:
                try:
                    result = handoff_platform(payload)
                except Exception as exc:  # noqa: BLE001
                    result = {"ok": False, "status": "error", "platform": payload.get("platform") or "", "message": str(exc)}
            write_log({"action": "handoff_platform", "platform": payload.get("platform") or "", "request": payload, "result": result})
        elif route == "/api/actions/check-all-channels":
            result = check_all_channels()
            write_log({"action": "check_all_channels", "request": payload, "result": result})
        elif route == "/api/actions/check-auth-artifacts":
            result = check_auth_artifacts()
            write_log({"action": "check_auth_artifacts", "request": payload, "result": result})
        elif route == "/api/actions/wait-auth-artifacts":
            result = wait_auth_artifacts(payload)
            write_log({"action": "wait_auth_artifacts", "request": payload, "result": result})
        elif route == "/api/actions/auth-qrcodes":
            result = {"ok": True, "status": "checked", "auth_qrcodes": collect_auth_qrcodes(), "login_sessions": login_sessions_status()}
            write_log({"action": "auth_qrcodes", "request": payload, "result": result})
        elif route == "/api/actions/login-sessions":
            result = {"ok": True, "status": "checked", "login_sessions": login_sessions_status(), "auth_qrcodes": collect_auth_qrcodes()}
            write_log({"action": "login_sessions", "request": payload, "result": result})
        elif route == "/api/actions/import-chrome-auth":
            result = import_chrome_auth(payload)
            write_log({"action": "import_chrome_auth", "platform": payload.get("platform") or "", "request": payload, "result": result})
        elif route == "/api/actions/install-youtube-oauth-client":
            result = install_youtube_oauth_client(payload)
            write_log({"action": "install_youtube_oauth_client", "request": payload, "result": result})
        elif route == "/api/actions/validate-channel-routes":
            result = validate_channel_routes(payload)
            write_log({"action": "validate_channel_routes", "request": payload, "result": result})
        elif route == "/api/actions/prepare-channel":
            try:
                result = prepare_channel(str(payload.get("platform") or ""))
            except Exception as exc:  # noqa: BLE001
                result = {
                    "ok": False,
                    "status": "prepare_channel_error",
                    "platform": payload.get("platform") or "",
                    "message": str(exc),
                }
            write_log({"action": "prepare_channel", "platform": payload.get("platform") or "", "request": payload, "result": result})
        elif route == "/api/actions/prepare-next-auth":
            result = prepare_next_auth_channel(payload)
            write_log({"action": "prepare_next_auth", "request": payload, "result": result})
        elif route == "/api/actions/prepare-missing-channels":
            result = prepare_missing_channels(payload)
            write_log({"action": "prepare_missing_channels", "request": payload, "result": result})
        elif route == "/api/actions/refresh-auth-prompts":
            result = restart_auth_prompts(payload)
            write_log({"action": "refresh_auth_prompts", "request": payload, "result": result})
        elif route == "/api/actions/preflight-source":
            try:
                result = preflight_source(payload)
            except Exception as exc:  # noqa: BLE001
                result = {"ok": False, "status": "error", "source_content_id": payload.get("source_content_id") or "", "message": str(exc)}
            write_log({"action": "preflight_source", "request": payload, "result": result})
        elif route == "/api/actions/prepare-local-asset":
            try:
                result = prepare_local_asset(payload)
            except Exception as exc:  # noqa: BLE001
                result = {
                    "ok": False,
                    "status": "error",
                    "platform": payload.get("platform") or "",
                    "source_content_id": payload.get("source_content_id") or "",
                    "message": str(exc),
                }
            write_log({"action": "prepare_local_asset", "platform": payload.get("platform") or "", "request": payload, "result": result})
        elif route == "/api/actions/generate-local-draft":
            try:
                result = generate_local_draft(payload)
            except Exception as exc:  # noqa: BLE001
                result = {
                    "ok": False,
                    "status": "error",
                    "platform": payload.get("platform") or "",
                    "source_content_id": payload.get("source_content_id") or "",
                    "message": str(exc),
                }
            write_log({"action": "generate_local_draft", "platform": payload.get("platform") or "", "request": payload, "result": result})
        elif route == "/api/actions/generate-content-package":
            try:
                result = generate_content_package_action(payload)
            except Exception as exc:  # noqa: BLE001
                result = {
                    "ok": False,
                    "status": "error",
                    "source_content_id": payload.get("source_content_id") or "",
                    "message": str(exc),
                }
            write_log({"action": "generate_content_package", "request": payload, "result": result})
        elif route == "/api/actions/approve-content-package":
            try:
                result = approve_content_package_action(payload)
            except Exception as exc:  # noqa: BLE001
                result = {
                    "ok": False,
                    "status": "error",
                    "source_content_id": payload.get("source_content_id") or "",
                    "message": str(exc),
                }
            write_log({"action": "approve_content_package", "request": payload, "result": result})
        elif route == "/api/actions/repair-local-gaps":
            try:
                result = repair_local_gaps(payload)
            except Exception as exc:  # noqa: BLE001
                result = {
                    "ok": False,
                    "status": "error",
                    "source_content_id": payload.get("source_content_id") or "",
                    "message": str(exc),
                }
            write_log({"action": "repair_local_gaps", "request": payload, "result": result})
        elif route == "/api/actions/repair-all-local-gaps":
            try:
                result = repair_all_local_gaps(payload)
            except Exception as exc:  # noqa: BLE001
                result = {
                    "ok": False,
                    "status": "error",
                    "message": str(exc),
                }
            write_log({"action": "repair_all_local_gaps", "request": payload, "result": result})
        elif route == "/api/actions/run-action-queue":
            try:
                result = run_action_queue(payload)
            except Exception as exc:  # noqa: BLE001
                result = {"ok": False, "status": "error", "message": str(exc)}
            write_log({"action": "run_action_queue", "request": payload, "result": result})
        elif route == "/api/actions/record-action-decision":
            try:
                result = record_action_decision(payload)
            except Exception as exc:  # noqa: BLE001
                result = {"ok": False, "status": "error", "message": str(exc)}
            write_log({"action": "record_action_decision", "request": payload, "result": result})
        elif route == "/api/actions/mark-sent":
            try:
                result = mark_sent(payload)
            except Exception as exc:  # noqa: BLE001
                result = {"ok": False, "status": "error", "platform": payload.get("platform") or "", "message": str(exc)}
            write_log({"action": "mark_sent", "platform": payload.get("platform") or "", "request": payload, "result": result})
        elif route == "/api/actions/repair-missing-videos":
            result = repair_missing_videos(payload)
            write_log({"action": "repair_missing_videos", "request": payload, "result": result})
        else:
            result = handle_push_draft(payload)
        self.send_json(result, status=200 if result.get("ok") or result.get("status") != "error" else 400)


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the Park-IO outbox workbench with local action APIs.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PARK_OUTBOX_WORKBENCH_PORT", "8788")))
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), WorkbenchHandler)
    print(f"Park-IO outbox workbench: http://{args.host}:{args.port}/dashboard.html")
    print("Video migration can publicly publish to configured platforms after explicit confirmation.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
