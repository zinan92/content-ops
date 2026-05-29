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
REPORT_PATH = ROOT / "work/content-ops/.runs/reports/xiaohongshu-pipeline-report.json"


def run_step(name: str, args: list[str]) -> dict:
    result = subprocess.run(
        args,
        text=True,
        capture_output=True,
        cwd=str(SCRIPT_DIR.parents[0]),
        timeout=600,
    )
    output = "\n".join(part for part in [result.stdout.strip(), result.stderr.strip()] if part)
    return {
        "step": name,
        "returncode": result.returncode,
        "command": " ".join(args),
        "output": output[-3000:],
        "ok": result.returncode == 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run reusable Xiaohongshu AI production pipeline.")
    parser.add_argument("--source-content-id", required=True, help="Douyin aweme id to process.")
    parser.add_argument("--engine", choices=["auto", "claude", "codex"], default="auto")
    parser.add_argument("--skip-generate", action="store_true")
    parser.add_argument("--skip-render", action="store_true")
    parser.add_argument("--skip-dbs-review", action="store_true",
                        help="Skip Layer 2 dbs 9-dim review step.")
    parser.add_argument("--dbs-review-model", default="sonnet",
                        help="Model for dbs_xhs_review.py (default: sonnet).")
    parser.add_argument("--verify", action="store_true", help="Run workflow verification after the source pipeline.")
    args = parser.parse_args()

    source_id = args.source_content_id
    steps: list[dict] = []

    if not args.skip_generate:
        steps.append(
            run_step(
                "generate_ai_drafts",
                [
                    "python3",
                    str(SCRIPT_DIR / "generate_xiaohongshu_from_content_package.py"),
                    "--source-content-id",
                    source_id,
                    "--overwrite",
                    "--engine",
                    args.engine,
                    "--timeout",
                    "240",
                ],
            )
        )
        if not steps[-1]["ok"]:
            return write_report(source_id, args.engine, steps)

    steps.append(
        run_step(
            "quality",
            [
                "python3",
                str(SCRIPT_DIR / "quality_xiaohongshu_drafts.py"),
                "--source-content-id",
                source_id,
                "--force",
            ],
        )
    )
    if not steps[-1]["ok"]:
        return write_report(source_id, args.engine, steps)

    if not args.skip_dbs_review:
        steps.append(
            run_step(
                "dbs_review",
                [
                    "python3",
                    str(SCRIPT_DIR / "dbs_xhs_review.py"),
                    "--source-content-id",
                    source_id,
                    "--model",
                    args.dbs_review_model,
                ],
            )
        )
        if not steps[-1]["ok"]:
            return write_report(source_id, args.engine, steps)

    if not args.skip_render:
        steps.append(
            run_step(
                "render",
                [
                    "python3",
                    str(SCRIPT_DIR / "render_xiaohongshu_cards.py"),
                    "--source-content-id",
                    source_id,
                    "--style",
                    "dense",
                    "--overwrite",
                ],
            )
        )
        if not steps[-1]["ok"]:
            return write_report(source_id, args.engine, steps)

    steps.append(
        run_step(
            "build_dashboard",
            ["python3", str(SCRIPT_DIR / "build_dashboard.py")],
        )
    )

    if args.verify:
        steps.append(
            run_step(
                "verify_workflow",
                ["python3", str(SCRIPT_DIR / "verify_xiaohongshu_workflow.py")],
            )
        )

    return write_report(source_id, args.engine, steps)


def write_report(source_id: str, engine: str, steps: list[dict]) -> int:
    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_content_id": source_id,
        "engine": engine,
        "ok": all(step["ok"] for step in steps),
        "steps": steps,
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
