#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path("/Users/wendy")
SCRIPT_DIR = Path(__file__).resolve().parent
RUNS_DIR = ROOT / "work/content-ops/.runs/reports"
REPORT_JSON = RUNS_DIR / "outbox-workflow-report.json"
REPORT_MD = RUNS_DIR / "outbox-workflow-report.md"
AUDIT_JSON = RUNS_DIR / "xiaohongshu-workflow-audit.json"
TRIAGE_JSON = RUNS_DIR / "xiaohongshu-blocked-source-triage.json"
ACTION_QUEUE_JSON = RUNS_DIR / "outbox-action-queue.json"
ACTION_QUEUE_MD = RUNS_DIR / "outbox-action-queue.md"
DASHBOARD = ROOT / "park-io/outbox/dashboard.html"


def run_step(name: str, args: list[str], timeout: int = 900) -> dict:
    result = subprocess.run(
        args,
        text=True,
        capture_output=True,
        cwd=str(SCRIPT_DIR.parents[0]),
        timeout=timeout,
    )
    output = "\n".join(part for part in [result.stdout.strip(), result.stderr.strip()] if part)
    return {
        "step": name,
        "returncode": result.returncode,
        "command": " ".join(args),
        "ok": result.returncode == 0,
        "output_tail": output[-4000:],
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


def write_markdown(path: Path, report: dict) -> None:
    audit = report.get("xiaohongshu_audit") or {}
    triage = report.get("xiaohongshu_triage") or {}
    action_queue = report.get("action_queue") or {}
    lines = [
        "# Park-IO Outbox Workflow Report",
        "",
        f"Generated: {report.get('generated_at')}",
        f"Status: {'OK' if report.get('ok') else 'Needs attention'}",
        f"Dashboard: `{report.get('dashboard')}`",
        "",
        "## Steps",
        "",
    ]
    for step in report.get("steps") or []:
        mark = "OK" if step.get("ok") else "FAIL"
        lines.append(f"- {mark} `{step.get('step')}`")
    lines.extend(
        [
            "",
            "## Xiaohongshu Workflow",
            "",
            f"- Drafts: {audit.get('draft_count', 0)}",
            f"- Passed: {audit.get('passed_count', 0)}",
            f"- Blocked source: {audit.get('blocked_source_count', 0)}",
            f"- Needs work: {audit.get('needs_work_count', 0)}",
            "",
            "## Blocked Source Triage",
            "",
        ]
    )
    for bucket, count in sorted((triage.get("bucket_counts") or {}).items()):
        lines.append(f"- `{bucket}`: {count}")
    lines.extend(["", "## Action Queue", ""])
    for lane, count in sorted((action_queue.get("lane_counts") or {}).items()):
        lines.append(f"- `{lane}`: {count}")
    lines.append(f"- Queue file: `{ACTION_QUEUE_MD}`")
    lines.extend(
        [
            "",
            "Interpretation:",
            "",
            "- `passed`: can be reviewed as a Xiaohongshu draft.",
            "- `blocked_source`: do not publish; return to source transcript/topic plan.",
            "- `skip_or_reingest`: local source is too thin or missing; re-download/transcribe or drop.",
            "- `near_threshold_review`: source exists; try source excerpt repair or merge adjacent unit.",
            "- `merge_or_drop_unit`: topic unit is too thin; merge into stronger note or keep blocked.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the reusable local Park-IO outbox production workflow. No platform publishing."
    )
    parser.add_argument("--min-chars", type=int, default=400, help="Minimum source excerpt chars for Xiaohongshu.")
    parser.add_argument("--verify", action="store_true", help="Run representative Xiaohongshu workflow verification.")
    parser.add_argument("--render-verify", action="store_true", help="When verifying, render representative card images too.")
    parser.add_argument(
        "--upgrade-xhs-v2",
        action="store_true",
        help="Upgrade eligible Xiaohongshu drafts to search-card-v2 before audit. Skips blocked/thin sources.",
    )
    parser.add_argument("--render-upgraded-xhs", action="store_true", help="Render upgraded Xiaohongshu PNG packages.")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero if any Xiaohongshu draft is blocked_source. By default blocked_source is an action queue.",
    )
    args = parser.parse_args()

    steps: list[dict] = []
    steps.append(run_step("build_dashboard_initial", ["python3", str(SCRIPT_DIR / "build_dashboard.py")]))
    if args.upgrade_xhs_v2:
        upgrade_args = [
            "python3",
            str(SCRIPT_DIR / "upgrade_xiaohongshu_search_cards.py"),
            "--apply",
            "--min-chars",
            str(args.min_chars),
            "--only-non-v2",
        ]
        if args.render_upgraded_xhs:
            upgrade_args.append("--render")
        steps.append(run_step("upgrade_xiaohongshu_search_cards_v2", upgrade_args, timeout=7200))
    steps.append(run_step("audit_xiaohongshu", ["python3", str(SCRIPT_DIR / "audit_xiaohongshu_workflow.py")]))
    steps.append(
        run_step(
            "triage_xiaohongshu_blocked",
            ["python3", str(SCRIPT_DIR / "triage_xiaohongshu_blocked_sources.py"), "--min-chars", str(args.min_chars)],
        )
    )
    steps.append(run_step("build_action_queue", ["python3", str(SCRIPT_DIR / "build_outbox_action_queue.py")]))
    steps.append(run_step("build_dashboard_final", ["python3", str(SCRIPT_DIR / "build_dashboard.py")]))
    if args.verify:
        steps.append(run_step("verify_outbox_workflow", ["python3", str(SCRIPT_DIR / "verify_outbox_workflow.py"), "--embedded"], timeout=900))
        verify_args = ["python3", str(SCRIPT_DIR / "verify_xiaohongshu_workflow.py")]
        if args.render_verify:
            verify_args.append("--render")
        steps.append(run_step("verify_xiaohongshu_workflow", verify_args, timeout=1800))

    audit = load_json(AUDIT_JSON)
    triage = load_json(TRIAGE_JSON)
    action_queue = load_json(ACTION_QUEUE_JSON)
    failed_steps = [step for step in steps if not step.get("ok")]
    needs_work = int(audit.get("needs_work_count") or 0)
    blocked = int(audit.get("blocked_source_count") or 0)
    ok = not failed_steps and needs_work == 0 and (blocked == 0 or not args.strict)
    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "ok": ok,
        "strict": args.strict,
        "dashboard": str(DASHBOARD),
        "steps": steps,
        "xiaohongshu_audit": {
            "draft_count": audit.get("draft_count", 0),
            "passed_count": audit.get("passed_count", 0),
            "blocked_source_count": blocked,
            "needs_work_count": needs_work,
            "status_counts": audit.get("status_counts") or {},
        },
        "xiaohongshu_triage": {
            "blocked_count": triage.get("blocked_count", 0),
            "bucket_counts": triage.get("bucket_counts") or {},
        },
        "action_queue": {
            "total_actions": action_queue.get("total_actions", 0),
            "lane_counts": action_queue.get("lane_counts") or {},
        },
        "reports": {
            "audit": str(AUDIT_JSON),
            "triage": str(TRIAGE_JSON),
            "action_queue_json": str(ACTION_QUEUE_JSON),
            "action_queue_md": str(ACTION_QUEUE_MD),
            "workflow_json": str(REPORT_JSON),
            "workflow_md": str(REPORT_MD),
        },
    }
    write_json(REPORT_JSON, report)
    write_markdown(REPORT_MD, report)
    console = {
        "generated_at": report["generated_at"],
        "ok": report["ok"],
        "dashboard": report["dashboard"],
        "steps": [{"step": step["step"], "ok": step["ok"]} for step in steps],
        "xiaohongshu": report["xiaohongshu_audit"],
        "triage": report["xiaohongshu_triage"],
        "action_queue": report["action_queue"],
        "reports": report["reports"],
    }
    print(json.dumps(console, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
