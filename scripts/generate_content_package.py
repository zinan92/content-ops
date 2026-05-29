#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path("/Users/wendy")
DOUYIN_SENT = ROOT / "park-io/outbox/sent/douyin"


SYSTEM_PROMPT = """你是 Wendy 的内容生产编辑，不是摘要助手。

你的最终回答必须只有一个 raw JSON object，不能有 Markdown，不能有“内容包已生成”之类的人类说明，不能有概览。所有长文本必须作为 JSON string 正确转义。

你的任务：把一条抖音口播 raw transcript 整理成“内容包”，作为后续小红书、公众号、X、clips 的共同上游。

硬性原则：
1. 不要把内容压缩成短摘要。保留 90% 以上的信息量、例子、推理链和原始观点顺序。
2. 删除口癖、明显重复、断句错误、无意义语气词，但不能删掉观点、例子、边界条件。
3. 先把正文整理成可读长文，再拆主题。主题不是机械章节，而是可以独立生产内容的观点单元。
4. topics 是原子选题：一个 topic 只能卖一个观点。不要为了控制数量而把不同阶段、不同层级、不同结论的观点揉在一起。
5. topic_groups 只是可选的生产批次/聚类建议，不能替代原子选题。后续小红书生产默认以 topics 为准；如果一个长视频确实有 14 个独立观点，就保留 14 个 topics。
6. 每个原子主题必须说明：用户视角、反对结论、论证与支持、支撑例子、边界/注意事项、适合的平台。
7. 输出必须是严格 JSON，不要 Markdown fence，不要解释。

JSON schema:
{
  "readable_transcript": "整理后的完整长文，保留原逻辑和绝大多数信息量，用自然段和小标题组织",
  "topics": [
    {
      "title": "主题标题",
      "priority": "main|secondary|discard",
      "claim": "这个主题的核心主张",
      "cognitive_contrast": "用户视角：读者原本怎么想，常见误区是什么。不要写“真正的反差是”这种元话术",
      "reader_mirror": "如果你也有什么具体感受、行为或困惑，这个观点就在说你",
      "why_it_matters": "论证与支持：为什么大众误区是错的，为什么你的反对结论成立",
      "points": [
        {
          "title": "支持论点标题",
          "reader_mirror": "这个论点对应读者的什么具体处境",
          "judgment": "这个论点的判断",
          "explanation": "为什么这个判断成立",
          "evidence": "原视频里的例子或场景"
        }
      ],
      "supporting_examples": ["原视频里的具体例子或场景"],
      "boundary": "这个观点的适用边界或容易误用的地方",
      "platform_fit": ["xiaohongshu", "wechat_mp", "x", "clips"],
      "source_span_summary": "这个主题在原视频里大致覆盖什么内容"
    }
  ],
  "topic_groups": [
    {
      "title": "可选生产批次标题；只在确实是同一观点上下游论据时才合并",
      "priority": "main|secondary|discard",
      "claim": "这个主题组的核心主张",
      "cognitive_contrast": "读者可能误解什么，真正的反差是什么",
      "reader_mirror": "如果你也有什么具体感受、行为或困惑，这个观点就在说你",
      "why_it_matters": "为什么这个观点成立，它背后的逻辑是什么",
      "points": [
        {
          "title": "要点标题",
          "reader_mirror": "这个要点对应读者的什么具体处境",
          "judgment": "这个要点的判断",
          "explanation": "为什么这个判断成立",
          "evidence": "原视频里的例子或场景"
        }
      ],
      "supporting_examples": ["来自原视频或子主题的具体例子"],
      "boundary": "这个主题组的适用边界或容易误用的地方",
      "takeaway": "读者看完之后，下一次应该怎么判断或行动",
      "platform_fit": ["xiaohongshu", "wechat_mp", "x", "clips"],
      "source_span_summary": "这个主题组在原视频里大致覆盖什么内容",
      "merged_topic_titles": ["被合并进来的原始 topic 标题"],
      "merge_reason": "为什么这些子主题只是同一观点的上下游论据，而不是不同观点"
    }
  ],
  "clip_candidates": [
    {
      "title": "clip 标题",
      "reason": "为什么适合剪成短视频",
      "source_span_summary": "大致对应原视频中的哪一段"
    }
  ],
  "production_notes": {
    "xiaohongshu": "这条视频转小红书时应该注意什么",
    "wechat_mp": "这条视频转公众号时应该注意什么",
    "x": "这条视频转 X 时应该注意什么"
  }
}
"""


OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "readable_transcript": {"type": "string"},
        "topics": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "priority": {"type": "string", "enum": ["main", "secondary", "discard"]},
                    "claim": {"type": "string"},
                    "cognitive_contrast": {"type": "string"},
                    "reader_mirror": {"type": "string"},
                    "why_it_matters": {"type": "string"},
                    "points": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 3,
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "reader_mirror": {"type": "string"},
                                "judgment": {"type": "string"},
                                "explanation": {"type": "string"},
                                "evidence": {"type": "string"},
                            },
                            "required": ["title", "reader_mirror", "judgment", "explanation", "evidence"],
                            "additionalProperties": False,
                        },
                    },
                    "supporting_examples": {"type": "array", "items": {"type": "string"}},
                    "boundary": {"type": "string"},
                    "takeaway": {"type": "string"},
                    "platform_fit": {
                        "type": "array",
                        "items": {"type": "string", "enum": ["xiaohongshu", "wechat_mp", "x", "clips"]},
                    },
                    "source_span_summary": {"type": "string"},
                },
                "required": [
                    "title",
                    "priority",
                    "claim",
                    "cognitive_contrast",
                    "reader_mirror",
                    "why_it_matters",
                    "points",
                    "supporting_examples",
                    "boundary",
                    "takeaway",
                    "platform_fit",
                    "source_span_summary",
                ],
                "additionalProperties": False,
            },
        },
        "topic_groups": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "priority": {"type": "string", "enum": ["main", "secondary", "discard"]},
                    "claim": {"type": "string"},
                    "cognitive_contrast": {"type": "string"},
                    "supporting_examples": {"type": "array", "items": {"type": "string"}},
                    "boundary": {"type": "string"},
                    "platform_fit": {
                        "type": "array",
                        "items": {"type": "string", "enum": ["xiaohongshu", "wechat_mp", "x", "clips"]},
                    },
                    "source_span_summary": {"type": "string"},
                    "merged_topic_titles": {"type": "array", "items": {"type": "string"}},
                    "merge_reason": {"type": "string"},
                },
                "required": [
                    "title",
                    "priority",
                    "claim",
                    "cognitive_contrast",
                    "supporting_examples",
                    "boundary",
                    "platform_fit",
                    "source_span_summary",
                    "merged_topic_titles",
                    "merge_reason",
                ],
                "additionalProperties": False,
            },
        },
        "clip_candidates": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "reason": {"type": "string"},
                    "source_span_summary": {"type": "string"},
                },
                "required": ["title", "reason", "source_span_summary"],
                "additionalProperties": False,
            },
        },
        "production_notes": {
            "type": "object",
            "properties": {
                "xiaohongshu": {"type": "string"},
                "wechat_mp": {"type": "string"},
                "x": {"type": "string"},
            },
            "required": ["xiaohongshu", "wechat_mp", "x"],
            "additionalProperties": False,
        },
    },
    "required": ["readable_transcript", "topics", "topic_groups", "clip_candidates", "production_notes"],
    "additionalProperties": False,
}


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def content_dir_from_id(source_content_id: str) -> Path:
    matches = sorted(DOUYIN_SENT.glob(f"20*--*--{source_content_id}"))
    if not matches:
        raise FileNotFoundError(f"source content not found: {source_content_id}")
    return matches[0]


def title_from_dir(path: Path) -> str:
    parts = path.name.split("--")
    if len(parts) >= 3:
        return "--".join(parts[1:-1]).strip()
    return path.name


def load_raw_transcript(content_dir: Path) -> dict[str, Any]:
    raw_json = content_dir / "transcript/raw.json"
    if not raw_json.exists():
        raise FileNotFoundError(f"missing raw transcript: {raw_json}")
    data = json.loads(raw_json.read_text(encoding="utf-8"))
    full_text = data.get("full_text") or " ".join(str(seg.get("text") or "") for seg in data.get("segments") or [])
    return {
        "path": raw_json,
        "full_text": clean_text(full_text),
        "segments": data.get("segments") or [],
    }


def extract_json(text: str) -> dict[str, Any]:
    raw = text.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            return json.loads(raw[start : end + 1])
        raise


def run_claude(title: str, source_content_id: str, transcript: str, timeout: int) -> tuple[dict[str, Any], str]:
    prompt = f"""视频标题：{title}
source_content_id：{source_content_id}
原始 transcript 字数：{len(clean_text(transcript))}

请生成内容包。

Raw transcript:
{transcript}
"""
    result = subprocess.run(
        [
            "claude",
            "-p",
            "--model",
            "sonnet",
            "--max-budget-usd",
            "1.20",
            "--output-format",
            "json",
            "--json-schema",
            json.dumps(OUTPUT_SCHEMA, ensure_ascii=False),
            "--system-prompt",
            SYSTEM_PROMPT,
            prompt,
        ],
        text=True,
        capture_output=True,
        timeout=timeout,
    )
    output = (result.stdout or "").strip()
    if result.returncode != 0:
        raise RuntimeError((result.stderr or output).strip())
    try:
        wrapper = json.loads(output)
        if isinstance(wrapper, dict) and isinstance(wrapper.get("structured_output"), dict):
            return wrapper["structured_output"], output
        if isinstance(wrapper, dict) and "result" in wrapper:
            output = str(wrapper.get("result") or "").strip()
        return extract_json(output), output
    except json.JSONDecodeError as exc:
        debug_path = Path("/tmp") / f"park-io-content-package-{source_content_id}.txt"
        debug_path.write_text(output, encoding="utf-8")
        raise RuntimeError(f"Claude returned invalid JSON. Raw output saved to {debug_path}: {exc}") from exc


def run_codex(title: str, source_content_id: str, transcript: str, timeout: int) -> tuple[dict[str, Any], str]:
    prompt = f"""{SYSTEM_PROMPT}

视频标题：{title}
source_content_id：{source_content_id}
原始 transcript 字数：{len(clean_text(transcript))}

请生成内容包。最终回答必须匹配给定 output schema。

Raw transcript:
{transcript}
"""
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as schema_file:
        json.dump(OUTPUT_SCHEMA, schema_file, ensure_ascii=False)
        schema_path = Path(schema_file.name)
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as output_file:
        output_path = Path(output_file.name)
    try:
        result = subprocess.run(
            [
                "codex",
                "exec",
                "--ephemeral",
                "--skip-git-repo-check",
                "-C",
                str(Path(__file__).resolve().parents[1]),
                "--sandbox",
                "read-only",
                "--output-schema",
                str(schema_path),
                "--output-last-message",
                str(output_path),
                "-",
            ],
            input=prompt,
            text=True,
            capture_output=True,
            timeout=timeout,
        )
        raw_output = output_path.read_text(encoding="utf-8", errors="replace").strip()
        if result.returncode != 0:
            raise RuntimeError(((result.stderr or "") + "\n" + raw_output).strip())
        return extract_json(raw_output), raw_output
    finally:
        schema_path.unlink(missing_ok=True)
        output_path.unlink(missing_ok=True)


def validate_package(package: dict[str, Any], source_chars: int) -> list[str]:
    warnings: list[str] = []
    readable = clean_text(str(package.get("readable_transcript") or ""))
    if len(readable) < source_chars * 0.75:
        warnings.append("readable_transcript 明显过短，可能被摘要化。")
    topics = package.get("topics") or []
    if not isinstance(topics, list) or not topics:
        warnings.append("没有生成可用主题。")
    for idx, topic in enumerate(topics, start=1):
        if not isinstance(topic, dict):
            warnings.append(f"topic {idx} 不是对象。")
            continue
        if not topic.get("claim") or not topic.get("supporting_examples"):
            warnings.append(f"topic {idx} 缺少 claim 或 supporting_examples。")
    topic_groups = package.get("topic_groups") or []
    if not isinstance(topic_groups, list):
        warnings.append("topic_groups 不是数组；它可以为空，但不能是其他类型。")
    for idx, group in enumerate(topic_groups, start=1):
        if not isinstance(group, dict):
            warnings.append(f"topic_group {idx} 不是对象。")
            continue
        if not group.get("claim") or not group.get("supporting_examples") or not group.get("merged_topic_titles"):
            warnings.append(f"topic_group {idx} 缺少 claim、supporting_examples 或 merged_topic_titles。")
        if not group.get("reader_mirror") or not group.get("why_it_matters") or not group.get("points") or not group.get("takeaway"):
            warnings.append(f"topic_group {idx} 缺少 reader_mirror、why_it_matters、points 或 takeaway。")
    return warnings


def write_package(content_dir: Path, source_content_id: str, package: dict[str, Any], raw_output: str, engine: str, source_chars: int) -> dict[str, Any]:
    transcript_dir = content_dir / "transcript"
    transcript_dir.mkdir(parents=True, exist_ok=True)
    out_json = transcript_dir / "content-package.json"
    out_md = transcript_dir / "content-package.md"
    warnings = validate_package(package, source_chars)
    payload = {
        "schema_version": "content-package-v1",
        "source_content_id": source_content_id,
        "title": title_from_dir(content_dir),
        "engine": engine,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_chars": source_chars,
        "readable_chars": len(clean_text(str(package.get("readable_transcript") or ""))),
        "warnings": warnings,
        **package,
    }
    topic_groups = payload.get("topic_groups") or []
    if topic_groups:
        payload["fine_topics"] = payload.get("topics") or []
        payload["production_topic_groups"] = topic_groups
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    raw_path = transcript_dir / "content-package.raw-response.txt"
    raw_path.write_text(raw_output, encoding="utf-8")

    topics = payload.get("topics") or []
    lines = [
        f"# {payload['title']}",
        "",
        f"- Engine: `{engine}`",
        f"- Source chars: `{payload['source_chars']}`",
        f"- Readable chars: `{payload['readable_chars']}`",
        f"- Generated at: `{payload['generated_at']}`",
        "",
        "## Readable Transcript",
        "",
        str(payload.get("readable_transcript") or "").strip(),
        "",
        "## Topic Groups",
        "",
    ]
    for idx, group in enumerate(topic_groups, start=1):
        lines.extend(
            [
                f"### {idx}. {group.get('title') or 'Untitled'}",
                "",
                f"- Priority: `{group.get('priority') or ''}`",
                f"- Claim: {group.get('claim') or ''}",
                f"- Contrast: {group.get('cognitive_contrast') or ''}",
                f"- Reader mirror: {group.get('reader_mirror') or ''}",
                f"- Why: {group.get('why_it_matters') or ''}",
                f"- Boundary: {group.get('boundary') or ''}",
                f"- Takeaway: {group.get('takeaway') or ''}",
                f"- Platform fit: {', '.join(group.get('platform_fit') or [])}",
                f"- Merged topics: {'; '.join(group.get('merged_topic_titles') or [])}",
                f"- Merge reason: {group.get('merge_reason') or ''}",
                "",
                "Examples:",
            ]
        )
        if group.get("points"):
            lines.extend(["", "Points:"])
            for point_idx, point in enumerate(group.get("points") or [], start=1):
                lines.append(
                    f"- {point_idx}. {point.get('title') or ''}: {point.get('judgment') or ''} / "
                    f"{point.get('reader_mirror') or ''} / {point.get('explanation') or ''} / {point.get('evidence') or ''}"
                )
            lines.append("")
        for item in group.get("supporting_examples") or []:
            lines.append(f"- {item}")
        lines.append("")
    lines.extend(["## Original Topics", ""])
    for idx, topic in enumerate(payload.get("fine_topics") or [], start=1):
        lines.extend(
            [
                f"### {idx}. {topic.get('title') or 'Untitled'}",
                "",
                f"- Priority: `{topic.get('priority') or ''}`",
                f"- Claim: {topic.get('claim') or ''}",
                f"- Contrast: {topic.get('cognitive_contrast') or ''}",
                f"- Boundary: {topic.get('boundary') or ''}",
                f"- Platform fit: {', '.join(topic.get('platform_fit') or [])}",
                "",
                "Examples:",
                "",
            ]
        )
        for example in topic.get("supporting_examples") or []:
            lines.append(f"- {example}")
        lines.append("")
    out_md.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return {
        "ok": not warnings,
        "status": "content_package_ready" if not warnings else "content_package_with_warnings",
        "content_dir": str(content_dir),
        "json": str(out_json),
        "markdown": str(out_md),
        "raw_response": str(raw_path),
        "warnings": warnings,
        "source_chars": payload["source_chars"],
        "readable_chars": payload["readable_chars"],
        "topic_count": len(topics),
    }


def generate(source_content_id: str, engine: str, timeout: int) -> dict[str, Any]:
    content_dir = content_dir_from_id(source_content_id)
    raw = load_raw_transcript(content_dir)
    source_text = raw["full_text"]
    source_chars = len(clean_text(source_text))
    title = title_from_dir(content_dir)
    if engine == "claude":
        package, raw_output = run_claude(title, source_content_id, source_text, timeout)
    elif engine == "codex":
        package, raw_output = run_codex(title, source_content_id, source_text, timeout)
    else:
        raise ValueError(f"unsupported engine: {engine}")
    return write_package(content_dir, source_content_id, package, raw_output, engine, source_chars)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate AI content package from one Douyin raw transcript.")
    parser.add_argument("--source-content-id", required=True)
    parser.add_argument("--engine", choices=["codex", "claude"], default="codex")
    parser.add_argument("--timeout", type=int, default=900)
    args = parser.parse_args()
    result = generate(args.source_content_id, args.engine, args.timeout)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    # Warnings should be visible in the dashboard, but still produce a reviewable package.


if __name__ == "__main__":
    main()
