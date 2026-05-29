#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path("/Users/wendy")
SCRIPT_DIR = Path(__file__).resolve().parent
DRAFT_DIR = ROOT / "park-io/outbox/drafts/xiaohongshu"
REPORT_PATH = ROOT / "work/content-ops/.runs/reports/xiaohongshu-workflow-verification.json"
VERIFY_TMP_DIR = ROOT / "work/content-ops/.runs/tmp/xiaohongshu-workflow-verification"

DEFAULT_SAMPLE_SPECS = [
    {
        "source_id": "7615222931199596096",
        "draft": str(DRAFT_DIR / "2026-05-20--100件事99件不赚钱--xiaohongshu-596096-02.json"),
        "expected_template": "trading_expectation",
    },
    {
        "source_id": "7615222931199596096",
        "draft": str(DRAFT_DIR / "2026-05-20--AI的remotion--xiaohongshu-596096-01.json"),
        "expected_template": "ai_visual_workflow",
    },
    {
        "source_id": "7615510060650777892",
        "draft": str(DRAFT_DIR / "2026-05-20--看AI本就是盲人摸象，为什么你不｜拆条2--xiaohongshu-777892-02.json"),
        "expected_template": "ai_adoption_mindset",
    },
    {
        "source_id": "7624875914207202596",
        "draft": str(DRAFT_DIR / "2026-05-20--能听懂的人也算是top0.01%｜拆条2--xiaohongshu-202596-02.json"),
        "expected_template": "agent_architecture",
    },
    {
        "source_id": "7612227309759646986",
        "draft": str(DRAFT_DIR / "2026-05-20--token消耗分析--xiaohongshu-646986-05.json"),
        "expected_template": "agent_cost_analysis",
    },
    {
        "source_id": "7615222931199596096",
        "draft": str(DRAFT_DIR / "2026-05-20--交易前先想清楚怎么输--xiaohongshu-596096-03.json"),
        "expected_template": "focus_ant_theory",
    },
    {
        "source_id": "7615222931199596096",
        "draft": str(DRAFT_DIR / "2026-05-20--第一性原理才是护城河--xiaohongshu-596096-04.json"),
        "expected_template": "decision_framework",
    },
    {
        "source_id": "7621048932151414054",
        "draft": str(DRAFT_DIR / "2026-05-20--专注--xiaohongshu-414054-06.json"),
        "expected_template": "life_choice",
    },
    {
        "source_id": "7621048932151414054",
        "draft": str(DRAFT_DIR / "2026-05-20--承担风险--xiaohongshu-414054-05.json"),
        "expected_template": "ai_workflow",
    },
    {
        "source_id": "7621048932151414054",
        "draft": str(DRAFT_DIR / "2026-05-20--建立护城河--xiaohongshu-414054-10.json"),
        "expected_template": "content_business",
    },
]


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def first_draft_for_source(source_id: str) -> Path | None:
    rows = []
    for path in sorted(DRAFT_DIR.glob("*.json")):
        record = load_json(path)
        if str(record.get("source_content_id") or "") == source_id:
            rows.append(path)
    return rows[0] if rows else None


def run_cmd(args: list[str]) -> tuple[int, str]:
    result = subprocess.run(
        args,
        text=True,
        capture_output=True,
        cwd=str(SCRIPT_DIR.parents[0]),
        timeout=300,
    )
    output = "\n".join(part for part in [result.stdout.strip(), result.stderr.strip()] if part)
    return result.returncode, output


def verify_source(spec: dict, render: bool) -> dict:
    source_id = str(spec.get("source_id") or "")
    row: dict = {"source_content_id": source_id, "expected_template": spec.get("expected_template") or ""}
    draft_path = Path(spec["draft"]).expanduser() if spec.get("draft") else first_draft_for_source(source_id)
    if not draft_path:
        row["status"] = "missing_draft"
        return row

    row["original_draft_path"] = str(draft_path)
    VERIFY_TMP_DIR.mkdir(parents=True, exist_ok=True)
    work_path = VERIFY_TMP_DIR / draft_path.name
    shutil.copy2(draft_path, work_path)
    md_path = draft_path.with_suffix(".md")
    if md_path.exists():
        shutil.copy2(md_path, work_path.with_suffix(".md"))
    row["draft_path"] = str(work_path)
    polish_code, polish_output = run_cmd(
        [
            "python3",
            str(SCRIPT_DIR / "polish_xiaohongshu_drafts.py"),
            str(work_path),
            "--source-content-id",
            source_id,
            "--force",
            "--limit",
            "1",
            "--engine",
            "local",
        ]
    )
    row["polish_returncode"] = polish_code
    row["polish_output"] = polish_output[-1200:]
    if polish_code != 0:
        row["status"] = "polish_failed"
        return row

    quality_code, quality_output = run_cmd(
        [
            "python3",
            str(SCRIPT_DIR / "quality_xiaohongshu_drafts.py"),
            str(work_path),
            "--source-content-id",
            source_id,
            "--force",
            "--limit",
            "1",
        ]
    )
    row["quality_returncode"] = quality_code
    row["quality_output"] = quality_output[-1200:]
    if quality_code != 0:
        row["status"] = "quality_failed"
        return row

    record = load_json(work_path)
    quality = record.get("xhs_quality") or {}
    row["title"] = record.get("title")
    row["template_kind"] = record.get("template_kind")
    row["cards"] = len(record.get("image_cards") or [])
    row["body_chars"] = len("".join(str(record.get("body") or "").split()))
    row["passes_quality_gate"] = bool(quality.get("passes_quality_gate"))
    row["quality_warnings"] = quality.get("quality_warnings") or []

    if not row["passes_quality_gate"]:
        row["status"] = "quality_gate_failed"
        return row
    if row["expected_template"] and row["template_kind"] != row["expected_template"]:
        row["status"] = "wrong_template"
        return row

    if render:
        render_code, render_output = run_cmd(
            [
                "python3",
                str(SCRIPT_DIR / "render_xiaohongshu_cards.py"),
                str(work_path),
                "--style",
                "dense",
                "--overwrite",
            ]
        )
        row["render_returncode"] = render_code
        row["render_output"] = render_output[-1200:]
        if render_code != 0:
            row["status"] = "render_failed"
            return row
        record = load_json(work_path)
        row["rendered_images"] = len(record.get("rendered_images") or [])

    row["status"] = "passed"
    return row


def verify_renderer_card_only() -> dict:
    row = {"name": "dense_renderer_uses_image_cards_only"}
    spec = importlib.util.spec_from_file_location("render_xiaohongshu_cards", SCRIPT_DIR / "render_xiaohongshu_cards.py")
    if not spec or not spec.loader:
        row["status"] = "import_failed"
        return row
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    pages = module.dense_pages_from_cards(
        "测试标题",
        ["封面\n只来自卡片", "第二张\n仍然只来自卡片"],
        "正文里有一个不该进入图片的 SENTINEL_BODY_TEXT 段落。",
    )
    rendered_text = json.dumps(pages, ensure_ascii=False)
    row["pages"] = len(pages)
    row["status"] = "failed" if "SENTINEL_BODY_TEXT" in rendered_text else "passed"
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify reusable Xiaohongshu local workflow templates.")
    parser.add_argument("--source-content-id", action="append", default=[])
    parser.add_argument("--render", action="store_true")
    args = parser.parse_args()

    specs = [{"source_id": source_id} for source_id in args.source_content_id] if args.source_content_id else DEFAULT_SAMPLE_SPECS
    if VERIFY_TMP_DIR.exists():
        shutil.rmtree(VERIFY_TMP_DIR)
    rows = [verify_source(spec, args.render) for spec in specs]
    regression_checks = [verify_renderer_card_only()]
    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "render": args.render,
        "items": rows,
        "regression_checks": regression_checks,
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if all(row.get("status") == "passed" for row in rows + regression_checks) else 1


if __name__ == "__main__":
    sys.exit(main())
