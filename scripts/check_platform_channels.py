#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path("/Users/wendy")
CONTENT_OPS = ROOT / "work/content-ops"
OUTBOX = ROOT / "park-io/outbox"
ASSETS_JSON = OUTBOX / ".system/data/assets.json"

sys.path.insert(0, str(CONTENT_OPS / "scripts"))

import workbench_server as workbench  # noqa: E402


PLATFORMS = ["xiaohongshu", "wechat_mp", "wechat_channels", "bilibili", "youtube", "x", "zhihu"]
AUTH_PREP_ORDER = ["xiaohongshu", "wechat_channels", "bilibili", "youtube"]
AUTH_STATUSES = {
    "bridge_not_ready",
    "cookie_missing",
    "cookie_invalid",
    "missing_account",
    "missing_account_biliup",
    "missing_account_python",
    "oauth_client_missing",
    "token_missing",
    "token_invalid",
    "login_check_failed",
    "login_unknown_check_timeout",
    "extension_host_permission_missing",
    "xhs_sau_cookie_missing_bridge_permission_missing",
    "xhs_sau_cookie_missing_bridge_not_ready",
    "account_or_biliup_missing",
}
AUTH_METADATA = {
    "xiaohongshu": {
        "label": "小红书",
        "expected_status": "sau_cookie_valid",
        "credential_file": "/Users/wendy/content-toolkit/capabilities/publish/cookies/xiaohongshu_creator.json",
        "prepare_button": "小红书 -> 准备通道",
        "manual_command": "cd /Users/wendy/content-toolkit/capabilities/publish && /Users/wendy/content-toolkit/capabilities/publish/.venv/bin/python sau_cli.py xiaohongshu login --account creator --headed",
        "browser_fix": "Preferred path: complete content-toolkit Xiaohongshu QR login. Fallback: reload XHS Bridge extension and allow site access for xiaohongshu.com.",
    },
    "wechat_channels": {
        "label": "视频号",
        "expected_status": "cookie_valid",
        "credential_file": "/Users/wendy/content-toolkit/capabilities/publish/cookies/tencent_uploader/account.json",
        "prepare_button": "视频号 -> 准备通道",
        "manual_command": "cd /Users/wendy/work/content-ops/scripts && /Users/wendy/content-toolkit/capabilities/publish/.venv/bin/python /Users/wendy/work/content-ops/scripts/push_wechat_channels_draft.py --title login-only --login-only",
    },
    "bilibili": {
        "label": "Bilibili",
        "expected_status": "ready",
        "credential_file": "/Users/wendy/content-toolkit/capabilities/publish/cookies/bilibili_creator.json",
        "prepare_button": "Bilibili -> 准备通道",
        "manual_command": "cd /Users/wendy/content-toolkit/capabilities/publish && /Users/wendy/content-toolkit/capabilities/publish/.venv/bin/python sau_cli.py bilibili login --account creator",
    },
    "youtube": {
        "label": "YouTube",
        "expected_status": "token_valid",
        "credential_file": "/Users/wendy/.config/park/youtube-token.json",
        "prepare_button": "YouTube -> 准备 OAuth",
        "manual_command": "cd /Users/wendy/work/content-ops && /Users/wendy/work/content-ops/.venv/bin/python /Users/wendy/work/content-ops/scripts/youtube_channel.py auth",
    },
}


def load_assets() -> list[dict[str, Any]]:
    return json.loads(ASSETS_JSON.read_text(encoding="utf-8"))


def pick_representative_source(source_content_id: str = "") -> dict[str, Any]:
    assets = load_assets()
    if source_content_id:
        for asset in assets:
            if str(asset.get("source_content_id") or "") == source_content_id:
                return asset
        raise SystemExit(f"source_content_id not found: {source_content_id}")
    for asset in assets:
        sid = str(asset.get("source_content_id") or "")
        if asset.get("content_type") != "video" or not asset.get("media_files"):
            continue
        xhs_draft = workbench.find_draft_record("xiaohongshu", sid)
        if xhs_draft and xhs_draft.get("package_dir"):
            return asset
    for asset in assets:
        if asset.get("content_type") == "video" and asset.get("media_files"):
            return asset
    raise SystemExit("No video source with media_files found.")


def pick_source_for_platform(platform: str) -> dict[str, Any] | None:
    assets = load_assets()
    for asset in assets:
        sid = str(asset.get("source_content_id") or "")
        if platform in {"wechat_channels", "bilibili", "youtube"}:
            if asset.get("content_type") != "video" or not asset.get("media_files"):
                continue
        draft = workbench.find_draft_record(platform, sid)
        if not draft:
            continue
        if platform == "xiaohongshu" and not draft.get("package_dir"):
            continue
        return asset
    return None


def classify_channel(status: str, ok: bool) -> str:
    if ok:
        return "ready"
    if status in AUTH_STATUSES or status.startswith("missing_"):
        return "needs_auth"
    return "code_or_runtime_gap"


def next_auth_platform(channels: list[dict[str, Any]]) -> dict[str, Any]:
    by_platform = {str(channel.get("platform") or ""): channel for channel in channels}
    for platform in AUTH_PREP_ORDER:
        channel = by_platform.get(platform) or {}
        if channel.get("class") == "needs_auth":
            return {
                "platform": platform,
                "status": channel.get("status") or "",
                **AUTH_METADATA.get(platform, {}),
            }
    return {}


def dry_run_platform(platform: str, source_content_id: str) -> dict[str, Any]:
    return workbench.handle_push_draft(
        {
            "platform": platform,
            "source_content_id": source_content_id,
            "dry_run": True,
            "confirmed": False,
        }
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Park-IO outbox platform channel readiness.")
    parser.add_argument("--source-content-id", default="", help="Representative source content id for dry-runs.")
    parser.add_argument("--json", action="store_true", help="Print full JSON report.")
    args = parser.parse_args()

    source = pick_representative_source(args.source_content_id)
    source_content_id = str(source.get("source_content_id") or "")
    channel_report = workbench.check_all_channels()
    preflight = workbench.preflight_source({"source_content_id": source_content_id, "platforms": PLATFORMS})
    dry_runs: list[dict[str, Any]] = []
    for platform in PLATFORMS:
        platform_source = pick_source_for_platform(platform)
        if not platform_source:
            dry_runs.append(
                {
                    "platform": platform,
                    "source_content_id": "",
                    "ok": False,
                    "status": "local_draft_missing",
                    "local_id": "",
                    "message": "没有找到适合 dry-run 的本地草稿。",
                }
            )
            continue
        platform_source_id = str(platform_source.get("source_content_id") or "")
        try:
            result = dry_run_platform(platform, platform_source_id)
        except Exception as exc:  # noqa: BLE001
            result = {"ok": False, "status": "exception", "platform": platform, "message": str(exc)}
        dry_runs.append(
            {
                "platform": platform,
                "source_content_id": platform_source_id,
                "ok": bool(result.get("ok")),
                "status": result.get("status") or "",
                "local_id": result.get("local_id") or "",
                "message": result.get("message") or "",
            }
        )

    channels = []
    for channel in channel_report.get("channels") or []:
        status = str(channel.get("status") or "")
        channels.append(
            {
                "platform": channel.get("platform") or "",
                "ok": bool(channel.get("ok")),
                "status": status,
                "class": classify_channel(status, bool(channel.get("ok"))),
                "next_step": channel.get("next_step") or "",
                "account_file": channel.get("account_file") or "",
                "token_file": channel.get("token_file") or "",
                "credential_candidates": channel.get("credential_candidates") or [],
                "client_file_candidates": channel.get("client_file_candidates") or channel.get("credential_candidates") or [],
                "client_secret": channel.get("client_secret") or "",
                "setup_command": channel.get("setup_command") or "",
            }
        )

    report = {
        "ok": True,
        "source": {
            "source_content_id": source_content_id,
            "title": source.get("title") or "",
            "content_type": source.get("content_type") or "",
            "media_count": len(source.get("media_files") or []),
            "cover_count": len(source.get("cover_files") or []),
        },
        "summary": {
            "ready_count": sum(1 for channel in channels if channel["class"] == "ready"),
            "needs_auth_count": sum(1 for channel in channels if channel["class"] == "needs_auth"),
            "code_or_runtime_gap_count": sum(1 for channel in channels if channel["class"] == "code_or_runtime_gap"),
            "dry_run_ok_count": sum(1 for item in dry_runs if item["ok"]),
        },
        "next_auth": next_auth_platform(channels),
        "channels": channels,
        "auth_artifacts": channel_report.get("auth_artifacts") or {},
        "preflight": {
            "ready_count": preflight.get("ready_count"),
            "needs_work_count": preflight.get("needs_work_count"),
            "platforms": [
                {
                    "platform": item.get("platform"),
                    "ready": item.get("ready"),
                    "mode": item.get("mode"),
                    "failed_checks": [
                        check.get("name")
                        for check in item.get("checks") or []
                        if not check.get("ok")
                    ],
                }
                for item in preflight.get("platforms") or []
            ],
        },
        "dry_runs": dry_runs,
    }

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"source: {source_content_id} | {report['source']['title']}")
        print(
            "summary: "
            f"{report['summary']['ready_count']} ready, "
            f"{report['summary']['needs_auth_count']} need auth, "
            f"{report['summary']['code_or_runtime_gap_count']} code/runtime gaps, "
            f"{report['summary']['dry_run_ok_count']} dry-runs ok"
        )
        print("")
        print("channels:")
        for channel in channels:
            print(f"- {channel['platform']}: {channel['class']} ({channel['status']})")
        if report["next_auth"]:
            item = report["next_auth"]
            print("")
            print(f"next auth: {item.get('label') or item.get('platform')} ({item.get('status')})")
            print(f"- dashboard: {item.get('prepare_button')}")
            if item.get("credential_file"):
                print(f"- credential: {item.get('credential_file')}")
            print(f"- command: {item.get('manual_command')}")
        print("")
        print("dry-runs:")
        for item in dry_runs:
            print(f"- {item['platform']}: {'ok' if item['ok'] else 'fail'} ({item['status']})")
    return 0 if report["summary"]["code_or_runtime_gap_count"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
