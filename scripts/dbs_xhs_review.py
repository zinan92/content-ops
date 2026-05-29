#!/usr/bin/env python3
"""Layer 2 dbs-content style semantic review for Xiaohongshu drafts.

Runs Wendy's 9-dimension checklist via `claude -p` subprocess:

    real_pain, topic_standalone, credibility_anchor, counterintuitive,
    conflict, core_claim, suspense, tension, cognitive_gap

Each dimension scored 0-10 with a one-line reason. `suspense` carries an extra
`structural` flag — true when the low score is locked in by template ordering
(e.g. method card front-loaded), which cannot be fixed by rewording.

Reads from each draft JSON:
    title, body, image_cards, card_plan, source_excerpt,
    source_organized_transcript_md (for credibility-anchor sourcing)

Writes back to `xhs_quality.dbs_review` and to a batch report at
`.runs/reports/xiaohongshu-dbs-review.json`.

Does NOT rewrite copy. Output includes a `first_action` field describing
exactly one concrete edit the human should make next.

Requires Layer 1 (`quality_xiaohongshu_drafts.py`) to pass first — drafts with
hard fails are skipped unless `--include-failed` is set.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path("/Users/wendy")
DRAFT_DIR = ROOT / "park-io/outbox/drafts/xiaohongshu"
REPORT_PATH = ROOT / "work/content-ops/.runs/reports/xiaohongshu-dbs-review.json"

DBS_REVIEW_VERSION = "v1"
DEFAULT_MODEL = "sonnet"
DEFAULT_TIMEOUT_S = 180
DEFAULT_MAX_RETRIES = 1
ORGANIZED_TRANSCRIPT_BUDGET_CHARS = 4000
SOURCE_EXCERPT_BUDGET_CHARS = 2000

DIMENSIONS = (
    "real_pain",
    "topic_standalone",
    "credibility_anchor",
    "counterintuitive",
    "conflict",
    "core_claim",
    "suspense",
    "tension",
    "cognitive_gap",
)

SYSTEM_INSTRUCTION = """你是 dontbesilent 的小红书内容诊断师。

风格纪律：
- 像编辑一样精准。指出具体问题，不说"还不错"。
- 不讨好。内容不行直接说不行。
- 给行动不给建议。「第一步做 X」比「你可以考虑 Y」有用。
- 不帮人写内容，只诊断。

你的输出会被自动解析。必须是纯 JSON，不要 markdown 代码块，不要前后解释文字。"""

RUBRIC = """评分规则（每维 0-10 整数）：

1. real_pain（真实痛点）
   8+ = 击中普世真实痛点，大量人正在经历的具体困境
   5 = 是个痛点但偏抽象/小众
   2- = 没有清晰痛点

2. topic_standalone（话题独立）
   8+ = 没有上下文时，标题+第一段能独立工作，三秒说清主张
   5 = 需要读两段才明白在说什么
   2- = 离开来源无法理解

3. credibility_anchor（可信度锚点）
   8+ = 文中明确交代作者身份/亏过多少/做过什么具体的事
   5 = 有暗示但无具体数字或案例
   2- = 全文零可信度，没说你是谁

4. counterintuitive（反常识）
   8+ = 打破一个广泛流传的常识，主张让人愣一下
   5 = 有点反直觉但已是老生常谈
   2- = 顺着常识在说

5. conflict（冲突）
   8+ = 明确的两方对立，A vs B 一句话讲清
   5 = 有冲突但不够尖锐
   2- = 没有对立

6. core_claim（核心主张）
   8+ = 有一句可以摘抄/背诵的金句，编辑能直接 highlight
   5 = 主张存在但表达散
   2- = 没有清晰主张

7. suspense（悬念）
   8+ = 第一段留住读者继续往下看的钩子，不把结论端完
   5 = 部分悬念，部分剧透
   2- = 第一段就把方法论/结论端完
   structural=true 当低分是因为模板结构（例如方法论卡前置 / cover→misunderstanding→reframe→reasoning→method 这种结论先行模板），这种情况文案改不动，必须换模板。

8. tension（张力）
   计数命中：反差 / 具体动作 / 冲突 / 承诺 / 数字（5 项中命中数）
   8+ = 命中 4 项以上
   5 = 命中 2-3 项
   2- = 命中 0-1 项

9. cognitive_gap（认知落差）
   8+ = 读者看完觉得「我以前完全错了」
   5 = 加深了已有认知但没颠覆
   2- = 读者会觉得「这我知道」"""

OUTPUT_SCHEMA = """输出 JSON 结构（必须严格遵守）：
{
  "scores": {
    "real_pain": {"score": 0, "reason": "一句话"},
    "topic_standalone": {"score": 0, "reason": ""},
    "credibility_anchor": {"score": 0, "reason": ""},
    "counterintuitive": {"score": 0, "reason": ""},
    "conflict": {"score": 0, "reason": ""},
    "core_claim": {"score": 0, "reason": ""},
    "suspense": {"score": 0, "reason": "", "structural": false},
    "tension": {"score": 0, "reason": ""},
    "cognitive_gap": {"score": 0, "reason": ""}
  },
  "total": 0,
  "structural_blockers": [],
  "first_action": "一句具体行动。指明改哪一句、加什么、删什么。不是建议。",
  "verdict": "keep | rewrite | kill"
}

- total = 9 维 score 之和（满分 90）
- structural_blockers = score 维度名数组，凡是 suspense.structural=true 就放入
- verdict 判断：
  - keep: total >= 65 且无 structural_blockers
  - rewrite: total 在 45-64，或有 structural_blockers
  - kill: total < 45"""


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


def read_text(path_str: str | None, budget: int) -> str:
    if not path_str:
        return ""
    path = Path(path_str).expanduser()
    if not path.exists():
        return ""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ""
    return text[:budget]


def render_cards(cards: list[Any]) -> str:
    lines = []
    for idx, card in enumerate(cards, start=1):
        text = re.sub(r"\s+", " ", str(card)).strip()
        if text:
            lines.append(f"{idx}. {text}")
    return "\n".join(lines)


def render_card_plan(card_plan: list[Any]) -> str:
    roles = []
    for row in card_plan or []:
        if isinstance(row, dict) and row.get("role"):
            roles.append(str(row["role"]))
    return " → ".join(roles) if roles else "(missing)"


def build_prompt(record: dict[str, Any]) -> str:
    title = str(record.get("title") or "").strip()
    body = str(record.get("body") or "").strip()
    cards = list(record.get("image_cards") or [])
    card_plan = record.get("card_plan") or []
    source_excerpt = str(record.get("source_excerpt") or "")[:SOURCE_EXCERPT_BUDGET_CHARS]
    organized = read_text(
        record.get("source_organized_transcript_md"),
        ORGANIZED_TRANSCRIPT_BUDGET_CHARS,
    )

    parts = [
        SYSTEM_INSTRUCTION,
        "",
        RUBRIC,
        "",
        OUTPUT_SCHEMA,
        "",
        "===== 待诊断草稿 =====",
        f"标题：{title}",
        "",
        "正文：",
        body,
        "",
        f"image_cards（{sum(1 for c in cards if str(c).strip())} 张）：",
        render_cards(cards),
        "",
        f"card_plan 角色序列：{render_card_plan(card_plan)}",
        "",
        "===== source_excerpt（生成草稿时使用的来源片段）=====",
        source_excerpt or "(无)",
        "",
        "===== organized_transcript（作者完整原话，用于判断 credibility_anchor 是否被保留）=====",
        organized or "(未提供)",
        "",
        "===== 任务 =====",
        "按上面的 rubric 和 schema 输出 JSON。立即开始，不要任何前置文字。",
    ]
    return "\n".join(parts)


def call_claude(prompt: str, model: str | None, timeout_s: int) -> tuple[str, str]:
    args = ["claude", "-p", "--output-format", "json"]
    if model:
        args.extend(["--model", model])
    result = subprocess.run(
        args,
        input=prompt,
        text=True,
        capture_output=True,
        timeout=timeout_s,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"claude exit {result.returncode}: {result.stderr.strip()[:500]}"
        )
    return result.stdout, result.stderr


def parse_envelope(stdout: str) -> tuple[dict[str, Any], dict[str, Any]]:
    envelope = json.loads(stdout)
    result_text = envelope.get("result") or ""
    try:
        inner = json.loads(result_text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", result_text, re.DOTALL)
        if not match:
            raise
        inner = json.loads(match.group(0))
    return envelope, inner


def validate_scores(scored: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    scores = scored.get("scores") or {}
    for dim in DIMENSIONS:
        node = scores.get(dim)
        if not isinstance(node, dict):
            issues.append(f"missing dimension: {dim}")
            continue
        score = node.get("score")
        if not isinstance(score, int) or not 0 <= score <= 10:
            issues.append(f"invalid score for {dim}: {score!r}")
    if not isinstance(scored.get("total"), int):
        issues.append("missing or non-int total")
    if scored.get("verdict") not in {"keep", "rewrite", "kill"}:
        issues.append(f"invalid verdict: {scored.get('verdict')!r}")
    return issues


def normalize_scored(scored: dict[str, Any]) -> dict[str, Any]:
    scores = scored.get("scores") or {}
    blockers: list[str] = []
    for dim in DIMENSIONS:
        node = scores.get(dim) or {}
        if dim == "suspense" and node.get("structural"):
            blockers.append(dim)
    computed_total = sum(
        (scores.get(dim) or {}).get("score") or 0 for dim in DIMENSIONS
    )
    if scored.get("total") != computed_total:
        scored["computed_total"] = computed_total
    declared = scored.get("structural_blockers") or []
    merged = sorted({*declared, *blockers})
    scored["structural_blockers"] = merged
    return scored


def review_one(
    json_path: Path,
    model: str | None,
    timeout_s: int,
    max_retries: int,
    include_failed: bool,
    force: bool,
) -> dict[str, Any]:
    record = load_json(json_path)
    if not record:
        return {"path": str(json_path), "status": "bad_json"}

    quality = record.get("xhs_quality") or {}
    layer1_passed = bool(quality.get("passes_quality_gate"))
    if not layer1_passed and not include_failed:
        return {
            "path": str(json_path),
            "status": "skipped_layer1_failed",
            "warnings": quality.get("quality_warnings") or [],
        }

    existing = quality.get("dbs_review") or {}
    if existing.get("dbs_review_version") == DBS_REVIEW_VERSION and not force:
        return {
            "path": str(json_path),
            "status": "exists",
            "total": existing.get("total"),
            "verdict": existing.get("verdict"),
        }

    prompt = build_prompt(record)
    last_error: str | None = None
    for attempt in range(max_retries + 1):
        try:
            stdout, _stderr = call_claude(prompt, model=model, timeout_s=timeout_s)
            envelope, scored = parse_envelope(stdout)
            validation_issues = validate_scores(scored)
            if validation_issues:
                last_error = f"validation failed: {validation_issues}"
                continue
            scored = normalize_scored(scored)
            break
        except (json.JSONDecodeError, subprocess.TimeoutExpired, RuntimeError) as exc:
            last_error = f"{type(exc).__name__}: {str(exc)[:300]}"
            envelope = {}
            scored = {}
    else:
        return {
            "path": str(json_path),
            "status": "failed",
            "error": last_error,
            "attempts": max_retries + 1,
        }

    dbs_review = {
        "dbs_review_version": DBS_REVIEW_VERSION,
        "engine": "claude-p-subprocess",
        "model": envelope.get("model") or model or "default",
        "reviewed_at": datetime.now().isoformat(timespec="seconds"),
        "duration_ms": envelope.get("duration_ms"),
        "cost_usd": envelope.get("total_cost_usd"),
        "scores": scored.get("scores"),
        "total": scored.get("total"),
        "computed_total": scored.get("computed_total"),
        "structural_blockers": scored.get("structural_blockers"),
        "first_action": scored.get("first_action"),
        "verdict": scored.get("verdict"),
        "rubric_dimensions": list(DIMENSIONS),
    }

    quality["dbs_review"] = dbs_review
    record["xhs_quality"] = quality
    write_json(json_path, record)

    return {
        "path": str(json_path),
        "status": "reviewed",
        "title": record.get("title"),
        "total": dbs_review["total"],
        "verdict": dbs_review["verdict"],
        "structural_blockers": dbs_review["structural_blockers"],
        "first_action": dbs_review["first_action"],
        "duration_ms": dbs_review["duration_ms"],
        "cost_usd": dbs_review["cost_usd"],
    }


def gather_paths(
    explicit_draft: str | None,
    source_content_id: str | None,
    limit: int,
) -> list[Path]:
    if explicit_draft:
        return [Path(explicit_draft).expanduser()]
    paths = sorted(DRAFT_DIR.glob("*.json"))
    if source_content_id:
        paths = [
            p for p in paths
            if load_json(p).get("source_content_id") == source_content_id
        ]
    paths = [
        p for p in paths
        if load_json(p).get("status") not in {"superseded", "archived"}
    ]
    if limit:
        paths = paths[:limit]
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Layer 2 dbs-content style 9-dim review for Xiaohongshu drafts."
    )
    parser.add_argument("draft", nargs="?")
    parser.add_argument("--source-content-id")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--model", default=DEFAULT_MODEL,
                        help="Claude model (sonnet/opus/haiku). Default: sonnet.")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_S)
    parser.add_argument("--retries", type=int, default=DEFAULT_MAX_RETRIES)
    parser.add_argument("--include-failed", action="store_true",
                        help="Review drafts even if Layer 1 failed.")
    parser.add_argument("--force", action="store_true",
                        help="Re-review drafts that already have a dbs_review at current version.")
    args = parser.parse_args()

    paths = gather_paths(args.draft, args.source_content_id, args.limit)
    if not paths:
        print("no drafts matched", file=sys.stderr)
        return 1

    report: list[dict[str, Any]] = []
    for path in paths:
        print(f"dbs_review={path.name}", flush=True)
        try:
            row = review_one(
                path,
                model=args.model,
                timeout_s=args.timeout,
                max_retries=args.retries,
                include_failed=args.include_failed,
                force=args.force,
            )
        except Exception as exc:
            row = {"path": str(path), "status": "failed", "error": str(exc)[:500]}
        report.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        json.dumps(
            {
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                "model": args.model,
                "rubric_version": DBS_REVIEW_VERSION,
                "rubric_dimensions": list(DIMENSIONS),
                "rows": report,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"report={REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
