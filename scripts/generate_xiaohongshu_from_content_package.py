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
OUTBOX = ROOT / "park-io/outbox"
DRAFT_DIR = OUTBOX / "drafts/xiaohongshu"


CLAUDE_SYSTEM_PROMPT = """你是 Park 的小红书图文主编，擅长把长口播里的一个主题改写成可收藏、可搜索、可发布的小红书图文。

你不是摘要助手。你的任务是把 approved topic 写成一篇 2000 字以上的图文笔记脚本。

硬性原则：
1. 核心观点、例子、边界必须来自输入主题和 source excerpt，不要编造投资建议、经历或事实。
2. 可以基于原观点补足解释层、读者体感层、类比层和行动清单，但不能改变原观点。
3. 语言要像作者直接跟读者说话，不要像报告，不要展示内部字段名。
4. 不得出现这些内部字段名：主张、认知反差、Reader Mirror、为什么成立、判断、解释、例子、Boundary、Takeaway、要点、point。
5. 每篇必须有一个贯穿或局部类比，让抽象观点变得可感。
6. 正文目标 2000-2600 中文字；图文卡片 8-10 张，每张适合做一张小红书图。
7. 卡片文案要比摘要更 dense：每张图推进一个判断，尽量包含具体场景、误区、代价、方法或自查问题。
8. 结尾必须给读者一个下一次可以执行的检查动作。

只输出 JSON，不要 Markdown fence，不要解释。
"""


CLAUDE_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "body": {"type": "string"},
        "xhs_argument_pack": {
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "topic": {"type": "string"},
                "one_sentence_claim": {"type": "string"},
                "reader_entry": {"type": "string"},
                "misunderstanding_to_break": {"type": "string"},
                "why_it_holds": {"type": "string"},
                "throughline": {"type": "string"},
                "analogy": {
                    "type": "object",
                    "properties": {
                        "image": {"type": "string"},
                        "setup": {"type": "string"},
                        "turn": {"type": "string"},
                        "lesson": {"type": "string"},
                    },
                    "required": ["image", "setup", "turn", "lesson"],
                    "additionalProperties": False,
                },
                "supporting_scenes": {"type": "array", "items": {"type": "string"}},
                "moves": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "reader_entry": {"type": "string"},
                            "judgment": {"type": "string"},
                            "explanation": {"type": "string"},
                            "scene": {"type": "string"},
                        },
                        "required": ["title", "reader_entry", "judgment", "explanation", "scene"],
                        "additionalProperties": False,
                    },
                },
                "boundary": {"type": "string"},
                "reader_action": {"type": "string"},
                "keywords": {"type": "array", "items": {"type": "string"}},
            },
            "required": [
                "status",
                "topic",
                "one_sentence_claim",
                "reader_entry",
                "misunderstanding_to_break",
                "why_it_holds",
                "throughline",
                "analogy",
                "supporting_scenes",
                "moves",
                "boundary",
                "reader_action",
                "keywords",
            ],
            "additionalProperties": False,
        },
        "image_cards": {"type": "array", "minItems": 8, "maxItems": 10, "items": {"type": "string"}},
        "note_brief": {
            "type": "object",
            "properties": {
                "search_keywords": {"type": "array", "items": {"type": "string"}},
                "target_reader": {"type": "string"},
                "reader_payoff": {"type": "string"},
                "format_rationale": {"type": "string"},
                "card_chain": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["search_keywords", "target_reader", "reader_payoff", "format_rationale", "card_chain"],
            "additionalProperties": False,
        },
    },
    "required": ["title", "body", "xhs_argument_pack", "image_cards", "note_brief"],
    "additionalProperties": False,
}


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def extract_json(text: str) -> dict[str, Any]:
    raw = text.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start < 0 or end <= start:
            raise
        data = json.loads(raw[start : end + 1])
    if isinstance(data, dict) and isinstance(data.get("structured_output"), dict):
        return data["structured_output"]
    if isinstance(data, dict) and isinstance(data.get("result"), str):
        return extract_json(data["result"])
    if not isinstance(data, dict):
        raise ValueError("Claude output is not a JSON object.")
    return data


def slugify(text: str, fallback: str) -> str:
    text = re.sub(r"[#/@:：，。！？!?、|｜\s]+", "-", text.strip())
    text = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff-]+", "", text)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return (text[:36] or fallback).strip("-")


def source_dir_for(source_content_id: str) -> Path:
    matches = sorted((OUTBOX / "sent/douyin").glob(f"*--{source_content_id}"))
    if not matches:
        matches = [path for path in (OUTBOX / "sent/douyin").iterdir() if path.is_dir() and source_content_id in path.name]
    if not matches:
        raise FileNotFoundError(f"没有找到抖音源内容：{source_content_id}")
    return matches[0]


def content_package_for(source_content_id: str) -> tuple[Path, dict[str, Any]]:
    package_path = source_dir_for(source_content_id) / "transcript/content-package.json"
    package = read_json(package_path)
    if not package.get("approved"):
        raise RuntimeError("内容包还没有 approved，先在 dashboard 第二步点通过。")
    return package_path, package


def compact_title(title: str, index: int) -> str:
    mapping = {
        "下场前，先定义自己到底在赌什么": "下场前先问3件事",
        "AI协作不是问神句，而是建立共同工作流": "AI协作别问神句",
        "不要追热点，要用第一性原理找不变变量": "为什么别追AI热点",
        "成长的本质，是提高可反馈的自我迭代速度": "为什么努力迭代还不够",
        "未来大多数事不赚钱，个人要媒体化并占住判断力": "99件事都不赚钱",
        "交易和创业前先回答“我到底在赌什么”": "先想清楚怎么输",
        "AI沟通的关键不是问对一句话，而是think out loud": "AI沟通先倒出来",
        "应用层会变化，底层抽象和思维框架才是人的能量来源": "别被工具热闹骗了",
        "重塑底层价值观，是AI时代最稀缺的能力之一": "旧经验正在失效",
        "在快速变化中找不变：不确定性、黄金、视频和存储": "变化越快越找不变",
        "康威生命游戏：简单规则、足够迭代，会产生复杂生命": "为什么4个条件会进化",
        "真正的成长是提高自我迭代速度": "成长就是提高迭代速度",
        "未来职业三件事：用AI、做媒体、重新理解交易": "未来职业三件事",
        "100件事99件不赚钱：AI和互联网会让资源更集中": "99件事都不赚钱",
        "AI不是附属工具，而是各取所长的合作伙伴": "别把AI当附属工具",
        "Prompt是给AI指针，护栏是承认AI的概率特性": "Prompt不是咒语",
        "第一性原理：每个行业都要问本质是什么": "先问行业本质",
        "所有个体都在用最小能耗预测未来": "人都在预测未来",
        "顺从别人的人性，管理自己的赏罚机制": "别硬扛人性",
    }
    return mapping.get(title) or re.sub(r"[：:，,].*$", "", title)[:18] or f"主题{index}"


def keywords_for(topic: dict[str, Any], title: str) -> list[str]:
    blob = "\n".join(
        str(topic.get(key) or "")
        for key in ("title", "claim", "cognitive_contrast", "boundary")
    )
    candidates = [
        "AI", "AI时代", "交易", "创业", "判断力", "底层框架", "第一性原理", "个人成长",
        "小红书", "自媒体", "工作流", "复盘", "迭代", "Prompt", "AI Agent", "风险管理",
        "止损", "预期差", "价值观", "长期主义", "职业规划", "人性",
    ]
    found = [item for item in candidates if item in blob or item in title]
    if "AI" in blob and "AI" not in found:
        found.insert(0, "AI")
    return (found + ["认知框架", "个人成长", "判断力"])[:5]


def topic_source_excerpt(topic: dict[str, Any], package: dict[str, Any], index: int) -> str:
    examples = topic.get("supporting_examples") or []
    transcript = str(package.get("readable_transcript") or "")
    window = ""
    if transcript:
        production_topics = package.get("fine_topics") or package.get("topics") or package.get("topic_groups") or []
        chunk = max(700, len(transcript) // max(1, len(production_topics)))
        start = min(max(0, (index - 1) * chunk), max(0, len(transcript) - chunk))
        window = transcript[start : start + chunk].strip()
    parts = [
        f"主题：{topic.get('title') or ''}",
        "原文支撑摘录：",
        *[f"- {item}" for item in examples],
        window,
    ]
    text = "\n".join(part for part in parts if str(part).strip())
    if len(text) < 450:
        text = text + "\n\n补充摘录：" + transcript[:700]
    return text


def validate_claude_result(data: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    body = str(data.get("body") or "").strip()
    cards = data.get("image_cards") or []
    pack = data.get("xhs_argument_pack") or {}
    if len(body.replace("\n", "")) < 1600:
        warnings.append("body_below_1600_chars")
    if not isinstance(cards, list) or len(cards) < 8:
        warnings.append("image_cards_below_8")
    if not isinstance(pack, dict) or not pack.get("one_sentence_claim") or not pack.get("analogy"):
        warnings.append("argument_pack_incomplete")
    forbidden = ["主张：", "认知反差", "Reader Mirror", "为什么成立", "判断：", "解释：", "例子：", "Boundary", "Takeaway", "要点：", "point"]
    public_text = "\n".join([body, "\n".join(str(card) for card in cards if str(card).strip())])
    leaked = [item for item in forbidden if item in public_text]
    if leaked:
        warnings.append("public_text_leaks_internal_labels:" + ",".join(leaked))
    return warnings


def xhs_ai_prompt(topic: dict[str, Any], note_title: str, keywords: list[str], source_excerpt: str) -> str:
    return f"""请把下面这个 approved topic 改写成一篇小红书图文笔记。

建议标题：{note_title}
关键词：{", ".join(keywords)}

Approved topic JSON:
{json.dumps(topic, ensure_ascii=False, indent=2)}

Source excerpt / 原视频支撑材料：
{source_excerpt}

请输出：
- title: 小红书标题
- body: 2000-2600 字正文，像作者直接和读者说话
- xhs_argument_pack: 内部立论包
- image_cards: 8-10 张图文卡片文案，每个元素一张图，第一行是该图标题，后面是正文
- note_brief: 给 dashboard 使用的简短结构元数据
"""


def assert_ai_result(data: dict[str, Any], engine: str) -> dict[str, Any]:
    warnings = validate_claude_result(data)
    if warnings:
        raise RuntimeError(f"{engine} output failed validation: " + ";".join(warnings))
    data["xhs_generation_engine"] = engine
    data["xhs_generation_warnings"] = []
    return data


def claude_xhs_draft(topic: dict[str, Any], note_title: str, keywords: list[str], source_excerpt: str, timeout: int) -> dict[str, Any]:
    prompt = xhs_ai_prompt(topic, note_title, keywords, source_excerpt)
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
            json.dumps(CLAUDE_OUTPUT_SCHEMA, ensure_ascii=False),
            "--system-prompt",
            CLAUDE_SYSTEM_PROMPT,
            prompt,
        ],
        text=True,
        capture_output=True,
        timeout=timeout,
    )
    output = (result.stdout or "").strip()
    if result.returncode != 0:
        raise RuntimeError((result.stderr or output).strip())
    envelope = extract_json(output)
    data = envelope.get("structured_output") if isinstance(envelope.get("structured_output"), dict) else envelope
    return assert_ai_result(data, "claude")


def codex_xhs_draft(topic: dict[str, Any], note_title: str, keywords: list[str], source_excerpt: str, timeout: int) -> dict[str, Any]:
    prompt = f"""{CLAUDE_SYSTEM_PROMPT}

{xhs_ai_prompt(topic, note_title, keywords, source_excerpt)}

最终回答必须是严格 JSON，并匹配这个 JSON Schema：
{json.dumps(CLAUDE_OUTPUT_SCHEMA, ensure_ascii=False, indent=2)}
"""
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as schema_file:
        json.dump(CLAUDE_OUTPUT_SCHEMA, schema_file, ensure_ascii=False)
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
        return assert_ai_result(extract_json(raw_output), "codex")
    finally:
        schema_path.unlink(missing_ok=True)
        output_path.unlink(missing_ok=True)


def ai_xhs_draft(topic: dict[str, Any], note_title: str, keywords: list[str], source_excerpt: str, engine: str, timeout: int) -> dict[str, Any]:
    errors: list[str] = []
    if engine in {"auto", "claude"}:
        try:
            claude_timeout = min(timeout, 120) if engine == "auto" else timeout
            return claude_xhs_draft(topic, note_title, keywords, source_excerpt, claude_timeout)
        except Exception as exc:
            errors.append(f"claude:{str(exc)[:1200]}")
            if engine == "claude":
                raise RuntimeError("; ".join(errors)) from exc
    if engine in {"auto", "codex"}:
        try:
            return codex_xhs_draft(topic, note_title, keywords, source_excerpt, timeout)
        except Exception as exc:
            errors.append(f"codex:{str(exc)[:1200]}")
            raise RuntimeError("; ".join(errors)) from exc
    raise ValueError(f"Unsupported engine: {engine}")


def card(role: str, title: str, body: str) -> str:
    return f"{title}\n{body.strip()}"


def xhs_argument_pack(topic: dict[str, Any], note_title: str, keywords: list[str]) -> dict[str, Any]:
    profile = profile_for(topic)
    analogy = analogy_for(topic, profile)
    points = [item for item in (topic.get("points") or []) if isinstance(item, dict)]
    examples = [str(item) for item in (topic.get("supporting_examples") or []) if str(item).strip()]
    claim = str(profile.get("focus") or topic.get("claim") or note_title)
    contrast = str(profile.get("mistake") or topic.get("cognitive_contrast") or "")
    reader_mirror = str(topic.get("reader_mirror") or profile["target_reader"])
    why = str(profile.get("reasoning") or topic.get("why_it_matters") or "")
    boundary = str(topic.get("boundary") or "")
    takeaway = str(topic.get("takeaway") or profile["method"])
    return {
        "status": "internal_argument_pack",
        "topic": note_title,
        "one_sentence_claim": claim,
        "reader_entry": reader_mirror,
        "misunderstanding_to_break": contrast,
        "why_it_holds": why,
        "throughline": f"{claim} 这篇要先抓住读者的常见误区，再给出反对结论，最后用原视频里的场景和边界把它说清楚。",
        "analogy": analogy,
        "supporting_scenes": examples[:4],
        "moves": [
            {
                "title": point.get("title") or f"第 {idx} 层",
                "reader_entry": point.get("reader_mirror") or "",
                "judgment": point.get("judgment") or "",
                "explanation": point.get("explanation") or "",
                "scene": point.get("evidence") or "",
            }
            for idx, point in enumerate(points[:3], start=1)
        ],
        "boundary": boundary,
        "reader_action": takeaway,
        "keywords": keywords,
    }


def analogy_for(topic: dict[str, Any], profile: dict[str, str]) -> dict[str, str]:
    title = str(topic.get("title") or "")
    blob = "\n".join(str(topic.get(key) or "") for key in ("title", "claim", "cognitive_contrast", "reader_mirror"))
    if "赌" in blob or "交易" in blob or "下场" in blob:
        return {
            "image": "在海上划船",
            "setup": "只看方向就下场，就像看到风往东吹，就立刻开始划船。",
            "turn": "但你还没看水流，也没看船上有多少粮，更没想过风变了怎么返航。",
            "lesson": "所以问题不是你会不会划，而是你有没有先定义航线和返航条件。",
        }
    if "AI" in blob or "prompt" in blob or "协作" in blob:
        return {
            "image": "和一个很快但不认识路的人一起开车",
            "setup": "AI 像一个反应很快的司机，但它不一定知道你真正要去哪里。",
            "turn": "你只喊一句“开快点”，它当然会动，但路线、终点、不能走的路都还没定义。",
            "lesson": "所以重点不是一句神 prompt，而是地图、目的地和护栏。",
        }
    if "第一性" in blob or "不变" in blob or "热点" in blob:
        return {
            "image": "在雾里追灯光",
            "setup": "追热点像在雾里追远处的灯，哪里亮就往哪里跑。",
            "turn": "但灯会移动，雾也会变。你跑得越快，越可能离自己的路越远。",
            "lesson": "真正稳定的是地图：地形、方向、边界，还有什么东西不会因为灯变了而消失。",
        }
    if "迭代" in blob or "成长" in blob or "反馈" in blob:
        return {
            "image": "调一台会自动学习的机器",
            "setup": "成长不是给机器喊口号，而是让它每次运行后都留下数据。",
            "turn": "没有反馈，机器只是在重复旧动作；有反馈，它才知道下一次该调哪里。",
            "lesson": "所以真正重要的不是更用力，而是让每一次动作都能反过来校准你。",
        }
    if "赚钱" in blob or "媒体" in blob or "职业" in blob:
        return {
            "image": "在人很多的集市里摆摊",
            "setup": "AI 时代像一个摊位突然变多的集市，门槛低了，摊主也多了。",
            "turn": "如果你卖的东西和别人一样，声音也没人记得，摊位越多，你越容易被淹没。",
            "lesson": "所以问题不是有没有摊位，而是你有没有判断、表达和让人回头找你的理由。",
        }
    return {
        "image": "看地图",
        "setup": "一个复杂问题如果只看表面动作，就像拿着地图只看图标。",
        "turn": "图标很多，但你不知道地形，也不知道自己在第几层路口。",
        "lesson": profile["payoff"],
    }


def sentence_join(*parts: str) -> str:
    return "".join(str(part or "").strip() for part in parts if str(part or "").strip())


def trim_text(text: str, max_len: int = 210) -> str:
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip("，。；、 ") + "。"


def dense_body(*parts: str, max_len: int = 230) -> str:
    cleaned = []
    seen = set()
    for part in parts:
        item = re.sub(r"\s+", " ", str(part or "")).strip(" ，。；\n")
        if not item:
            continue
        key = re.sub(r"\s+", "", item)
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(item)
    text = "。".join(item for item in cleaned if item)
    text = re.sub(r"。{2,}", "。", text).strip("。")
    if text:
        text += "。"
    return trim_text(text, max_len)


TOPIC_PROFILES: dict[str, dict[str, str]] = {
    "下场前，先定义自己到底在赌什么": {
        "focus": "任何重投入之前，先定义赌注、错误信号和退出条件",
        "mistake": "常见错误是先被机会吸引，再用情绪和仓位替自己找理由。",
        "reframe": "先不要问这件事能不能赢，先问自己错的时候怎么退。",
        "reasoning": "因为一旦下场，人会自然筛选支持自己选择的信息；边界必须在压力出现之前定义。",
        "proof_prefix": "市场波动",
        "proof_takeaway": "外部变量一变，原有判断就会被重写；提前写清退出条件，是为了防止临场自我说服。",
        "scene_prefix": "创业和交易",
        "scene_takeaway": "仓位、面子和沉没成本都会改变人的信息系统，所以理性必须前置。",
        "method": "写下三句话：我在赌什么、什么证明我错、错了怎么退出。",
        "close": "勇敢不是不设边界，而是先承认自己可能错。",
        "payoff": "读完后你能把一个机会拆成赌注、止损和退出条件。",
        "search_intent": "交易复盘、创业决策、风险管理",
        "target_reader": "准备交易、创业或投入资源，但还没有明确退出条件的人",
    },
    "AI协作不是问神句，而是建立共同工作流": {
        "focus": "AI协作的核心不是完美 prompt，而是共同工作流和验收边界",
        "mistake": "很多人把 AI 当成命令执行器，以为会问神句就能得到好结果。",
        "reframe": "先把脑内半成品倒出来，让 AI 帮你追问和整理；聊完以后再把共识归档成 source of truth；真正执行时再给任务、边界和验收标准。",
        "reasoning": "因为 brain dump、source of truth 和 guardrails 是三个阶段：先暴露混乱，再沉淀共识，最后带着边界执行。",
        "proof_prefix": "think out loud",
        "proof_takeaway": "先倒出想法不是为了直接形成答案，而是为了让 AI 有材料追问、整理和收敛。",
        "scene_prefix": "prompt 和护栏",
        "scene_takeaway": "prompt 和 guardrails 属于执行阶段；它们应该基于已经确认过的 source of truth，而不是替代前面的思考。",
        "method": "第一步 brain dump；第二步让 AI 追问和整理；第三步人工确认并归档 source of truth；第四步带着 guardrails 执行。",
        "close": "真正高级的 AI 用法，不是把判断交出去，而是把协作结构搭起来。",
        "payoff": "读完后你能把一次 AI 对话变成可复用工作流。",
        "search_intent": "AI工作流、Prompt、AI协作",
        "target_reader": "经常用 AI 但输出不稳定、不知道如何表达需求的人",
    },
    "不要追热点，要用第一性原理找不变变量": {
        "focus": "AI时代最稀缺的是底层框架：从第一性原理找不变变量",
        "mistake": "很多人追工具、平台和热点，以为换一个应用层动作就能解决问题。",
        "reframe": "先问行业本质、结构位置和什么不会变，再决定具体工具和动作。",
        "reasoning": "因为应用层变化最快，底层抽象和价值观才决定能力能不能迁移。",
        "proof_prefix": "不确定性、黄金、视频和存储",
        "proof_takeaway": "这些例子不是投资建议，而是在示范如何从不变变量推导需求。",
        "scene_prefix": "行业本质",
        "scene_takeaway": "交易、电商、VC、自媒体都要先问结构位置，再谈上层玩法。",
        "method": "写下三层：这个行业的本质是什么、过去假设哪里可能失效、什么变量不依赖单一赢家。",
        "close": "别让工具热闹替代底层判断；先找不变，再追变化。",
        "payoff": "读完后你能用第一性原理重看一个行业或机会。",
        "search_intent": "第一性原理、AI时代、底层框架",
        "target_reader": "被工具和热点带着跑，想建立长期判断框架的人",
    },
    "成长的本质，是提高可反馈的自我迭代速度": {
        "focus": "成长不是一次顿悟，而是有反馈的高频自我迭代",
        "mistake": "很多人把成长理解成意志力、决心或一次大改变。",
        "reframe": "真正可持续的成长，是简单规则、记录、复盘和奖励机制一起工作。",
        "reasoning": "因为复杂能力来自长期迭代；没有反馈，重复再多也只是重复错误。",
        "proof_prefix": "康威生命游戏",
        "proof_takeaway": "简单规则给足空间、时间和迭代，会产生复杂形态；个人成长也是类似系统。",
        "scene_prefix": "交易复盘和奖励机制",
        "scene_takeaway": "记录决策、复盘反馈、设计奖励，能让反人性的正确动作更容易持续。",
        "method": "每天记录一个判断、一个结果、一个修正；同时给难动作配明确反馈。",
        "close": "别硬扛人性，要设计一个让正确行为更容易发生的系统。",
        "payoff": "读完后你能把成长拆成记录、反馈、复盘和奖励机制。",
        "search_intent": "个人成长、复盘、自律方法",
        "target_reader": "想成长但总停留在口号和短期热情里的人",
    },
    "未来大多数事不赚钱，个人要媒体化并占住判断力": {
        "focus": "AI和互联网会让资源更集中，个人必须用媒体化承接判断力",
        "mistake": "很多人以为门槛降低后，每个人机会都会变多。",
        "reframe": "门槛降低会让竞争更激烈，真正赚钱的是能判断、能表达、能承接注意力的人。",
        "reasoning": "因为工具平权之后，简单路径消失，资源更容易流向高手和有分发能力的人。",
        "proof_prefix": "过去二十年的路径",
        "proof_takeaway": "外贸、电商、互联网曾经让很多普通方向赚钱，但这类红利不能机械外推到未来。",
        "scene_prefix": "AI、媒体和交易",
        "scene_takeaway": "未来个人要用 AI 处理边缘任务，把过程媒体化，同时重新理解自己凭什么成为少数赚钱的人。",
        "method": "检查一个方向：它是否只是过去红利的延长线；我是否有判断、表达和承接流量的能力。",
        "close": "不是所有事都不能做，而是先别把普通方向误判成机会。",
        "payoff": "读完后你能判断一个方向是不是大概率不赚钱。",
        "search_intent": "AI赚钱、个人品牌、自媒体",
        "target_reader": "想在 AI 时代找机会，但不想盲目追风口的人",
    },
    "交易和创业前先回答“我到底在赌什么”": {
        "focus": "交易和创业的第一步，不是判断方向，而是先定义自己输在哪里",
        "mistake": "这里的坑是把“看对方向”当成核心能力，忽略了下场之后人会被仓位、面子和沉没成本改写判断。",
        "reframe": "把问题从“我会不会赢”改成“我错的时候怎么退”。能说清退出条件，才说明你不是在情绪里下注。",
        "reasoning": "因为有仓位以后，人会自然筛选支持自己的信息；所以真正理性的判断，必须发生在下单、创业、投入资源之前。",
        "proof_prefix": "市场波动这个例子",
        "proof_takeaway": "外部变量一变，原来的计划就会被重写；提前定义止损，是为了防止自己在压力里临时改剧本。",
        "scene_prefix": "仓位这个场景",
        "scene_takeaway": "你不是突然变聪明或变笨，而是屁股决定脑袋，信息系统开始为已有选择服务。",
        "method": "做任何重投入前，写三行：赌注是什么、什么证明我错、错了怎么退出。写不出来，就先别加仓、别all in、别用故事说服自己。",
        "close": "真正要检查的不是胆子够不够大，而是你有没有提前给错误留出口。",
        "payoff": "读完后你能把一笔交易或一次创业投入，拆成赌注、止损和退出条件。",
        "search_intent": "交易复盘、创业决策、风险管理",
        "target_reader": "准备交易、创业或投入资源，但还没有明确退出条件的人",
    },
    "AI沟通的关键不是问对一句话，而是think out loud": {
        "focus": "和AI沟通的关键，不是憋出一句完美prompt，而是把脑子里的半成品先倒出来",
        "mistake": "很多人卡在“我不会问问题”，于是把AI当成考试老师；但AI更像一个可以追问、整理、收敛需求的协作者。",
        "reframe": "不要先追求精准表达，先做brain dump。把不完整、互相矛盾、还没想清楚的东西交给AI，让它反问你。",
        "reasoning": "因为需求本来就不是一开始清楚的；所以第一步不是建立 single source of truth，而是先让 AI 看到足够多的原始想法，帮你把问题问清楚。",
        "proof_prefix": "brain dump的用法",
        "proof_takeaway": "brain dump 的价值是给 AI 足够材料来追问和整理；source of truth 是后续归档，不是第一句话就能完成的东西。",
        "scene_prefix": "需求收敛这个过程",
        "scene_takeaway": "当 AI 把散乱表达整理成几个可能方向，人要做的是确认哪一个才是真需求，然后再归档。",
        "method": "打开AI后先写“我现在脑子里有这些东西”，不要修饰。接着让它问你10个澄清问题，最后把确认后的需求另存成 source of truth。",
        "close": "会用AI不是会写咒语，而是会把自己的混乱变成可讨论、可确认、可执行的结构。",
        "payoff": "读完后你能用brain dump把模糊想法变成一份可执行需求。",
        "search_intent": "AI沟通、prompt方法、需求整理",
        "target_reader": "想用AI做事但总觉得自己不会提问的人",
    },
    "应用层会变化，底层抽象和思维框架才是人的能量来源": {
        "focus": "工具会换，平台会换，真正能迁移的是你的底层抽象能力",
        "mistake": "很多人把最新工具清单当成能力本身，今天追一个AI插件，明天追一个工作流，最后只积累了一堆过期操作。",
        "reframe": "把应用层当练习场，把底层框架当资产。每学一个工具，都要问它背后的输入、处理、输出和反馈是什么。",
        "reasoning": "因为应用层变化最快，底层抽象变化最慢；所以能不能迁移能力，取决于你有没有把经验沉淀到框架里。",
        "proof_prefix": "工具热闹这个现象",
        "proof_takeaway": "网上不断出现AI教程、客服玩法、股票工具，但这些都只是表层入口，不是长期能力。",
        "scene_prefix": "个人气场这个说法",
        "scene_takeaway": "一个人真正稳定的能量，来自他遇到问题时调用的底层模型，而不是他今天会哪个按钮。",
        "method": "每次学新工具都写四项：它解决什么问题、依赖什么输入、输出如何验收、失败时暴露哪个假设。",
        "close": "别把应用层热闹误认为成长；能留下来的，是你把经验抽象成框架的能力。",
        "payoff": "读完后你能把一个AI工具用法，转成可迁移的底层框架。",
        "search_intent": "AI工具学习、底层框架、个人能力迁移",
        "target_reader": "每天追AI工具但担心自己只是在跟热点跑的人",
    },
    "重塑底层价值观，是AI时代最稀缺的能力之一": {
        "focus": "AI时代最难的不是学工具，而是敢不敢重审自己过去相信的真理",
        "mistake": "很多人把过去几十年有效的社会经验，当成未来一定成立的规则；问题是周期变了，假设也可能失效。",
        "reframe": "不要急着找新技巧，先盘点旧假设：哪些来自家庭，哪些来自时代红利，哪些只是别人当年成功后的总结。",
        "reasoning": "因为价值观决定你如何分配时间、关系和风险；所以底层假设不更新，上层动作越努力，越可能走向旧地图。",
        "proof_prefix": "婚姻和家庭观念",
        "proof_takeaway": "这些看似天然正确的规则，很多其实是具体历史和资源结构下形成的，不一定能外推。",
        "scene_prefix": "欧美繁荣周期",
        "scene_takeaway": "过去80年的秩序不能自动代表未来；把周期经验当永恒真理，会让判断滞后。",
        "method": "列出你最相信的5条人生规则，逐条问：它来自哪里、依赖什么环境、AI冲击后还成立吗。",
        "close": "重塑价值观不是叛逆，而是承认世界变了以后，旧答案需要重新验算。",
        "payoff": "读完后你能开始审计自己的底层价值观，而不是只更新工具箱。",
        "search_intent": "AI时代价值观、人生假设、认知更新",
        "target_reader": "感觉旧经验不再稳定，但还不知道该从哪里重建判断的人",
    },
    "在快速变化中找不变：不确定性、黄金、视频和存储": {
        "focus": "变化越快，越不要押单点赢家，而要找更底层的不变量",
        "mistake": "很多人一上来就问哪家公司会赢、哪个芯片最强，却忽略了更稳定的需求变量。",
        "reframe": "与其赌某个具体赢家，不如先找那些不依赖单一公司的趋势：不确定性、视频化、存储需求、避险资产。",
        "reasoning": "因为单点判断需要大量细节和运气；底层需求一旦成立，即使路径变化，方向也更不容易被推翻。",
        "proof_prefix": "战争和市场下跌",
        "proof_takeaway": "不确定性会快速改变资产价格，这比猜某天涨跌更像一个可持续变量。",
        "scene_prefix": "视频和存储",
        "scene_takeaway": "更多人表达生活、视频质量提高、内容体量变大，会把存储需求推到更底层的位置。",
        "method": "看一个机会时，先问它依赖一个赢家，还是依赖一个长期变量。如果只靠单点赢家，就降低确定性评分。",
        "close": "这不是投资建议，而是一种找变量的方法：少赌故事，多找不变。",
        "payoff": "读完后你能把热点机会拆成单点赢家和底层变量两类。",
        "search_intent": "不确定性投资、黄金逻辑、视频存储需求",
        "target_reader": "想理解AI时代资产和机会，但不想只追热点的人",
    },
    "康威生命游戏：简单规则、足够迭代，会产生复杂生命": {
        "focus": "复杂东西不一定来自复杂规则，也可能来自简单规则的长期迭代",
        "mistake": "很多人听到AI预测下一个词，就直接判定它没有智能；这忽略了规模、空间和迭代带来的涌现。",
        "reframe": "把AI、市场和生命都先看成系统：规则可以很简单，但参与者足够多、反馈足够快，结果就会复杂到超出直觉。",
        "reasoning": "因为复杂性不是每一步都被设计出来的；它经常来自简单单元在大量互动中的累积。",
        "proof_prefix": "康威生命游戏",
        "proof_takeaway": "简单规则给足时间和空间，会演化出像生命一样的形态，这正是涌现的直观例子。",
        "scene_prefix": "金融市场",
        "scene_takeaway": "几十亿人按简单利益规则互动，也会产生没有任何单个人能完全设计的复杂市场。",
        "method": "遇到复杂系统时，不要只问规则复杂不复杂；还要问规模多大、迭代多快、反馈是否会累积。",
        "close": "这个类比不能证明AI有意识，但能提醒我们：不要低估简单机制在大规模迭代后的变化。",
        "payoff": "读完后你能用涌现视角理解AI、市场和生命游戏。",
        "search_intent": "康威生命游戏、AI涌现、复杂系统",
        "target_reader": "对AI是否只是概率模型、复杂系统如何出现感兴趣的人",
    },
    "真正的成长是提高自我迭代速度": {
        "focus": "成长不是一次想通，而是让自己更快进入记录、反馈和修正",
        "mistake": "很多人把成长想成一次大顿悟，但真正拉开差距的是复盘频率和反馈质量。",
        "reframe": "不要只问自己有没有努力，要问自己多久更新一次判断。一天一复盘和一年一复盘，几乎是两个物种。",
        "reasoning": "因为错误不可避免，关键是错误停留多久；迭代速度越快，错误沉淀成规则的速度越快。",
        "proof_prefix": "交易复盘",
        "proof_takeaway": "稳定赚钱的人不是永远判断对，而是每天、每周回看逻辑，拆清方向、仓位和随机激励。",
        "scene_prefix": "康威生命游戏的iteration",
        "scene_takeaway": "每秒迭代越多，演化越快；人也是这样，反馈周期越短，变化越明显。",
        "method": "每天只记三件事：今天判断了什么、结果哪里偏了、下次规则怎么改。不要写情绪日记，要写可更新的规则。",
        "close": "真正的自我提升，不是更用力地重复，而是更快地发现自己哪里错。",
        "payoff": "读完后你能把成长拆成记录、反馈、修正规则三个动作。",
        "search_intent": "自我迭代、复盘方法、成长系统",
        "target_reader": "想成长但总觉得努力没有复利的人",
    },
    "未来职业三件事：用AI、做媒体、重新理解交易": {
        "focus": "未来职业不是只找一个岗位，而是把AI、媒体化和交易判断组合起来",
        "mistake": "很多人还在等一个稳定职业或现成产品，但过程、判断和公开表达本身已经能成为资产。",
        "reframe": "把职业理解成三个模块：AI处理边缘任务，媒体承接注意力，交易训练你理解风险和少数人位置。",
        "reasoning": "因为个人能调用的杠杆变多了；不会表达、不会借AI、不会理解风险的人，会越来越依赖别人给机会。",
        "proof_prefix": "AI处理边缘任务",
        "proof_takeaway": "邮件、客户回复、数据整理这些不再需要占据核心精力，个人可以把注意力转向判断和表达。",
        "scene_prefix": "注意力案例",
        "scene_takeaway": "无论是口号还是香蕉，背后都是注意力资产化；职业也会越来越像个人媒体系统。",
        "method": "给自己做一张职业表：哪些任务交给AI，哪些过程可以公开表达，哪些判断需要用交易式复盘训练。",
        "close": "未来的职业安全感，不只来自职位，而来自你能不能持续制造判断、内容和注意力。",
        "payoff": "读完后你能把个人职业拆成AI、媒体和风险判断三条线。",
        "search_intent": "AI职业规划、个人媒体、交易思维",
        "target_reader": "想重新设计职业路径，但不想只换一个岗位的人",
    },
    "100件事99件不赚钱：AI和互联网会让资源更集中": {
        "focus": "AI降低门槛以后，普通方向反而更容易不赚钱",
        "mistake": "很多人以为工具平权等于机会平权，但当所有人都能做，简单机会会更快被打成红海。",
        "reframe": "先别问自己能不能做，先问这个方向为什么不是99个不赚钱之一。没有壁垒、没有分发、没有复利，就只是拥挤赛道。",
        "reasoning": "因为AI让执行成本下降，也让竞争者数量上升；真正稀缺的不是会做，而是能占住注意力、资源和判断位置。",
        "proof_prefix": "背单词app和todo list",
        "proof_takeaway": "这类方向一开始就容易错，不是不能做产品，而是默认没有足够强的分发和差异。",
        "scene_prefix": "过去20年的外贸和互联网",
        "scene_takeaway": "过去很多方向都能赚钱，是时代红利；把红利期经验外推到今天，会误判难度。",
        "method": "判断一个新方向，先打三分：分发从哪来、壁垒是什么、为什么现在做还不晚。三项答不出，就默认它属于99个。",
        "close": "这句话不是劝退，而是让你先排除大概率错误，别把AI时代想得太容易。",
        "payoff": "读完后你能用分发、壁垒、时机三项筛掉低胜率方向。",
        "search_intent": "AI时代赚钱、创业方向、商业判断",
        "target_reader": "想用AI创业或做产品，但还没有判断方向胜率的人",
    },
    "AI不是附属工具，而是各取所长的合作伙伴": {
        "focus": "AI不是听话工具，而是需要分工、验收和护栏的合作伙伴",
        "mistake": "很多人只会给AI下命令，然后抱怨结果不稳定；这相当于把协作关系降级成一次性外包。",
        "reframe": "人负责方向、边界、成功标准；AI负责快速执行、补知识、反复试错。分工清楚，协作才会稳定。",
        "reasoning": "因为AI强在速度和广度，人强在上下文、取舍和验收；把判断外包给AI，会把优势组合变成风险叠加。",
        "proof_prefix": "写代码的例子",
        "proof_takeaway": "不先钻语法，而是让AI执行、自己定义边界和验收标准，这体现的是角色分工。",
        "scene_prefix": "token重新跑",
        "scene_takeaway": "AI错了可以低成本重试，但低成本不等于无边界；没有验收标准，重试也会漂移。",
        "method": "给AI任务前写三项：目标是什么、不能做什么、怎样算通过。让AI执行，不代表让AI决定。",
        "close": "好的AI协作不是更会命令，而是更会分工。",
        "payoff": "读完后你能给AI任务加上目标、边界和验收标准。",
        "search_intent": "AI协作、AI Agent、工作流",
        "target_reader": "已经开始用AI做事，但输出不稳定的人",
    },
    "Prompt是给AI指针，护栏是承认AI的概率特性": {
        "focus": "Prompt不是神秘咒语，而是把AI指向正确知识区域的指针",
        "mistake": "很多人把prompt当技巧合集，或者幻想模型变强后就不需要护栏；这低估了概率模型的漂移。",
        "reframe": "把prompt理解成导航，把guardrails理解成轨道。一个负责找对区域，一个负责限制偏航。",
        "reasoning": "因为AI不是固定数据库查询，而是在概率空间里生成答案；没有指针和护栏，输出就容易看似合理但逐层漂移。",
        "proof_prefix": "你是designer这个提示",
        "proof_takeaway": "角色提示不是玄学，它是在巨大知识库里缩小调用区域。",
        "scene_prefix": "多层AI输出",
        "scene_takeaway": "一层漂移还能检查，多层叠加会把小偏差放大成系统性错误。",
        "method": "写prompt时先写角色、任务、输入、禁止项和验收标准。护栏不是补丁，而是生产级AI流程的一部分。",
        "close": "不要迷信神prompt；真正可靠的是指针清楚、边界清楚、验收清楚。",
        "payoff": "读完后你能把prompt和guardrails拆成可执行结构。",
        "search_intent": "prompt方法、AI护栏、AI工作流",
        "target_reader": "想让AI输出更稳定，而不是只收藏prompt模板的人",
    },
    "第一性原理：每个行业都要问本质是什么": {
        "focus": "越是上层玩法变多，越要回到行业本质和自己所处的位置",
        "mistake": "很多人先看投流、做号、买什么，却不问这个行业到底如何分配利润和风险。",
        "reframe": "先问本质，再看玩法。交易、电商、VC、自媒体都一样：你在结构哪一层，资源从哪里来，谁承担最后风险。",
        "reasoning": "因为上层动作会变，结构位置更稳定；不知道自己在金字塔哪一层，就很容易替别人承担风险。",
        "proof_prefix": "交易金字塔",
        "proof_takeaway": "交易不是只看涨跌，而是要知道自己上面是谁、下面是谁，谁可能成为最后接盘者。",
        "scene_prefix": "自媒体投流",
        "scene_takeaway": "流量是平台资源，不是自己的资源；不理解资源归属，就会把租来的东西当资产。",
        "method": "分析行业时写四问：本质交易是什么，资源归谁，风险给谁，自己在哪一层。",
        "close": "第一性原理不是抽象口号，而是让你别被上层玩法牵着走。",
        "payoff": "读完后你能用四个问题审视一个行业或项目。",
        "search_intent": "第一性原理、行业本质、商业分析",
        "target_reader": "想做行业判断，但容易被具体玩法带偏的人",
    },
    "所有个体都在用最小能耗预测未来": {
        "focus": "人际关系、AI协作和组织合作，本质上都在交换对未来的预测能力",
        "mistake": "很多人只把关系理解成资源交换，却忽略了每个人都在降低不确定性和能耗。",
        "reframe": "把人、AI agent、朋友和团队都看成预测系统。谁能提高对未来的判断效率，谁就提供了真实价值。",
        "reasoning": "因为行动之前都需要预测；预测越准、能耗越低，个体越愿意继续协作。",
        "proof_prefix": "人与AI的互相价值",
        "proof_takeaway": "作者会问自己能给AI什么、AI能给自己什么，这不是玄学，而是在设计协作价值。",
        "scene_prefix": "朋友圈里的个体观察",
        "scene_takeaway": "所有个体都在用更少能量预测未来，这个说法可以转成更清晰的协作逻辑。",
        "method": "看一段关系时问：我让对方更确定什么，对方让我的判断更省力什么。",
        "close": "所谓同频，不只是感觉像，而是双方都在提高彼此预测未来的效率。",
        "payoff": "读完后你能用预测效率重新理解AI协作和人际关系。",
        "search_intent": "AI Agent、人际关系、预测未来",
        "target_reader": "想理解人与AI、人与人协作底层逻辑的人",
    },
    "顺从别人的人性，管理自己的赏罚机制": {
        "focus": "真正的自律不是硬扛人性，而是重新设计自己的奖励机制",
        "mistake": "很多人把克制理解成咬牙坚持，所以一旦压力变大，就只能靠意志力硬撑。",
        "reframe": "对别人要理解人性，对自己要设计反馈。把正确行为变得没那么反人性，才更可能长期持续。",
        "reasoning": "因为大脑会追逐即时奖励；如果正确行为长期只有痛苦，没有反馈，它迟早会被更轻松的选择打败。",
        "proof_prefix": "录完视频就出去玩",
        "proof_takeaway": "这不是偷懒，而是给大脑一个可预期奖励，让反人性的动作更容易启动。",
        "scene_prefix": "顺从别人性",
        "scene_takeaway": "做内容、做产品、做协作，都不能假设别人会主动克制本能，要顺着激励设计路径。",
        "method": "给一个难动作配一个明确奖励：完成什么、奖励什么、什么时候兑现。不要只写目标，要写反馈。",
        "close": "别把自律想成永远痛苦；能长期坚持的系统，通常更懂人性。",
        "payoff": "读完后你能给一个反人性的正确动作设计奖励机制。",
        "search_intent": "自律方法、人性、奖励机制",
        "target_reader": "想长期坚持正确行为，但总靠硬扛失败的人",
    },
}


def profile_for(topic: dict[str, Any]) -> dict[str, str]:
    title = str(topic.get("title") or "")
    return TOPIC_PROFILES.get(title) or {
        "focus": str(topic.get("claim") or title),
        "mistake": str(topic.get("cognitive_contrast") or "常见错误是把表面动作当成核心问题。"),
        "reframe": "先把问题拆到变量、边界和反馈，再决定具体动作。",
        "reasoning": "因为动作会变，判断结构更稳定；结构不清楚，动作越多越容易偏。",
        "proof_prefix": "原视频支撑",
        "proof_takeaway": "这个例子用来说明主题不是空观点，而是来自具体场景。",
        "scene_prefix": "具体场景",
        "scene_takeaway": "把场景拆开后，才知道应该保留哪个判断。",
        "method": "写下主题、错误理解、边界和下一步动作，再决定是否继续投入。",
        "close": "先把判断讲清楚，再追求执行速度。",
        "payoff": "读完后你能把这个主题拆成一个可复盘的判断。",
        "search_intent": "认知框架、个人成长、AI时代",
        "target_reader": "想把复杂问题想清楚的人",
    }


def image_cards(topic: dict[str, Any], note_title: str, keywords: list[str], argument_pack: dict[str, Any] | None = None) -> list[str]:
    argument_pack = argument_pack or xhs_argument_pack(topic, note_title, keywords)
    claim = str(argument_pack.get("one_sentence_claim") or topic.get("claim") or "")
    contrast = str(argument_pack.get("misunderstanding_to_break") or topic.get("cognitive_contrast") or "")
    reader_mirror = str(argument_pack.get("reader_entry") or topic.get("reader_mirror") or "")
    why = str(argument_pack.get("why_it_holds") or topic.get("why_it_matters") or "")
    boundary = str(argument_pack.get("boundary") or topic.get("boundary") or "")
    takeaway = str(argument_pack.get("reader_action") or topic.get("takeaway") or "")
    points = [item for item in (argument_pack.get("moves") or []) if isinstance(item, dict)]
    examples = [str(item) for item in (topic.get("supporting_examples") or []) if str(item).strip()]
    profile = profile_for(topic)
    analogy = argument_pack.get("analogy") or analogy_for(topic, profile)
    fallback_points = [
        {
            "title": profile["proof_prefix"],
            "reader_entry": profile["target_reader"],
            "judgment": profile["proof_takeaway"],
            "explanation": profile["reasoning"],
            "scene": examples[0] if examples else profile["scene_takeaway"],
        },
        {
            "title": profile["scene_prefix"],
            "reader_entry": "如果你只看表面动作，很容易以为自己缺的是技巧。",
            "judgment": profile["scene_takeaway"],
            "explanation": profile["reframe"],
            "scene": examples[1] if len(examples) > 1 else profile["method"],
        },
        {
            "title": "换成行动问题",
            "reader_entry": "真正要改变的不是一句口号，而是下一次具体怎么检查。",
            "judgment": profile["method"],
            "explanation": profile["payoff"],
            "scene": examples[2] if len(examples) > 2 else profile["close"],
        },
    ]
    merged_points = [*points, *fallback_points]
    while len(merged_points) < 3:
        merged_points.append(fallback_points[len(merged_points) % len(fallback_points)])

    evidence_1 = examples[0] if examples else profile["proof_takeaway"]
    evidence_2 = examples[1] if len(examples) > 1 else profile["scene_takeaway"]
    evidence_3 = examples[2] if len(examples) > 2 else profile["method"]

    p1, p2, p3 = merged_points[:3]
    cards = [
        card(
            "cover",
            note_title,
            dense_body(
                claim,
                "先不要把它当成一句好听的结论；把它放回你最近一次真实选择里，看它能不能帮你少犯一个具体错误",
            ),
        ),
        card(
            "reader",
            "如果你也这样想",
            dense_body(
                reader_mirror or profile["target_reader"],
                contrast or profile["mistake"],
                "这种想法很自然，因为人在信息很多、机会很多的时候，最容易把“看见更多”误以为“判断更准”",
            ),
        ),
        card(
            "reframe",
            "我会反过来看",
            dense_body(
                profile["reframe"],
                "真正要先处理的不是动作本身，而是动作之前的变量、边界和验收标准",
                "顺序一旦错了，后面越努力，越可能只是把错误包装得更合理",
            ),
        ),
        card(
            "reasoning",
            "为什么这个判断成立",
            dense_body(
                why or profile["reasoning"],
                "很多问题不是输在信息少，而是输在一开始没有把任务、变量和验收方式拆开；问题没拆清楚，后面的答案越流畅越容易误导你",
            ),
        ),
        card(
            "analogy",
            analogy["image"],
            dense_body(
                analogy["setup"],
                analogy["turn"],
                analogy["lesson"],
                "这个类比的作用，是让你下次遇到类似情况时，能先停下来检查路线，而不是只想着继续加速",
            ),
        ),
        card(
            "method",
            p1.get("title") or "第一个检查点",
            dense_body(
                p1.get("reader_entry") or profile["target_reader"],
                p1.get("judgment") or profile["proof_takeaway"],
                p1.get("explanation") or profile["reasoning"],
                p1.get("scene") or evidence_1,
            ),
        ),
        card(
            "method",
            p2.get("title") or "第二个检查点",
            dense_body(
                p2.get("reader_entry") or "如果你发现自己已经开始替选择找理由，就要停一下",
                p2.get("judgment") or profile["scene_takeaway"],
                p2.get("explanation") or profile["reframe"],
                p2.get("scene") or evidence_2,
            ),
        ),
        card(
            "proof",
            p3.get("title") or "第三个检查点",
            dense_body(
                p3.get("reader_entry") or "不要只问这件事听起来对不对",
                p3.get("judgment") or profile["method"],
                p3.get("explanation") or profile["payoff"],
                p3.get("scene") or evidence_3,
            ),
        ),
        card(
            "boundary",
            "这不是让你别行动",
            dense_body(
                boundary or "这个观点不是让你永远保守，也不是让你用规则替代判断",
                "它真正反对的是没有边界地投入，然后等压力出现以后再临时解释",
                "边界不是为了限制想象力，而是为了防止人在成本变高以后自我欺骗",
            ),
        ),
        card(
            "close",
            "下次就问这一句",
            dense_body(
                takeaway or profile["method"],
                profile["method"],
                "如果这几个问题答不出来，就先不要急着加码；先把判断写清楚，再决定要不要继续",
            ),
        ),
    ]
    return cards


def card_plan(cards: list[str]) -> list[dict[str, str]]:
    roles = [
        "cover",
        "misunderstanding",
        "reframe",
        "reasoning",
        "example",
        "method",
        "method",
        "proof",
        "boundary",
        "close",
    ]
    labels = {
        "cover": "封面",
        "misunderstanding": "误区",
        "reframe": "体感",
        "reasoning": "论证",
        "method": "方法",
        "proof": "论证",
        "example": "例子",
        "boundary": "边界",
        "close": "收束",
    }
    return [
        {"index": idx, "role": role, "label": labels[role], "purpose": cards[idx - 1].split("\n", 1)[0]}
        for idx, role in enumerate(roles[: len(cards)], start=1)
    ]


def body_text(topic: dict[str, Any], note_title: str, keywords: list[str], argument_pack: dict[str, Any] | None = None) -> str:
    argument_pack = argument_pack or xhs_argument_pack(topic, note_title, keywords)
    claim = str(argument_pack.get("one_sentence_claim") or topic.get("claim") or "")
    contrast = str(argument_pack.get("misunderstanding_to_break") or topic.get("cognitive_contrast") or "")
    reader_mirror = str(argument_pack.get("reader_entry") or topic.get("reader_mirror") or "")
    why = str(argument_pack.get("why_it_holds") or topic.get("why_it_matters") or "")
    boundary = str(argument_pack.get("boundary") or topic.get("boundary") or "")
    takeaway = str(argument_pack.get("reader_action") or topic.get("takeaway") or "")
    points = [item for item in (argument_pack.get("moves") or []) if isinstance(item, dict)]
    examples = [str(item) for item in (argument_pack.get("supporting_scenes") or topic.get("supporting_examples") or []) if str(item).strip()]
    profile = profile_for(topic)
    analogy = argument_pack.get("analogy") or analogy_for(topic, profile)
    intro = [
        f"如果你也有过这种感觉：{reader_mirror or profile['target_reader']}，那这个问题可能不是信息量不够。",
        f"大多数人的第一反应是：{contrast or profile['mistake']}",
        f"但我会反过来看：{claim}",
        profile["reframe"],
        f"我更想让你有一个具体画面：{analogy.get('setup')} {analogy.get('turn')} {analogy.get('lesson')}",
        "这个画面重要，是因为抽象道理很容易被记住，但很难在压力里被调用。只有当它变成一个你能感受到的场景，你下次才可能真的停一下，重新问问题。",
    ]
    logic = [
        why or profile["reasoning"],
        f"所以我不会先给你一句漂亮结论，而是给你一套可以落地的检查顺序：{profile['method']}",
        "你要做的不是给自己增加更多信息，而是先把信息放到正确的位置。很多时候，信息越多，人越容易用它来保护已有选择；但如果一开始的问题错了，后面所有信息都会被带偏。",
        "差别就在这个顺序里：普通判断是看到机会以后马上问“能不能成”；更稳定的判断会先问“我现在到底在检查什么变量”。这两个顺序看起来只差一步，结果完全不同。",
    ]
    point_paragraphs = [
        "\n".join(
            part
            for part in [
                f"{idx}. {point.get('title') or f'第 {idx} 步'}",
                str(point.get("reader_entry") or point.get("reader_mirror") or ""),
                str(point.get("judgment") or ""),
                str(point.get("explanation") or ""),
                str(point.get("scene") or point.get("evidence") or ""),
                "这一点的关键，是不要只看它听起来对不对，而要看它能不能让你下一次少犯一个具体错误。",
            ]
            if part.strip()
        )
        for idx, point in enumerate(points[:3], start=1)
    ]
    support_paragraphs = [
        "\n".join(
            part
            for part in [
                f"再把第 {idx} 个支撑点说得更具体一点。",
                f"如果你在现实里遇到的情况是：{point.get('reader_entry') or point.get('reader_mirror') or profile['target_reader']}，你要先停下来，不要急着继续堆信息。",
                f"这个支撑点真正想提醒你的是：{point.get('judgment') or point.get('title') or claim}",
                f"它背后的原因是：{point.get('explanation') or why or profile['reasoning']}",
                f"放回原视频的场景，就是：{point.get('scene') or point.get('evidence') or (examples[idx - 1] if idx - 1 < len(examples) else profile['proof_takeaway'])}",
            ]
            if str(part).strip()
        )
        for idx, point in enumerate(points[:3], start=1)
    ]
    example_paragraphs = [
        f"原视频里有一个支撑场景：{item} 这个例子不是为了证明某个具体结论永远正确，而是提醒你，真实世界里的变量会突然改变。你如果没有提前写下判断边界，变化一来，很容易把新的信息解释成对自己有利的样子。"
        for item in examples[:4]
    ]
    ending = [
        *[
            f"还有一个容易误用的地方：{boundary}" if boundary else "",
            "边界非常重要。没有边界的观点很容易变成口号。比如你不能把它理解成永远不要冒险，也不能理解成所有事情都必须机械执行。它真正要求的是：在你投入资源、情绪、时间和面子之前，先把判断条件写清楚。",
        ],
        f"这篇的重点不是让你记住标题，而是让你下次遇到类似机会时，能马上换一种看法。{profile['payoff']}",
        f"你可以把它当成一次自查：{profile['method']}",
        takeaway,
        f"如果你现在就要用，可以拿最近一个正在考虑的选择来测试：先写机会，再写代价，再写失败信号。只要失败信号写不出来，就说明这个选择还没有被你真正想清楚。",
        "它不是一句结论，而是一套判断顺序：先看变量，再看边界，最后才决定动作。你下次真正要练的，不是更快地冲进去，而是在冲进去之前先把问题问对。",
        profile["close"],
        " ".join(f"#{kw}" for kw in keywords[:5]),
    ]
    return "\n\n".join(part for part in [*intro, *logic, *point_paragraphs, *support_paragraphs, *example_paragraphs, *ending] if str(part).strip()).strip()


def short_example_hint(text: str) -> str:
    text = re.sub(r"\s+", "", text or "")
    text = re.sub(r"[。！？!?；;].*$", "", text)
    if len(text) <= 34:
        return text or "一个具体例子"
    return text[:32] + "..."


def note_brief(topic: dict[str, Any], note_title: str, keywords: list[str], argument_pack: dict[str, Any] | None = None) -> dict[str, Any]:
    argument_pack = argument_pack or xhs_argument_pack(topic, note_title, keywords)
    profile = profile_for(topic)
    return {
        "search_keywords": keywords,
        "search_intent": profile["search_intent"],
        "target_reader": profile["target_reader"],
        "core_claim": str(argument_pack.get("one_sentence_claim") or topic.get("claim") or note_title),
        "cognitive_conflict": str(argument_pack.get("misunderstanding_to_break") or topic.get("cognitive_contrast") or ""),
        "reader_mirror": str(argument_pack.get("reader_entry") or topic.get("reader_mirror") or ""),
        "why_it_matters": str(argument_pack.get("why_it_holds") or topic.get("why_it_matters") or ""),
        "points": argument_pack.get("moves") or topic.get("points") or [],
        "takeaway": str(argument_pack.get("reader_action") or topic.get("takeaway") or ""),
        "source_evidence": argument_pack.get("supporting_scenes") or topic.get("supporting_examples") or [],
        "reader_payoff": profile["payoff"],
        "format_rationale": "适合做搜索型小红书图文：每篇只承接一个 approved 主题，不复用跨主题通用话术。",
        "card_chain": ["封面", "误判", "体感", "原因", "要点1", "要点2", "要点3", "边界"],
    }


def write_markdown(path: Path, record: dict[str, Any]) -> None:
    lines = [
        "---",
        "platform: xiaohongshu",
        "status: draft",
        f"local_id: {record['local_id']}",
        f"source_content_id: {record['source_content_id']}",
        "review_required: true",
        "---",
        "",
        f"# {record['title']}",
        "",
        "## 发布正文",
        "",
        record["body"],
        "",
        "## 图文卡片",
        "",
    ]
    for idx, item in enumerate(record.get("image_cards") or [], start=1):
        lines.extend([f"### {idx}", "", item, ""])
    lines.extend(["## 来源片段", "", record.get("source_excerpt") or "", ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def supersede_existing(source_content_id: str, keep_paths: set[Path] | None = None) -> int:
    keep_paths = {path.resolve() for path in (keep_paths or set())}
    count = 0
    for path in DRAFT_DIR.glob("*.json"):
        if path.resolve() in keep_paths:
            continue
        try:
            record = read_json(path)
        except Exception:
            continue
        if record.get("platform") != "xiaohongshu":
            continue
        if str(record.get("source_content_id") or "") != source_content_id:
            continue
        if record.get("status") in {"superseded", "archived"}:
            continue
        record["status"] = "superseded"
        record["superseded_reason"] = "replaced_by_content_package_topics_v1"
        record["superseded_at"] = now_iso()
        write_json(path, record)
        count += 1
    return count


def generate(
    source_content_id: str,
    overwrite: bool = False,
    supersede: bool = True,
    engine: str = "auto",
    timeout: int = 600,
    limit: int = 0,
) -> dict[str, Any]:
    source_dir = source_dir_for(source_content_id)
    package_path, package = content_package_for(source_content_id)
    topics = package.get("fine_topics") or package.get("topics") or package.get("topic_groups") or []
    DRAFT_DIR.mkdir(parents=True, exist_ok=True)
    generated = []
    generated_paths: set[Path] = set()
    selected_topics = topics[:limit] if limit > 0 else topics
    for idx, topic in enumerate(selected_topics, start=1):
        title = compact_title(str(topic.get("title") or ""), idx)
        keywords = [title, *[item for item in keywords_for(topic, title) if item != title]][:5]
        local_id = f"xiaohongshu-{source_content_id[-6:]}-topic-{idx:02d}"
        basename = f"2026-05-26--{slugify(title, f'topic-{idx:02d}')}--{local_id}"
        json_path = DRAFT_DIR / f"{basename}.json"
        md_path = DRAFT_DIR / f"{basename}.md"
        if json_path.exists() and not overwrite:
            generated.append({"path": str(json_path), "status": "exists"})
            continue
        source_excerpt = topic_source_excerpt(topic, package, idx)
        print(f"[xhs] generating {idx}/{len(selected_topics)}: {title} via {engine}", file=sys.stderr, flush=True)
        ai_result = ai_xhs_draft(topic, title, keywords, source_excerpt, engine, timeout)
        title = str(ai_result.get("title") or title).strip() or title
        keywords = [title, *[item for item in keywords if item != title]][:5]
        argument_pack = ai_result["xhs_argument_pack"]
        cards = [str(card).strip() for card in (ai_result.get("image_cards") or []) if str(card).strip()]
        body = str(ai_result.get("body") or "").strip()
        brief = ai_result["note_brief"]
        generation_engine = str(ai_result.get("xhs_generation_engine") or engine)
        generation_warnings = ai_result.get("xhs_generation_warnings") or []
        record = {
            "platform": "xiaohongshu",
            "status": "draft",
            "intended_publish_at": "2026-05-26",
            "local_id": local_id,
            "source_platform": "douyin",
            "source_content_id": source_content_id,
            "source_url": f"https://www.douyin.com/video/{source_content_id}",
            "source_asset_id": source_dir.name,
            "source_content_type": "video",
            "source_content_package_json": str(package_path),
            "source_content_package_approved_at": package.get("approved_at") or "",
            "source_unit_title": topic.get("title") or title,
            "source_excerpt": source_excerpt,
            "topic_priority": topic.get("priority") or "",
            "topic_index": idx,
            "xhs_generation_source": "content-package-atomic-topics-v2",
            "xhs_generation_engine": generation_engine,
            "xhs_generation_warnings": generation_warnings,
            "xhs_workflow_version": "search-card-v4-atomic-topic",
            "title": title,
            "body": body,
            "xhs_argument_pack": argument_pack,
            "note_brief": brief,
            "xhs_format": {
                "format": "search_knowledge_cards",
                "visual_mode": "manual_method_cards",
                "source_policy": "approved atomic content-package topic is source; do not merge unrelated topics for Xiaohongshu",
                "best_for": "Xiaohongshu search, saves, and manual review before platform push",
            },
            "image_cards": cards,
            "card_plan": card_plan(cards),
            "generated_at": now_iso(),
            "review_required": True,
        }
        write_json(json_path, record)
        write_markdown(md_path, record)
        generated_paths.add(json_path)
        print(f"[xhs] generated {idx}/{len(selected_topics)}: {json_path.name}", file=sys.stderr, flush=True)
        generated.append({
            "path": str(json_path),
            "status": "generated",
            "cards": len(cards),
            "priority": topic.get("priority"),
            "engine": generation_engine,
            "body_chars": len(body.replace("\n", "")),
            "warnings": generation_warnings,
        })
    superseded_count = supersede_existing(source_content_id, generated_paths) if supersede and limit <= 0 and generated_paths else 0
    return {
        "ok": True,
        "source_content_id": source_content_id,
        "topics": len(selected_topics),
        "total_topics": len(topics),
        "superseded": superseded_count,
        "generated": generated,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Xiaohongshu drafts from approved content-package topics.")
    parser.add_argument("--source-content-id", required=True)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--keep-existing", action="store_true")
    parser.add_argument("--engine", choices=["auto", "claude", "codex"], default="auto")
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument("--limit", type=int, default=0, help="Generate only the first N topics for validation.")
    args = parser.parse_args()
    result = generate(
        args.source_content_id,
        overwrite=args.overwrite,
        supersede=not args.keep_existing,
        engine=args.engine,
        timeout=args.timeout,
        limit=args.limit,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
