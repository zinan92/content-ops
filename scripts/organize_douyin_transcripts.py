#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path


ROOT = Path("/Users/wendy")
DOUYIN_SENT = ROOT / "park-io/outbox/sent/douyin"


SYSTEM_PROMPT = """你是 Wendy 的口播内容整理助手。

任务：把抖音口播转录整理成更可读的 organized transcript。

硬性要求：
- 保留至少 90% 的原始信息量和论证链，不要总结，不要改写成文章。
- 可以删除明显口癖、连续重复、断句错误、无意义语气词。
- 可以修正明显 ASR 错字，但不要擅自替换观点。
- 保留 Wendy 原本的逻辑顺序。
- 输出中文 Markdown 正文，不要写解释、不要写总结、不要写“以下是”。
- 可以用小标题分段，但每个小标题下面仍然保留原内容展开。
"""


def clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    text = re.sub(r"\b(对吧|OK|ok)\b([，。,. ]*\1\b)+", r"\1", text)
    text = re.sub(r"(然后\s*){3,}", "然后 ", text)
    return text


def title_from_dir(path: Path) -> str:
    parts = path.name.split("--")
    if len(parts) >= 3:
        return "--".join(parts[1:-1]).strip()
    return path.name


def split_chunks(text: str, max_chars: int = 6000) -> list[str]:
    sentences = re.split(r"(?<=[。！？!?])\s+", text)
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        if not sentence:
            continue
        if current and len(current) + len(sentence) > max_chars:
            chunks.append(current.strip())
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        chunks.append(current.strip())
    return chunks


def local_organize(text: str) -> str:
    text = clean_text(text)
    paragraphs = []
    for paragraph in re.split(r"(?<=[。！？!?])\s+", text):
        paragraph = paragraph.strip()
        if paragraph:
            paragraphs.append(paragraph)
    return "\n\n".join(paragraphs)


def claude_organize(chunk: str, title: str, index: int, total: int) -> str:
    prompt = f"""视频标题：{title}
片段：{index}/{total}

请整理下面这段口播转录。再次强调：不要总结，不要压缩成短文，保留至少 90% 的内容和推理链。

原始转录：
{chunk}
"""
    result = subprocess.run(
        [
            "claude",
            "-p",
            "--model",
            "sonnet",
            "--max-budget-usd",
            "0.60",
            "--system-prompt",
            SYSTEM_PROMPT,
            prompt,
        ],
        text=True,
        capture_output=True,
        timeout=300,
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout).strip())
    return result.stdout.strip()


def load_transcript(path: Path) -> tuple[str, list[dict]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    segments = data.get("segments") or []
    full_text = data.get("full_text") or " ".join(str(seg.get("text") or "") for seg in segments)
    return clean_text(full_text), segments


def organize_one(content_dir: Path, engine: str, force: bool) -> dict:
    transcript_json = content_dir / "transcript/raw.json"
    if not transcript_json.exists():
        transcript_json = content_dir / "transcript.json"
    transcript_dir = content_dir / "transcript"
    out_md = transcript_dir / "organized.md"
    out_json = transcript_dir / "organized.json"
    if not transcript_json.exists():
        return {"directory": str(content_dir), "status": "missing_transcript"}
    if out_md.exists() and out_json.exists() and not force:
        return {"directory": str(content_dir), "status": "exists"}

    title = title_from_dir(content_dir)
    source_text, segments = load_transcript(transcript_json)
    chunks = split_chunks(source_text)
    organized_chunks: list[str] = []
    engine_used = engine

    for idx, chunk in enumerate(chunks, start=1):
        if engine == "claude":
            try:
                organized = claude_organize(chunk, title, idx, len(chunks))
            except Exception:
                organized = local_organize(chunk)
                engine_used = "mixed_claude_local_fallback"
        else:
            organized = local_organize(chunk)
        if len(clean_text(organized)) < len(clean_text(chunk)) * 0.85:
            organized = local_organize(chunk)
            engine_used = "mixed_retention_fallback" if engine == "claude" else engine_used
        organized_chunks.append(organized)

    organized_text = "\n\n".join(organized_chunks).strip()
    retention = len(clean_text(organized_text)) / max(1, len(clean_text(source_text)))
    if retention < 0.85:
        organized_text = local_organize(source_text)
        retention = len(clean_text(organized_text)) / max(1, len(clean_text(source_text)))
        engine_used = "local_retention_fallback"

    lines = [
        f"# {title}",
        "",
        f"- Source transcript: `{transcript_json.name}`",
        f"- Engine: `{engine_used}`",
        f"- Retention ratio: `{retention:.2f}`",
        f"- Organized at: `{datetime.now().isoformat(timespec='seconds')}`",
        "",
        "## Organized Transcript",
        "",
        organized_text,
        "",
    ]
    transcript_dir.mkdir(parents=True, exist_ok=True)
    out_md.write_text("\n".join(lines), encoding="utf-8")
    out_json.write_text(
        json.dumps(
            {
                "title": title,
                "source_transcript": str(transcript_json),
                "engine": engine_used,
                "organized_at": datetime.now().isoformat(timespec="seconds"),
                "source_chars": len(clean_text(source_text)),
                "organized_chars": len(clean_text(organized_text)),
                "retention_ratio": retention,
                "source_segments": len(segments),
                "organized_text": organized_text,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return {
        "directory": str(content_dir),
        "status": "organized",
        "engine": engine_used,
        "source_chars": len(clean_text(source_text)),
        "organized_chars": len(clean_text(organized_text)),
        "retention_ratio": round(retention, 3),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Organize Douyin transcripts without compressing them.")
    parser.add_argument("--engine", choices=["local", "claude"], default="local")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    dirs = sorted({p.parents[1] for p in DOUYIN_SENT.glob("20*--*--*/transcript/raw.json")})
    legacy_dirs = [p.parent for p in sorted(DOUYIN_SENT.glob("20*--*--*/transcript.json"))]
    dirs = sorted(set(dirs + legacy_dirs))
    if args.limit:
        dirs = dirs[: args.limit]

    report = []
    for content_dir in dirs:
        print(f"organizing={content_dir.name}", flush=True)
        row = organize_one(content_dir, args.engine, args.force)
        report.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)

    report_path = Path("/Users/wendy/work/content-ops/.runs/reports/douyin-organized-transcript-report.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote={report_path}")


if __name__ == "__main__":
    main()
