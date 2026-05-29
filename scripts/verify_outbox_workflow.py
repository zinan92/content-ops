#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path("/Users/wendy")
SCRIPT_DIR = Path(__file__).resolve().parent
REPORTS_DIR = ROOT / "work/content-ops/.runs/reports"
TMP_DIR = ROOT / "work/content-ops/.runs/tmp/outbox-workflow-verification"
REPORT_JSON = REPORTS_DIR / "outbox-workflow-verification.json"
REPORT_MD = REPORTS_DIR / "outbox-workflow-verification.md"
ACTION_QUEUE_JSON = REPORTS_DIR / "outbox-action-queue.json"
WORKFLOW_JSON = REPORTS_DIR / "outbox-workflow-report.json"
DASHBOARD = ROOT / "park-io/outbox/dashboard.html"
DRAFT_DIR = ROOT / "park-io/outbox/drafts/xiaohongshu"


CORE_SCRIPTS = [
    "build_dashboard.py",
    "build_outbox_action_queue.py",
    "outbox_doctor.py",
    "record_outbox_action_decision.py",
    "run_outbox_action_queue.py",
    "run_outbox_workflow.py",
    "render_xiaohongshu_cards.py",
    "workbench_server.py",
]


def run_cmd(args: list[str], timeout: int = 300) -> dict:
    result = subprocess.run(
        args,
        text=True,
        capture_output=True,
        cwd=str(SCRIPT_DIR.parents[0]),
        timeout=timeout,
    )
    output = "\n".join(part for part in [result.stdout.strip(), result.stderr.strip()] if part)
    return {
        "command": args,
        "returncode": result.returncode,
        "ok": result.returncode == 0,
        "output_tail": output[-3000:],
    }


def load_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def first_sample_draft() -> Path | None:
    for path in sorted(DRAFT_DIR.glob("*.json")):
        record = load_json(path)
        if record.get("status") and not record.get("manual_decision"):
            return path
    return next(iter(sorted(DRAFT_DIR.glob("*.json"))), None)


def verify_py_compile() -> dict:
    args = [sys.executable, "-m", "py_compile"] + [str(SCRIPT_DIR / name) for name in CORE_SCRIPTS]
    row = run_cmd(args)
    row["name"] = "py_compile_core_scripts"
    return row


def verify_decision_roundtrip() -> dict:
    row = {"name": "manual_decision_record_and_clear"}
    sample = first_sample_draft()
    if not sample:
        row["ok"] = False
        row["status":] = "missing_sample_draft"
        return row
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    work_draft = TMP_DIR / sample.name
    decisions_path = TMP_DIR / "action-decisions.json"
    shutil.copy2(sample, work_draft)
    before = load_json(work_draft)
    record = run_cmd(
        [
            sys.executable,
            str(SCRIPT_DIR / "record_outbox_action_decision.py"),
            str(work_draft),
            "--decision",
            "merge",
            "--reason",
            "verification roundtrip",
            "--merge-target",
            "verification target",
            "--source-content-id",
            str(before.get("source_content_id") or "verification-source"),
            "--operator",
            "verifier",
            "--decisions-path",
            str(decisions_path),
        ]
    )
    after_record = load_json(work_draft)
    decisions_after_record = load_json(decisions_path)
    clear = run_cmd(
        [
            sys.executable,
            str(SCRIPT_DIR / "record_outbox_action_decision.py"),
            str(work_draft),
            "--clear",
            "--decisions-path",
            str(decisions_path),
        ]
    )
    after_clear = load_json(work_draft)
    decisions_after_clear = load_json(decisions_path)
    row.update(
        {
            "sample": str(sample),
            "work_draft": str(work_draft),
            "record": record,
            "clear": clear,
            "recorded_manual_decision": bool(after_record.get("manual_decision")),
            "recorded_status": after_record.get("status"),
            "cleared_manual_decision": "manual_decision" not in after_clear,
            "restored_status": after_clear.get("status"),
            "restored_workflow_status": after_clear.get("workflow_status"),
            "decision_items_after_record": len((decisions_after_record.get("items") or {})),
            "decision_items_after_clear": len((decisions_after_clear.get("items") or {})),
        }
    )
    row["ok"] = (
        record.get("ok")
        and clear.get("ok")
        and row["recorded_manual_decision"]
        and row["recorded_status"] == "needs_merge"
        and row["cleared_manual_decision"]
        and row["restored_status"] == before.get("status")
        and row["decision_items_after_record"] == 1
        and row["decision_items_after_clear"] == 0
    )
    return row


def verify_action_queue_dry_run() -> dict:
    before = load_json(ACTION_QUEUE_JSON)
    row = run_cmd([sys.executable, str(SCRIPT_DIR / "run_outbox_action_queue.py"), "--lane", "auto_repair_candidate"])
    row["name"] = "action_queue_dry_run"
    report = load_json(REPORTS_DIR / "outbox-action-queue-execution.json")
    rebuild = run_cmd([sys.executable, str(SCRIPT_DIR / "build_outbox_action_queue.py")])
    after = load_json(ACTION_QUEUE_JSON)
    row["selected_count"] = report.get("selected_count")
    row["mode"] = "dry-run" if report.get("apply") is False else "unknown"
    row["lane_counts_before"] = before.get("lane_counts") or {}
    row["lane_counts_after"] = after.get("lane_counts") or {}
    row["rebuild_ok"] = rebuild.get("ok")
    row["ok"] = (
        bool(row.get("ok"))
        and report.get("apply") is False
        and rebuild.get("ok")
        and row["lane_counts_before"] == row["lane_counts_after"]
    )
    return row


def verify_reports_and_dashboard(embedded: bool = False) -> dict:
    queue = load_json(ACTION_QUEUE_JSON)
    workflow = load_json(WORKFLOW_JSON)
    dashboard_text = DASHBOARD.read_text(encoding="utf-8") if DASHBOARD.exists() else ""
    required_dashboard_tokens = [
        "下一步行动队列",
        "标记重抓",
        "标记跳过",
        "标记合并",
        "标记丢弃",
        "clear-action-decision",
        "预演自动修复",
        "执行自动修复",
    ]
    missing_tokens = [token for token in required_dashboard_tokens if token not in dashboard_text]
    row = {
        "name": "reports_and_dashboard_contract",
        "workflow_ok": workflow.get("ok"),
        "embedded": embedded,
        "queue_total_actions": queue.get("total_actions"),
        "queue_lane_counts": queue.get("lane_counts") or {},
        "queue_has_resolved": "resolved" in queue,
        "dashboard_exists": DASHBOARD.exists(),
        "missing_dashboard_tokens": missing_tokens,
    }
    row["ok"] = (embedded or bool(workflow.get("ok"))) and isinstance(queue.get("actions"), list) and row["queue_has_resolved"] and not missing_tokens
    return row


def verify_doctor(embedded: bool = False) -> dict:
    args = [sys.executable, str(SCRIPT_DIR / "outbox_doctor.py"), "--allow-active-jobs"]
    if embedded:
        args.append("--allow-report-failures")
    row = run_cmd(args)
    row["name"] = "outbox_doctor"
    doctor = load_json(REPORTS_DIR / "outbox-doctor.json")
    row["doctor_ok"] = doctor.get("ok")
    row["next_action"] = doctor.get("next_action") or ""
    row["ok"] = bool(row.get("ok")) and bool(doctor.get("ok")) and bool(row["next_action"])
    return row


def write_markdown(path: Path, report: dict) -> None:
    lines = [
        "# Park-IO Outbox Workflow Verification",
        "",
        f"Generated: {report.get('generated_at')}",
        f"Status: {'OK' if report.get('ok') else 'Needs attention'}",
        "",
        "## Checks",
        "",
    ]
    for check in report.get("checks") or []:
        lines.append(f"- {'OK' if check.get('ok') else 'FAIL'} `{check.get('name')}`")
    lines.extend(["", "## Reports", "", f"- JSON: `{REPORT_JSON}`", f"- Markdown: `{REPORT_MD}`"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Park-IO outbox workflow contracts without publishing.")
    parser.add_argument("--refresh", action="store_true", help="Run run_outbox_workflow.py before verification.")
    parser.add_argument("--embedded", action="store_true", help="Run inside run_outbox_workflow before parent reports are finalized.")
    args = parser.parse_args()

    refresh = None
    if args.refresh:
        refresh = run_cmd([sys.executable, str(SCRIPT_DIR / "run_outbox_workflow.py")], timeout=1200)
    checks = [
        verify_py_compile(),
        verify_decision_roundtrip(),
        verify_action_queue_dry_run(),
        verify_reports_and_dashboard(args.embedded),
        verify_doctor(args.embedded),
    ]
    if refresh:
        refresh["name"] = "refresh_outbox_workflow"
        checks.insert(0, refresh)
    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "ok": all(check.get("ok") for check in checks),
        "checks": checks,
    }
    write_json(REPORT_JSON, report)
    write_markdown(REPORT_MD, report)
    print(json.dumps({"ok": report["ok"], "report": str(REPORT_JSON), "markdown": str(REPORT_MD)}, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
