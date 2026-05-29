#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import os
import re
import shutil
import signal
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path


ROOT = Path("/Users/wendy")
DRAFT_DIR = ROOT / "park-io/outbox/drafts/xiaohongshu"
CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
RENDER_TIMEOUT_SECONDS = 30


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def quote_card_html(text: str, index: int, total: int, title: str) -> str:
    escaped = html.escape(text).replace("\n", "<br>")
    escaped_title = html.escape(title)
    eyebrow = "PARK AI WORLD" if index == 1 else f"{index:02d} / {total:02d}"
    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<style>
* {{ box-sizing: border-box; }}
html, body {{
  width: 1080px;
  height: 1440px;
  margin: 0;
  overflow: hidden;
  background: #f5f2ea;
  font-family: "PingFang SC", "Hiragino Sans GB", "Noto Sans CJK SC", -apple-system, sans-serif;
  -webkit-font-smoothing: antialiased;
}}
.card {{
  width: 1080px;
  height: 1440px;
  position: relative;
  background:
    linear-gradient(90deg, rgba(30,30,30,.05) 1px, transparent 1px),
    linear-gradient(180deg, rgba(30,30,30,.05) 1px, transparent 1px),
    #f5f2ea;
  background-size: 54px 54px;
  color: #191816;
  padding: 92px 96px 78px;
}}
.top {{
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 28px;
  font-weight: 700;
  letter-spacing: .08em;
  color: #6e6255;
}}
.mark {{
  width: 74px;
  height: 8px;
  background: #d1493f;
  border-radius: 999px;
}}
.content {{
  position: absolute;
  left: 96px;
  right: 96px;
  top: 50%;
  transform: translateY(-50%);
}}
.text {{
  font-size: 78px;
  line-height: 1.22;
  font-weight: 850;
  letter-spacing: 0;
  word-break: keep-all;
  overflow-wrap: anywhere;
}}
.text.small {{
  font-size: 62px;
  line-height: 1.28;
}}
.text.tiny {{
  font-size: 52px;
  line-height: 1.34;
}}
.footer {{
  position: absolute;
  left: 96px;
  right: 96px;
  bottom: 70px;
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  gap: 40px;
  color: #6e6255;
  font-size: 26px;
  line-height: 1.35;
}}
.source {{
  max-width: 690px;
}}
.account {{
  font-weight: 800;
  color: #191816;
}}
</style>
</head>
<body>
<main class="card">
  <div class="top">
    <div>{eyebrow}</div>
    <div class="mark"></div>
  </div>
  <section class="content">
    <div class="text {font_class(text)}">{escaped}</div>
  </section>
  <footer class="footer">
    <div class="source">{escaped_title}</div>
    <div class="account">@Park的AI世界</div>
  </footer>
</main>
</body>
</html>
"""


def dense_card_html(page: dict, index: int, total: int, title: str, body_chars: int, reading_minutes: int) -> str:
    escaped_title = html.escape(title)
    subtitle = html.escape(page.get("subtitle") or "")
    paragraphs = page.get("paragraphs") or []
    page_no = f"{index}/{total}"
    logic_items = logic_chart_items(index, total)
    logic_html = ""
    if index > 1 and logic_items:
        logic_html = '<div class="logic-strip">' + "".join(
            f"<span>{html.escape(item)}</span>" for item in logic_items
        ) + "</div>"
    if index == 1:
        h1 = html.escape(page.get("headline") or title).replace("\n", "<br>")
        body_html = "\n".join(f"<p>{html.escape(p)}</p>" for p in paragraphs)
        content = f"""
  <div class="meta">全文{body_chars}字｜阅读需{reading_minutes}分钟</div>
  <h1>{h1}</h1>
  <div class="subtitle">{subtitle}</div>
  <div class="body cover-body">{body_html}</div>
"""
    else:
        body_html = "\n".join(f"<p>{html.escape(p)}</p>" for p in paragraphs)
        content = f"""
  <div class="page-title">{subtitle}</div>
  <div class="body">{body_html}</div>
  {logic_html}
"""

    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<style>
* {{ box-sizing: border-box; }}
html, body {{
  width: 1080px;
  height: 1440px;
  margin: 0;
  overflow: hidden;
  background: #f7f8f5;
  color: #252525;
  font-family: "Songti SC", "STSong", "Noto Serif CJK SC", "PingFang SC", serif;
  -webkit-font-smoothing: antialiased;
}}
.card {{
  width: 1080px;
  height: 1440px;
  position: relative;
  padding: 58px 56px 60px;
  background:
    radial-gradient(circle at 68% 25%, rgba(32, 123, 91, .08) 0 1px, transparent 2px),
    linear-gradient(90deg, rgba(35, 126, 92, .12) 1px, transparent 1px),
    linear-gradient(180deg, rgba(35, 126, 92, .10) 1px, transparent 1px),
    #f7f8f5;
  background-size: 140px 140px, 54px 54px, 54px 54px, auto;
}}
.count {{
  position: absolute;
  right: 56px;
  top: 52px;
  padding: 9px 18px;
  border-radius: 999px;
  background: rgba(80, 80, 80, .68);
  color: white;
  font-family: "PingFang SC", sans-serif;
  font-size: 30px;
  font-weight: 700;
}}
.content {{
  position: relative;
  z-index: 1;
}}
.meta {{
  margin-top: 112px;
  padding-bottom: 16px;
  border-bottom: 1px solid rgba(37,37,37,.22);
  font-family: "PingFang SC", sans-serif;
  font-size: 34px;
  color: #2b2b2b;
}}
h1 {{
  margin: 36px 0 34px;
  color: #16865d;
  font-size: 82px;
  line-height: 1.10;
  font-weight: 500;
  letter-spacing: 0;
}}
.subtitle, .page-title {{
  margin: 0 0 34px;
  color: #252525;
  font-size: 42px;
  line-height: 1.48;
  font-weight: 700;
}}
.page-title {{
  margin-top: 72px;
}}
.body {{
  font-size: 36px;
  line-height: 1.55;
  font-weight: 500;
  text-align: justify;
  letter-spacing: 0;
}}
.body p {{
  margin: 0 0 24px;
}}
.body p:last-child {{
  margin-bottom: 0;
}}
.cover-body {{
  font-size: 34px;
  line-height: 1.52;
}}
.logic-strip {{
  margin-top: 42px;
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
  font-family: "PingFang SC", sans-serif;
}}
.logic-strip span {{
  min-height: 78px;
  padding: 15px 14px;
  border: 1px solid rgba(22, 134, 93, .32);
  border-radius: 4px;
  background: rgba(22, 134, 93, .07);
  color: #176445;
  font-size: 26px;
  line-height: 1.28;
  font-weight: 700;
  text-align: center;
}}
.footer {{
  position: absolute;
  left: 56px;
  right: 56px;
  bottom: 24px;
  height: 44px;
  border-top: 1px solid rgba(37,37,37,.18);
}}
.account {{
  position: absolute;
  right: 56px;
  bottom: 48px;
  font-family: "PingFang SC", sans-serif;
  font-size: 24px;
  font-weight: 700;
  color: rgba(37,37,37,.72);
}}
</style>
</head>
<body>
<main class="card">
  <div class="count">{page_no}</div>
  <section class="content">
{content}
  </section>
  <div class="account">@Park的AI世界</div>
  <div class="footer"></div>
</main>
</body>
</html>
"""


def manual_section_label(index: int, total: int) -> str:
    if index == 1:
        return "先看结论"
    if index == 2:
        return "你可能卡在这里"
    if index == 3:
        return "换个比喻"
    if index == total:
        return "最后怎么用"
    return "怎么判断"


def manual_paragraph_html(paragraphs: list[str]) -> str:
    items: list[str] = []
    list_open = False
    for paragraph in paragraphs:
        text = re.sub(r"\s+", " ", str(paragraph or "")).strip()
        if not text:
            continue
        ordered = re.match(r"^(\d+)[.、]\s*(.+)$", text)
        if ordered:
            if not list_open:
                items.append("<ol>")
                list_open = True
            items.append(f"<li>{html.escape(ordered.group(2))}</li>")
            continue
        if list_open:
            items.append("</ol>")
            list_open = False
        items.append(f"<p>{html.escape(text)}</p>")
    if list_open:
        items.append("</ol>")
    return "\n".join(items)


def manual_illustration() -> str:
    return """
  <svg class="illustration" viewBox="0 0 280 250" aria-hidden="true">
    <ellipse cx="150" cy="224" rx="100" ry="16" fill="#4a2414" opacity=".22"/>
    <path d="M74 188h64v28H74zM108 154h64v28h-64zM142 120h64v28h-64z" fill="#fff8e8" stroke="#5a2d1b" stroke-width="4"/>
    <path d="M161 59c21-9 38 4 36 25-1 13-9 21-23 27l-21 9 30 78" fill="none" stroke="#5a2d1b" stroke-width="10" stroke-linecap="round"/>
    <path d="M141 84l48 8-8 53-48-8z" fill="#ff8a2a" stroke="#5a2d1b" stroke-width="4"/>
    <path d="M141 137l34 4 15 62h-22l-16-45-22 43h-23z" fill="#3b2418"/>
    <circle cx="169" cy="45" r="18" fill="#5a2d1b"/>
    <path d="M192 84c20 8 34 21 42 39" fill="none" stroke="#5a2d1b" stroke-width="8" stroke-linecap="round"/>
    <path d="M202 74l54 18-32 104-54-18z" fill="#fff8e8" stroke="#5a2d1b" stroke-width="4"/>
    <path d="M213 99h25M209 118h28M205 137h25M201 156h27" stroke="#8d6b55" stroke-width="4" stroke-linecap="round"/>
  </svg>
"""


def manual_card_html(page: dict, index: int, total: int, title: str, body_chars: int, reading_minutes: int) -> str:
    headline = html.escape(page.get("headline") or page.get("subtitle") or title)
    subtitle = html.escape(page.get("subtitle") or "")
    paragraphs = [str(item).strip() for item in (page.get("paragraphs") or []) if str(item).strip()]
    if index == 1 and subtitle:
        paragraphs = [subtitle] + paragraphs
    body_html = manual_paragraph_html(paragraphs)
    label = html.escape(manual_section_label(index, total))
    brand = "Park AI Content Method"
    footer = "@Park的AI世界"
    page_no = f"{index}"
    illustration = manual_illustration() if index in {1, total} else ""
    body_class = " with-illustration" if illustration else ""
    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<style>
* {{ box-sizing: border-box; }}
html, body {{
  width: 1080px;
  height: 1440px;
  margin: 0;
  overflow: hidden;
  background: #ffffff;
  color: #101010;
  font-family: "PingFang SC", "Noto Sans CJK SC", -apple-system, BlinkMacSystemFont, sans-serif;
  -webkit-font-smoothing: antialiased;
}}
.card {{
  width: 1080px;
  height: 1440px;
  position: relative;
  padding: 58px 82px 74px;
  background: #fff;
}}
.brand {{
  position: absolute;
  right: 82px;
  top: 58px;
  font-size: 20px;
  color: #202020;
  letter-spacing: 0;
}}
.step {{
  margin-top: 78px;
  text-align: center;
  font-family: "Comic Sans MS", "Marker Felt", "PingFang SC", cursive;
  font-size: 48px;
  line-height: 1;
  letter-spacing: .08em;
  font-weight: 400;
}}
h1 {{
  width: 820px;
  margin: 24px auto 54px;
  text-align: center;
  font-size: 46px;
  line-height: 1.28;
  font-weight: 900;
  letter-spacing: 0;
}}
.section-label {{
  display: inline-block;
  margin: 0 0 28px 8px;
  padding: 2px 12px 4px;
  background: linear-gradient(180deg, transparent 42%, #f2a52d 42%);
  font-size: 32px;
  line-height: 1.18;
  font-weight: 900;
}}
.body {{
  position: relative;
  font-size: 30px;
  line-height: 1.52;
  font-weight: 500;
  letter-spacing: 0;
}}
.body.with-illustration {{
  padding-bottom: 282px;
}}
p {{
  margin: 0 0 22px;
}}
ol {{
  margin: 0 0 28px 38px;
  padding: 0;
}}
li {{
  margin: 0 0 14px;
  padding-left: 4px;
}}
.illustration {{
  position: absolute;
  right: 92px;
  bottom: 118px;
  width: 310px;
  height: 276px;
}}
.footer {{
  position: absolute;
  left: 48px;
  right: 48px;
  bottom: 36px;
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: 30px;
  font-size: 32px;
  color: #101010;
}}
.line {{
  height: 1px;
  background: #101010;
  opacity: .72;
}}
.page {{
  font-size: 24px;
  font-weight: 800;
}}
</style>
</head>
<body>
<main class="card">
  <div class="brand">{html.escape(brand)}</div>
  <div class="step">Step {index:02d}</div>
  <h1>{headline}</h1>
  <div class="section-label">{label}</div>
  <section class="body{body_class}">
    {body_html}
  </section>
  {illustration}
  <footer class="footer">
    <div>{html.escape(footer)}</div>
    <div class="line"></div>
    <div class="page">{page_no}</div>
  </footer>
</main>
</body>
</html>
"""


def logic_chart_items(index: int, total: int) -> list[str]:
    return []


def font_class(text: str) -> str:
    length = len(text.replace("\n", ""))
    if length > 90:
        return "tiny"
    if length > 58:
        return "small"
    return ""


def render_png(html_path: Path, output_path: Path) -> None:
    if not CHROME.exists():
        raise RuntimeError(f"Chrome not found: {CHROME}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        output_path.unlink()

    def run_chrome(headless_flag: str) -> subprocess.CompletedProcess[str]:
        command = [
            str(CHROME),
            headless_flag,
            "--disable-gpu",
            "--no-sandbox",
            "--disable-extensions",
            "--hide-scrollbars",
            "--window-size=1080,1440",
            f"--screenshot={output_path}",
            f"file://{html_path}",
        ]
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        try:
            stdout, stderr = process.communicate(timeout=RENDER_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired as exc:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                stdout, stderr = process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                stdout, stderr = process.communicate()
            raise TimeoutError(
                f"Chrome screenshot timed out after {RENDER_TIMEOUT_SECONDS}s with {headless_flag}: {html_path}"
            ) from exc
        return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)

    errors: list[str] = []
    for headless_flag in ["--headless=new", "--headless"]:
        try:
            result = run_chrome(headless_flag)
        except TimeoutError as exc:
            errors.append(str(exc))
            continue
        if result.returncode != 0:
            errors.append((result.stderr or result.stdout or "").strip() or f"Chrome exited {result.returncode}")
            continue
        if output_path.exists() and output_path.stat().st_size > 0:
            return
        errors.append(f"Chrome exited 0 but did not write screenshot: {output_path}")
    raise RuntimeError("; ".join(errors))


def clean_body_for_publish(body: str) -> str:
    if "## 图文卡片文案" in body:
        body = body.split("## 图文卡片文案", 1)[0]
    return body.strip()


def body_without_tags(body: str) -> str:
    lines = [line.rstrip() for line in body.splitlines()]
    while lines and not lines[-1].strip():
        lines.pop()
    if lines and re.fullmatch(r"(#\S+\s*)+", lines[-1].strip()):
        lines.pop()
    return "\n".join(lines).strip()


def split_paragraphs(body: str) -> list[str]:
    body = body_without_tags(body)
    paragraphs = []
    for block in re.split(r"\n\s*\n", body):
        block = re.sub(r"\s+", " ", block).strip()
        if block:
            paragraphs.append(block)
    return paragraphs


def chunk_paragraphs(paragraphs: list[str], max_chars: int = 350) -> list[list[str]]:
    chunks: list[list[str]] = []
    current: list[str] = []
    count = 0
    for paragraph in paragraphs:
        length = len(paragraph)
        if current and count + length > max_chars:
            chunks.append(current)
            current = [paragraph]
            count = length
        else:
            current.append(paragraph)
            count += length
    if current:
        chunks.append(current)
    while len(chunks) >= 2:
        last_len = sum(len(paragraph) for paragraph in chunks[-1])
        prev_len = sum(len(paragraph) for paragraph in chunks[-2])
        if last_len >= 180 or prev_len <= 260 or len(chunks[-2]) <= 1:
            break
        chunks[-1].insert(0, chunks[-2].pop())
    return chunks


def dense_pages(title: str, body: str) -> list[dict]:
    paragraphs = split_paragraphs(body)
    if not paragraphs:
        return [{"headline": title, "subtitle": "", "paragraphs": []}]

    pages: list[dict] = []
    cover_paragraphs = paragraphs[:3]
    pages.append(
        {
            "headline": title,
            "subtitle": cover_paragraphs[0] if cover_paragraphs else "",
            "paragraphs": cover_paragraphs[1:3],
        }
    )
    remaining = paragraphs[3:] if len(paragraphs) > 3 else paragraphs[1:]
    for idx, chunk in enumerate(chunk_paragraphs(remaining), start=2):
        pages.append(
            {
                "subtitle": chunk[0] if len(chunk[0]) <= 42 else "",
                "paragraphs": chunk if len(chunk[0]) > 42 else chunk[1:] or chunk,
            }
        )
    return pages[:12]


def split_card_text(card: str) -> tuple[str, list[str]]:
    card = re.sub(r"^(封面|第\s*\d+\s*张|收尾)[:：]\s*", "", card or "").strip()
    lines = [re.sub(r"\s+", " ", line).strip() for line in card.splitlines()]
    lines = [line for line in lines if line]
    if not lines:
        return "", []
    headline = lines[0]
    rest = lines[1:]
    if len(headline) > 44:
        fragments = re.split(r"(?<=[。！？!?；;])", headline)
        fragments = [frag.strip() for frag in fragments if frag.strip()]
        if len(fragments) >= 2:
            headline = fragments[0]
            rest = fragments[1:] + rest
    paragraphs: list[str] = []
    for item in rest:
        if len(item) <= 90:
            paragraphs.append(item)
            continue
        pieces = [piece.strip() for piece in re.split(r"(?<=[。！？!?；;])", item) if piece.strip()]
        paragraphs.extend(pieces or [item])
    return headline, paragraphs


def dense_pages_from_cards(title: str, cards: list[str], body: str) -> list[dict]:
    """Render the approved Xiaohongshu card script, not the long publish body.

    The long body is useful for platform caption text. Image pages should come
    from the card script so they stay structured as cover -> conflict ->
    reasoning -> example -> action, instead of becoming transcript screenshots.
    """
    pages: list[dict] = []
    for idx, card in enumerate(cards, start=1):
        headline, paragraphs = split_card_text(card)
        if not headline:
            continue
        if idx == 1:
            pages.append(
                {
                    "headline": headline,
                    "subtitle": paragraphs[0] if paragraphs else "",
                    "paragraphs": paragraphs[1:],
                }
            )
        else:
            pages.append(
                {
                    "subtitle": headline,
                    "paragraphs": paragraphs,
                }
            )
    if pages:
        return pages[:12]
    return dense_pages(title, body)


def render_one(json_path: Path, overwrite: bool, style: str) -> dict:
    record = load_json(json_path)
    cards = [str(card).strip() for card in record.get("image_cards") or [] if str(card).strip()]
    title = str(record.get("title") or "").strip()
    body = clean_body_for_publish(str(record.get("body") or ""))
    if style in {"dense", "manual"}:
        pages = dense_pages_from_cards(title, cards, body)
    else:
        pages = [{"text": card} for card in cards]
    if not pages:
        return {"path": str(json_path), "status": "missing_cards"}

    package_dir = json_path.with_suffix("")
    images_dir = package_dir / "images"
    if package_dir.exists() and overwrite:
        shutil.rmtree(package_dir)
    images_dir.mkdir(parents=True, exist_ok=True)

    (package_dir / "title.txt").write_text(title + "\n", encoding="utf-8")
    (package_dir / "content.txt").write_text(body + "\n", encoding="utf-8")

    image_paths: list[str] = []
    body_chars = len(body_without_tags(body).replace("\n", ""))
    reading_minutes = max(1, round(body_chars / 500))
    with tempfile.TemporaryDirectory(prefix="xhs-cards-") as tmp:
        tmp_dir = Path(tmp)
        for idx, page in enumerate(pages, start=1):
            html_path = tmp_dir / f"{idx:02d}.html"
            png_path = images_dir / f"{idx:02d}.png"
            if style == "dense":
                html_text = dense_card_html(page, idx, len(pages), title, body_chars, reading_minutes)
            elif style == "manual":
                html_text = manual_card_html(page, idx, len(pages), title, body_chars, reading_minutes)
            else:
                html_text = quote_card_html(page["text"], idx, len(pages), title)
            html_path.write_text(html_text, encoding="utf-8")
            render_png(html_path, png_path)
            image_paths.append(str(png_path))

    manifest = {
        "platform": "xiaohongshu",
        "type": "image_text",
        "status": "rendered",
        "rendered_at": datetime.now().isoformat(timespec="seconds"),
        "source_draft_json": str(json_path),
        "title_file": str(package_dir / "title.txt"),
        "content_file": str(package_dir / "content.txt"),
        "images": image_paths,
        "render_style": style,
        "source_content_id": record.get("source_content_id"),
        "source_url": record.get("source_url"),
    }
    write_json(package_dir / "manifest.json", manifest)
    record["rendered_package_dir"] = str(package_dir)
    record["rendered_images"] = image_paths
    record["rendered_at"] = manifest["rendered_at"]
    record["render_style"] = style
    write_json(json_path, record)
    return {"path": str(json_path), "status": "rendered", "images": len(image_paths), "package_dir": str(package_dir)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Render Xiaohongshu image-card drafts into PNG packages.")
    parser.add_argument("draft", nargs="?", help="Draft JSON path. If omitted, use --source-content-id.")
    parser.add_argument("--source-content-id")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--style", choices=["dense", "manual", "quote"], default="dense")
    args = parser.parse_args()

    if args.draft:
        paths = [Path(args.draft)]
    else:
        paths = sorted(DRAFT_DIR.glob("*.json"))
        if args.source_content_id:
            paths = [p for p in paths if load_json(p).get("source_content_id") == args.source_content_id]
        paths = [
            p
            for p in paths
            if load_json(p).get("status") not in {"superseded", "archived"}
        ]
        if args.limit:
            paths = paths[: args.limit]

    report = [render_one(path, args.overwrite, args.style) for path in paths]
    report_path = ROOT / "work/content-ops/.runs/reports/xiaohongshu-render-report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(report_path, {"generated_at": datetime.now().isoformat(timespec="seconds"), "items": report})
    print(json.dumps({"report": str(report_path), "items": report}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
