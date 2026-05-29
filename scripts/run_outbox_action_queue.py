#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path("/Users/wendy")
SCRIPT_DIR = Path(__file__).resolve().parent
REPORTS_DIR = ROOT / "work/content-ops/.runs/reports"
QUEUE_JSON = REPORTS_DIR / "outbox-action-queue.json"
EXEC_REPORT_JSON = REPORTS_DIR / "outbox-action-queue-execution.json"
EXEC_REPORT_MD = REPORTS_DIR / "outbox-action-queue-execution.md"
ATTEMPTS_JSON = ROOT / "park-io/outbox/.system/data/action-attempts.json"

ALLOWED_SCRIPTS = {
    str(SCRIPT_DIR / "repair_xiaohongshu_source_excerpts.py"),
    str(SCRIPT_DIR / "run_xiaohongshu_pipeline.py"),
    str(SCRIPT_DIR / "quality_xiaohongshu_drafts.py"),
    str(SCRIPT_DIR / "polish_xiaohongshu_drafts.py"),
    str(SCRIPT_DIR / "render_xiaohongshu_cards.py"),
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


def update_attempts(report: dict) -> None:
    if not report.get("apply"):
        return
    attempts = load_json(ATTEMPTS_JSON)
    items = attempts.get("items")
    if not isinstance(items, dict):
        items = {}
    now = str(report.get("generated_at") or datetime.now().isoformat(timespec="seconds"))
    for item in report.get("items") or []:
        draft_path = str(item.get("draft_path") or "")
        if not draft_path:
            continue
        repair = item.get("repair") or {}
        follow_up = item.get("follow_up") or {}
        items[draft_path] = {
            "updated_at": now,
            "lane": item.get("lane") or "",
            "source_content_id": item.get("source_content_id") or "",
            "draft_title": item.get("draft_title") or "",
            "draft_path": draft_path,
            "repair_ok": bool(repair.get("ok")),
            "repair_reason": repair.get("reason") or "",
            "repair_returncode": repair.get("returncode"),
            "follow_up_ok": bool(follow_up.get("ok")) if follow_up else None,
        }
    write_json(
        ATTEMPTS_JSON,
        {
            "updated_at": now,
            "schema": "park-io.outbox.action-attempts.v1",
            "items": items,
        },
    )


def command_to_args(command: str) -> list[str]:
    args = shlex.split(command)
    if not args:
        return []
    if args[0] == "python3":
        args[0] = sys.executable
    return args


def validate_command(command: str) -> tuple[bool, str]:
    args = command_to_args(command)
    if len(args) < 2:
        return False, "empty_or_short_command"
    script = args[1]
    if script not in ALLOWED_SCRIPTS:
        return False, f"script_not_allowed:{script}"
    return True, ""


def semantic_result(command: str, output: str, default_ok: bool) -> tuple[bool, str]:
    if not default_ok:
        return False, ""
    args = command_to_args(command)
    script_name = Path(args[1]).name if len(args) > 1 else ""
    if script_name == "repair_xiaohongshu_source_excerpts.py":
        min_chars = 0
        if "--min-chars" in args:
            try:
                min_chars = int(args[args.index("--min-chars") + 1])
            except (ValueError, IndexError):
                min_chars = 0
        new_chars = [int(value) for value in re.findall(r'"new_chars":\s*(\d+)', output)]
        if min_chars and new_chars and min(new_chars) < min_chars:
            return False, f"repair_below_min_chars:{min(new_chars)}<{min_chars}"
    if script_name == "quality_xiaohongshu_drafts.py" and '"passes_quality_gate": false' in output:
        return False, "quality_gate_failed"
    return True, ""


def run_command(command: str, apply: bool, timeout: int) -> dict:
    valid, reason = validate_command(command)
    if not valid:
        return {"command": command, "ok": False, "skipped": True, "reason": reason, "returncode": None, "output_tail": ""}
    if not apply:
        return {"command": command, "ok": True, "skipped": True, "reason": "dry_run", "returncode": None, "output_tail": ""}
    result = subprocess.run(
        command_to_args(command),
        text=True,
        capture_output=True,
        cwd=str(SCRIPT_DIR.parents[0]),
        timeout=timeout,
    )
    output = "\n".join(part for part in [result.stdout.strip(), result.stderr.strip()] if part)
    ok, reason = semantic_result(command, output, result.returncode == 0)
    return {
        "command": command,
        "ok": ok,
        "skipped": False,
        "reason": reason,
        "returncode": result.returncode,
        "output_tail": output[-3000:],
    }


def draft_follow_up_commands(draft_path: str) -> list[str]:
    quoted = shlex.quote(draft_path)
    return [
        f"python3 {SCRIPT_DIR / 'polish_xiaohongshu_drafts.py'} {quoted} --engine auto --force",
        f"python3 {SCRIPT_DIR / 'quality_xiaohongshu_drafts.py'} {quoted} --force",
        f"python3 {SCRIPT_DIR / 'render_xiaohongshu_cards.py'} {quoted} --style dense --overwrite",
    ]


def run_follow_up(action: dict, apply: bool, timeout: int) -> dict:
    draft_path = str(action.get("draft_path") or "")
    commands = draft_follow_up_commands(draft_path) if draft_path else []
    if not commands and action.get("follow_up_command"):
        commands = [str(action.get("follow_up_command") or "")]
    steps = [run_command(command, apply, timeout) for command in commands]
    return {
        "ok": all(step.get("ok") for step in steps),
        "scoped_to": draft_path or "source",
        "steps": steps,
    }


def select_actions(queue: dict, lane: str, limit: int | None, priorities: set[int]) -> list[dict]:
    rows = [row for row in queue.get("actions") or [] if row.get("lane") == lane]
    if priorities:
        rows = [row for row in rows if int(row.get("priority") or 0) in priorities]
    if limit is not None:
        rows = rows[:limit]
    return rows


def write_markdown(path: Path, report: dict) -> None:
    lines = [
        "# Park-IO Outbox Action Queue Execution",
        "",
        f"Generated: {report.get('generated_at')}",
        f"Mode: {'apply' if report.get('apply') else 'dry-run'}",
        f"Lane: `{report.get('lane')}`",
        f"Selected actions: {report.get('selected_count')}",
        f"Status: {'OK' if report.get('ok') else 'Needs attention'}",
        "",
        "## Items",
        "",
    ]
    for row in report.get("items") or []:
        lines.extend(
            [
                f"### {row.get('priority')}. {row.get('draft_title')}",
                "",
                f"- Source: `{row.get('source_content_id')}`",
                f"- Draft: `{row.get('draft_path')}`",
                f"- Repair: {'OK' if row.get('repair', {}).get('ok') else 'FAIL'} ({row.get('repair', {}).get('reason') or row.get('repair', {}).get('returncode')})",
            ]
        )
        if row.get("follow_up"):
            follow_up = row.get("follow_up", {})
            lines.append(f"- Follow-up: {'OK' if follow_up.get('ok') else 'FAIL'} ({follow_up.get('scoped_to')})")
            for step in follow_up.get("steps") or []:
                lines.append(f"  - `{Path(str(step.get('command') or '').split()[1]).name if step.get('command') else 'command'}`: {'OK' if step.get('ok') else 'FAIL'} ({step.get('reason') or step.get('returncode')})")
        lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Safely execute selected Park-IO outbox action queue items.")
    parser.add_argument("--lane", default="auto_repair_candidate", help="Queue lane to execute.")
    parser.add_argument("--priority", action="append", type=int, help="Run only this priority. Can be repeated.")
    parser.add_argument("--limit", type=int, help="Limit selected actions.")
    parser.add_argument("--apply", action="store_true", help="Actually execute commands. Default is dry-run.")
    parser.add_argument("--skip-follow-up", action="store_true", help="Only run repair command, not follow-up pipeline.")
    parser.add_argument("--timeout", type=int, default=900)
    args = parser.parse_args()

    queue = load_json(QUEUE_JSON)
    priorities = set(args.priority or [])
    actions = select_actions(queue, args.lane, args.limit, priorities)
    items: list[dict] = []
    for action in actions:
        repair = run_command(str(action.get("command") or ""), args.apply, args.timeout)
        follow_up = {}
        if action.get("follow_up_command") and not args.skip_follow_up and repair.get("ok"):
            follow_up = run_follow_up(action, args.apply, args.timeout)
        items.append(
            {
                "priority": action.get("priority"),
                "lane": action.get("lane"),
                "source_content_id": action.get("source_content_id"),
                "draft_title": action.get("draft_title"),
                "draft_path": action.get("draft_path"),
                "repair": repair,
                "follow_up": follow_up,
            }
        )
    ok = all(item.get("repair", {}).get("ok") and (not item.get("follow_up") or item.get("follow_up", {}).get("ok")) for item in items)
    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "apply": args.apply,
        "lane": args.lane,
        "selected_count": len(actions),
        "ok": ok,
        "items": items,
    }
    write_json(EXEC_REPORT_JSON, report)
    update_attempts(report)
    write_markdown(EXEC_REPORT_MD, report)
    print(
        json.dumps(
            {
                "ok": ok,
                "mode": "apply" if args.apply else "dry-run",
                "lane": args.lane,
                "selected_count": len(actions),
                "report": str(EXEC_REPORT_JSON),
                "markdown": str(EXEC_REPORT_MD),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
