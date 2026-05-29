#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime
from pathlib import Path


ROOT = Path("/Users/wendy")
REPORTS_DIR = ROOT / "work/content-ops/.runs/reports"
TRIAGE_JSON = REPORTS_DIR / "xiaohongshu-blocked-source-triage.json"
QUEUE_JSON = REPORTS_DIR / "outbox-action-queue.json"
QUEUE_MD = REPORTS_DIR / "outbox-action-queue.md"
EXEC_REPORT_JSON = REPORTS_DIR / "outbox-action-queue-execution.json"
DECISIONS_JSON = ROOT / "park-io/outbox/.system/data/action-decisions.json"
ATTEMPTS_JSON = ROOT / "park-io/outbox/.system/data/action-attempts.json"


BUCKET_ACTION = {
    "near_threshold_review": {
        "lane": "auto_repair_candidate",
        "label": "可自动尝试修复",
        "operator_action": "run_repair_then_pipeline",
    },
    "skip_or_reingest": {
        "lane": "manual_reingest_or_drop",
        "label": "需要重抓或跳过",
        "operator_action": "redownload_transcribe_or_drop",
    },
    "merge_or_drop_unit": {
        "lane": "manual_merge_or_drop",
        "label": "需要合并或丢弃",
        "operator_action": "merge_topic_unit_or_drop",
    },
    "stale_quality_recheck": {
        "lane": "auto_recheck_candidate",
        "label": "可重跑质检",
        "operator_action": "rerun_quality",
    },
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


def repair_command(item: dict, min_chars: int) -> str:
    draft_path = item.get("path") or ""
    return (
        "python3 /Users/wendy/work/content-ops/scripts/repair_xiaohongshu_source_excerpts.py "
        f"'{draft_path}' --min-chars {min_chars} --force"
    )


def polish_command(source_content_id: str) -> str:
    return (
        "python3 /Users/wendy/work/content-ops/scripts/run_xiaohongshu_pipeline.py "
        f"--source-content-id {source_content_id} --engine auto --skip-generate"
    )


def failed_auto_repair_reasons() -> dict[str, str]:
    failed: dict[str, str] = {}
    attempts = load_json(ATTEMPTS_JSON)
    items = attempts.get("items")
    if isinstance(items, dict):
        for draft_path, item in items.items():
            reason = str((item or {}).get("repair_reason") or "")
            if draft_path and reason.startswith("repair_below_min_chars"):
                failed[str(draft_path)] = reason
    report = load_json(EXEC_REPORT_JSON)
    if not report.get("apply"):
        return failed
    for item in report.get("items") or []:
        draft_path = str(item.get("draft_path") or "")
        repair = item.get("repair") or {}
        reason = str(repair.get("reason") or "")
        if draft_path and reason.startswith("repair_below_min_chars"):
            failed[draft_path] = reason
    return failed


def decision_key(draft_path: str) -> str:
    path = Path(draft_path)
    try:
        return str(path.relative_to(ROOT / "park-io/outbox"))
    except ValueError:
        return draft_path


def load_decisions() -> dict[str, dict]:
    data = load_json(DECISIONS_JSON)
    items = data.get("items")
    return items if isinstance(items, dict) else {}


def build_queue() -> dict:
    triage = load_json(TRIAGE_JSON)
    failed_repairs = failed_auto_repair_reasons()
    decisions = load_decisions()
    min_chars = int(triage.get("min_chars") or 400)
    actions: list[dict] = []
    resolved: list[dict] = []
    for index, item in enumerate(triage.get("items") or [], start=1):
        bucket = str(item.get("bucket") or "unknown")
        draft_path = str(item.get("path") or "")
        existing_decision = decisions.get(decision_key(draft_path)) or decisions.get(draft_path)
        if existing_decision:
            resolved.append(
                {
                    "priority": index,
                    "draft_path": draft_path,
                    "draft_title": item.get("draft_title") or item.get("filename") or "",
                    "source_content_id": str(item.get("source_content_id") or ""),
                    "source_title": item.get("source_title") or "",
                    "source_unit_title": item.get("source_unit_title") or "",
                    "source_excerpt_chars": item.get("source_excerpt_chars") or 0,
                    "decision": existing_decision,
                }
            )
            continue
        repair_failure_reason = failed_repairs.get(draft_path)
        if repair_failure_reason and bucket == "near_threshold_review":
            bucket = "merge_or_drop_unit"
        config = BUCKET_ACTION.get(
            bucket,
            {"lane": "manual_investigate", "label": "需要人工检查", "operator_action": "inspect_source_fields"},
        )
        source_id = str(item.get("source_content_id") or "")
        command = ""
        follow_up = ""
        if bucket in {"near_threshold_review", "stale_quality_recheck"}:
            command = repair_command(item, min_chars)
            follow_up = polish_command(source_id) if source_id else ""
        actions.append(
            {
                "priority": index,
                "lane": config["lane"],
                "label": config["label"],
                "operator_action": config["operator_action"],
                "bucket": bucket,
                "source_content_id": source_id,
                "source_title": item.get("source_title") or "",
                "draft_title": item.get("draft_title") or item.get("filename") or "",
                "source_unit_title": item.get("source_unit_title") or "",
                "draft_path": draft_path,
                "source_excerpt_chars": item.get("source_excerpt_chars") or 0,
                "media_count": item.get("media_count") or 0,
                "transcript_chars": item.get("transcript_chars") or 0,
                "reason": (
                    f"{item.get('reason') or ''} 自动修复后仍未达到阈值：{repair_failure_reason}。"
                    if repair_failure_reason
                    else item.get("reason") or ""
                ),
                "next_action": (
                    "自动修复已经尝试过但 source excerpt 仍偏短；请合并相邻 topic unit，或保持 blocked/删除该 draft。"
                    if repair_failure_reason
                    else item.get("next_action") or ""
                ),
                "command": command,
                "follow_up_command": follow_up,
            }
        )
    lane_counts = Counter(row["lane"] for row in actions)
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": str(TRIAGE_JSON),
        "decisions": str(DECISIONS_JSON),
        "attempts": str(ATTEMPTS_JSON),
        "total_actions": len(actions),
        "resolved_count": len(resolved),
        "lane_counts": dict(lane_counts),
        "actions": actions,
        "resolved": resolved,
    }


def write_markdown(path: Path, queue: dict) -> None:
    lines = [
        "# Park-IO Outbox Action Queue",
        "",
        f"Generated: {queue.get('generated_at')}",
        f"Actions: {queue.get('total_actions')}",
        f"Resolved: {queue.get('resolved_count') or 0}",
        "",
        "## Lane Counts",
        "",
    ]
    for lane, count in sorted((queue.get("lane_counts") or {}).items()):
        lines.append(f"- `{lane}`: {count}")
    lanes = [
        ("auto_repair_candidate", "可自动尝试修复"),
        ("auto_recheck_candidate", "可重跑质检"),
        ("manual_reingest_or_drop", "需要重抓或跳过"),
        ("manual_merge_or_drop", "需要合并或丢弃"),
        ("manual_investigate", "需要人工检查"),
    ]
    for lane, title in lanes:
        rows = [row for row in queue.get("actions") or [] if row.get("lane") == lane]
        if not rows:
            continue
        lines.extend(["", f"## {title}", ""])
        for row in rows:
            lines.extend(
                [
                    f"### {row['priority']}. {row['draft_title']}",
                    "",
                    f"- Source: `{row['source_content_id']}` {row['source_title']}",
                    f"- Unit: {row['source_unit_title'] or '(none)'}",
                    f"- Source chars: {row['source_excerpt_chars']}",
                    f"- Reason: {row['reason']}",
                    f"- Draft: `{row['draft_path']}`",
                ]
            )
            if row.get("command"):
                lines.extend(["- Command:", "", "```bash", row["command"], "```"])
            if row.get("follow_up_command"):
                lines.extend(["- Follow up after repair:", "", "```bash", row["follow_up_command"], "```"])
            if not row.get("command"):
                lines.append(f"- Next action: {row['next_action']}")
            lines.append("")
    resolved = queue.get("resolved") or []
    if resolved:
        lines.extend(["", "## 已有人工决策", ""])
        for row in resolved:
            decision = row.get("decision") or {}
            lines.extend(
                [
                    f"### {row.get('priority')}. {row.get('draft_title')}",
                    "",
                    f"- Source: `{row.get('source_content_id')}` {row.get('source_title')}",
                    f"- Unit: {row.get('source_unit_title') or '(none)'}",
                    f"- Decision: `{decision.get('decision')}` {decision.get('label') or ''}",
                    f"- Reason: {decision.get('reason') or '(none)'}",
                    f"- Draft: `{row.get('draft_path')}`",
                    "",
                ]
            )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a human/actionable queue from outbox workflow reports.")
    parser.parse_args()
    queue = build_queue()
    write_json(QUEUE_JSON, queue)
    write_markdown(QUEUE_MD, queue)
    print(json.dumps({"queue": str(QUEUE_JSON), "markdown": str(QUEUE_MD), "total_actions": queue["total_actions"], "lane_counts": queue["lane_counts"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
