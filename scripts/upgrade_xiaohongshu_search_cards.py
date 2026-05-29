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
DRAFT_DIR = ROOT / "park-io/outbox/drafts/xiaohongshu"
ACTION_QUEUE_JSON = ROOT / "work/content-ops/.runs/reports/outbox-action-queue.json"
REPORT_JSON = ROOT / "work/content-ops/.runs/reports/xiaohongshu-search-card-upgrade.json"
REPORT_MD = ROOT / "work/content-ops/.runs/reports/xiaohongshu-search-card-upgrade.md"


def load_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def source_chars(record: dict) -> int:
    return len("".join(str(record.get("source_excerpt") or "").split()))


def blocked_draft_paths() -> set[str]:
    queue = load_json(ACTION_QUEUE_JSON)
    rows = queue.get("actions") or []
    return {str(row.get("draft_path") or "") for row in rows if row.get("draft_path")}


def run_cmd(name: str, args: list[str], timeout: int = 900) -> dict:
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
        "ok": result.returncode == 0,
        "command": " ".join(args),
        "output_tail": output[-3000:],
    }


def collect_drafts(min_chars: int, only_non_v2: bool, source_id: str | None) -> tuple[list[Path], list[dict]]:
    blocked = blocked_draft_paths()
    eligible: list[Path] = []
    skipped: list[dict] = []
    for path in sorted(DRAFT_DIR.glob("*.json")):
        record = load_json(path)
        if not record:
            skipped.append({"path": str(path), "reason": "bad_json"})
            continue
        if source_id and str(record.get("source_content_id") or "") != source_id:
            continue
        chars = source_chars(record)
        if str(path) in blocked:
            skipped.append({"path": str(path), "reason": "blocked_action_queue", "source_excerpt_chars": chars})
            continue
        if chars < min_chars:
            skipped.append({"path": str(path), "reason": "source_excerpt_too_short", "source_excerpt_chars": chars})
            continue
        if only_non_v2 and record.get("xhs_workflow_version") == "search-card-v2":
            skipped.append({"path": str(path), "reason": "already_v2", "source_excerpt_chars": chars})
            continue
        eligible.append(path)
    return eligible, skipped


def quality_passed(path: Path) -> tuple[bool, list[str]]:
    record = load_json(path)
    quality = record.get("xhs_quality") or {}
    return bool(quality.get("passes_quality_gate")), quality.get("quality_warnings") or []


def process_one(path: Path, engine: str, render: bool, render_only: bool = False) -> dict:
    row: dict = {"path": str(path), "name": path.name, "steps": []}
    if not render_only:
        row["steps"].append(
            run_cmd(
                "polish",
                [
                    "python3",
                    str(SCRIPT_DIR / "polish_xiaohongshu_drafts.py"),
                    str(path),
                    "--engine",
                    engine,
                    "--force",
                ],
                timeout=900,
            )
        )
        if not row["steps"][-1]["ok"]:
            row["status"] = "polish_failed"
            return row

        row["steps"].append(
            run_cmd(
                "quality",
                [
                    "python3",
                    str(SCRIPT_DIR / "quality_xiaohongshu_drafts.py"),
                    str(path),
                    "--force",
                ],
                timeout=900,
            )
        )
        if not row["steps"][-1]["ok"]:
            row["status"] = "quality_command_failed"
            return row

    passed, warnings = quality_passed(path)
    row["passes_quality_gate"] = passed
    row["quality_warnings"] = warnings
    if not passed:
        row["status"] = "quality_gate_failed"
        return row

    if render:
        row["steps"].append(
            run_cmd(
                "render",
                [
                    "python3",
                    str(SCRIPT_DIR / "render_xiaohongshu_cards.py"),
                    str(path),
                    "--style",
                    "dense",
                    "--overwrite",
                ],
                timeout=900,
            )
        )
        if not row["steps"][-1]["ok"]:
            row["status"] = "render_failed"
            return row

    record = load_json(path)
    row["status"] = "upgraded"
    row["title"] = record.get("title")
    row["source_content_id"] = record.get("source_content_id")
    row["xhs_workflow_version"] = record.get("xhs_workflow_version")
    row["cards"] = len(record.get("image_cards") or [])
    row["rendered_images"] = len(record.get("rendered_images") or [])
    return row


def write_markdown(path: Path, report: dict) -> None:
    lines = [
        "# Xiaohongshu Search-Card Upgrade Report",
        "",
        f"Generated: {report.get('generated_at')}",
        f"Mode: {'apply' if report.get('apply') else 'dry-run'}",
        f"Render: {report.get('render')}",
        f"Minimum source chars: {report.get('min_chars')}",
        "",
        "## Summary",
        "",
        f"- Eligible: {report.get('eligible_count')}",
        f"- Processed: {report.get('processed_count')}",
        f"- Upgraded: {report.get('upgraded_count')}",
        f"- Failed: {report.get('failed_count')}",
        f"- Skipped: {report.get('skipped_count')}",
        "",
        "## Processed",
        "",
    ]
    for row in report.get("processed") or []:
        lines.append(f"- `{row.get('status')}` {row.get('name')} -> {row.get('title') or ''}")
        for warning in row.get("quality_warnings") or []:
            lines.append(f"  - warning: {warning}")
    lines.extend(["", "## Skipped", ""])
    for row in report.get("skipped") or []:
        lines.append(f"- `{row.get('reason')}` {row.get('path')} ({row.get('source_excerpt_chars', '')} chars)")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Upgrade eligible Xiaohongshu drafts to search-card-v2 without touching blocked sources."
    )
    parser.add_argument("--apply", action="store_true", help="Actually rewrite drafts. Default is dry-run.")
    parser.add_argument("--render", action="store_true", help="Render PNG packages after quality passes.")
    parser.add_argument("--render-only", action="store_true", help="Only render already-quality-passing eligible drafts.")
    parser.add_argument("--engine", choices=["auto", "claude"], default="auto")
    parser.add_argument("--min-chars", type=int, default=400)
    parser.add_argument("--only-non-v2", action="store_true", help="Skip drafts already marked search-card-v2.")
    parser.add_argument("--source-content-id")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    eligible, skipped = collect_drafts(args.min_chars, args.only_non_v2, args.source_content_id)
    if args.limit:
        eligible = eligible[: args.limit]

    processed: list[dict] = []
    if args.apply:
        for path in eligible:
            print(f"upgrade={path.name}", flush=True)
            try:
                row = process_one(path, args.engine, args.render or args.render_only, args.render_only)
            except Exception as exc:  # noqa: BLE001
                row = {"path": str(path), "name": path.name, "status": "failed", "error": str(exc)[:500]}
            processed.append(row)
            print(json.dumps(row, ensure_ascii=False), flush=True)
        processed.append(
            {
                "name": "build_dashboard",
                "status": "ok" if run_cmd("build_dashboard", ["python3", str(SCRIPT_DIR / "build_dashboard.py")])["ok"] else "failed",
            }
        )

    upgraded_count = len([row for row in processed if row.get("status") == "upgraded"])
    failed_count = len([row for row in processed if row.get("status") not in {"upgraded", "ok"}])
    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "apply": args.apply,
        "render": args.render,
        "render_only": args.render_only,
        "engine": args.engine,
        "min_chars": args.min_chars,
        "only_non_v2": args.only_non_v2,
        "source_content_id": args.source_content_id,
        "eligible_count": len(eligible),
        "processed_count": len(processed),
        "upgraded_count": upgraded_count,
        "failed_count": failed_count,
        "skipped_count": len(skipped),
        "eligible": [str(path) for path in eligible],
        "processed": processed,
        "skipped": skipped,
        "reports": {"json": str(REPORT_JSON), "markdown": str(REPORT_MD)},
    }
    write_json(REPORT_JSON, report)
    write_markdown(REPORT_MD, report)
    print(json.dumps({k: report[k] for k in ["apply", "render", "eligible_count", "upgraded_count", "failed_count", "skipped_count", "reports"]}, ensure_ascii=False, indent=2))
    return 0 if failed_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
