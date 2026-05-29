#!/usr/bin/env python3
"""Layer 1 hard-fail quality gate for Xiaohongshu drafts.

Deterministic, cheap, string-based checks only. Catches problems that LLM
review (Layer 2, dbs_xhs_review.py) can miss or confuse:

- Instruction / oral / internal-ops marker leaks
- Card count, card length bounds, repeated sentences, transcript overlap
- Required structure presence: note_brief, card_plan, xhs_format

This layer does NOT score, infer topics, generate title candidates, or judge
semantic quality (real pain, credibility anchor, suspense, cognitive gap,
etc.). Those belong to dbs_xhs_review.py.

Contract preserved for downstream consumers (build_dashboard, audit, verify,
triage):
    xhs_quality.passes_quality_gate : bool
    xhs_quality.quality_warnings    : list[str]
    xhs_quality.recommended_title   : str (may be empty; populated by Layer 2)
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path("/Users/wendy")
DRAFT_DIR = ROOT / "park-io/outbox/drafts/xiaohongshu"
REPORT_PATH = ROOT / "work/content-ops/.runs/reports/xiaohongshu-quality-report.json"

INSTRUCTION_MARKERS = [
    "建议结构",
    "核心原话",
    "改写要求",
    "这条可以拆成",
    "适合小红书的处理方式",
    "结论先行，6个短段落",
    "Instruction",
    "instruction",
]

INTERNAL_OPS_MARKERS = [
    "这张卡必须帮助读者做判断",
    "如果没有例子和边界",
    "好的卡片要让读者知道自己下一步该检查什么",
    "卡片应该",
    "quality gate",
]

ORAL_TRANSCRIPT_MARKERS = [
    "然后呢",
    "就是说",
    "对吧",
    "啊",
    "嗯",
    "呃",
    "我刚刚",
    "这个这个",
    "这些这些",
]

REQUIRED_CARD_ROLES_BY_TEMPLATE: dict[str, frozenset[str]] = {
    "suspense_first": frozenset({"cover", "conflict", "example", "reasoning", "method"}),
}
DEFAULT_REQUIRED_CARD_ROLES = frozenset({"cover", "misunderstanding", "reframe", "reasoning", "method"})


def required_card_roles(template_kind: str) -> frozenset[str]:
    return REQUIRED_CARD_ROLES_BY_TEMPLATE.get(template_kind, DEFAULT_REQUIRED_CARD_ROLES)

MIN_CARDS = 7
MIN_CARD_CHARS = 70
MAX_CARD_CHARS = 260
MAX_TITLE_CHARS = 20
MIN_SOURCE_EXCERPT_CHARS = 400
REPEATED_SENTENCE_THRESHOLD = 3
REPEATED_SENTENCE_MIN_LEN = 18
OVERLAP_FRAGMENT_MIN_LEN = 28
OVERLAP_PREFIX_LEN = 45
OVERLAP_TRIGGER_COUNT = 2

LAYER1_VERSION = "v3"
QUALITY_ENGINE = "layer1-hard-fail"
WORKFLOW_VERSION = "search-card-v2"

LAYER2_PRESERVED_FIELDS = (
    "recommended_title",
    "recommended_title_formula_id",
    "recommended_title_formula_name",
    "title_candidates",
    "opening_hook",
    "first_card_hook",
    "content_diagnosis",
    "dbs_review",
)


def load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def chinese_len(text: str) -> int:
    return len(re.sub(r"\s+", "", text or ""))


def sentence_fragments(text: str) -> list[str]:
    fragments = re.split(r"[。！？!?；;\n]+", text or "")
    return [frag.strip() for frag in fragments if len(frag.strip()) >= 8]


def marker_leaks(text: str, markers: list[str]) -> list[str]:
    return [m for m in markers if m in text]


def card_length_summary(cards: list[Any]) -> tuple[int, int, list[int]]:
    lengths = [chinese_len(str(c)) for c in cards if str(c).strip()]
    too_thin = sum(1 for length in lengths if length < MIN_CARD_CHARS)
    too_long = sum(1 for length in lengths if length > MAX_CARD_CHARS)
    return too_thin, too_long, lengths


def card_role_set(card_plan: list[Any]) -> frozenset[str]:
    roles: set[str] = set()
    for row in card_plan or []:
        if isinstance(row, dict) and row.get("role"):
            roles.add(str(row["role"]))
    return frozenset(roles)


def has_repeated_card_sentence(cards: list[Any]) -> bool:
    counts: dict[str, int] = {}
    for card in cards:
        for sentence in re.split(r"[。！？!?；;]\s*", str(card)):
            sentence = re.sub(r"\s+", " ", sentence or "").strip(" ，,.")
            if chinese_len(sentence) < REPEATED_SENTENCE_MIN_LEN:
                continue
            counts[sentence] = counts.get(sentence, 0) + 1
    return any(count >= REPEATED_SENTENCE_THRESHOLD for count in counts.values())


def has_transcript_overlap(record: dict[str, Any]) -> bool:
    source = str(record.get("source_excerpt") or "")
    cards = [str(c) for c in record.get("image_cards") or [] if str(c).strip()]
    if not source or not cards:
        return False
    fragments = sentence_fragments(source)
    if not fragments:
        return False
    risky = 0
    for card in cards:
        norm_card = re.sub(r"\s+", "", card)
        for frag in fragments:
            norm_frag = re.sub(r"\s+", "", frag)
            if chinese_len(norm_frag) < OVERLAP_FRAGMENT_MIN_LEN:
                continue
            if (
                norm_frag[:OVERLAP_PREFIX_LEN] in norm_card
                or norm_card[:OVERLAP_PREFIX_LEN] in norm_frag
            ):
                risky += 1
                break
    return risky >= OVERLAP_TRIGGER_COUNT


def check_layer1(record: dict[str, Any]) -> tuple[bool, list[str], dict[str, Any]]:
    fails: list[str] = []
    title = str(record.get("title") or "")
    body = str(record.get("body") or "")
    cards = list(record.get("image_cards") or [])
    source_excerpt = str(record.get("source_excerpt") or "")
    card_plan = record.get("card_plan") or []
    xhs_format = record.get("xhs_format") or {}
    note_brief = record.get("note_brief") or {}

    full_text = "\n".join([title, body, *[str(c) for c in cards]])
    for leak in marker_leaks(full_text, INSTRUCTION_MARKERS):
        fails.append(f"指令痕迹泄漏: {leak!r}")
    for leak in marker_leaks(full_text, INTERNAL_OPS_MARKERS):
        fails.append(f"内部 OPS/QA 文案泄漏: {leak!r}")
    for leak in marker_leaks(full_text, ORAL_TRANSCRIPT_MARKERS):
        fails.append(f"口播残留: {leak!r}")

    if not title:
        fails.append("缺少标题")
    elif chinese_len(title) > MAX_TITLE_CHARS:
        fails.append(f"标题过长: {chinese_len(title)} > {MAX_TITLE_CHARS}")

    card_count = sum(1 for c in cards if str(c).strip())
    if card_count < MIN_CARDS:
        fails.append(f"卡片数量不足: {card_count} < {MIN_CARDS}")
    too_thin, too_long, lengths = card_length_summary(cards)
    if too_thin:
        fails.append(f"{too_thin} 张卡片低于 {MIN_CARD_CHARS} 字（过薄）")
    if too_long:
        fails.append(f"{too_long} 张卡片超过 {MAX_CARD_CHARS} 字（接近 transcript 切片）")

    if not source_excerpt:
        fails.append("缺少 source_excerpt")
    elif chinese_len(source_excerpt) < MIN_SOURCE_EXCERPT_CHARS:
        fails.append(
            f"source_excerpt 过短: {chinese_len(source_excerpt)} < {MIN_SOURCE_EXCERPT_CHARS}"
        )

    if (
        not isinstance(note_brief, dict)
        or not note_brief.get("search_keywords")
        or not note_brief.get("core_claim")
    ):
        fails.append("缺少 note_brief.search_keywords 或 core_claim")

    template_kind = str(record.get("template_kind") or "")
    required_roles = required_card_roles(template_kind)
    if not isinstance(card_plan, list) or len(card_plan) < card_count:
        fails.append("card_plan 缺失或长度小于 image_cards")
    else:
        missing_roles = required_roles - card_role_set(card_plan)
        if missing_roles:
            fails.append(
                f"card_plan 角色不全（模板 {template_kind or 'default'}）: 缺少 {sorted(missing_roles)}"
            )

    if not isinstance(xhs_format, dict) or xhs_format.get("format") != "search_knowledge_cards":
        fails.append("xhs_format.format 必须是 search_knowledge_cards")

    if has_repeated_card_sentence(cards):
        fails.append(f"多张卡片重复同一句话（>= {REPEATED_SENTENCE_THRESHOLD} 次）")
    if has_transcript_overlap(record):
        fails.append("卡片与 source_excerpt 大段重合（疑似逐字搬运）")

    metrics = {
        "card_count": card_count,
        "card_lengths": lengths,
        "title_chars": chinese_len(title),
        "source_excerpt_chars": chinese_len(source_excerpt),
        "card_roles_present": sorted(card_role_set(card_plan)),
    }
    return not fails, fails, metrics


def quality_one(json_path: Path, force: bool = False) -> dict[str, Any]:
    record = load_json(json_path)
    if not record:
        return {"path": str(json_path), "status": "bad_json"}

    existing = record.get("xhs_quality") or {}
    if (
        existing.get("layer1_version") == LAYER1_VERSION
        and not force
    ):
        return {
            "path": str(json_path),
            "status": "exists",
            "title": record.get("title"),
            "passes_quality_gate": existing.get("passes_quality_gate"),
        }

    passes, fails, metrics = check_layer1(record)

    new_quality: dict[str, Any] = {
        "layer1_version": LAYER1_VERSION,
        "quality_engine": QUALITY_ENGINE,
        "checked_at": datetime.now().isoformat(timespec="seconds"),
        "passes_quality_gate": passes,
        "quality_warnings": fails,
        "structural_metrics": metrics,
    }
    for key in LAYER2_PRESERVED_FIELDS:
        if key in existing:
            new_quality[key] = existing[key]
    new_quality.setdefault("recommended_title", "")

    record["xhs_quality"] = new_quality
    record.setdefault("xhs_workflow_version", WORKFLOW_VERSION)
    write_json(json_path, record)
    return {
        "path": str(json_path),
        "status": "checked",
        "title": record.get("title"),
        "passes_quality_gate": passes,
        "warnings": fails,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Layer 1 hard-fail quality gate for Xiaohongshu drafts."
    )
    parser.add_argument("draft", nargs="?", help="Optional explicit draft JSON path.")
    parser.add_argument("--source-content-id")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if args.draft:
        paths = [Path(args.draft).expanduser()]
    else:
        paths = sorted(DRAFT_DIR.glob("*.json"))
    if args.source_content_id and not args.draft:
        paths = [
            p for p in paths
            if load_json(p).get("source_content_id") == args.source_content_id
        ]
    if not args.draft:
        paths = [
            p for p in paths
            if load_json(p).get("status") not in {"superseded", "archived"}
        ]
    if args.limit:
        paths = paths[: args.limit]

    report: list[dict[str, Any]] = []
    for path in paths:
        print(f"layer1_check={path.name}", flush=True)
        try:
            row = quality_one(path, force=args.force)
        except Exception as exc:
            row = {"path": str(path), "status": "failed", "error": str(exc)[:500]}
        report.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"report={REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
