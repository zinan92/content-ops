#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path


ROOT = Path("/Users/wendy")
DEFAULT_DECISIONS_PATH = ROOT / "park-io/outbox/.system/data/action-decisions.json"
DRAFTS_ROOT = ROOT / "park-io/outbox/drafts"

DECISION_LABELS = {
    "reingest": "重新抓取/转录",
    "skip": "跳过该草稿",
    "merge": "合并到其他主题",
    "drop": "移出生产队列",
    "keep_blocked": "保留 blocked",
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


def normalize_draft_path(raw: str) -> Path:
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = DRAFTS_ROOT / path
    return path.resolve()


def decision_key(draft_path: Path) -> str:
    try:
        return str(draft_path.relative_to(ROOT / "park-io/outbox"))
    except ValueError:
        return str(draft_path)


def update_draft(draft_path: Path, decision: dict) -> None:
    draft = load_json(draft_path)
    if not draft:
        return
    draft["manual_decision"] = decision
    if decision["decision"] in {"skip", "drop"}:
        draft["status"] = "blocked_removed_from_queue"
        draft["workflow_status"] = "manual_removed"
    elif decision["decision"] == "reingest":
        draft["status"] = "needs_reingest"
        draft["workflow_status"] = "manual_reingest"
    elif decision["decision"] == "merge":
        draft["status"] = "needs_merge"
        draft["workflow_status"] = "manual_merge"
    else:
        draft["status"] = draft.get("status") or "blocked"
    write_json(draft_path, draft)


def clear_draft_decision(draft_path: Path, existing: dict | None = None) -> None:
    draft = load_json(draft_path)
    if not draft:
        return
    draft.pop("manual_decision", None)
    previous = (existing or {}).get("previous_draft_state") or {}
    if previous.get("had_status"):
        draft["status"] = previous["status"]
    elif draft.get("status") in {"blocked_removed_from_queue", "needs_reingest", "needs_merge"}:
        draft["status"] = "draft_ready"
    if previous.get("had_workflow_status"):
        draft["workflow_status"] = previous["workflow_status"]
    elif "workflow_status" in draft and draft.get("workflow_status") in {"manual_removed", "manual_reingest", "manual_merge"}:
        draft.pop("workflow_status", None)
    elif draft.get("workflow_status") in {"manual_removed", "manual_reingest", "manual_merge"}:
        draft["workflow_status"] = "blocked_source"
    write_json(draft_path, draft)


def main() -> int:
    parser = argparse.ArgumentParser(description="Record a durable manual decision for an outbox action queue item.")
    parser.add_argument("draft", help="Draft JSON path.")
    parser.add_argument(
        "--decision",
        required=False,
        choices=sorted(DECISION_LABELS),
        help="Manual decision to record.",
    )
    parser.add_argument("--clear", action="store_true", help="Remove the existing manual decision for this draft.")
    parser.add_argument("--reason", default="", help="Short reason for the decision.")
    parser.add_argument("--merge-target", default="", help="Target draft path or note title when decision=merge.")
    parser.add_argument("--source-content-id", default="", help="Optional source id for traceability.")
    parser.add_argument("--operator", default="codex", help="Who made/recorded the decision.")
    parser.add_argument("--dry-run", action="store_true", help="Validate and print the decision without writing files.")
    parser.add_argument("--decisions-path", default=str(DEFAULT_DECISIONS_PATH), help="Decision store path. Defaults to Park-IO outbox state.")
    args = parser.parse_args()

    decisions_path = Path(args.decisions_path).expanduser()
    draft_path = normalize_draft_path(args.draft)
    now = datetime.now().isoformat(timespec="seconds")
    decisions = load_json(decisions_path)
    items = decisions.get("items")
    if not isinstance(items, dict):
        items = {}
    key = decision_key(draft_path)

    if args.clear:
        existing = items.pop(key, None) or items.pop(str(draft_path), None)
        if args.dry_run:
            print(json.dumps({"ok": True, "dry_run": True, "clear": True, "existing": existing, "draft_path": str(draft_path), "decisions_path": str(decisions_path)}, ensure_ascii=False, indent=2))
            return 0
        decisions = {
            "updated_at": now,
            "schema": "park-io.outbox.action-decisions.v1",
            "items": items,
        }
        write_json(decisions_path, decisions)
        clear_draft_decision(draft_path, existing)
        print(json.dumps({"ok": True, "cleared": bool(existing), "draft_path": str(draft_path), "decisions_path": str(decisions_path)}, ensure_ascii=False, indent=2))
        return 0

    if not args.decision:
        parser.error("--decision is required unless --clear is used")

    draft_before = load_json(draft_path)
    decision = {
        "decision": args.decision,
        "label": DECISION_LABELS[args.decision],
        "reason": args.reason.strip(),
        "merge_target": args.merge_target.strip(),
        "source_content_id": args.source_content_id.strip(),
        "operator": args.operator.strip() or "codex",
        "decided_at": now,
        "previous_draft_state": {
            "had_status": "status" in draft_before,
            "status": draft_before.get("status") or "",
            "had_workflow_status": "workflow_status" in draft_before,
            "workflow_status": draft_before.get("workflow_status") or "",
        },
    }

    if args.dry_run:
        print(json.dumps({"ok": True, "dry_run": True, "decision": decision, "draft_path": str(draft_path), "decisions_path": str(decisions_path)}, ensure_ascii=False, indent=2))
        return 0

    items[key] = {
        **decision,
        "draft_path": str(draft_path),
        "key": key,
    }
    decisions = {
        "updated_at": now,
        "schema": "park-io.outbox.action-decisions.v1",
        "items": items,
    }
    write_json(decisions_path, decisions)
    update_draft(draft_path, decision)
    print(json.dumps({"ok": True, "decision": decision, "draft_path": str(draft_path), "decisions_path": str(decisions_path)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
