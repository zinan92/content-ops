#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import html
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright


ROOT = Path("/Users/wendy")
OUTBOX = ROOT / "park-io/outbox"
DRAFT_DIR = OUTBOX / "drafts/wechat_mp"

WECHAT_STYLES: dict[str, dict[str, str]] = {
    "professional": {
        "label": "简洁专业",
        "description": "当前默认版本，克制、清晰、适合大多数公众号长文。",
        "accent": "#16845b",
        "paper": "#fffef9",
        "soft": "#f4f8f1",
        "ink": "#17231d",
        "muted": "#5f7067",
        "line": "#d8e3dc",
        "font": "-apple-system,BlinkMacSystemFont,'PingFang SC','Hiragino Sans GB','Microsoft YaHei',sans-serif",
    },
    "deep_read": {
        "label": "深度长文",
        "description": "更像专栏文章，正文阅读感更强，视觉块更少。",
        "accent": "#7a4b24",
        "paper": "#fffdfa",
        "soft": "#f7f1e9",
        "ink": "#241a14",
        "muted": "#765f50",
        "line": "#eadccd",
        "font": "'Songti SC','STSong','Noto Serif CJK SC','PingFang SC',serif",
    },
    "memo": {
        "label": "投资备忘录",
        "description": "更像研究 memo，强调判断、边界和行动清单。",
        "accent": "#245ea8",
        "paper": "#fbfdff",
        "soft": "#edf4fb",
        "ink": "#172333",
        "muted": "#596a7d",
        "line": "#d8e2ef",
        "font": "-apple-system,BlinkMacSystemFont,'PingFang SC','Hiragino Sans GB','Microsoft YaHei',sans-serif",
    },
    "diagram": {
        "label": "图解框架",
        "description": "更强调图表和结构，适合 AI / 方法论 / 交易框架内容。",
        "accent": "#0f766e",
        "paper": "#fbfffc",
        "soft": "#eaf7f4",
        "ink": "#12231f",
        "muted": "#55706b",
        "line": "#cfe6df",
        "font": "-apple-system,BlinkMacSystemFont,'PingFang SC','Hiragino Sans GB','Microsoft YaHei',sans-serif",
    },
}


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def source_dir_for(source_content_id: str) -> Path:
    matches = list((OUTBOX / "sent/douyin").glob(f"*--{source_content_id}"))
    if not matches:
        matches = [path for path in (OUTBOX / "sent/douyin").iterdir() if path.is_dir() and source_content_id in path.name]
    if not matches:
        raise FileNotFoundError(f"没有找到抖音源内容：{source_content_id}")
    return matches[0]


def clean_hashtags(title: str) -> str:
    return " ".join(part for part in title.split() if not part.startswith("#")).strip()


def pick_topics(package: dict[str, Any]) -> list[dict[str, Any]]:
    topics = package.get("topics") or []
    main = [topic for topic in topics if topic.get("priority") == "main"]
    return (main or topics)[:8]


def topic_field(topic: dict[str, Any], key: str) -> str:
    value = topic.get(key)
    if value:
        return str(value).strip()
    aliases = {"claim": "Claim", "contrast": "Contrast", "boundary": "Boundary"}
    for raw in topic.get("raw_lines") or []:
        if str(raw).lower().startswith(aliases.get(key, key).lower() + ":"):
            return str(raw).split(":", 1)[1].strip()
    return ""


def section_markdown(title: str, body: list[str]) -> str:
    return "\n".join([f"## {title}", "", *body, ""]).strip()


def media_dir_for(json_path: Path) -> Path:
    return json_path.with_suffix("")


def image_ref(path: Path) -> str:
    return f"{path.parent.name}/{path.name}"


def figure_html(image_path: str | None, caption: str, alt: str = "", style_id: str = "professional") -> str:
    if not image_path:
        return ""
    style = WECHAT_STYLES.get(style_id, WECHAT_STYLES["professional"])
    ref = image_ref(Path(image_path))
    return (
        f'<section style="margin:30px 0 34px;padding:12px;background:{style["soft"]};border:1px solid {style["line"]};border-radius:12px;">'
        f'<img src="{html.escape(ref)}" alt="{html.escape(alt)}" '
        f'style="display:block;width:100%;height:auto;border-radius:8px;border:1px solid {style["line"]};background:#fff;box-sizing:border-box;" />'
        f'<p style="margin:10px 4px 0;text-align:center;color:{style["muted"]};font-size:13px;line-height:1.7;">{html.escape(caption)}</p>'
        "</section>"
    )


def markdown_body_to_wechat_html(markdown: str, style_id: str = "professional") -> str:
    style = WECHAT_STYLES.get(style_id, WECHAT_STYLES["professional"])
    parts: list[str] = []
    paragraph_buffer: list[str] = []
    first_h1_skipped = False

    def flush_paragraph() -> None:
        nonlocal paragraph_buffer
        if not paragraph_buffer:
            return
        text = "<br>".join(html.escape(item) for item in paragraph_buffer)
        parts.append(
            f'<p style="margin:0 0 19px;color:{style["ink"]};font-size:16px;line-height:2.08;letter-spacing:0;">'
            f"{text}</p>"
        )
        paragraph_buffer = []

    for raw in markdown.splitlines():
        line = raw.strip()
        if not line:
            flush_paragraph()
            continue
        if line.startswith("# "):
            flush_paragraph()
            if not first_h1_skipped:
                first_h1_skipped = True
                continue
            parts.append(
                f'<h1 style="margin:34px 0 18px;color:{style["ink"]};font-size:26px;line-height:1.35;font-weight:800;">'
                f"{html.escape(line[2:].strip())}</h1>"
            )
            continue
        if line.startswith("## "):
            flush_paragraph()
            heading = html.escape(line[3:].strip())
            parts.append(
                f'<section style="margin:46px 0 20px;padding:18px 0 0;border-top:1px solid {style["line"]};">'
                f'<h2 style="margin:0;color:{style["ink"]};font-size:23px;line-height:1.42;font-weight:800;">'
                f"{heading}</h2></section>"
            )
            continue
        if line.startswith("> "):
            flush_paragraph()
            parts.append(
                f'<blockquote style="margin:0 0 30px;padding:18px 20px;border-left:4px solid {style["accent"]};'
                f'background:{style["soft"]};color:{style["ink"]};font-size:16px;line-height:1.95;font-weight:500;">'
                f"{html.escape(line[2:].strip())}</blockquote>"
            )
            continue
        if line.startswith("- "):
            flush_paragraph()
            parts.append(
                f'<p style="margin:0 0 10px;padding-left:16px;color:{style["ink"]};font-size:16px;line-height:1.9;">'
                f"• {html.escape(line[2:].strip())}</p>"
            )
            continue
        paragraph_buffer.append(line)
    flush_paragraph()
    return "\n".join(parts)


def visual_html(kind: str, article: dict[str, Any]) -> str:
    if kind == "cover":
        return f"""<!doctype html><html><head><meta charset="utf-8"><style>
        body {{ margin:0; width:900px; height:383px; background:#f8f7ef; font-family:"PingFang SC","Songti SC",serif; color:#17231d; }}
        .wrap {{ box-sizing:border-box; width:900px; height:383px; padding:42px 54px; position:relative; overflow:hidden; }}
        .rule {{ position:absolute; left:54px; right:54px; bottom:38px; height:1px; background:#cdd9d2; }}
        .tag {{ color:#16845b; font-size:24px; font-weight:800; margin-bottom:24px; }}
        h1 {{ margin:0; font-size:58px; line-height:1.05; letter-spacing:0; max-width:710px; }}
        .sub {{ margin-top:18px; font-size:24px; color:#4d5b53; }}
        .mark {{ position:absolute; right:50px; top:42px; width:118px; height:118px; border:1px solid #b9cbc1; border-radius:50%; display:grid; place-items:center; color:#16845b; font-size:18px; font-weight:800; }}
        </style></head><body><div class="wrap"><div class="tag">Park 的 AI 世界</div><h1>100件事里<br>99件不赚钱</h1><div class="sub">AI时代，先别急着找机会</div><div class="mark">判断<br>先于<br>行动</div><div class="rule"></div></div></body></html>"""
    if kind == "spine":
        return """<!doctype html><html><head><meta charset="utf-8"><style>
        body { margin:0; width:920px; height:520px; background:#f7f5ee; font-family:"PingFang SC","Songti SC",serif; color:#17231d; }
        .wrap { padding:44px; box-sizing:border-box; }
        h2 { margin:0 0 36px; font-size:34px; line-height:1.2; }
        .grid { display:grid; grid-template-columns:repeat(3,1fr); gap:36px; }
        .card { border:1px solid #d4ded8; background:white; border-radius:14px; padding:34px 24px; min-height:210px; }
        .num { color:#16845b; font-size:22px; font-weight:900; }
        h3 { margin:28px 0 16px; font-size:28px; }
        p { margin:0; font-size:20px; line-height:1.65; color:#46544d; }
        .foot { margin-top:34px; padding:18px 22px; background:#e8f3ee; border-left:5px solid #16845b; font-size:22px; line-height:1.55; }
        </style></head><body><div class="wrap"><h2>文章主线</h2><div class="grid"><div class="card"><div class="num">01</div><h3>先定义赌注</h3><p>知道自己在赌什么</p></div><div class="card"><div class="num">02</div><h3>再找不变变量</h3><p>避开无效机会</p></div><div class="card"><div class="num">03</div><h3>最后加速迭代</h3><p>把 AI 放进系统</p></div></div><div class="foot">先定义赌注，再识别不变变量，最后用 AI 加速迭代。</div></div></body></html>"""
    if kind == "decision":
        return """<!doctype html><html><head><meta charset="utf-8"><style>
        body { margin:0; width:920px; height:520px; background:#fbfaf4; font-family:"PingFang SC","Songti SC",serif; color:#17231d; }
        .wrap { padding:44px; box-sizing:border-box; }
        h2 { margin:0 0 26px; font-size:34px; line-height:1.2; }
        .grid { display:grid; grid-template-columns:repeat(3,1fr); gap:18px; }
        .card { border:1px solid #d4ded8; background:white; border-radius:14px; padding:24px; min-height:230px; }
        .num { color:#16845b; font-size:22px; font-weight:900; }
        h3 { margin:18px 0 12px; font-size:25px; }
        p { margin:0; font-size:19px; line-height:1.65; color:#46544d; }
        .foot { margin-top:24px; padding:16px 18px; background:#edf5ef; border-left:5px solid #16845b; font-size:20px; line-height:1.55; }
        </style></head><body><div class="wrap"><h2>做一件事之前，先回答三个问题</h2><div class="grid"><div class="card"><div class="num">01</div><h3>我在赌什么？</h3><p>先说清楚真正的变量，不要只看机会表面。</p></div><div class="card"><div class="num">02</div><h3>错了怎么知道？</h3><p>提前定义失效信号，避免有仓位后自我说服。</p></div><div class="card"><div class="num">03</div><h3>我在哪里离开？</h3><p>止盈可以动态，但亏损边界要前置。</p></div></div><div class="foot">理智必须发生在下场之前，而不是亏损之后。</div></div></body></html>"""
    if kind == "framework":
        return """<!doctype html><html><head><meta charset="utf-8"><style>
        body { margin:0; width:920px; height:560px; background:#f7f8f2; font-family:"PingFang SC","Songti SC",serif; color:#17231d; }
        .wrap { padding:44px 54px; box-sizing:border-box; }
        h2 { margin:0 0 28px; font-size:34px; }
        .tree { display:grid; gap:14px; }
        .row { display:grid; grid-template-columns:150px 1fr; gap:16px; align-items:stretch; }
        .label { display:grid; place-items:center; border-radius:12px; background:#173329; color:white; font-size:22px; font-weight:800; }
        .box { border:1px solid #d4ded8; background:white; border-radius:12px; padding:18px 22px; font-size:21px; line-height:1.55; }
        .box b { color:#16845b; }
        .note { margin-top:24px; font-size:20px; color:#4b5a52; line-height:1.6; }
        </style></head><body><div class="wrap"><h2>别只换工具，要改底层框架</h2><div class="tree"><div class="row"><div class="label">上层</div><div class="box"><b>工具和动作</b>：AI软件、平台玩法、提示词、发布流程</div></div><div class="row"><div class="label">中层</div><div class="box"><b>方法和系统</b>：复盘、工作流、选题、判断标准</div></div><div class="row"><div class="label">底层</div><div class="box"><b>价值观和假设</b>：什么值得做，什么不值得做，什么不能变</div></div></div><div class="note">应用层会变，但底层抽象决定你能不能持续迁移能力。</div></div></body></html>"""
    if kind == "memo_matrix":
        return """<!doctype html><html><head><meta charset="utf-8"><style>
        body { margin:0; width:920px; height:560px; background:#f6f9fd; font-family:"PingFang SC","Songti SC",serif; color:#172333; }
        .wrap { padding:42px 46px; box-sizing:border-box; }
        h2 { margin:0 0 24px; font-size:34px; }
        table { width:100%; border-collapse:separate; border-spacing:0; overflow:hidden; border:1px solid #d8e2ef; border-radius:14px; background:white; }
        th, td { padding:18px 20px; border-bottom:1px solid #d8e2ef; text-align:left; vertical-align:top; font-size:20px; line-height:1.55; }
        th { width:170px; color:#245ea8; background:#edf4fb; font-weight:900; }
        tr:last-child th, tr:last-child td { border-bottom:0; }
        .foot { margin-top:22px; padding:16px 20px; background:#e8f0fb; border-left:5px solid #245ea8; font-size:20px; line-height:1.6; }
        </style></head><body><div class="wrap"><h2>这件事是否值得做？</h2><table><tr><th>判断</th><td>不要先问机会大不大，先问赌注、失效信号和退出条件是否清楚。</td></tr><tr><th>证据</th><td>仓位会改变判断；工具平权后，简单机会会被更快卷掉。</td></tr><tr><th>风险</th><td>把旧周期经验当永恒真理，把一次结果误认为因果。</td></tr><tr><th>行动</th><td>先排除 99 件低复利的事，再把 AI 放进高频迭代系统。</td></tr></table><div class="foot">备忘录不是为了好看，而是为了下次决策时能直接复用。</div></div></body></html>"""
    if kind == "iteration_loop":
        return """<!doctype html><html><head><meta charset="utf-8"><style>
        body { margin:0; width:920px; height:560px; background:#f4fbf9; font-family:"PingFang SC","Songti SC",serif; color:#12231f; }
        .wrap { padding:42px 48px; box-sizing:border-box; }
        h2 { margin:0 0 34px; font-size:34px; }
        .flow { display:grid; grid-template-columns:repeat(4,1fr); gap:18px; align-items:stretch; }
        .node { background:white; border:1px solid #cfe6df; border-radius:18px; padding:24px 18px; min-height:190px; position:relative; }
        .node:after { content:"→"; position:absolute; right:-18px; top:72px; color:#0f766e; font-size:28px; font-weight:900; }
        .node:last-child:after { content:""; }
        .num { color:#0f766e; font-size:22px; font-weight:900; }
        h3 { margin:18px 0 12px; font-size:25px; }
        p { margin:0; font-size:19px; line-height:1.6; color:#4b625d; }
        .note { margin-top:28px; padding:18px 22px; background:#e4f5f1; border-left:5px solid #0f766e; font-size:21px; line-height:1.55; }
        </style></head><body><div class="wrap"><h2>AI时代的个人迭代回路</h2><div class="flow"><div class="node"><div class="num">01</div><h3>记录</h3><p>把判断、行动和理由留下来。</p></div><div class="node"><div class="num">02</div><h3>复盘</h3><p>区分结果、样本和真实因果。</p></div><div class="node"><div class="num">03</div><h3>修正</h3><p>改底层框架，而不是只换工具。</p></div><div class="node"><div class="num">04</div><h3>再行动</h3><p>用 AI 加速下一轮小步快跑。</p></div></div><div class="note">竞争不只是聪明程度，而是正向迭代的速度。</div></div></body></html>"""
    return """<!doctype html><html><body></body></html>"""


async def render_visuals(media_dir: Path, article: dict[str, Any]) -> dict[str, str]:
    media_dir.mkdir(parents=True, exist_ok=True)
    specs = {
        "cover": media_dir / "cover.png",
        "spine": media_dir / "article-spine.png",
        "decision": media_dir / "decision-checklist.png",
        "framework": media_dir / "framework-layers.png",
        "memo_matrix": media_dir / "memo-matrix.png",
        "iteration_loop": media_dir / "iteration-loop.png",
    }
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 920, "height": 620}, device_scale_factor=2)
        try:
            for kind, path in specs.items():
                await page.set_content(visual_html(kind, article), wait_until="load")
                if kind == "cover":
                    await page.set_viewport_size({"width": 900, "height": 383})
                else:
                    await page.set_viewport_size({"width": 920, "height": 620})
                await page.screenshot(path=str(path), full_page=False)
        finally:
            await browser.close()
    return {key: str(value) for key, value in specs.items()}


def build_article(package: dict[str, Any]) -> dict[str, Any]:
    original_title = str(package.get("title") or "")
    title = "100件事里99件不赚钱：AI时代，先别急着找机会"
    digest = "AI时代最重要的不是做更多事，而是先判断哪些事不值得做：定义赌注、守住止损、重塑底层框架，再用AI加速迭代。"
    topics = pick_topics(package)
    topic_lookup = {str(topic.get("title") or ""): topic for topic in topics}

    intro = [
        "如果把这条视频压缩成一句话，我会说：AI时代不是机会突然变少了，而是“看起来能做的事”变多了，但真正能赚钱、能积累、能长期复利的事反而更少了。",
        "过去很多事情，只要赶上流量、赶上平台、赶上某个行业红利，就有机会做成。但现在不一样。工具平权以后，真正拉开差距的不是谁会用一个新工具，而是谁能更早判断：这件事到底值不值得做。",
        "所以这篇文章不讲某个具体工具，也不讲一个简单的赚钱方法。它讲的是在 AI 时代做判断的一套底层顺序：先定义赌注，再识别不变的东西，然后用 AI 加速自己的迭代。",
    ]

    sections: list[str] = []
    sections.append(section_markdown("一、先问清楚：我到底在赌什么？", intro))

    trading = topic_lookup.get("交易和创业前先回答“我到底在赌什么”") or (topics[0] if topics else {})
    sections.append(
        section_markdown(
            "二、交易和创业的第一步，不是找机会，而是定义退出条件",
            [
                topic_field(trading, "claim")
                or "不管交易、创业还是投钱下场，真正重要的是先定义赌注、止损和退出条件，而不是只看机会本身。",
                "很多人以为交易靠的是判断方向，但只要你真的有了仓位，就会发现另一件事：人会自动寻找支持自己仓位的信息。仓位一旦存在，屁股就会开始决定脑袋。",
                "所以理智必须前置。你不能等市场已经打到脸上，才开始问自己“我是不是错了”。下单之前就要知道：我赌的变量是什么？什么情况说明这个变量失效？我在哪里离开？",
                "止盈可以动态，因为趋势加速时，空间可能比一开始想象得更大。但亏损边界最好提前设定。它不是为了限制想象力，而是为了防止人在压力中自我欺骗。",
            ],
        )
    )

    frame = topic_lookup.get("应用层会变化，底层抽象和思维框架才是人的能量来源") or {}
    sections.append(
        section_markdown(
            "三、不要被应用层热闹骗了，真正稀缺的是底层框架",
            [
                topic_field(frame, "claim")
                or "AI工具、部署、自媒体应用都会变，但一个人真正长期有价值的是自己的底层抽象和可迭代的思维框架。",
                "网上每天都有新的 AI 工具、新的部署教程、新的提示词、新的自媒体玩法。这些当然有用，但它们都是应用层。",
                "应用层会不断变化。今天流行这个工具，明天换成另一个工具；今天某个平台有效，明天规则可能又变了。真正决定一个人能不能迁移能力的，是他有没有自己的底层抽象。",
                "我会把思维框架想成一棵树。最底层是价值观和判断标准，中层是方法论，上层才是具体工具和动作。一个人如果只在上层换工具，就会很忙；如果能修改底层框架，就会真的变强。",
            ],
        )
    )

    assumption = topic_lookup.get("重塑底层价值观，是AI时代最稀缺的能力之一") or {}
    sections.append(
        section_markdown(
            "四、AI冲击下，旧假设不一定继续成立",
            [
                topic_field(assumption, "claim")
                or "AI冲击下，过去很多被当成真理的假设都可能失效，能不能质疑并重塑底层价值观决定个人上限。",
                "很多长辈会说：我活了几十年，世界一直是这样运行的。但问题是，过去几十年的经验，可能只是一个历史周期里的经验。",
                "美国霸权、全球化、互联网红利、平台流量、职业稳定性，这些东西都曾经看起来很稳。但当 AI 进入社会，它会重新分配生产力、注意力和资源。",
                "这时最重要的能力不是否定一切，而是区分两件事：哪些假设只是时代产物，哪些东西真的接近不变。",
            ],
        )
    )

    certainty = topic_lookup.get("在快速变化中找不变：不确定性、黄金、视频和存储") or {}
    sections.append(
        section_markdown(
            "五、变化越快，越要找“不用赌太多”的确定性",
            [
                topic_field(certainty, "claim")
                or "未来的不确定性会增加，科技发展会加速，视频内容会爆发，存储需求会成为更接近确定性的长期变量。",
                "很多时候，真正好的判断不是找到一个别人完全不知道的秘密，而是在一堆变化里找到最稳定的变量。",
                "比如不确定性增加时，黄金为什么有价值？不是因为它每天都涨，而是因为它代表一种长期存在的避险需求。",
                "再比如 AI 时代，视频会越来越多，视频质量会越来越高，生成内容会越来越便宜。那么随之而来的存储需求，就比押注某一家具体公司更接近底层变量。",
                "这就是我说的：不要总是在最拥挤、最细节的地方下注。先找出房间里的大象，再判断哪些细节值得看。",
            ],
        )
    )

    ai_workflow = topic_lookup.get("AI沟通的关键不是问对一句话，而是think out loud") or {}
    sections.append(
        section_markdown(
            "六、和 AI 协作，不是一次问对，而是把思考倒出来",
            [
                topic_field(ai_workflow, "claim")
                or "普通人不必一开始就问出完美问题，更有效的方式是把脑内想法完整倒出来，让AI追问、整理、收敛成single source of truth。",
                "很多人用 AI 的压力来自于：我是不是要先写出一个完美 prompt？我觉得不需要。",
                "真正有效的方式是 think out loud。你先把脑子里的东西倒出来，哪怕它们混乱、重复、不成体系，也没关系。让 AI 帮你追问、归类、提炼，最后收敛成一个 single source of truth。",
                "人擅长判断方向、设定边界、定义成功标准。AI 擅长快速整理、快速执行、快速迭代。把 AI 当合作伙伴，而不是当一个被动工具，这件事会改变你的工作方式。",
            ],
        )
    )

    iteration = topic_lookup.get("人的成长，本质是提高迭代速度") or {}
    sections.append(
        section_markdown(
            "七、人的成长，本质是提高迭代速度",
            [
                topic_field(iteration, "claim")
                or "人与人之间的差距，很多时候不是单次判断差距，而是复盘、记录、修正和重新行动的迭代速度差距。",
                "康威生命游戏给我的启发是：简单规则在足够大的空间、足够长的时间和足够多的迭代里，会演化出非常复杂的结果。",
                "人也是这样。你每天写日记、复盘决策、记录自己为什么判断、为什么行动、为什么失败，本质上是在提高自己的 iteration rate。",
                "AI 的价值也在这里。它能让很多原来需要几天的整理和尝试，变成十几分钟一次的小步快跑。只要每次迭代方向大体正确，长期差距会非常大。",
            ],
        )
    )

    media = topic_lookup.get("一定要做自媒体：过程本身也可以成为产品") or {}
    sections.append(
        section_markdown(
            "八、为什么普通人也要做自媒体",
            [
                topic_field(media, "claim")
                or "普通人不一定一开始就能做出强产品，但可以把做产品、学工具、建立判断的过程公开出来，让过程本身成为内容和产品。",
                "做一个真正有价值的产品很难。但把自己做产品、学 AI、建立判断系统的过程记录下来，这件事本身就可以成为内容。",
                "你做不出来一个很厉害的 app 没关系，你把怎么做、怎么失败、怎么调整、怎么复盘讲清楚，这个过程就有价值。",
                "在未来，个人既是生产者，也是媒介，也是产品。你能不能持续输出判断，能不能让别人相信你的框架，会变得越来越重要。",
            ],
        )
    )

    conclusion = [
        "所以，AI时代不是让人去追更多工具，而是逼每个人重新问：我到底靠什么做判断？我如何定义边界？我能不能持续迭代？",
        "100件事里99件不赚钱，听起来很悲观。但反过来看，它也意味着：如果你能更早排除那99件事，把精力放到真正有复利的方向上，你的胜率反而会变高。",
        "不要急着做更多事。先问清楚你在赌什么，哪些假设已经变了，哪些东西仍然不变。然后，把 AI 放进你的系统里，让它帮你更快复盘、更快执行、更快迭代。",
        "这可能才是普通人在 AI 时代最现实的生存方式。",
    ]
    sections.append(section_markdown("结尾：少做无效动作，把 AI 放进自己的迭代系统", conclusion))

    markdown = "\n\n".join(
        [
            f"# {title}",
            "",
            f"> {digest}",
            "",
            *sections,
        ]
    ).strip() + "\n"
    return {
        "title": title,
        "digest": digest,
        "source_title": clean_hashtags(original_title),
        "markdown": markdown,
    }


def style_article(base: dict[str, Any], style_id: str) -> dict[str, Any]:
    if style_id == "professional":
        return base
    title = base["title"]
    source_title = base["source_title"]
    if style_id == "deep_read":
        digest = "这不是一篇工具清单，而是一篇关于 AI 时代如何判断机会、重塑底层框架、提高个人迭代速度的长文。"
        markdown = f"""# {title}

> {digest}

## 开头：真正稀缺的不是机会，而是判断机会的能力

AI 时代看起来什么都能做：新工具、新平台、新模型、新工作流每天都在出现。但问题也在这里。当选择突然变多，一个人最需要的能力反而不是做更多事，而是更早判断哪些事根本不值得做。

这条视频里真正重要的主线，不是某个具体工具，也不是某个单点机会，而是一套判断顺序：先定义自己在赌什么，再识别哪些变量真的变化了，最后把 AI 放进自己的迭代系统。

## 第一层：先定义赌注，再谈机会

不管交易、创业还是投钱下场，很多人一开始就盯着机会本身。但只要你真的有了仓位，就会发现判断会被位置改变。你会主动寻找支持自己仓位的信息，也会更难承认自己错了。

所以理智必须前置。下场之前，要先回答三个问题：我到底在赌什么？什么情况说明我错了？我在哪里离开？止盈可以动态，但亏损边界和退出理由最好提前定义。

## 第二层：应用层会变，底层框架才决定迁移能力

很多 AI 内容讲的是应用层：怎么用工具、怎么部署、怎么写提示词、怎么做自媒体。这些当然有用，但它们不是最底层的能力。应用层每天都在变，今天有效的工具，明天可能被另一个工具替代。

真正长期有价值的是自己的底层抽象：你如何判断什么值得做，什么不值得做；你如何识别变量；你如何复盘一次成败；你如何从旧经验里分离出仍然有效的部分。

## 第三层：旧周期经验不能自动外推到未来

过去几十年的很多经验，可能只是一个特定历史周期的产物。全球化、平台流量、职业稳定性、互联网红利，这些都曾经看起来很稳。但 AI 进入社会以后，生产力、注意力和资源都会重新分配。

所以质疑底层假设不是为了否定一切，而是为了区分：哪些只是时代产物，哪些更接近不变的人性、伦理和基本价值。

## 第四层：变化越快，越要找不用赌太多的确定性

好的判断不一定是找到一个别人完全不知道的秘密，而是在变化中找到稳定变量。比如不确定性增加时，黄金代表一种长期避险需求；视频越来越多、质量越来越高时，存储需求会被持续放大。

这类判断不依赖押中某一家公司的短期胜负，而是来自对底层变量的识别。

## 第五层：AI 的价值，是提高个人迭代速度

AI 不只是帮你写东西或查资料。更重要的是，它可以让一个人更快记录、更快整理、更快复盘、更快试错。过去需要几天才能完成的一轮思考，现在可能十几分钟就能跑一遍。

人与人之间的差距，很多时候不是单次聪明程度，而是长期迭代速度。每天记录判断、复盘决策、修正框架，再把 AI 放进这个循环里，才是更现实的生存方式。

## 结尾：少做无效动作，把 AI 放进自己的系统

100 件事里 99 件不赚钱，听起来悲观。但反过来看，如果你能更早排除那 99 件低复利的事，把精力放到真正有复利的方向上，胜率会更高。

不要急着做更多事。先问清楚你在赌什么，哪些假设已经变了，哪些东西仍然不变。然后让 AI 帮你更快复盘、更快执行、更快迭代。
"""
    elif style_id == "memo":
        digest = "一份面向决策的备忘录：先定义赌注，再识别不变变量，最后用 AI 提高迭代速度。"
        markdown = f"""# {title}

> {digest}

## Memo 结论

- AI 时代不是机会变少，而是看起来能做的事变多，真正值得做的事变少。
- 做任何交易、创业或内容生产之前，先定义赌注、失效信号和退出条件。
- 不要把应用层工具当成核心能力，底层判断框架才决定迁移能力。
- AI 的核心价值不是替你判断，而是提高记录、复盘、修正和执行的迭代速度。

## 1. 判断：我到底在赌什么？

很多决策失败，不是因为一开始没有信息，而是因为没有定义赌注。下场之后，人会主动寻找支持自己仓位的信息，所以理智必须前置到行动之前。

最小判断清单：
- 我押注的核心变量是什么？
- 什么信号说明这个变量失效？
- 如果我错了，退出条件是什么？
- 这个机会是否真的值得占用注意力和时间？

## 2. 证据：为什么应用层机会会越来越卷？

AI 和互联网表面上让工具更平权，但资源会向更会使用工具、更会定义问题、更会快速迭代的人集中。过去很多简单赚钱路径，在工具平权之后会被更快抹平。

所以只追逐应用层热闹是不够的。新工具、提示词、平台玩法都会变，真正能迁移的是底层抽象：判断标准、复盘方法、边界意识和对变量的识别能力。

## 3. 风险：哪些旧经验不能继续外推？

过去几十年的职业稳定性、平台流量红利、互联网机会，不一定能自动外推到未来。把旧周期经验当成永恒真理，是 AI 时代很危险的决策方式。

需要警惕的误判：
- 用一次结果倒推整套系统对错。
- 把短期流量当成自己的资产。
- 把工具熟练度误认为判断能力。
- 把旧周期的成功经验当成新周期的底层规律。

## 4. 机会：什么东西更接近不变变量？

变化越快，越要寻找更少依赖单一赢家的底层变量。不确定性增加、视频内容扩张、存储需求上升、个人媒体化，这些都比押注某一个短期热点更接近结构性变量。

这不是具体投资建议，而是一种判断方式：不要先问哪个机会最热，先问哪个变量最不容易消失。

## 5. 行动条件：下一步应该怎么做？

- 每天记录自己的重要判断。
- 对每次行动写下赌注、失效信号和退出条件。
- 用 AI 帮自己整理、追问、复盘，而不是只让 AI 执行碎片任务。
- 每周复盘一次：哪些判断来自旧假设？哪些变量真的变了？哪些动作只是热闹但没有复利？

## Final Note

100 件事里 99 件不赚钱，不是让人停止行动，而是提醒人：先排除低复利动作，再把 AI 放进真正值得迭代的系统里。
"""
    elif style_id == "diagram":
        digest = "用一套图解框架理解这条视频：赌注、变量、框架、迭代。"
        markdown = f"""# {title}

> {digest}

## 先看整条逻辑链

这条视频可以拆成四个层级：

- 第一层：行动之前，先定义赌注。
- 第二层：变化之中，寻找不变变量。
- 第三层：不要只换工具，要改底层框架。
- 第四层：用 AI 提高个人迭代速度。

## 01 先定义赌注

任何交易、创业、投资或内容生产，都不是先问“机会在哪里”，而是先问“我到底在赌什么”。

如果你不知道自己在赌什么，就不知道什么情况说明自己错了；如果不知道什么情况说明自己错了，就会在下场之后不断寻找支持自己的信息。

## 02 找到不变变量

AI 时代变化会越来越快，但不是所有东西都变。真正重要的是识别哪些变量更接近长期存在。

比如不确定性增加、视频媒介扩张、存储需求上升、个人媒体化，这些都比短期热点更值得作为框架变量来观察。

## 03 改底层框架

很多人以为学会一个新工具就完成升级，但工具只是上层。更底层的是你如何判断一件事是否值得做，如何复盘一次失败，如何修改自己的旧假设。

应用层热闹会不断变化，底层框架决定你能不能迁移。

## 04 提高迭代速度

AI 真正改变个人生产力的地方，是把一次复盘、一次整理、一次试错的成本压低。

过去一周才能完成的一轮思考，现在可能十几分钟就能跑一次。如果每次迭代方向大体正确，长期差距会被快速拉开。

## 最后一句

不要急着做更多事。先定义赌注，识别变量，改底层框架，再用 AI 加速迭代。
"""
    else:
        return base
    return {
        "title": title,
        "digest": digest,
        "source_title": source_title,
        "markdown": markdown.strip() + "\n",
    }


def figures_for_style(style_id: str, images: dict[str, str]) -> tuple[list[tuple[str, str, str]], list[tuple[str, str, str]]]:
    if style_id == "deep_read":
        return (
            [("spine", "文章主线：先定义赌注，再识别不变变量，最后用 AI 加速迭代。", "文章主线")],
            [],
        )
    if style_id == "memo":
        return (
            [("memo_matrix", "这不是灵感记录，而是一份可以复用的决策备忘录。", "判断备忘录")],
            [("decision", "行动前先写清楚赌注、失效信号和退出条件。", "做一件事之前，先回答三个问题")],
        )
    if style_id == "diagram":
        return (
            [
                ("spine", "整条内容的主线：赌注、变量、框架、迭代。", "文章主线"),
                ("iteration_loop", "AI 时代的个人迭代回路。", "AI时代的个人迭代回路"),
            ],
            [("framework", "真正能迁移的不是工具，而是底层框架。", "底层框架决定迁移能力")],
        )
    return (
        [
            ("spine", "先定义赌注，再识别不变变量，最后用 AI 加速迭代。", "文章主线"),
            ("decision", "判断先于行动：先定义赌注、失效信号和退出条件。", "做一件事之前，先回答三个问题"),
        ],
        [("framework", "不要只追应用层热闹，真正长期有效的是底层框架。", "底层框架决定迁移能力")],
    )


def preview_figures_html(figures: list[tuple[str, str, str]], images: dict[str, str]) -> str:
    chunks = []
    for key, caption, alt in figures:
        image = images.get(key)
        if not image:
            continue
        chunks.append(
            f'<figure><img src="{html.escape(image_ref(Path(image)))}" alt="{html.escape(alt)}">'
            f"<figcaption>{html.escape(caption)}</figcaption></figure>"
        )
    return "\n".join(chunks)


def markdown_to_preview_html(article: dict[str, Any], images: dict[str, str] | None = None, style_id: str = "professional") -> str:
    images = images or {}
    style = WECHAT_STYLES.get(style_id, WECHAT_STYLES["professional"])
    lines = article["markdown"].splitlines()
    html_lines: list[str] = []
    in_list = False
    for raw in lines:
        line = raw.strip()
        if not line:
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            continue
        if line.startswith("# "):
            html_lines.append(f"<h1>{html.escape(line[2:])}</h1>")
        elif line.startswith("## "):
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append(f"<h2>{html.escape(line[3:])}</h2>")
        elif line.startswith("> "):
            html_lines.append(f"<blockquote>{html.escape(line[2:])}</blockquote>")
        elif line.startswith("- "):
            if not in_list:
                html_lines.append("<ul>")
                in_list = True
            html_lines.append(f"<li>{html.escape(line[2:])}</li>")
        else:
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append(f"<p>{html.escape(line)}</p>")
    if in_list:
        html_lines.append("</ul>")

    leading_figures, trailing_figures = figures_for_style(style_id, images)

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(article['title'])}</title>
  <style>
    :root {{
      --ink:#17231d;
      --muted:#65736b;
      --line:#d9e2dc;
      --accent:#16845b;
      --paper:#fffef9;
      --soft:#f4f8f3;
    }}
    body {{
      margin:0;
      background:#eef2ed;
      color:var(--ink);
      font-family:"PingFang SC","Songti SC","Noto Serif CJK SC",serif;
    }}
    .phone {{
      max-width:720px;
      margin:0 auto;
      background:var(--paper);
      min-height:100vh;
      box-shadow:0 16px 50px rgba(27,48,38,.12);
    }}
    .cover {{
      padding:42px 44px 34px;
      border-bottom:1px solid var(--line);
      background:linear-gradient(135deg,#fdfbf4 0%,#f4f8f3 100%);
    }}
    .eyebrow {{
      color:var(--accent);
      font-size:14px;
      font-weight:700;
      margin-bottom:18px;
    }}
    h1 {{
      margin:0;
      font-size:34px;
      line-height:1.18;
      letter-spacing:0;
      font-weight:800;
    }}
    .meta {{
      margin-top:20px;
      color:var(--muted);
      font-size:14px;
    }}
    article {{
      padding:34px 44px 52px;
    }}
    blockquote {{
      margin:0 0 28px;
      padding:16px 18px;
      border-left:4px solid var(--accent);
      background:var(--soft);
      color:#34453b;
      line-height:1.8;
      font-size:16px;
    }}
    h2 {{
      margin:34px 0 16px;
      font-size:23px;
      line-height:1.35;
      letter-spacing:0;
      padding-top:10px;
      border-top:1px solid var(--line);
    }}
    p {{
      margin:0 0 16px;
      font-size:17px;
      line-height:1.95;
    }}
    ul {{
      margin:0 0 18px;
      padding-left:22px;
      color:#2d3b34;
      font-size:16px;
      line-height:1.8;
    }}
    .diagram {{
      margin:26px 0;
      border:1px solid var(--line);
      background:#fbfdf9;
      border-radius:10px;
      padding:18px;
      display:grid;
      gap:10px;
    }}
    .diagram strong {{
      color:var(--accent);
    }}
    .diagram-grid {{
      display:grid;
      grid-template-columns:repeat(3,1fr);
      gap:10px;
    }}
    .diagram-grid div {{
      border:1px solid var(--line);
      background:#fff;
      border-radius:8px;
      padding:12px;
      line-height:1.55;
      font-size:14px;
    }}
    figure {{
      margin:26px 0 30px;
    }}
    figure img {{
      display:block;
      width:100%;
      border-radius:10px;
      border:1px solid var(--line);
      background:#fff;
    }}
    figcaption {{
      margin-top:8px;
      text-align:center;
      color:var(--muted);
      font-size:13px;
      line-height:1.5;
    }}
  </style>
</head>
<body>
  <main class="phone">
    <section class="cover">
      <div class="eyebrow">公众号草稿预览 · {html.escape(style["label"])} · Park 的 AI 世界</div>
      <h1>{html.escape(article['title'])}</h1>
      <div class="meta">基于抖音视频整理：{html.escape(article['source_title'])}</div>
    </section>
    <article>
      {preview_figures_html(leading_figures, images)}
      {''.join(html_lines)}
      {preview_figures_html(trailing_figures, images)}
    </article>
  </main>
</body>
</html>
""".replace("--ink:#17231d;", f"--ink:{style['ink']};").replace("--muted:#65736b;", f"--muted:{style['muted']};").replace("--line:#d9e2dc;", f"--line:{style['line']};").replace("--accent:#16845b;", f"--accent:{style['accent']};").replace("--paper:#fffef9;", f"--paper:{style['paper']};").replace("--soft:#f4f8f3;", f"--soft:{style['soft']};")


def markdown_to_wechat_compatible_html(article: dict[str, Any], images: dict[str, str] | None = None, style_id: str = "professional") -> str:
    images = images or {}
    style = WECHAT_STYLES.get(style_id, WECHAT_STYLES["professional"])
    body_html = markdown_body_to_wechat_html(article["markdown"], style_id)
    leading_figures, trailing_figures = figures_for_style(style_id, images)
    leading_html = "\n    ".join(figure_html(images.get(key), caption, alt, style_id) for key, caption, alt in leading_figures)
    trailing_html = "\n    ".join(figure_html(images.get(key), caption, alt, style_id) for key, caption, alt in trailing_figures)
    return f"""<section style="max-width:677px;margin:0 auto;padding:0 0 36px;background:{style["paper"]};color:{style["ink"]};font-family:{style["font"]};">
  <section style="margin:0 0 28px;padding:36px 28px 28px;background:{style["soft"]};border-bottom:1px solid {style["line"]};">
    <p style="margin:0 0 14px;color:{style["accent"]};font-size:14px;line-height:1.6;font-weight:800;">Park 的 AI 世界 · {html.escape(style["label"])}</p>
    <h1 style="margin:0;color:{style["ink"]};font-size:30px;line-height:1.28;font-weight:800;letter-spacing:0;">{html.escape(article['title'])}</h1>
    <p style="margin:18px 0 0;color:{style["muted"]};font-size:14px;line-height:1.8;">基于抖音视频整理：{html.escape(article['source_title'])}</p>
  </section>
  <section style="padding:0 28px;">
    <section style="margin:0 0 30px;padding:18px 18px;background:#ffffff;border:1px solid {style["line"]};border-radius:12px;">
      <p style="margin:0 0 8px;color:{style["accent"]};font-size:13px;line-height:1.6;font-weight:800;">文章主线</p>
      <p style="margin:0;color:{style["ink"]};font-size:16px;line-height:1.95;">先定义赌注，再识别不变变量，最后把 AI 放进自己的迭代系统。重点不是追更多机会，而是更早排除不值得做的事。</p>
    </section>
    {leading_html}
    {body_html}
    {trailing_html}
  </section>
</section>
"""


def style_suffix(style_id: str) -> str:
    return "" if style_id == "professional" else f".{style_id}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate WeChat MP article draft from a Park-IO content package.")
    parser.add_argument("--source-content-id", required=True)
    parser.add_argument("--output-json", default="")
    args = parser.parse_args()

    source_dir = source_dir_for(args.source_content_id)
    package = read_json(source_dir / "transcript/content-package.json")
    article = build_article(package)

    DRAFT_DIR.mkdir(parents=True, exist_ok=True)
    slug = "2026-05-25--ai-100-99--wechat_mp-7613803738997722394-01"
    json_path = Path(args.output_json) if args.output_json else DRAFT_DIR / f"{slug}.json"
    md_path = json_path.with_suffix(".md")
    html_path = json_path.with_suffix(".html")
    wechat_html_path = json_path.with_name(f"{json_path.stem}.wechat.html")
    media_dir = media_dir_for(json_path)
    previous_record = read_json(json_path) if json_path.exists() else {}

    md_path.write_text(article["markdown"], encoding="utf-8")
    images = asyncio.run(render_visuals(media_dir, article))
    style_variants: dict[str, dict[str, Any]] = {}
    for style_id, style in WECHAT_STYLES.items():
        variant_article = style_article(article, style_id)
        suffix = style_suffix(style_id)
        variant_html_path = json_path.with_name(f"{json_path.stem}{suffix}.html")
        variant_wechat_html_path = json_path.with_name(f"{json_path.stem}{suffix}.wechat.html")
        variant_html_path.write_text(markdown_to_preview_html(variant_article, images, style_id), encoding="utf-8")
        variant_wechat_html_path.write_text(markdown_to_wechat_compatible_html(variant_article, images, style_id), encoding="utf-8")
        leading_figures, trailing_figures = figures_for_style(style_id, images)
        style_variants[style_id] = {
            "id": style_id,
            "label": style["label"],
            "description": style["description"],
            "title": variant_article["title"],
            "digest": variant_article["digest"],
            "html_preview_path": str(variant_html_path),
            "wechat_html_path": str(variant_wechat_html_path),
            "cover_path": images.get("cover") or "",
            "image_keys": [key for key, _, _ in [*leading_figures, *trailing_figures]],
            "image_paths": [images[key] for key, _, _ in [*leading_figures, *trailing_figures] if images.get(key)],
            "body_chars": len(variant_article["markdown"]),
            "is_default": style_id == "professional",
        }

    record = {
        "platform": "wechat_mp",
        "status": "draft_ready",
        "intended_publish_at": "2026-05-25",
        "local_id": "wechat_mp-7613803738997722394-01",
        "source_platform": "douyin",
        "source_content_id": args.source_content_id,
        "source_url": f"https://www.douyin.com/video/{args.source_content_id}",
        "source_content_type": "video",
        "title": article["title"],
        "digest": article["digest"],
        "body": article["markdown"],
        "markdown_path": str(md_path),
        "html_preview_path": str(html_path),
        "wechat_html_path": str(wechat_html_path),
        "wechat_style": "professional",
        "wechat_style_label": WECHAT_STYLES["professional"]["label"],
        "style_variants": style_variants,
        "cover_path": images.get("cover") or "",
        "rendered_images": [images[key] for key in ("cover", "spine", "decision", "framework") if images.get(key)],
        "rendered_package_dir": str(media_dir),
        "cover_strategy": "text_cover_plus_structure_diagram",
        "image_plan": [
            "封面：使用文字封面，标题直接呈现核心判断。",
            "正文结构图：先定义赌注 → 找不变变量 → 加速迭代。",
            "正文框架图：上层工具 / 中层系统 / 底层价值观。",
            "v1 不依赖 AI 插图；图片只是增强理解，不承载核心信息。",
        ],
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "review_required": True,
    }
    for key in ("latest_platform_draft", "platform_draft_history", "last_push_status", "last_push_message", "last_pushed_at"):
        if previous_record.get(key):
            record[key] = previous_record[key]
    for old_path in DRAFT_DIR.glob("*.json"):
        if old_path == json_path:
            continue
        try:
            old_record = read_json(old_path)
        except Exception:
            continue
        if old_record.get("platform") == "wechat_mp" and str(old_record.get("source_content_id") or "") == args.source_content_id:
            old_record["status"] = "superseded"
            old_record["superseded_by"] = str(json_path)
            old_path.write_text(json.dumps(old_record, ensure_ascii=False, indent=2), encoding="utf-8")
    json_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True, "json": str(json_path), "md": str(md_path), "html": str(html_path), "styles": list(style_variants), "images": images}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
