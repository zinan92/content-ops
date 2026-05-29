#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path


ROOT = Path("/Users/wendy")
DOUYIN_SENT = ROOT / "park-io/outbox/sent/douyin"
MLX_PYTHON = ROOT / "videocut/.venv-mlx-whisper/bin/python"
DEFAULT_MODEL = "mlx-community/whisper-small-mlx"


def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, capture_output=True)


def mmss(seconds: float | int | None) -> str:
    total = int(float(seconds or 0))
    return f"{total // 60:02d}:{total % 60:02d}"


def title_from_dir(path: Path) -> str:
    parts = path.name.split("--")
    if len(parts) >= 3:
        return "--".join(parts[1:-1]).strip()
    return path.name


def aweme_id_from_dir(path: Path) -> str:
    return path.name.rsplit("--", 1)[-1]


def extract_audio(video: Path, audio: Path) -> None:
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(video),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-b:a",
        "64k",
        str(audio),
    ]
    result = run(cmd)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout).strip())


def mlx_transcribe(audio: Path, raw_output: Path, model: str) -> None:
    code = """
import json
import sys
from mlx_whisper import transcribe

audio_path, model_repo, output_path = sys.argv[1:4]
result = transcribe(
    audio_path,
    path_or_hf_repo=model_repo,
    verbose=False,
    language="zh",
    task="transcribe",
    word_timestamps=False,
    fp16=True,
)
with open(output_path, "w", encoding="utf-8") as fh:
    json.dump(result, fh, ensure_ascii=False, indent=2)
"""
    result = run([str(MLX_PYTHON), "-c", code, str(audio), model, str(raw_output)])
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout).strip())


def normalize_transcript(raw: dict, content_dir: Path) -> dict:
    segments = []
    full_parts = []
    for segment in raw.get("segments") or []:
        text = re.sub(r"\s+", " ", segment.get("text") or "").strip()
        if not text:
            continue
        item = {
            "start": float(segment.get("start") or 0),
            "end": float(segment.get("end") or 0),
            "text": text,
        }
        if "avg_logprob" in segment:
            item["avg_logprob"] = segment["avg_logprob"]
        segments.append(item)
        full_parts.append(text)
    return {
        "content_id": aweme_id_from_dir(content_dir),
        "content_type": "video",
        "language": raw.get("language") or "zh",
        "generated_at": datetime.now().isoformat(),
        "engine": "mlx-whisper",
        "model": raw.get("model") or DEFAULT_MODEL,
        "segments": segments,
        "full_text": "\n".join(full_parts),
    }


def write_markdown(content_dir: Path, transcript: dict) -> None:
    title = title_from_dir(content_dir)
    aweme_id = aweme_id_from_dir(content_dir)
    lines = [
        f"# {title}",
        "",
        f"- Douyin ID: `{aweme_id}`",
        f"- Source: https://www.douyin.com/video/{aweme_id}",
        f"- Transcript engine: {transcript.get('engine')} ({transcript.get('model')})",
        "",
        "## Transcript",
        "",
    ]
    for segment in transcript.get("segments") or []:
        text = (segment.get("text") or "").strip()
        if text:
            lines.append(f"[{mmss(segment.get('start'))}] {text}")
            lines.append("")
    transcript_dir = content_dir / "transcript"
    transcript_dir.mkdir(parents=True, exist_ok=True)
    (transcript_dir / "raw.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def transcribe_one(content_dir: Path, model: str, force: bool) -> dict:
    video = content_dir / "media/video.mp4"
    transcript_dir = content_dir / "transcript"
    transcript_json = transcript_dir / "raw.json"
    transcript_md = transcript_dir / "raw.md"
    if not video.exists():
        return {"directory": str(content_dir), "video": False, "transcript": False, "status": "missing_video"}
    if transcript_json.exists() and transcript_md.exists() and not force:
        return {"directory": str(content_dir), "video": True, "transcript": True, "status": "exists"}

    with tempfile.TemporaryDirectory(prefix="douyin-mlx-") as tmp:
        audio = Path(tmp) / "audio.mp3"
        raw_output = Path(tmp) / "mlx_result.json"
        extract_audio(video, audio)
        mlx_transcribe(audio, raw_output, model)
        raw = json.loads(raw_output.read_text(encoding="utf-8"))

    raw["model"] = model
    raw_dir = content_dir / "_raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / "mlx_result.json").write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    transcript = normalize_transcript(raw, content_dir)
    transcript_dir.mkdir(parents=True, exist_ok=True)
    transcript_json.write_text(json.dumps(transcript, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_markdown(content_dir, transcript)
    return {
        "directory": str(content_dir),
        "video": True,
        "transcript": True,
        "status": "transcribed",
        "segments": len(transcript["segments"]),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Fast MLX Whisper transcription for clean Douyin outbox assets.")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--only-missing", action="store_true", default=True)
    args = parser.parse_args()

    if not MLX_PYTHON.exists():
        raise SystemExit(f"Missing MLX runtime: {MLX_PYTHON}")

    dirs = sorted(DOUYIN_SENT.glob("20*--*--*"))
    if args.only_missing:
        dirs = [p for p in dirs if not (p / "transcript/raw.md").exists()]
    if args.limit:
        dirs = dirs[: args.limit]

    report = []
    for content_dir in dirs:
        print(f"transcribing={content_dir.name}", flush=True)
        try:
            row = transcribe_one(content_dir, args.model, args.force)
        except Exception as exc:
            row = {"directory": str(content_dir), "status": "failed", "error": str(exc)}
        report.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)

    report_path = Path("/Users/wendy/work/content-ops/.runs/reports/douyin-transcription-report.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote={report_path}")


if __name__ == "__main__":
    main()
