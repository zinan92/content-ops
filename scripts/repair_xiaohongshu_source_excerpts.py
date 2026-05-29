#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import re
from datetime import datetime
from pathlib import Path


ROOT = Path("/Users/wendy")
SCRIPT_DIR = Path(__file__).resolve().parent
DRAFT_DIR = ROOT / "park-io/outbox/drafts/xiaohongshu"
ASSETS_PATH = ROOT / "park-io/outbox/.system/data/assets.json"
REPORT_PATH = ROOT / "work/content-ops/.runs/reports/xiaohongshu-source-excerpt-repair.json"


def load_generate_module():
    path = SCRIPT_DIR / "generate_repurpose_drafts.py"
    spec = importlib.util.spec_from_file_location("generate_repurpose_drafts", path)
    if not spec or not spec.loader:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GEN = load_generate_module()


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def chinese_len(text: str) -> int:
    return len(re.sub(r"\s+", "", text or ""))


def load_assets_by_source_id() -> dict[str, dict]:
    assets = json.loads(ASSETS_PATH.read_text(encoding="utf-8")) if ASSETS_PATH.exists() else []
    return {str(asset.get("source_content_id") or ""): asset for asset in assets}


def unit_index(record: dict) -> int:
    raw_index = record.get("draft_index")
    if isinstance(raw_index, int) and raw_index > 0:
        return raw_index
    local_id = str(record.get("local_id") or "")
    match = re.search(r"-(\d+)$", local_id)
    if match:
        return int(match.group(1))
    return 1


def repair_one(path: Path, assets_by_source_id: dict[str, dict], min_chars: int, force: bool) -> dict:
    record = load_json(path)
    if not record:
        return {"path": str(path), "status": "bad_json"}
    current_chars = chinese_len(str(record.get("source_excerpt") or ""))
    if current_chars >= min_chars and not force:
        return {"path": str(path), "status": "skipped", "source_excerpt_chars": current_chars}
    source_id = str(record.get("source_content_id") or "")
    asset = assets_by_source_id.get(source_id)
    if not asset:
        return {"path": str(path), "status": "missing_asset", "source_content_id": source_id}

    units = GEN.xhs_units_for_asset(asset)
    if not units:
        return {"path": str(path), "status": "no_units", "source_content_id": source_id}
    idx = max(1, min(unit_index(record), len(units)))
    unit = units[idx - 1]
    text = str(unit.get("text") or "")
    new_chars = chinese_len(text)
    if new_chars <= current_chars and not force:
        return {
            "path": str(path),
            "status": "not_improved",
            "source_content_id": source_id,
            "source_excerpt_chars": current_chars,
            "candidate_chars": new_chars,
            "unit_index": idx,
        }

    record["source_transcript_json"] = asset.get("transcript_json") or record.get("source_transcript_json") or ""
    record["source_transcript_md"] = asset.get("transcript_md") or record.get("source_transcript_md") or ""
    record["source_organized_transcript_json"] = asset.get("organized_transcript_json") or record.get("source_organized_transcript_json") or ""
    record["source_organized_transcript_md"] = asset.get("organized_transcript_md") or record.get("source_organized_transcript_md") or ""
    record["source_transcript_chars"] = asset.get("transcript_chars") or record.get("source_transcript_chars") or 0
    record["source_organized_transcript_chars"] = asset.get("organized_transcript_chars") or record.get("source_organized_transcript_chars") or 0
    record["xhs_count_for_asset"] = len(units)
    record["source_unit_title"] = unit.get("unit_title") or record.get("source_unit_title")
    record["source_unit_start_s"] = unit.get("start_s")
    record["source_unit_end_s"] = unit.get("end_s")
    record["source_excerpt"] = text
    record["source_excerpt_repaired_at"] = datetime.now().isoformat(timespec="seconds")
    record["source_excerpt_repair"] = {
        "method": "xhs_units_for_asset",
        "unit_index": idx,
        "previous_chars": current_chars,
        "new_chars": new_chars,
    }
    write_json(path, record)
    return {
        "path": str(path),
        "status": "repaired",
        "source_content_id": source_id,
        "unit_index": idx,
        "previous_chars": current_chars,
        "new_chars": new_chars,
        "source_unit_title": record.get("source_unit_title") or "",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Repair Xiaohongshu draft source_excerpt from current Douyin transcript units.")
    parser.add_argument("draft", nargs="?", help="Optional single draft JSON path.")
    parser.add_argument("--source-content-id")
    parser.add_argument("--min-chars", type=int, default=400)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    assets_by_source_id = load_assets_by_source_id()
    if args.draft:
        paths = [Path(args.draft).expanduser()]
    else:
        paths = sorted(DRAFT_DIR.glob("*.json"))
    if args.source_content_id and not args.draft:
        paths = [path for path in paths if str(load_json(path).get("source_content_id") or "") == args.source_content_id]

    rows = [repair_one(path, assets_by_source_id, args.min_chars, args.force) for path in paths]
    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "min_chars": args.min_chars,
        "items": rows,
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    write_json(REPORT_PATH, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
