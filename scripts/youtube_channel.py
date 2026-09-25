#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path("/Users/wendy")
DEFAULT_CLIENT_SECRET_CANDIDATES = [
    ROOT / ".config/park/youtube-oauth.json",
    ROOT / ".credentials/youtube.json",
]
DEFAULT_TOKEN = ROOT / ".config/park/youtube-token.json"
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
# 9/25：内容工作台每天读自己视频的播放量算触达，授权时多要一个只读权限。
READ_SCOPE = "https://www.googleapis.com/auth/youtube.readonly"
AUTH_SCOPES = [*SCOPES, READ_SCOPE]
GCLOUD_ADC_CANDIDATES = [
    ROOT / ".config/gcloud/application_default_credentials.json",
    ROOT / ".config/gcloud/legacy_credentials/zinan92@hotmail.com/adc.json",
]
PROJECT_PYTHON = ROOT / "work/content-ops/.venv/bin/python"


def reexec_in_project_venv() -> None:
    if os.environ.get("PARK_YOUTUBE_NO_REEXEC") == "1":
        return
    if not PROJECT_PYTHON.exists():
        return
    current = Path(sys.executable)
    if current == PROJECT_PYTHON or str(current) == str(PROJECT_PYTHON):
        return
    os.environ["PARK_YOUTUBE_NO_REEXEC"] = "1"
    os.execv(str(PROJECT_PYTHON), [str(PROJECT_PYTHON), *sys.argv])


def emit(payload: dict[str, Any], exit_code: int | None = None) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    raise SystemExit(exit_code if exit_code is not None else (0 if payload.get("ok") else 2))


def dependency_error() -> dict[str, Any] | None:
    missing = []
    for module in [
        "google.oauth2.credentials",
        "google_auth_oauthlib.flow",
        "google.auth.transport.requests",
        "googleapiclient.discovery",
        "googleapiclient.http",
    ]:
        try:
            __import__(module)
        except Exception as exc:  # noqa: BLE001
            missing.append({"module": module, "error": f"{type(exc).__name__}: {exc}"})
    if not missing:
        return None
    return {
        "ok": False,
        "status": "deps_missing",
        "missing": missing,
        "install_command": "cd /Users/wendy/work/content-ops && uv venv .venv && uv pip install --python .venv/bin/python google-api-python-client google-auth google-auth-oauthlib google-auth-httplib2",
    }


def client_secret_candidates(explicit: str = "") -> list[Path]:
    paths = []
    if explicit:
        paths.append(Path(explicit).expanduser())
    env_path = os.environ.get("PARK_YOUTUBE_CLIENT_SECRET")
    if env_path:
        paths.append(Path(env_path).expanduser())
    paths.extend(DEFAULT_CLIENT_SECRET_CANDIDATES)
    seen = set()
    unique = []
    for path in paths:
        key = str(path)
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return unique


def first_existing(paths: list[Path]) -> Path | None:
    for path in paths:
        if path.exists():
            return path
    return None


def adc_reuse_report() -> list[dict[str, Any]]:
    deps = dependency_error()
    if deps:
        return []
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request

    reports = []
    for path in GCLOUD_ADC_CANDIDATES:
        if not path.exists():
            reports.append({"path": str(path), "exists": False, "reusable": False})
            continue
        try:
            creds = Credentials.from_authorized_user_file(str(path), SCOPES)
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
            reports.append(
                {
                    "path": str(path),
                    "exists": True,
                    "reusable": bool(creds.valid),
                    "status": "valid_for_youtube_upload" if creds.valid else "not_valid_for_youtube_upload",
                }
            )
        except Exception as exc:  # noqa: BLE001
            reports.append(
                {
                    "path": str(path),
                    "exists": True,
                    "reusable": False,
                    "status": "not_reusable",
                    "error": f"{type(exc).__name__}: {str(exc)[:220]}",
                }
            )
    return reports


def token_path(explicit: str = "") -> Path:
    if explicit:
        return Path(explicit).expanduser()
    return Path(os.environ.get("PARK_YOUTUBE_TOKEN", str(DEFAULT_TOKEN))).expanduser()


def load_credentials(token_file: Path):
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request

    if not token_file.exists():
        return None, {
            "ok": False,
            "status": "token_missing",
            "token_file": str(token_file),
            "message": "没有 YouTube OAuth token；先运行 auth。",
        }
    # 按 token 自己记着的权限加载：传 SCOPES 会让刷新出来的 token 只剩上传权限。
    creds = Credentials.from_authorized_user_file(str(token_file))
    refreshed = False
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        refreshed = True
        token_file.parent.mkdir(parents=True, exist_ok=True)
        token_file.write_text(creds.to_json(), encoding="utf-8")
        token_file.chmod(0o600)
    if not creds.valid:
        return None, {
            "ok": False,
            "status": "token_invalid",
            "token_file": str(token_file),
            "has_refresh_token": bool(creds.refresh_token),
            "message": "YouTube OAuth token 不可用；请重新运行 auth。",
        }
    return creds, {"ok": True, "status": "token_valid", "token_file": str(token_file), "refreshed": refreshed}


def check(args: argparse.Namespace) -> dict[str, Any]:
    deps = dependency_error()
    if deps:
        return deps
    token_file = token_path(args.token)
    secret = first_existing(client_secret_candidates(args.client_secret))
    if not secret:
        return {
            "ok": False,
            "status": "oauth_client_missing",
            "token_file": str(token_file),
            "credential_candidates": [str(path) for path in client_secret_candidates(args.client_secret)],
            "gcloud_adc": adc_reuse_report(),
            "message": "缺 Google OAuth desktop client JSON；需要先放到候选路径之一。",
        }
    creds, status = load_credentials(token_file)
    if not creds:
        status.update(
            {
                "client_secret": str(secret),
                "credential_candidates": [str(path) for path in client_secret_candidates(args.client_secret)],
                "next_step": "运行 auth 生成 YouTube token。",
            }
        )
        return status
    status.update({"client_secret": str(secret), "checked_at": datetime.now(timezone.utc).isoformat()})
    return status


def auth(args: argparse.Namespace) -> dict[str, Any]:
    deps = dependency_error()
    if deps:
        return deps
    from google_auth_oauthlib.flow import InstalledAppFlow

    secret = first_existing(client_secret_candidates(args.client_secret))
    if not secret:
        return {
            "ok": False,
            "status": "oauth_client_missing",
            "credential_candidates": [str(path) for path in client_secret_candidates(args.client_secret)],
            "gcloud_adc": adc_reuse_report(),
            "message": "缺 Google OAuth desktop client JSON；请从 Google Cloud Console 下载 OAuth client 后放到候选路径。",
        }
    token_file = token_path(args.token)
    flow = InstalledAppFlow.from_client_secrets_file(str(secret), AUTH_SCOPES)
    creds = flow.run_local_server(host="127.0.0.1", port=args.port, open_browser=True)
    token_file.parent.mkdir(parents=True, exist_ok=True)
    token_file.write_text(creds.to_json(), encoding="utf-8")
    token_file.chmod(0o600)
    return {
        "ok": True,
        "status": "token_saved",
        "client_secret": str(secret),
        "token_file": str(token_file),
        "scopes": AUTH_SCOPES,
        "message": "YouTube 授权好了，可以关掉浏览器那一页。",
    }


def stats(args: argparse.Namespace) -> dict[str, Any]:
    """自己频道最近的视频和播放量（只读）。"""
    deps = dependency_error()
    if deps:
        return deps
    creds, status = load_credentials(token_path(args.token))
    if not creds:
        return status
    if READ_SCOPE not in (creds.scopes or []):
        return {"ok": False, "status": "needs_reauth", "message": "YouTube 授权里还没有「查看」权限，重新授权一次（auth）。"}
    from googleapiclient.discovery import build

    youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)
    channels = youtube.channels().list(part="contentDetails", mine=True).execute().get("items") or []
    if not channels:
        return {"ok": True, "items": []}
    uploads = channels[0]["contentDetails"]["relatedPlaylists"]["uploads"]
    ids: list[str] = []
    page = None
    while len(ids) < args.limit:
        res = youtube.playlistItems().list(part="contentDetails", playlistId=uploads, maxResults=50, pageToken=page).execute()
        ids += [i["contentDetails"]["videoId"] for i in res.get("items") or []]
        page = res.get("nextPageToken")
        if not page:
            break
    items = []
    for start in range(0, min(len(ids), args.limit), 50):
        res = youtube.videos().list(part="snippet,statistics", id=",".join(ids[start:start + 50])).execute()
        for v in res.get("items") or []:
            items.append({"id": v["id"], "title": v["snippet"].get("title", ""), "publishedAt": v["snippet"].get("publishedAt"),
                          "views": int((v.get("statistics") or {}).get("viewCount") or 0)})
    return {"ok": True, "items": items}


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def upload(args: argparse.Namespace) -> dict[str, Any]:
    deps = dependency_error()
    if deps:
        return deps
    video = Path(args.video).expanduser()
    if not video.exists():
        return {"ok": False, "status": "video_missing", "video": str(video)}
    title = args.title.strip()
    description = args.description.strip()
    if args.draft_json:
        draft = read_json(Path(args.draft_json).expanduser())
        title = title or str(draft.get("title") or "").strip()
        description = description or str(draft.get("body") or draft.get("description") or "").strip()
    if not title:
        title = video.stem[:90]
    if args.dry_run:
        return {
            "ok": True,
            "status": f"dry_run_{args.privacy_status}_upload_ready",
            "video": str(video),
            "title": title,
            "description_chars": len(description),
            "privacy_status": args.privacy_status,
            "message": f"dry-run: 会上传为 {args.privacy_status}。",
        }
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    token_file = token_path(args.token)
    creds, status = load_credentials(token_file)
    if not creds:
        return status
    youtube = build("youtube", "v3", credentials=creds)
    body = {
        "snippet": {
            "title": title[:100],
            "description": description[:5000],
            "categoryId": args.category_id,
            "tags": [tag for tag in args.tags.split(",") if tag.strip()][:15],
        },
        "status": {
            "privacyStatus": args.privacy_status,
            "selfDeclaredMadeForKids": False,
        },
    }
    media = MediaFileUpload(str(video), chunksize=-1, resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    while response is None:
        _status, response = request.next_chunk()
    video_id = response.get("id")
    return {
        "ok": True,
        "status": f"{args.privacy_status}_uploaded",
        "video_id": video_id,
        "url": f"https://studio.youtube.com/video/{video_id}/edit" if video_id else "",
        "privacy_status": args.privacy_status,
        "title": title[:100],
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "message": "已公开发布到 YouTube。" if args.privacy_status == "public" else f"已上传为 YouTube {args.privacy_status} 视频。",
    }


def upload_private(args: argparse.Namespace) -> dict[str, Any]:
    args.privacy_status = "private"
    return upload(args)


def main() -> None:
    reexec_in_project_venv()
    parser = argparse.ArgumentParser(description="Park-IO YouTube private upload channel.")
    parser.add_argument("--client-secret", default="")
    parser.add_argument("--token", default="")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("check", help="Check YouTube OAuth client/token readiness.")

    auth_parser = sub.add_parser("auth", help="Run local browser OAuth and save token.")
    auth_parser.add_argument("--port", type=int, default=8095)

    stats_parser = sub.add_parser("stats", help="List my recent videos with view counts (read-only).")
    stats_parser.add_argument("--limit", type=int, default=200)

    upload_parser = sub.add_parser("upload", help="Upload one video.")
    upload_parser.add_argument("--video", required=True)
    upload_parser.add_argument("--draft-json", default="")
    upload_parser.add_argument("--title", default="")
    upload_parser.add_argument("--description", default="")
    upload_parser.add_argument("--tags", default="")
    upload_parser.add_argument("--category-id", default="28")
    upload_parser.add_argument("--privacy-status", choices=["public", "private", "unlisted"], default="private")
    upload_parser.add_argument("--dry-run", action="store_true")

    private_parser = sub.add_parser("upload-private", help="Upload one video as private.")
    private_parser.add_argument("--video", required=True)
    private_parser.add_argument("--draft-json", default="")
    private_parser.add_argument("--title", default="")
    private_parser.add_argument("--description", default="")
    private_parser.add_argument("--tags", default="")
    private_parser.add_argument("--category-id", default="28")
    private_parser.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()
    if args.command == "check":
        emit(check(args))
    if args.command == "auth":
        emit(auth(args))
    if args.command == "stats":
        emit(stats(args))
    if args.command == "upload":
        emit(upload(args))
    if args.command == "upload-private":
        emit(upload_private(args))
    emit({"ok": False, "status": "unknown_command"})


if __name__ == "__main__":
    main()
