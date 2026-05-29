#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen


ROOT = Path("/Users/wendy")
CONTENT_OPS = ROOT / "work/content-ops"
REPORTS_DIR = CONTENT_OPS / ".runs/reports"
OUTBOX = ROOT / "park-io/outbox"
DASHBOARD = OUTBOX / "dashboard.html"
WORKFLOW_REPORT = REPORTS_DIR / "outbox-workflow-report.json"
VERIFY_REPORT = REPORTS_DIR / "outbox-workflow-verification.json"
ACTION_QUEUE = REPORTS_DIR / "outbox-action-queue.json"
DECISIONS = OUTBOX / ".system/data/action-decisions.json"
ATTEMPTS = OUTBOX / ".system/data/action-attempts.json"
DOCTOR_JSON = REPORTS_DIR / "outbox-doctor.json"
DOCTOR_MD = REPORTS_DIR / "outbox-doctor.md"


def load_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def check_path(path: Path, kind: str = "file") -> dict:
    exists = path.exists() and (path.is_dir() if kind == "dir" else path.is_file())
    return {"path": str(path), "exists": exists, "ok": exists}


def http_get(url: str, timeout: int = 3) -> dict:
    try:
        with urlopen(url, timeout=timeout) as response:
            return {"ok": 200 <= response.status < 400, "status": response.status, "url": url}
    except URLError as exc:
        return {"ok": False, "status": None, "url": url, "error": str(exc)}


def http_post_json(url: str, payload: dict, timeout: int = 3) -> dict:
    try:
        request = Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"content-type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
            data = json.loads(body) if body else {}
            return {"ok": 200 <= response.status < 400, "status": response.status, "url": url, "body": data}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "status": None, "url": url, "error": str(exc)}


def running_processes() -> dict:
    result = subprocess.run(
        ["ps", "-axo", "pid,command"],
        text=True,
        capture_output=True,
        timeout=10,
    )
    text = result.stdout
    server_rows = [line.strip() for line in text.splitlines() if "workbench_server.py --port 8788" in line and "rg " not in line]
    active_job_rows = [
        line.strip()
        for line in text.splitlines()
        if any(
            token in line
            for token in [
                "run_outbox_action_queue.py",
                "run_outbox_workflow.py",
                "polish_xiaohongshu_drafts.py",
                "quality_xiaohongshu_drafts.py",
                "render_xiaohongshu_cards.py",
            ]
        )
        and "outbox_doctor.py" not in line
        and "rg " not in line
    ]
    return {
        "ok": result.returncode == 0,
        "workbench_server_count": len(server_rows),
        "workbench_server_rows": server_rows,
        "active_job_count": len(active_job_rows),
        "active_job_rows": active_job_rows,
    }


def summarize_queue(queue: dict) -> dict:
    return {
        "total_actions": int(queue.get("total_actions") or 0),
        "resolved_count": int(queue.get("resolved_count") or 0),
        "lane_counts": queue.get("lane_counts") or {},
    }


def recommended_next_action(queue_summary: dict, server: dict, verification: dict, allow_report_failures: bool = False) -> str:
    lane_counts = queue_summary.get("lane_counts") or {}
    if not allow_report_failures and not verification.get("ok"):
        return "先运行 verify_outbox_workflow.py --refresh，修复 workflow 回归问题。"
    if not server.get("ok"):
        return "启动 workbench_server.py --port 8788，然后打开 http://127.0.0.1:8788/dashboard.html。"
    if int(lane_counts.get("manual_reingest_or_drop") or 0):
        return "先处理需要重抓/跳过的 source；这些不能从标题硬编。"
    if int(lane_counts.get("manual_merge_or_drop") or 0):
        return "处理需要合并/丢弃的薄 topic unit。"
    if int(lane_counts.get("auto_repair_candidate") or 0):
        return "先在 dashboard 里预演自动修复，再决定是否执行。"
    return "队列清空后，进入平台草稿审核和发送记录。"


def write_markdown(path: Path, report: dict) -> None:
    lines = [
        "# Park-IO Outbox Doctor",
        "",
        f"Generated: {report.get('generated_at')}",
        f"Status: {'OK' if report.get('ok') else 'Needs attention'}",
        f"Next: {report.get('next_action')}",
        "",
        "## Checks",
        "",
    ]
    for check in report.get("checks") or []:
        lines.append(f"- {'OK' if check.get('ok') else 'FAIL'} `{check.get('name')}`")
    queue = report.get("action_queue") or {}
    lines.extend(
        [
            "",
            "## Action Queue",
            "",
            f"- Total: {queue.get('total_actions')}",
            f"- Resolved: {queue.get('resolved_count')}",
        ]
    )
    for lane, count in sorted((queue.get("lane_counts") or {}).items()):
        lines.append(f"- `{lane}`: {count}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Park-IO outbox production health without mutating state.")
    parser.add_argument("--json", action="store_true", help="Print full JSON report.")
    parser.add_argument("--allow-active-jobs", action="store_true", help="Do not fail if a workflow job is currently running.")
    parser.add_argument("--allow-report-failures", action="store_true", help="Do not fail on existing workflow/verification report status.")
    args = parser.parse_args()

    workflow = load_json(WORKFLOW_REPORT)
    verification = load_json(VERIFY_REPORT)
    queue = load_json(ACTION_QUEUE)
    decisions = load_json(DECISIONS)
    attempts = load_json(ATTEMPTS)
    server = http_get("http://127.0.0.1:8788/dashboard.html")
    api_probe = http_post_json(
        "http://127.0.0.1:8788/api/actions/record-action-decision",
        {"decision": "invalid", "draft_path": "/tmp/noop.json"},
    )
    process_state = running_processes()
    queue_summary = summarize_queue(queue)
    checks = [
        {"name": "outbox_root", **check_path(OUTBOX, "dir")},
        {"name": "dashboard_html", **check_path(DASHBOARD)},
        {"name": "workflow_report_ok", "ok": args.allow_report_failures or bool(workflow.get("ok")), "allow_report_failures": args.allow_report_failures, "generated_at": workflow.get("generated_at")},
        {"name": "verification_report_ok", "ok": args.allow_report_failures or bool(verification.get("ok")), "allow_report_failures": args.allow_report_failures, "generated_at": verification.get("generated_at")},
        {"name": "action_queue_present", "ok": isinstance(queue.get("actions"), list), **queue_summary},
        {"name": "workbench_server_http", **server},
        {
            "name": "workbench_action_api",
            "ok": bool(api_probe.get("body", {}).get("status") == "invalid_decision"),
            "probe_status": api_probe.get("status"),
            "probe_body": api_probe.get("body") or {},
            "error": api_probe.get("error") or "",
        },
        {
            "name": "no_active_local_jobs",
            "ok": args.allow_active_jobs or process_state.get("active_job_count") == 0,
            "allow_active_jobs": args.allow_active_jobs,
            "active_job_count": process_state.get("active_job_count"),
            "active_job_rows": process_state.get("active_job_rows") or [],
        },
    ]
    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "ok": all(check.get("ok") for check in checks),
        "checks": checks,
        "workflow": {
            "ok": workflow.get("ok"),
            "generated_at": workflow.get("generated_at"),
        },
        "verification": {
            "ok": verification.get("ok"),
            "generated_at": verification.get("generated_at"),
        },
        "action_queue": queue_summary,
        "state": {
            "decisions_count": len(decisions.get("items") or {}),
            "attempts_count": len(attempts.get("items") or {}),
        },
        "processes": process_state,
        "next_action": recommended_next_action(queue_summary, server, verification, args.allow_report_failures),
        "reports": {
            "json": str(DOCTOR_JSON),
            "markdown": str(DOCTOR_MD),
        },
    }
    write_json(DOCTOR_JSON, report)
    write_markdown(DOCTOR_MD, report)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(
            json.dumps(
                {
                    "ok": report["ok"],
                    "next_action": report["next_action"],
                    "queue": report["action_queue"],
                    "report": str(DOCTOR_JSON),
                    "markdown": str(DOCTOR_MD),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
