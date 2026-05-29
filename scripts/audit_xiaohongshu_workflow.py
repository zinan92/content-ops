#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path


ROOT = Path("/Users/wendy")
DRAFT_DIR = ROOT / "park-io/outbox/drafts/xiaohongshu"
REPORT_PATH = ROOT / "work/content-ops/.runs/reports/xiaohongshu-workflow-audit.json"


REQUIRED_NOTE_BRIEF_FIELDS = [
    "search_keywords",
    "search_intent",
    "target_reader",
    "core_claim",
    "cognitive_conflict",
    "source_evidence",
    "reader_payoff",
    "format_rationale",
    "card_chain",
]

ORAL_MARKERS = ["然后呢", "就是说", "对吧", "嗯", "呃", "这个这个", "这些这些"]
INSTRUCTION_MARKERS = ["建议结构", "核心原话", "改写要求", "这条可以拆成", "Instruction", "instruction"]
REQUIRED_CARD_ROLES = {"cover", "misunderstanding", "reframe", "reasoning", "method"}


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def chinese_len(text: str) -> int:
    return len(re.sub(r"\s+", "", text or ""))


def rendered_images(record: dict, path: Path) -> list[str]:
    images = [image for image in record.get("rendered_images") or [] if Path(str(image)).exists()]
    if images:
        return images
    package_dir = Path(str(record.get("rendered_package_dir") or ""))
    if package_dir.exists():
        return [str(item) for item in sorted((package_dir / "images").glob("*.png"))]
    fallback_dir = path.with_suffix("")
    if fallback_dir.exists():
        return [str(item) for item in sorted((fallback_dir / "images").glob("*.png"))]
    return []


def item_issues(record: dict, path: Path, require_images: bool) -> list[str]:
    issues: list[str] = []
    title = str(record.get("title") or "")
    body = str(record.get("body") or "")
    cards = [str(card).strip() for card in record.get("image_cards") or [] if str(card).strip()]
    card_plan = record.get("card_plan") or []
    note_brief = record.get("note_brief") or {}
    xhs_format = record.get("xhs_format") or {}
    quality = record.get("xhs_quality") or {}

    if not title:
        issues.append("missing_title")
    if chinese_len(title) > 24:
        issues.append("title_too_long")
    if chinese_len(body) < 700:
        issues.append("body_too_short")
    if any(marker in body for marker in INSTRUCTION_MARKERS):
        issues.append("body_contains_instruction_markers")
    if len(cards) < 7:
        issues.append("not_enough_image_cards")
    if any(any(marker in card for marker in ORAL_MARKERS) for card in cards):
        issues.append("image_cards_contain_oral_markers")
    if not isinstance(note_brief, dict):
        issues.append("missing_note_brief")
    else:
        for field in REQUIRED_NOTE_BRIEF_FIELDS:
            value = note_brief.get(field)
            if value in (None, "", []):
                issues.append(f"missing_note_brief.{field}")
    if not isinstance(card_plan, list) or len(card_plan) < len(cards):
        issues.append("missing_or_short_card_plan")
    else:
        roles = {str(row.get("role")) for row in card_plan if isinstance(row, dict) and row.get("role")}
        if REQUIRED_CARD_ROLES - roles:
            issues.append("incomplete_card_role_chain")
        for idx, row in enumerate(card_plan[: len(cards)], start=1):
            if not isinstance(row, dict) or not row.get("role") or not row.get("purpose") or not row.get("text"):
                issues.append(f"incomplete_card_plan.{idx}")
                break
    if xhs_format.get("format") != "search_knowledge_cards":
        issues.append("wrong_xhs_format")
    if xhs_format.get("visual_mode") != "light_ppt_text_cards":
        issues.append("wrong_visual_mode")
    if not record.get("template_kind"):
        issues.append("missing_template_kind")
    if not quality.get("passes_quality_gate"):
        issues.append("quality_gate_not_passed")
    if require_images and len(rendered_images(record, path)) < len(cards):
        issues.append("missing_rendered_images")
    return issues


def source_excerpt_chars(record: dict) -> int:
    return chinese_len(str(record.get("source_excerpt") or ""))


def workflow_status(record: dict, issues: list[str]) -> str:
    if not issues:
        return "passed"
    if not record:
        return "needs_work"
    quality = record.get("xhs_quality") or {}
    warnings = quality.get("quality_warnings") or []
    if source_excerpt_chars(record) < 400 or any("source_excerpt" in str(warning) for warning in warnings):
        return "blocked_source"
    return "needs_work"


def audit(paths: list[Path], require_images: bool) -> dict:
    items: list[dict] = []
    issue_counts: Counter[str] = Counter()
    template_counts: Counter[str] = Counter()
    source_counts: defaultdict[str, int] = defaultdict(int)

    for path in paths:
        record = load_json(path)
        if not record:
            issues = ["bad_json"]
            template = "bad_json"
            source_id = ""
            image_count = 0
            source_chars = 0
        else:
            issues = item_issues(record, path, require_images)
            template = str(record.get("template_kind") or "missing")
            source_id = str(record.get("source_content_id") or "")
            image_count = len(rendered_images(record, path))
            source_chars = source_excerpt_chars(record)
        status = workflow_status(record, issues)
        issue_counts.update(issues)
        template_counts[template] += 1
        if source_id:
            source_counts[source_id] += 1
        items.append(
            {
                "path": str(path),
                "filename": path.name,
                "source_content_id": source_id,
                "title": record.get("title") if record else "",
                "template_kind": template,
                "quality_passed": bool((record.get("xhs_quality") or {}).get("passes_quality_gate")) if record else False,
                "quality_warnings": (record.get("xhs_quality") or {}).get("quality_warnings") or [] if record else [],
                "source_excerpt_chars": source_chars,
                "image_cards": len(record.get("image_cards") or []) if record else 0,
                "card_plan": len(record.get("card_plan") or []) if record else 0,
                "rendered_images": image_count,
                "issues": issues,
                "status": status,
            }
        )

    status_counts = Counter(item["status"] for item in items)
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "draft_count": len(paths),
        "passed_count": status_counts.get("passed", 0),
        "blocked_source_count": status_counts.get("blocked_source", 0),
        "needs_work_count": status_counts.get("needs_work", 0),
        "status_counts": dict(status_counts),
        "issue_counts": dict(issue_counts),
        "template_counts": dict(template_counts),
        "source_counts": dict(sorted(source_counts.items())),
        "items": items,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit Xiaohongshu drafts against the reusable search-card workflow.")
    parser.add_argument("draft", nargs="?", help="Optional single Xiaohongshu draft JSON path.")
    parser.add_argument("--source-content-id")
    parser.add_argument("--require-images", action="store_true", help="Require rendered PNG count to match image_cards count.")
    parser.add_argument("--fail-on-issues", action="store_true", help="Fail if any item still needs script/content work. Source-blocked items are reported but not failed.")
    parser.add_argument("--fail-on-blocked", action="store_true", help="Also fail on source-blocked items.")
    args = parser.parse_args()

    if args.draft:
        paths = [Path(args.draft).expanduser()]
    else:
        paths = sorted(DRAFT_DIR.glob("*.json"))
    if args.source_content_id and not args.draft:
        paths = [path for path in paths if str(load_json(path).get("source_content_id") or "") == args.source_content_id]

    report = audit(paths, args.require_images)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.fail_on_issues and report["needs_work_count"]:
        return 1
    if args.fail_on_blocked and report["blocked_source_count"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
