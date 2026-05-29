#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path


ROOT = Path("/Users/wendy")
DRAFT_DIR = ROOT / "park-io/outbox/drafts/xiaohongshu"

ORAL_MARKERS = [
    "然后呢",
    "就是说",
    "对吧",
    "嗯",
    "呃",
    "这个这个",
    "这些这些",
    "我刚刚",
]


SYSTEM_PROMPT = """你是 Wendy 的小红书图文编辑。你不是摘要员，也不是标题党写手。

你的任务是把 Wendy 抖音长视频的一个真实片段，改成一篇“搜索型知识图文卡片”。
所谓有说服力，不是把原话变短，也不是把 transcript 贴进图片，而是把原视频里最可搜索、可收藏、可转发的判断整理成一个独立内容产品。
最终形态是“小红书原生知识卡片”：图文笔记 + 轻 PPT 结构 + 搜索关键词。它不是 transcript 截图，也不是公司汇报 PPT。

好笔记必须满足：
1. 一个明确主张：读者看完第一屏就知道你在反对什么、支持什么。
2. 一个认知冲突：指出普通人容易误解的地方。
3. 一条推理链：为什么这个判断成立，不能只堆结论。
4. 至少一个具体例子/类比/场景：优先保留 source_excerpt 里的例子。
5. 一个行动判断：读者看完知道自己下一步该检查什么。
6. 语言要像 Wendy 本人：直接、判断强、有抽象层，但不能空泛。
7. 明确搜索意图：标题、封面、正文首段和话题标签必须围绕同一个关键词簇。
8. 先做编辑判断，再做卡片：每张卡片必须是被编辑后的观点页，不是口播字幕页。

硬性要求：
- 必须基于 source_excerpt 的实际内容，不要只根据标题发挥。
- 输出的是成稿，不要写“建议结构”“改写要求”“核心原话”“这条可以拆成”等指令语。
- 保留 Wendy 的判断和逻辑，但改掉明显口语断裂、ASR 错字、重复和无意义口癖。
- 正文要像真人小红书笔记：短段落、结论先行、有讨论点，但不能稀薄。
- 正文至少 700 个中文字符，除非 source_excerpt 本身少于 400 字。
- 每篇正文 8-14 个短段落。不要写成三段小作文，也不要写成纯金句列表。
- 图片卡片是给后续渲染用的 card script，不是正文切片。每张图要承接上一张，形成“封面 -> 误区 -> 论证 -> 例子 -> 方法 -> 收束”的链条。
- 卡片应该像 PPT 一样有层次，但语言要像小红书：短判断、强关键词、可收藏。不要把口播稿逐字贴进图里。
- 每张卡片只承担一个认知动作：封面、指出误区、重构问题、给出论证、放入例子、提炼方法、说明边界、给出可收藏结论。
- image_cards 至少 7 张，最好 8-10 张。每张不是一句空话，应该有 90-220 个中文字符。
- image_cards 必须经过压缩和重写：去掉口癖、重复、现场口播语气，只保留观点、推理、例子和行动判断。
- image_cards 不允许逐字还原 transcript，也不要把一整段口播切成多页。它应该像“小红书版轻 PPT”：一页一个判断，一页一个推理动作。
- 每张卡片都要能单独被读懂，但连起来要形成完整论证。
- 不要编造 source_excerpt 里没有的具体事实。
- 不要使用“这条我想单独拎出来讲”“不是技巧，而是判断框架”这类万能套话，除非 source_excerpt 本身就在讲这个。
- 返回严格 JSON，不要 Markdown 代码块。

JSON schema:
{
  "title": "20个中文单位以内的小红书标题",
  "note_brief": {
    "search_keywords": ["关键词1", "关键词2"],
    "search_intent": "这篇笔记要命中的搜索/收藏意图",
    "target_reader": "最该看到这篇的人",
    "core_claim": "一个明确主张",
    "cognitive_conflict": "普通人错在哪里/反差在哪里",
    "source_evidence": ["保留的原视频例子或论据"],
    "reader_payoff": "读者看完能带走什么",
    "format_rationale": "为什么这篇适合做搜索型知识图文，而不是 transcript 截图或普通 PPT",
    "card_chain": ["封面", "误区", "重构", "论证", "例子", "方法", "收束"]
  },
  "xhs_format": {
    "format": "search_knowledge_cards",
    "visual_mode": "light_ppt_text_cards",
    "source_policy": "organized transcript is source; image_cards are rewritten card scripts, not transcript chunks"
  },
  "card_plan": [
    {"index": 1, "role": "cover", "purpose": "封面：关键词 + 最强判断", "text": "第1张卡片文案"}
  ],
  "body": "可直接发布的小红书正文，最后一行带话题标签",
  "image_cards": ["封面文案", "第2张文案", "..."],
  "quality_notes": ["简短说明你保留了哪些原始论点"]
}
"""

JSON_SCHEMA = json.dumps(
    {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "note_brief": {
                "type": "object",
                "properties": {
                    "search_keywords": {"type": "array", "items": {"type": "string"}},
                    "search_intent": {"type": "string"},
                    "target_reader": {"type": "string"},
                    "core_claim": {"type": "string"},
                    "cognitive_conflict": {"type": "string"},
                    "source_evidence": {"type": "array", "items": {"type": "string"}},
                    "reader_payoff": {"type": "string"},
                    "format_rationale": {"type": "string"},
                    "card_chain": {"type": "array", "items": {"type": "string"}},
                },
                "required": [
                    "search_keywords",
                    "search_intent",
                    "target_reader",
                    "core_claim",
                    "cognitive_conflict",
                    "source_evidence",
                    "reader_payoff",
                    "format_rationale",
                    "card_chain",
                ],
                "additionalProperties": False,
            },
            "xhs_format": {
                "type": "object",
                "properties": {
                    "format": {"type": "string"},
                    "visual_mode": {"type": "string"},
                    "source_policy": {"type": "string"},
                },
                "required": ["format", "visual_mode", "source_policy"],
                "additionalProperties": False,
            },
            "card_plan": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "index": {"type": "number"},
                        "role": {"type": "string"},
                        "purpose": {"type": "string"},
                        "text": {"type": "string"},
                    },
                    "required": ["index", "role", "purpose", "text"],
                    "additionalProperties": False,
                },
            },
            "body": {"type": "string"},
            "image_cards": {"type": "array", "items": {"type": "string"}, "minItems": 4},
            "quality_notes": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["title", "note_brief", "xhs_format", "card_plan", "body", "image_cards"],
        "additionalProperties": False,
    },
    ensure_ascii=False,
)


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def extract_json(raw: str) -> dict:
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    try:
        data = json.loads(raw)
        if isinstance(data, dict) and isinstance(data.get("result"), str):
            return extract_json(data["result"])
        return data
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, flags=re.S)
        if not match:
            raise
        data = json.loads(match.group(0))
        if isinstance(data, dict) and isinstance(data.get("result"), str):
            return extract_json(data["result"])
        return data


def extract_markdown_output(raw: str) -> dict:
    raw = raw.split("--- STDERR ---", 1)[0]
    title = ""
    title_match = re.search(r"\*\*[^*\n]*标题[^*\n]*\*\*[:：]?\s*\n?(.+?)(?:\n-{3,}|\n\n)", raw, flags=re.S)
    if title_match:
        title = title_match.group(1).strip()
    body = ""
    body_match = re.search(r"\*\*[^*\n]*正文[^*\n]*\*\*\s*(.+?)(?:\n-{3,}\s*\n\*\*[^*\n]*图片|\n\*\*[^*\n]*图片)", raw, flags=re.S)
    if body_match:
        body = body_match.group(1).strip()
    cards: list[str] = []
    cards_match = re.search(r"\*\*[^*\n]*图片[^*\n]*\*\*\s*(.+?)(?:\n-{3,}\s*\n\*\*保留|\n\*\*保留|$)", raw, flags=re.S)
    if cards_match:
        for line in cards_match.group(1).splitlines():
            line = line.strip()
            if not line or line.startswith("|---") or "卡片文案" in line:
                continue
            if line.startswith("|"):
                cells = [cell.strip() for cell in line.strip("|").split("|")]
                if len(cells) >= 2 and cells[0] != "#":
                    cards.append(cells[-1].replace("／", "\n"))
            else:
                bullet = re.sub(r"^[-*\\d.、\\s]+", "", line).strip()
                if bullet:
                    cards.append(bullet)
    notes: list[str] = []
    notes_match = re.search(r"\*\*保留.*?\*\*\s*(.+)$", raw, flags=re.S)
    if notes_match:
        for line in notes_match.group(1).splitlines():
            line = re.sub(r"^[-*\\s]+", "", line).strip()
            if line:
                notes.append(line)
    if not title or not body or len(cards) < 4:
        raise ValueError("markdown output missing title/body/cards")
    return {"title": title, "body": body, "image_cards": cards, "quality_notes": notes}


def compact_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def chinese_len(text: str) -> int:
    return len(re.sub(r"\s+", "", text or ""))


def sentence_fragments(text: str) -> list[str]:
    text = compact_spaces(text)
    fragments = re.split(r"[。！？!?；;]\s*", text)
    rows = [frag.strip(" ，,.") for frag in fragments if chinese_len(frag) >= 12]
    if len(rows) <= 2:
        cue_pattern = r"(?=(?:比如说|所以说|也就是说|如果|但是|因为|真正|这时候|当|你要|我觉得|回到|第一|第二|第三))"
        rows = [frag.strip(" ，,.") for frag in re.split(cue_pattern, text) if chinese_len(frag) >= 12]
    expanded: list[str] = []
    for row in rows:
        if chinese_len(row) <= 150:
            expanded.append(row)
            continue
        start = 0
        while start < len(row):
            piece = row[start : start + 140].strip(" ，,.")
            if chinese_len(piece) >= 12:
                expanded.append(piece)
            start += 140
    return expanded


def clean_oral_text(text: str) -> str:
    text = compact_spaces(text)
    for marker in ORAL_MARKERS:
        text = text.replace(marker, "")
    text = re.sub(r"\b(PVT)\b", "PPT", text, flags=re.I)
    text = re.sub(r"\bsecondary\b", "secondary", text, flags=re.I)
    text = re.sub(r"\bprimary\b", "primary", text, flags=re.I)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"([。！？!?；;])\s+", r"\1", text)
    return text.strip()


def card_line(text: str, limit: int = 118) -> str:
    text = clean_oral_text(text)
    text = re.sub(r"[。！？!?；;]+$", "", text)
    if chinese_len(text) <= limit:
        return text.rstrip("，,. ") + "。"
    cut = text[:limit].rstrip("，,. ")
    return cut + "。"


def card_script_line(
    heading: str,
    body: str,
    *,
    keyword: str = "",
    limit: int = 220,
) -> str:
    """Create a Xiaohongshu card line from an edited judgment, not transcript."""
    heading = clean_oral_text(heading).strip("。；; ")
    body = clean_oral_text(body).strip("。；; ")
    if keyword and keyword not in heading and keyword not in body:
        heading = f"{keyword}：{heading}"
    text = f"{heading}\n{body}" if heading else body
    return card_line(text, limit)


def record_context(record: dict) -> tuple[str, str, str]:
    topic_text = "\n".join(
        str(record.get(key) or "")
        for key in ["_draft_file_topic", "source_unit_title", "title", "local_id"]
    )
    source_text = str(record.get("source_excerpt") or record.get("body") or "")
    combined = f"{topic_text}\n{source_text}"
    return topic_text, source_text, combined


def source_classification_context(record: dict) -> str:
    """Classify from source material, not from previously generated draft titles."""
    return "\n".join(
        str(record.get(key) or "")
        for key in ["source_unit_title", "source_excerpt", "source_organized_transcript_md", "source_transcript_md"]
    )


def is_trading_expectation_case(source_text: str) -> bool:
    return any(word in source_text for word in ["战争", "石油", "预期差", "风险资产", "霍尔木兹", "明牌"])


def is_decision_framework_case(source_text: str) -> bool:
    return any(word in source_text for word in ["第一性原理", "样本", "大数定律", "不要通过果来判断因", "随机", "决策行为"])


def is_focus_ant_case(source_text: str) -> bool:
    return any(word in source_text for word in ["蚂蚁理论", "二维生物", "贪多嚼不", "人生选择有很多", "只能做一件"])


def is_ai_visual_workflow_case(source_text: str) -> bool:
    return any(word in source_text for word in ["Remotion", "remotion", "PPT", "PVT", "抽象的概念", "自动判断", "视频过程中"])


def is_agent_cost_case(source_text: str) -> bool:
    return any(word in source_text for word in ["token", "Token", "消耗", "coding agent", "Codex", "Gemini", "Claude"]) and any(
        word in source_text for word in ["测试", "对比", "成本", "听话", "agent", "Agent"]
    )


def is_ai_adoption_mindset_case(source_text: str) -> bool:
    strong_markers = ["盲人摸象", "忙人摸", "阴谋论", "愚昧", "熟视无睹", "视而不见", "passive", "主动去找工作"]
    boundary_markers = ["不敢探索", "等大家看清楚", "那我就不摸", "享受这个劳动成果"]
    return any(word in source_text for word in strong_markers) or any(word in source_text for word in boundary_markers)


def is_agent_architecture_case(source_text: str) -> bool:
    return any(
        word in source_text
        for word in ["单点capability", "多agent", "十个agent", "二十个agent", "上下文", "unnecessary", "弹出二维码", "公司架构"]
    ) and any(word in source_text for word in ["agent", "Agent", "AI", "skill", "工作流"])


def is_ai_workflow_case(source_text: str) -> bool:
    return any(word in source_text for word in ["AI", "Claude", "Agent", "智能体", "工具", "工作流", "自动化", "prompt", "Prompt"])


def is_life_choice_case(source_text: str) -> bool:
    return any(word in source_text for word in ["选择", "人生", "职业", "复利", "专注", "意愿", "努力", "上限", "价值观", "成长"])


def is_content_business_case(source_text: str) -> bool:
    return any(word in source_text for word in ["自媒体", "小红书", "公众号", "电商", "一人公司", "内容产品", "内容复用"])


def template_kind(source_text: str) -> str:
    if is_ai_adoption_mindset_case(source_text):
        return "ai_adoption_mindset"
    if is_focus_ant_case(source_text):
        return "focus_ant_theory"
    if is_agent_architecture_case(source_text):
        return "agent_architecture"
    if is_agent_cost_case(source_text):
        return "agent_cost_analysis"
    if is_decision_framework_case(source_text):
        return "decision_framework"
    if is_ai_visual_workflow_case(source_text):
        return "ai_visual_workflow"
    if is_trading_expectation_case(source_text):
        return "trading_expectation"
    if is_content_business_case(source_text):
        return "content_business"
    if is_ai_workflow_case(source_text):
        return "ai_workflow"
    if is_life_choice_case(source_text):
        return "life_choice"
    return "general_framework"


TOPIC_TITLES = {
    "trading_expectation": "为什么90%人错过明牌",
    "ai_visual_workflow": "为什么AI视频不是靠剪辑",
    "ai_adoption_mindset": "别等AI边界清楚",
    "agent_architecture": "别一上来就多Agent",
    "agent_cost_analysis": "AI Agent别只看能力",
    "focus_ant_theory": "为什么聪明人反而贪多",
    "decision_framework": "别用结果倒推决策",
    "content_business": "为什么内容复用不是搬运",
    "ai_workflow": "别把AI只当工具",
    "life_choice": "努力不会自动复利",
    "general_framework": "",
}

TOPIC_KEYWORDS = {
    "trading_expectation": ["交易", "明牌", "预期差", "石油", "战争", "常识"],
    "ai_visual_workflow": ["AI视频", "Remotion", "视觉化", "剪辑"],
    "ai_adoption_mindset": ["AI", "边界", "探索", "一人公司"],
    "agent_architecture": ["AI Agent", "Agent", "工作流", "多Agent", "架构"],
    "agent_cost_analysis": ["AI Agent", "Token", "成本", "返工", "稳定性"],
    "focus_ant_theory": ["专注", "贪多", "复利", "聪明"],
    "decision_framework": ["结果", "因果", "第一性原理", "决策", "样本"],
    "content_business": ["小红书", "内容复用", "自媒体", "内容工作流"],
    "ai_workflow": ["AI", "工作流", "SOP", "自动化"],
    "life_choice": ["个人成长", "专注", "复利", "努力", "判断力"],
    "general_framework": ["认知框架", "个人成长", "判断"],
}


def title_hits_topic(title: str, kind: str) -> bool:
    if not title:
        return False
    return any(keyword in title for keyword in TOPIC_KEYWORDS.get(kind, []))


def planned_title(record: dict, kind: str) -> str:
    file_topic = shorten_title(str(record.get("_draft_file_topic") or ""))
    source_unit_title = shorten_title(str(record.get("source_unit_title") or ""))
    topic_text = str(record.get("source_unit_title") or "")
    source_text = str(record.get("source_excerpt") or record.get("body") or "")
    combined = f"{topic_text}\n{source_text}"
    if file_topic and not any(marker in file_topic for marker in ["拆条", "xiaohongshu"]):
        if "remotion" in file_topic.lower():
            return "为什么AI视频不是靠剪辑"
        if "token" in file_topic.lower():
            return "AIAgent别只看能力"
        if "明牌" in file_topic or "90%" in file_topic:
            return file_topic
        if chinese_len(file_topic) >= 5 and title_hits_topic(file_topic, kind):
            return file_topic
    if kind in TOPIC_TITLES and TOPIC_TITLES[kind]:
        return TOPIC_TITLES[kind]
    if (
        source_unit_title
        and chinese_len(source_unit_title) >= 5
        and source_unit_title not in {"结论", "测试目的", "未来职业建议"}
        and title_hits_topic(source_unit_title, kind)
    ):
        return source_unit_title
    existing = str(record.get("source_unit_title") or record.get("title") or "")
    if "专注" in combined:
        return "专注不是意志力"
    if "复利" in combined:
        return "真正值得做的事会复利"
    return shorten_title(existing or "这条值得重看")


CARD_PLAN_TEMPLATES: dict[str, list[tuple[str, str]]] = {
    "conclusion_first": [
        ("cover", "封面：关键词 + 最强判断"),
        ("misunderstanding", "误区：普通人错在哪里"),
        ("reframe", "重构：换一个更高层的问题"),
        ("reasoning", "论证：为什么这个判断成立"),
        ("example", "例子：保留视频中的具体场景"),
        ("method", "方法：如何判断或操作"),
        ("boundary", "边界：这个观点什么时候会失效"),
        ("saveable_rule", "收藏点：一句可复用判断"),
        ("application", "迁移：把框架用到其他场景"),
        ("close", "收束：下一步检查动作"),
    ],
    "suspense_first": [
        ("cover", "封面：抛冲突 / 数字 / 反差，不剧透结论"),
        ("conflict", "冲突：把两方对立放大成一句话"),
        ("example", "案例：第一人称真实经历，带 credibility 锚点"),
        ("consequence", "代价：这种错误判断会导致什么"),
        ("reasoning", "揭示：为什么大家会做错"),
        ("reframe", "重构：给出新的看问题角度"),
        ("method", "方法：到这里才给操作动作"),
        ("boundary", "边界：什么情况下不适用"),
        ("saveable_rule", "收藏点：一句可复用判断"),
        ("close", "收束：留一个反问 / 下一步动作"),
    ],
}


def card_plan(cards: list[str], kind: str) -> list[dict]:
    template_key = "suspense_first" if kind == "suspense_first" else "conclusion_first"
    roles = CARD_PLAN_TEMPLATES[template_key]
    return [
        {
            "index": idx,
            "role": roles[min(idx - 1, len(roles) - 1)][0],
            "purpose": roles[min(idx - 1, len(roles) - 1)][1],
            "text": card,
        }
        for idx, card in enumerate(cards, start=1)
    ]


def prioritize_keywords(preferred: list[str], existing: list[str]) -> list[str]:
    out: list[str] = []
    for item in preferred + existing:
        item = str(item).strip()
        if item and item not in out:
            out.append(item)
    return out[:5]


def align_keywords_to_title(title: str, brief: dict) -> dict:
    keywords = [str(item).strip() for item in brief.get("search_keywords") or [] if str(item).strip()]
    if title and keywords and any(keyword in title for keyword in keywords):
        return brief
    title_keyword = shorten_title(title)
    if title_keyword and chinese_len(title_keyword) >= 4:
        brief = dict(brief)
        brief["search_keywords"] = prioritize_keywords([title_keyword], keywords)
    return brief


FORBIDDEN_EXTERNAL_PHRASES = [
    "这张卡必须帮助读者做判断",
    "如果没有例子和边界",
    "好的卡片要让读者知道自己下一步该检查什么",
    "不只是标题",
    "卡片应该",
    "quality gate",
]


def strip_internal_phrases(text: str) -> str:
    for phrase in FORBIDDEN_EXTERNAL_PHRASES:
        text = text.replace(phrase, "")
    text = re.sub(r"(但|但是|就是|所以|然后|这个|那个|你说|我说)$", "", text.strip())
    text = re.sub(r"。{2,}", "。", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip(" ，。,.")


KIND_EVIDENCE_KEYWORDS = {
    "trading_expectation": ["交易", "明牌", "战争", "石油", "市场", "预期", "primary", "secondary", "风险资产", "黄金"],
    "decision_framework": ["决策", "结果", "样本", "因果", "第一性原理", "复盘", "系统"],
    "focus_ant_theory": ["蚂蚁", "专注", "聪明", "机会", "复利", "方向"],
    "ai_visual_workflow": ["Remotion", "视频", "画面", "可视化", "剪辑", "动画"],
    "ai_adoption_mindset": ["AI", "工具", "主动", "探索", "盲人摸象", "尝试"],
    "agent_architecture": ["agent", "Agent", "架构", "上下文", "能力", "任务", "节点"],
    "agent_cost_analysis": ["agent", "Agent", "token", "成本", "返工", "稳定", "测试"],
    "ai_workflow": ["AI", "工作流", "SOP", "自动化", "流程", "工具"],
    "life_choice": ["努力", "方向", "复利", "专注", "职业", "判断"],
    "content_business": ["小红书", "内容", "复用", "自媒体", "草稿", "发布"],
}


def source_evidence_fragments(source_text: str, keywords: list[str], kind: str) -> list[str]:
    out: list[tuple[int, int, str]] = []
    evidence_keywords = [str(item) for item in keywords if str(item).strip()]
    evidence_keywords.extend(KIND_EVIDENCE_KEYWORDS.get(kind) or [])
    seen_keywords: list[str] = []
    for keyword in evidence_keywords:
        keyword = keyword.strip()
        if keyword and keyword not in seen_keywords:
            seen_keywords.append(keyword)
    for order, fragment in enumerate(sentence_fragments(clean_oral_text(source_text))):
        fragment = strip_internal_phrases(fragment)
        if chinese_len(fragment) < 24:
            continue
        if any(phrase in fragment for phrase in FORBIDDEN_EXTERNAL_PHRASES):
            continue
        score = sum(1 for keyword in seen_keywords if keyword and keyword in fragment)
        if score <= 0 and seen_keywords:
            continue
        out.append((score, order, fragment))
    out.sort(key=lambda item: (-item[0], item[1]))
    deduped: list[str] = []
    for _score, _order, fragment in out:
        if fragment not in deduped:
            deduped.append(fragment)
    return deduped


def enrich_cards(cards: list[str], kind: str, source_text: str, brief: dict) -> list[str]:
    evidence = source_evidence_fragments(source_text, [str(item) for item in brief.get("search_keywords") or []], kind)
    used_evidence: set[int] = set()
    out: list[str] = []
    for idx, card in enumerate(cards):
        text = strip_internal_phrases(clean_oral_text(str(card).strip()))
        for evidence_index, addition in enumerate(evidence):
            if chinese_len(text) >= 90:
                break
            if evidence_index in used_evidence:
                continue
            normalized_addition = re.sub(r"\s+", "", addition)
            normalized_text = re.sub(r"\s+", "", text)
            if normalized_addition[:32] in normalized_text:
                continue
            if normalized_text[:32] and normalized_text[:32] in normalized_addition:
                continue
            if addition not in text:
                text = f"{text}\n{addition}"
                used_evidence.add(evidence_index)
        out.append(card_line(text, 220))
    return out


def trading_expectation_cards(title: str) -> list[str]:
    return [
        f"{title}\n很多人不是缺信息，而是看见太多细节，反而忽略了真正决定方向的大变量。",
        "今年很多交易其实是明牌。\n问题不是答案藏得太深，而是常识太简单，所以大家反而不愿意抄。\n他们更愿意找一个小众逻辑，证明自己比别人早。",
        "我把这个大变量叫做：房间里的大象。\n它不一定复杂，但它会让所有资产重新定价。\n如果你没先看见它，后面的技术分析和板块轮动都会变成噪音。",
        "比如战争。\n它会影响风险偏好，影响石油，影响黄金，也影响所有风险资产。\n所以你先要问的不是某个资产怎么走，而是市场正在围绕什么重新定价。",
        "这时候还在问“板块该不该轮动”，就是用 secondary 问题替代 primary 问题。\n这些问题不是完全没用，但顺序错了，就会把你带到错误的交易里。",
        "真正的问题不是新闻本身。\n真正的问题是：市场对战争的预期，是太乐观，还是太悲观？\n交易要看的不是事件，而是事件和市场预期之间的差。",
        "石油刚涨到 75 就做空，可能是在赌一个还没结束的变量已经结束。\n这不是逆向思维，这是在忽略变量仍然有效。",
        "石油冲到 120 再追，也可能是在买情绪的最高点。\n这时候不是你终于看懂了，而是市场可能已经把最悲观的预期打进去了。",
        "交易赚的不是“我知道了新闻”。\n交易赚的是预期差：真实发生的事，和市场以为会发生的事之间的差。\n这也是为什么常识比小聪明更重要。",
        "先别急着证明自己聪明。\n先问：这个房间里最大的大象是什么？\n我是在做 primary，还是在追 secondary？这个问题比多看十条消息更值钱。",
    ]


def trading_expectation_body(title: str, brief: dict) -> str:
    tags = " ".join(f"#{tag}" for tag in (brief.get("search_keywords") or [])[:6])
    body = f"""{title}。

很多人做交易不赚钱，不是因为不努力，也不是因为信息太少。

恰恰相反，是因为他看了太多细节，最后反而忽略了真正决定市场方向的那件事。

我把它叫做：房间里的大象。

比如一段时间里，真正主导全球资产的变量是战争。战争会影响风险偏好，会影响石油，会影响黄金，也会影响所有风险资产。

这时候你还在问：A 股是不是到了技术关键位？板块是不是该轮动了？某个小赛道会不会补涨？

这些问题不是完全没用，但它们都是 secondary。

如果最大变量是战争，你真正应该问的是：市场现在对战争的预期，是太乐观，还是太悲观？真实发生的事情，和市场预期之间有没有差距？

石油刚涨到 75 就做空，可能是在赌一个还没结束的变量已经结束。石油冲到 120 再追，也可能是在买情绪的最高点。

这就是我说的“明牌”：不是看见新闻就冲进去，而是知道所有资产正在围绕同一个变量重新定价，也知道市场情绪走到了哪个位置。

大部分人错过明牌，是因为他们觉得常识太简单，不够聪明。他们更愿意找一个小众逻辑，证明自己比别人早。

但真正能赚到的钱，往往来自一个更朴素的问题：现在房间里最大的大象是什么？我做的是 primary，还是 secondary？

如果你要把这个判断用在自己的交易里，可以先检查三件事：

第一，现在影响所有资产的最大变量是什么。

第二，市场对这个变量的预期已经走到哪里，是过度乐观，还是过度悲观。

第三，我现在想做的那笔交易，是在押真实变化和市场预期之间的差，还是只是在证明自己比别人聪明。

这三个问题问清楚之后，再谈技术位、板块轮动、短期情绪，顺序才是对的。

最后你可以把每一次判断都写进复盘里：当时最大的变量是什么，我的预期是什么，市场共识是什么，最后真实发生了什么。这样你积累的就不是一次输赢，而是一套越来越可靠的判断系统。

{tags}"""
    return body.strip()


def ai_workflow_cards(title: str) -> list[str]:
    return [
        f"{title}\n真正的分水岭不是会不会用一个 AI 工具，而是你有没有把它接进自己的工作流。",
        "很多人用 AI 的方式还是旧世界的。\n他们问一个问题，拿一个答案，然后继续靠自己手动拼接后面的步骤。",
        "这不是 AI 工作流，只是把搜索框换成了聊天框。\n效率会提高一点，但不会改变你的生产方式。",
        "真正要问的是：这个任务里最重复、最耗脑、最容易断掉的环节是什么？\nAI 应该先接管那里。",
        "比如内容生产，不是让 AI 替你写一句文案。\n而是从选题、拆稿、转平台、质检、渲染、归档，都变成一条可复用链路。",
        "工具本身不是护城河。\n护城河是你反复跑过之后，沉淀出来的判断标准、文件结构、命名规范和验收步骤。",
        "很多人焦虑，是因为每天都在换工具。\n但真正有价值的是：一个工具进来以后，你的系统有没有少一个手动动作。",
        "所以不要问“哪个 AI 工具最强”。\n先问：我现在这件事，有没有被写成一个可以复用、可以检查、可以交接的流程？",
        "AI 时代的能力，不是 prompt 写得多漂亮。\n而是你能不能把自己的经验，沉淀成机器也能执行的 SOP。",
        "最后检查一句话：这个 AI 用完之后，我是多了一个玩具，还是少了一段摩擦？",
    ]


def ai_workflow_body(title: str, brief: dict) -> str:
    tags = " ".join(f"#{tag}" for tag in (brief.get("search_keywords") or ["AI", "工作流", "自动化"])[:6])
    body = f"""{title}。

很多人现在用 AI，还是停留在“找一个工具、问一个问题、拿一个答案”的阶段。

这个阶段当然有用，但它不是 AI 工作流。它只是把搜索框换成了聊天框。

真正的变化，不是某个模型回答得更漂亮，而是你原来必须手动完成的一串动作，现在能不能变成一条稳定链路。

比如内容生产。不是让 AI 替你写一句标题，而是从选题判断、转录整理、平台改写、卡片脚本、质量检查、图片渲染、草稿推送，全部沉淀成可复用流程。

这时候 AI 才不是“工具”，而是系统里的一个节点。

工具本身不是护城河。今天这个模型强，明天那个模型强，你不可能靠追工具建立长期优势。

真正的护城河，是你在反复使用工具时沉淀出来的判断标准、文件结构、命名规范和验收步骤。

所以不要先问“哪个 AI 工具最强”。先问：我现在这件事，有没有被写成一个可以复用、可以检查、可以交接的流程？

如果答案是否定的，那你其实还在手工作坊里，只是手里拿着一个更聪明的锤子。

AI 时代真正值得积累的，不是 prompt 收藏夹，而是你自己的 SOP 库。

每次用完一个 AI 工具，都应该问一句：它到底帮我减少了哪一段摩擦？这段摩擦能不能从明天开始永久消失？

如果一个环节只是今天省了十分钟，但明天还要重新来一遍，那它只是临时提效。

如果一个环节被写进脚本、文件结构、检查标准和 dashboard，明天可以直接复用，那它才真的变成了生产力。

所以我判断 AI 能不能改变一个人，不看他试过多少工具，而看他有没有把自己的经验沉淀成系统。

最简单的检查方法是：把你今天用 AI 完成的事情，明天交给另一个人或另一个 agent，它能不能照着你的流程跑出差不多的结果。

如果不能，说明你只是完成了一次任务，还没有形成能力。真正的 AI 杠杆，一定会留下可以复用的轨道。

{tags}"""
    return body.strip()


def life_choice_cards(title: str) -> list[str]:
    return [
        f"{title}\n真正拉开差距的，往往不是努力程度，而是你把努力放进了什么系统。",
        "很多人一辈子都活在“努力”这一层。\n努力工作，努力赚钱，努力读书，努力维持关系。",
        "但环境一变，单纯的努力就可能被系统吞掉。\n你会发现自己很累，却没有真的走向想要的结果。",
        "努力只能解决“今天多做一点”的问题。\n它解决不了“我这一生到底往哪里走”的问题。",
        "所以更重要的是方向。\n方向不是一句口号，而是你知道什么事值得长期投入，什么事只是消耗你。",
        "一个人如果只有努力，没有方向，就像在海上拼命划船。\n他很累，但并不知道自己是在靠近陆地，还是原地打转。",
        "比努力更深的一层，是判断。\n判断决定你把时间、注意力、风险和信用押在哪里。",
        "真正可复利的事，通常不会立刻给你反馈。\n但它会让你每一次投入，都变成下一次选择的底层资产。",
        "所以不要只问：我今天有没有努力？\n还要问：我现在努力的这件事，十年后还会不会站在我这边？",
        "努力是底子，但不是命运的最高层。\n更重要的是方向、判断，以及你有没有在积累真正能复利的东西。",
    ]


def life_choice_body(title: str, brief: dict) -> str:
    tags = " ".join(f"#{tag}" for tag in (brief.get("search_keywords") or ["个人成长", "认知框架"])[:6])
    body = f"""{title}。

很多人对“努力”这件事有一种误解：好像只要足够努力，结果自然会变好。

但现实里，很多人明明已经很努力了，还是没有活成自己想要的样子。

问题不一定出在努力不够，而是努力所在的层级太低。

努力解决的是“今天多做一点”。但人生真正难的不是今天多做一点，而是你到底应该往哪里走。

方向错了，越努力，沉没成本越高。方向对了，很多看起来很慢的积累，反而会在后面变成复利。

所以我更关心一个人有没有判断力。

判断力决定你把自己的时间、注意力、信用和风险押在哪里。它比短期勤奋更重要。

一个人如果只有努力，没有方向，就像在海上拼命划船。你可以划得很累，但你不知道自己是在靠近陆地，还是在原地打转。

真正值得做的事，往往不会马上给你反馈。它一开始甚至显得很慢、很笨、很不划算。

但如果它能让你的能力、认知、关系和信用持续复利，那它就不是消耗，而是在积累资产。

所以不要只问：我今天有没有努力。

更应该问：我现在努力的这件事，十年后还会不会站在我这边？

专注也是同一个逻辑。

专注不是把所有机会都拒绝掉，而是你知道自己这一阶段最重要的积累是什么。你愿意为了这个积累，放弃那些看起来很聪明、很新鲜、很容易让人兴奋的选项。

很多人做不成事，不是因为没有能力，而是每隔几天就被一个新机会带走。每一次转向都像是在重新开始，最后什么都碰过一点，但没有一件事真的形成复利。

比如一个人今天想做内容，明天想做交易，后天想做工具，过几天又觉得应该去学销售。每一件事看起来都有道理，但如果它们没有汇入同一条主线，最后只会变成分散消耗。

所以真正的专注，不是意志力表演，而是一种判断：我知道什么值得长期做，也知道什么只是短期噪音。

如果你能把这个判断稳定下来，努力才会开始变得有意义。

{tags}"""
    return body.strip()


def content_business_cards(title: str) -> list[str]:
    return [
        f"{title}\n内容不是把想法发出去，而是把一个判断包装成可以被搜索、收藏和转化的产品。",
        "很多人做内容，只是在搬运自己的表达欲。\n他说了很多，但读者不知道为什么要点开、为什么要收藏、为什么要相信。",
        "平台不会因为你讲得多就给你流量。\n平台奖励的是明确的搜索意图、清楚的封面标题、稳定的完读和收藏。",
        "所以内容生产的第一步不是写稿。\n第一步是判断：这条内容到底命中哪个关键词，解决哪个具体问题？",
        "一条抖音视频可以拆成很多小红书笔记。\n但不是按时间切，而是按独立主题切：每篇都要有自己的搜索入口。",
        "图文卡片也不是把字幕贴进图片。\n它应该是封面、误区、框架、例子、方法、结论，一张一张推进读者理解。",
        "真正可复用的内容工作流，一定要有文件结构。\n源视频、转录稿、organized transcript、note brief、card script、rendered images，各自有位置。",
        "有了结构之后，内容才不是一次性手工活。\n它会变成一条生产线：能检查、能重跑、能改进、能交接。",
        "内容要长期做，靠灵感不够。\n你需要的是一套能每天稳定产出的 SOP，而不是每次从空白文档开始。",
        "最后判断一句：这条内容是一个作品，还是一个可以反复生产同类作品的流程？",
    ]


def content_business_body(title: str, brief: dict) -> str:
    tags = " ".join(f"#{tag}" for tag in (brief.get("search_keywords") or ["内容创作", "小红书", "自媒体"])[:6])
    body = f"""{title}。

内容不是把想法发出去。

内容是把一个判断，包装成可以被搜索、可以被点击、可以被收藏、可以被转化的产品。

很多人做内容时，只是在搬运自己的表达欲。他说了很多，但读者不知道为什么要点开，也不知道为什么要收藏。

尤其是小红书，它不是单纯的信息流平台。它有很强的搜索逻辑。

这意味着一篇笔记首先要回答：我到底要命中哪个关键词？用户是在什么场景下搜到我？他看完之后为什么要保存？

所以从抖音转小红书，不能简单把视频字幕塞进图片里。

更好的做法是：先判断这条视频能拆成几个独立主题。每一个主题，都应该有自己的标题、搜索关键词、封面判断和卡片脚本。

一条长视频可以变成 3 篇、5 篇，甚至 10 篇小红书笔记。但拆分依据不是时间长度，而是“每篇是否能独立解决一个问题”。

图文卡片也不是 PPT 汇报。它应该像一条论证链：封面先给判断，第二张指出误区，第三张给框架，后面用例子和方法推进，最后给一个值得收藏的结论。

如果没有这个结构，图文就会变成 transcript 截图。看起来信息很多，但读者很难抓住重点。

长期来看，内容生产不能靠灵感。要靠 SOP。

源视频放哪里、转录稿放哪里、organized transcript 怎么生成、note brief 怎么写、card script 怎么质检、图片怎么渲染，这些都要固定下来。

只有这样，内容才不是一次性的手工活，而是一条可以重跑、可以检查、可以升级的生产线。

这也是我现在做 outbox 的原因：不是为了把每条内容都手动搬一遍，而是要让每条抖音进入系统后，都能自动出现它应该去的小红书、公众号、X、视频平台位置。

当这个流程跑顺以后，内容生产的重点就会从“我今天又要从零写什么”，变成“我今天要审核哪几个已经成型的内容资产”。

这才是长期做内容更可持续的方式。

{tags}"""
    return body.strip()


def ai_visual_workflow_cards(title: str) -> list[str]:
    return [
        f"{title}\n真正的变化不是把视频剪得更花，而是让抽象概念在画面里自动被讲清楚。",
        "很多人看到 AI 视频，以为重点是剪辑、转场、字幕和包装。\n但更大的变化，是视频开始能根据你的表达内容，自动生成对应的视觉解释。",
        "比如你讲一个抽象概念，画面里可以自动出现时间线、表格、流程图、对比图。\n这不是装饰，而是在帮观众理解你原本说不清的部分。",
        "Remotion 这类工作流的价值，不是多一个酷炫效果。\n它真正解决的是：讲复杂问题时，画面能不能跟着逻辑一起变。",
        "过去做这种视频，需要你先写脚本，再设计 PPT，再剪辑，再对齐口播。\n每一步都是手工活，所以很难稳定产出。",
        "AI 接进来以后，关键不是让它替你剪一个片段。\n而是让它判断：哪里需要图，哪里需要表，哪里需要时间线，哪里只需要保留人声。",
        "这会改变内容生产的分工。\n人负责判断和表达，AI 负责把表达翻译成更容易被理解的视觉结构。",
        "所以真正值得积累的不是某个模板。\n而是你能不能把“什么内容适合什么视觉表达”写成可复用规则。",
        "如果每次都从零剪，那只是提效。\n如果一条长视频能自动识别抽象段落、生成画面、输出卡片和短视频，那才是工作流升级。",
        "AI 视频的核心不是更会剪辑。\n而是让你的思考过程，自动变成观众能看懂的视觉结构。",
    ]


def ai_visual_workflow_body(title: str, brief: dict) -> str:
    tags = " ".join(f"#{tag}" for tag in (brief.get("search_keywords") or ["AI视频", "Remotion", "内容创作"])[:6])
    body = f"""{title}。

很多人看到 AI 视频，第一反应是：这个剪辑好炫，这个转场好复杂，这个字幕好高级。

但我觉得真正重要的不是剪辑。

真正重要的是：当你在讲一个抽象概念时，画面能不能跟着你的逻辑一起变化。

比如你讲一个时间线，画面里就应该出现时间线。你讲一个对比，画面里就应该出现表格。你讲一个复杂流程，画面里就应该出现流程图。

这不是为了好看，而是为了降低理解成本。

过去做这件事很难。你需要先写脚本，再做 PPT，再剪辑，再把口播和画面对齐。每一步都靠人工，所以它很难每天稳定产出。

但 Remotion 这类工作流加上 AI 之后，问题就变了。

你不再只是问：怎么把视频剪得更好看？

你开始问：这一段内容里，哪里是抽象概念？哪里需要被视觉化？哪里应该用时间线？哪里应该用表格？哪里只需要保留原始口播？

这个问题一旦能被 AI 判断，内容生产就从“手工剪视频”变成了“把表达翻译成视觉结构”。

这也是我现在更关心的方向。

不是做一个更酷的模板，而是沉淀一套规则：什么样的内容，应该被变成什么样的画面。

如果每一条视频都要从零开始剪，那只是临时提效。

如果一条长视频进入系统后，能自动识别抽象段落、生成卡片、生成画面、生成短视频切片，那才是真的生产方式变化。

所以 AI 视频真正的重点，不是更会剪辑，而是让思考过程本身变得可视化。

如果你也在做知识内容，可以直接用一个检查清单：

第一，这段话里有没有抽象概念。第二，这个概念能不能被画成时间线、表格、流程或对比。第三，画面出现以后，观众是不是更容易理解，而不是只是觉得更热闹。

如果答案是肯定的，这一段就值得被视觉化。

你可以先检查这一条：这个画面出现以后，观众是更容易理解了，还是只是被更多元素分散了注意力。

如果画面只是为了炫技，没有降低理解成本，那它就不是工作流升级，只是换了一层包装。

{tags}"""
    return body.strip()


def focus_ant_cards(title: str) -> list[str]:
    return [
        f"{title}\n聪明人最大的问题，往往不是能力不够，而是觉得自己什么都能做。",
        "我把它叫做蚂蚁理论。\n如果一个生命只能在二维世界里移动，它看见的选择很多，但它其实很难理解更高维度的方向。",
        "很多年轻且聪明的人也是这样。\n他觉得自己学习能力强，所以什么都想试，什么都想抓住。",
        "问题是，选择太多的时候，人很容易把“我能做”误解成“我应该做”。\n这两句话差别非常大。",
        "交易里也是一样。\n你今天看缠论，明天看波浪，后天又研究宏观，最后不是系统更强，而是变量越来越乱。",
        "真正难的不是多学一个东西。\n真正难的是承认：这一阶段，我只能把一件最重要的事做好。",
        "聪明人最容易输在贪多。\n因为他总能为每个新方向找到理由，也总觉得自己可以很快学会。",
        "但复利不奖励横跳。\n复利奖励的是你在同一条主线上，持续积累样本、反馈和判断力。",
        "所以判断一个机会，不要只问它有没有价值。\n还要问：它会不会打断我现在最重要的主线？",
        "能做很多事不是优势。\n知道这一阶段只做哪一件事，才是真正的优势。",
    ]


def focus_ant_body(title: str, brief: dict) -> str:
    tags = " ".join(f"#{tag}" for tag in (brief.get("search_keywords") or ["专注", "个人成长", "认知框架"])[:6])
    body = f"""{title}。

很多聪明人最大的问题，不是能力不够。

恰恰相反，是因为他觉得自己什么都能做。

我把这个问题暂时叫做“蚂蚁理论”。

如果一个生命只能在二维世界里移动，它会看见很多路，也会觉得每一条路都可以走。但它未必能理解更高维度里真正重要的方向。

很多年轻且聪明的人也是这样。

他学习能力很强，反应很快，什么都能上手。所以他很容易产生一种错觉：既然我能做，那我就应该做。

但“我能做”和“我应该做”，中间差了一个判断系统。

交易里尤其明显。

你今天看缠论，明天看波浪，后天研究宏观，过几天又觉得应该学量化。每个东西都有道理，每个东西都能解释一部分世界。

但如果它们没有汇入同一套系统，最后你得到的不是更多判断力，而是更多噪音。

人生选择也一样。

一个人总觉得自己可以做内容，可以做交易，可以做工具，可以做产品，可以做投资。看起来选择很多，但如果每一个方向都只做一点，最后没有一个方向能形成复利。

所以真正难的不是多学。

真正难的是承认：这一阶段，我只能把一件最重要的事做好。

聪明人最容易输在贪多。因为他总能为每个新方向找到理由，也总觉得自己可以很快学会。

但复利不奖励横跳。复利奖励的是你在同一条主线上，持续积累样本、反馈和判断力。

所以判断一个机会，不要只问它有没有价值。

还要问：它会不会打断我现在最重要的主线？

能做很多事不是优势。知道这一阶段只做哪一件事，才是真正的优势。

你可以把所有新机会都放进同一个判断框里：

它是否服务我当前主线？它是否能带来长期样本？它是否会让我过去的积累继续复利？如果三个问题有两个是否定的，即使它看起来很诱人，也大概率只是分散注意力。

专注不是靠忍住欲望。

专注是你真的知道，自己现在最应该积累的那条主线是什么。

你可以先把最近想做的所有事列出来，然后只问一个问题：哪一件事最能服务我未来三年的主线？如果回答不出来，说明问题不是机会不够，而是主线还不够清楚。

{tags}"""
    return body.strip()


def decision_framework_cards(title: str) -> list[str]:
    return [
        f"{title}\n很多人复盘最大的问题，是用一次结果去证明一套决策是对是错。",
        "这件事在交易里特别常见。\n赚了，就觉得系统有效；亏了，就马上推翻系统。\n但一次结果根本说明不了那么多。",
        "不要通过果来倒推因。\n除非你已经积累了足够多样本，否则你看到的很可能只是随机性。",
        "第一性原理不是一句口号。\n它要求你先问：这个系统里真正决定结果的变量是什么？哪些只是噪音？",
        "如果样本不够，你就急着改系统，最后会变成今天修一个点，明天换一个逻辑。\n看起来很勤奋，实际是在破坏可验证性。",
        "做交易最怕的不是一次亏损。\n最怕的是每一次亏损后，你都随机改一套规则。",
        "用 AI 也是一样。\n你不能因为一次输出不好，就马上换模型、换 prompt、换工具。\n你要先判断问题到底出在目标、上下文、流程，还是模型能力。",
        "真正的护城河，是你能持续积累样本，并且知道什么时候该调整系统，什么时候只是接受波动。",
        "所以复盘时先别问：这次对了吗？\n先问：这个结果有没有足够样本支撑？它能不能证明我的因果判断？",
        "高手不是每次都猜对。\n高手是不会被单次结果牵着走，他知道怎样让系统在足够多样本里变得可靠。",
    ]


def decision_framework_body(title: str, brief: dict) -> str:
    tags = " ".join(f"#{tag}" for tag in (brief.get("search_keywords") or ["第一性原理", "交易复盘", "决策框架"])[:6])
    body = f"""{title}。

很多人复盘最大的问题，是用一次结果去证明一套决策是对是错。

这在交易里特别明显。

赚了，就觉得自己的系统有效。亏了，就马上推翻系统。今天改一个指标，明天换一个逻辑，后天又觉得是心态问题。

但一次结果根本说明不了那么多。

不要通过果来倒推因。

除非你已经积累了足够多样本，否则你看到的很可能只是随机性，而不是因果关系。

第一性原理不是一句口号。

它真正要求你做的，是先问清楚：这个系统里真正决定结果的变量是什么？哪些变量只是噪音？我现在看到的这个结果，有没有足够样本支撑？

如果样本不够，你就急着改系统，最后系统永远无法被验证。

做交易最怕的不是一次亏损。

最怕的是每一次亏损后，你都随机改一套规则。这样你永远不知道自己到底是在修正错误，还是在追逐噪音。

用 AI 也是一样。

一次输出不好，不代表模型不行。可能是目标不清楚，可能是上下文不够，可能是流程设计错了，也可能只是你没有给它足够明确的验收标准。

如果你每次都直接换工具，就没有办法积累真正的判断。

真正的护城河，是你能持续积累样本，并且知道什么时候该调整系统，什么时候只是接受波动。

所以复盘时，先别问：这次对了吗？

先问：这个结果有没有足够样本支撑？它能不能证明我的因果判断？如果不能，那我现在要做的不是立刻推翻系统，而是继续记录、继续观察、继续让变量可验证。

高手不是每次都猜对。

高手是不会被单次结果牵着走。他知道怎样让系统在足够多样本里变得可靠。

这个原则可以放到很多事情里。

做内容，一条笔记数据不好，不代表选题方向错了。用 AI，一次输出不好，不代表模型不行。做产品，一次用户反馈不好，也不代表整个产品判断错了。

真正要检查的是：我有没有足够样本？变量有没有被控制住？我现在改的是系统里的关键因，还是只是被一个结果刺激到了？

如果这个问题没问清楚，越复盘越容易把自己带偏。

{tags}"""
    return body.strip()


def agent_cost_cards(title: str) -> list[str]:
    return [
        f"{title}\n选 AI Agent 不能只看谁更聪明，还要看它在真实任务里的成本、稳定性和可控性。",
        "很多人测试 coding agent，只看一个结果：它最后有没有写出来。\n但这其实不够，因为真实生产不是一次演示，而是每天反复用。",
        "真正要看的第一件事，是它听不听话。\n同样一个任务，它能不能按你的边界做，能不能少自作主张，能不能稳定遵守文件结构。",
        "第二件事，是 token 消耗。\n一个 agent 很强，但每次都要消耗大量上下文和调用成本，它未必适合高频工作流。",
        "第三件事，是返工率。\n如果它第一次做得很快，但后面需要你不断修偏、解释、重跑，真实成本就会被低估。",
        "所以测试 agent 不应该只看“谁赢了”。\n更应该记录：输入多长、跑了多久、用了多少 token、改了几轮、最后有没有符合验收标准。",
        "这也是为什么我更重视 workflow。\n单次能力强只是起点，能不能被放进稳定流程里，才决定它有没有生产价值。",
        "比如 Codex、Claude、Gemini 这类工具，不能只比较模型聪明程度。\n要比较它们在同一个任务、同一套文件、同一条验收标准下的表现。",
        "一个好 agent 的标准不是“偶尔惊艳”。\n而是它能不能在明确边界里，稳定产出你可以接着用的结果。",
        "所以测试 AI Agent 时，别只看答案。\n要看成本、返工、稳定性和可复用性。真正贵的不是 token，而是你被迫反复盯着它。",
    ]


def agent_cost_body(title: str, brief: dict) -> str:
    tags = " ".join(f"#{tag}" for tag in (brief.get("search_keywords") or ["AI Agent", "Token", "工作流"])[:6])
    body = f"""{title}。

很多人测试 AI Agent，只看一个结果：它最后有没有把东西做出来。

但如果你真的要把它放进日常生产，这个标准是不够的。

因为真实工作不是一次演示。真实工作是每天反复跑、反复改、反复接入你的文件结构和验收标准。

所以我看 coding agent，不只看它聪不聪明。

我会先看它听不听话。

同样一个任务，它能不能按边界做？能不能不要乱改无关文件？能不能理解现在这个 repo 的结构，而不是每次都按自己的习惯重来？

第二件事，是 token 消耗。

一个 agent 看起来很强，但如果每次都需要巨大上下文、很长推理、很多轮返工，它未必适合高频生产。

第三件事，是返工率。

有些工具第一次输出很快，但你后面要花很多时间解释、纠偏、补测试、补验收。这个时间也是成本。

所以测试 agent 不应该只问“谁赢了”。

更应该记录几个指标：输入多长，跑了多久，用了多少 token，改了几轮，最后有没有通过验收标准。

这也是为什么我越来越重视 workflow。

单次能力强只是起点。一个工具能不能被放进稳定流程里，能不能每天产出差不多质量的结果，才决定它有没有生产价值。

比如 Codex、Claude、Gemini 这类工具，不能只比较模型聪明程度。

要比较它们在同一个任务、同一套文件、同一条验收标准下，谁更稳定，谁更少返工，谁更容易接进你的工作流。

一个好 agent 的标准不是偶尔惊艳。

它应该能在明确边界里，稳定产出你可以接着用的结果。

如果要做成自己的测试表，我会把每一次测试都记录下来：任务是什么、约束是什么、上下文多长、跑了几轮、哪里偏离、最后人工修了多少。

这样比较几次以后，你就不会被一次惊艳输出骗到，也不会因为一次失败就误判一个工具。

真正适合进入工作流的 agent，应该能在多数普通任务里稳定减少你的摩擦，而不是偶尔给你一个很漂亮的 demo。

所以测试 AI Agent 时，别只看答案。

要看成本、返工、稳定性和可复用性。真正贵的不是 token，而是你被迫反复盯着它。

你可以从下一次测试开始，把每个 agent 的任务结果、token 消耗、返工次数和人工修正时间都记下来。连续记录十次以后，再决定哪个工具进入你的长期工作流。

{tags}"""
    return body.strip()


def ai_adoption_mindset_cards(title: str) -> list[str]:
    return [
        f"{title}\nAI 不是等别人研究清楚以后，你再来安全享受成果的东西。真正的差距来自主动探索。",
        "很多人现在像在盲人摸象。\n摸到一点不完整，就说这东西不行；听到别人争议，就干脆选择不摸。",
        "但问题是：如果你一直等能力边界被别人画清楚，凭什么最后的劳动成果会留给你？",
        "最危险的不是焦虑。\n焦虑至少说明你知道世界在变。更危险的是熟视无睹，还用阴谋论给自己找理由。",
        "比如说 AI 是为了让你烧 token，比如说一人公司只是概念，比如说 vibe coding 代替不了工程师。",
        "这些判断里可能有一部分事实。\n但如果它最后让你停止探索，它就不再是判断，而是逃避。",
        "AI 的变化不是从聊天机器人到另一个聊天机器人。\n它已经在变成能开发、能协作、能编排 workflow 的生产节点。",
        "你不需要一开始就相信所有概念。\n但你至少要亲手做任务，亲手试边界，亲手知道哪些能闭环，哪些还不行。",
        "真正的分水岭不是乐观还是悲观。\n而是你有没有把 passive 变成 active：主动找工作给 AI 做，主动把能力接进流程。",
        "别等 AI 边界清楚。\n边界通常是用出来的。你越晚开始摸，越只能引用别人的结论。",
    ]


def ai_adoption_mindset_body(title: str, brief: dict) -> str:
    tags = " ".join(f"#{tag}" for tag in (brief.get("search_keywords") or ["AI", "一人公司", "AI时代", "认知差"])[:6])
    body = f"""{title}。

现在很多人看 AI，有点像盲人摸象。

摸到一点不完整，就说这个东西不行；听到几个专家说还不能闭环，就干脆选择不摸；看到有人讨论 token 成本，就把整件事理解成“厂家让你烧钱”。

这些担心不是完全没有道理。

但更大的问题是：如果你一直等别人把 AI 的能力边界研究清楚，凭什么最后的劳动成果会留给你？

很多人以为自己是在保持理性。

但实际情况可能是，他用“理性怀疑”给自己找了一个不探索的理由。

比如说，有人 dis 一人公司，有人说 OpenClaw 只是为了让你烧 token，有人说 vibe coding 不能代替工程师，因为它不能长期完成复杂任务。

这些说法里当然有真实问题。

可是你要分清楚：一个判断是在帮助你更准确地使用 AI，还是在帮你合理化自己的停滞。

过去两年，AI 不是只从一个聊天机器人变成另一个聊天机器人。

它已经在变成可以开发、可以协作、可以编排 workflow、可以接入真实生产任务的节点。

如果你只在外面看争论，很容易觉得一切都还很早。

但如果你真的把任务丢进去，让不同 agent 协作，让它写脚本、整理文件、生成草稿、做质检，你会更快知道它的边界在哪里。

这个边界不是靠听别人讲出来的。

它是靠你一次一次把真实工作交给它以后摸出来的。

所以我不觉得最危险的是焦虑。

焦虑至少说明你知道世界在变。

更危险的是熟视无睹，甚至用阴谋论、专家背书、概念争议，让自己继续待在原地。

你不需要一开始就相信所有 AI 叙事。

但你至少要主动做实验：找一个真实任务，拆成几个步骤，看看 AI 到底能不能完成，哪里会错，哪里需要人类判断，哪里已经可以变成流程。

这才是真正有用的怀疑。

不是站在岸边说大象不存在，而是亲手去摸，然后记录它到底长什么样。

{tags}"""
    return body.strip()


def agent_architecture_cards(title: str) -> list[str]:
    return [
        f"{title}\nAI 工作流不是 agent 越多越高级。真正重要的是：每个节点有没有必要存在。",
        "很多人第一次设计 AI 系统，很容易上来就想四五层架构、十几个 agent。\n看起来很智能，但大概率是错误选项。",
        "因为你真正需要的，通常不是一堆 agent 开会。\n而是先找到一个明确的单点 capability。",
        "什么叫单点 capability？\n比如 PDF 转 PPT、推文转公众号、下载数据后生成文章、弹出二维码。",
        "这些能力很多在网上已经有人做过。\n先找成熟 skill 或 repo，比让 AI 从零开始造一遍更划算。",
        "多 agent 最大的问题，是上下文被无意义放大。\n每个人都要知道很多信息，但很多信息其实跟它的任务无关。",
        "比如我点“弹出二维码”，我想要的是 100% 弹出二维码。\n不是先让大模型猜测我的意图，再决定要不要展示。",
        "所以判断要不要多 agent，先问：这个任务是不是天然需要分工？每个分工有没有独立输入、输出和验收标准？",
        "如果没有，单 agent 加明确工具，往往比多 agent 更稳。\n复杂系统不是为了看起来复杂，而是为了减少摩擦。",
        "AI 架构的第一原则：先找单点能力，再接工作流；先证明必要性，再增加 agent。",
    ]


def agent_architecture_body(title: str, brief: dict) -> str:
    tags = " ".join(f"#{tag}" for tag in (brief.get("search_keywords") or ["AI Agent", "工作流", "自动化", "Agent架构"])[:6])
    body = f"""{title}。

很多人一开始设计 AI 工作流，很容易犯一个错误：上来就把系统想得特别复杂。

公司架构四五层，每层四五个人；AI 架构也照着来，十个 agent、二十个 agent，每个 agent 负责一个环节。

这件事看起来很高级，但很多时候是错误选项。

因为 AI 系统的目标不是“看起来像公司”，而是更稳定、更低成本地完成任务。

你真正要找的，通常不是一堆 agent 开会，而是一个明确的单点 capability。

比如 PDF 转 PPT 是一个 skill。

把推文改成公众号，是一个 skill。

把下载好的数据整理成文章，也是一个 skill。

这些单点能力，很多在网上已经有人做得很成熟。你要先判断：这个能力是不是已经有现成方案，而不是默认让 AI 从零造一遍。

很多 AI 的 default 路径，是自己开发所有东西。

但人的判断要补上：这件事值得自己做吗？网上有没有成熟 repo？有没有别人已经 star 过、用过、验证过的工具？

多 agent 还有一个很大的成本：上下文会被无意义放大。

每个 agent 都要知道一堆信息，但很多信息对它的任务没有意义。上下文越大，成本越高，错误空间也越大。

比如我点一个按钮，想要 100% 弹出二维码。

这件事就不需要大模型先判断“用户是不是想看二维码”。它应该是一个确定动作，而不是一个智能推理任务。

所以判断要不要多 agent，先问三个问题：

第一，这个任务是不是天然需要分工？

第二，每个分工有没有清楚的输入、输出和验收标准？

第三，多一个 agent，是真的减少摩擦，还是只是让架构看起来更像 AI？

如果这三个问题答不清楚，先不要多 agent。

先找单点能力，先接进工作流，先跑通一条稳定链路。

复杂系统不是为了炫技，而是为了减少长期摩擦。

AI 架构的第一原则不是“多”，而是“必要”。

{tags}"""
    return body.strip()


def infer_keywords(text: str) -> list[str]:
    candidates = [
        "AI",
        "AI视频",
        "Remotion",
        "AI Agent",
        "Token",
        "交易",
        "明牌",
        "石油",
        "战争",
        "风险管理",
        "预期差",
        "第一性原理",
        "结果倒推",
        "决策框架",
        "赚钱思维",
        "个人成长",
        "认知框架",
        "工作流",
        "自我迭代",
        "内容创作",
        "小红书",
        "自媒体",
        "一人公司",
        "内容复用",
        "复利",
        "专注",
        "贪多",
        "样本",
    ]
    out = [item for item in candidates if item in text]
    return out[:5] or ["认知框架", "个人成长"]


def deterministic_note_brief(title: str, source_text: str, kind: str | None = None) -> dict:
    keywords = infer_keywords(f"{title}\n{source_text}")
    kind = kind or template_kind(source_text)
    if kind == "ai_adoption_mindset":
        keywords = prioritize_keywords(["AI", "AI边界", "主动探索", "一人公司"], keywords)
        return {
            "search_keywords": keywords or ["AI", "一人公司", "AI时代"],
            "search_intent": "AI 认知差、AI 能力边界、一人公司和主动探索",
            "target_reader": "看到 AI 争议很多、还在等别人证明结论的人",
            "core_claim": title,
            "cognitive_conflict": "很多人以为自己在理性怀疑，实际是在用怀疑合理化不探索。",
            "source_evidence": sentence_fragments(source_text)[:3],
            "reader_payoff": "学会把对 AI 的怀疑变成主动实验，而不是停留在观望和否定。",
            "format_rationale": "适合做搜索型知识图文；用户会搜索 AI 边界、一人公司、AI 是否值得学。",
            "card_chain": ["封面", "盲人摸象", "能力边界", "阴谋论", "AI变化", "主动实验", "收束"],
        }
    if kind == "agent_architecture":
        keywords = prioritize_keywords(["AI Agent", "多Agent", "工作流", "Agent架构"], keywords)
        return {
            "search_keywords": keywords or ["AI Agent", "工作流", "多Agent"],
            "search_intent": "AI Agent 架构、多 agent 取舍、工作流设计和 skill 复用",
            "target_reader": "正在设计 AI 工作流，但容易把系统做复杂的人",
            "core_claim": title,
            "cognitive_conflict": "很多人以为 agent 越多越高级，实际先要证明每个节点是否必要。",
            "source_evidence": sentence_fragments(source_text)[:3],
            "reader_payoff": "学会先找单点能力，再决定是否需要多 agent 和复杂架构。",
            "format_rationale": "适合做搜索型知识图文；主题本身是 AI 工作流架构判断，不适合逐字贴稿。",
            "card_chain": ["封面", "误区", "单点能力", "现成工具", "上下文成本", "二维码例子", "三问", "收束"],
        }
    if kind == "focus_ant_theory":
        keywords = prioritize_keywords(["贪多", "专注", "个人成长", "复利"], keywords)
        return {
            "search_keywords": keywords,
            "search_intent": "专注、个人成长、聪明人贪多、长期复利",
            "target_reader": "能力强但方向很多、每个机会都想抓住的人",
            "core_claim": title,
            "cognitive_conflict": "聪明人容易把“我能做”误解成“我应该做”，最后因为贪多破坏复利。",
            "source_evidence": sentence_fragments(source_text)[:3],
            "reader_payoff": "学会用主线判断机会，减少横跳，把能力放进能复利的方向。",
            "format_rationale": "适合做搜索型知识图文，不适合直接贴 transcript；卡片要围绕专注和贪多的认知冲突推进。",
            "card_chain": ["封面", "蚂蚁理论", "聪明人的误区", "交易/人生例子", "复利逻辑", "机会判断", "收束"],
        }
    if kind == "decision_framework":
        keywords = prioritize_keywords(["结果倒推", "第一性原理", "决策框架", "样本"], keywords)
        return {
            "search_keywords": keywords,
            "search_intent": "第一性原理、交易复盘、决策框架、样本判断",
            "target_reader": "做交易、用 AI 或做复杂决策时，容易被单次结果影响判断的人",
            "core_claim": title,
            "cognitive_conflict": "很多人用一次结果倒推决策对错，实际可能只是随机性，不是因果关系。",
            "source_evidence": sentence_fragments(source_text)[:3],
            "reader_payoff": "学会区分结果、样本和因果，不被单次成败牵着改系统。",
            "format_rationale": "适合做轻 PPT 化知识卡：用概念层级和例子解释，不做逐字稿截图。",
            "card_chain": ["封面", "误区", "因果/样本", "第一性原理", "交易例子", "AI例子", "复盘方法", "收束"],
        }
    if kind == "ai_visual_workflow":
        keywords = prioritize_keywords(["AI视频", "Remotion", "视觉化", "内容创作"], keywords)
        return {
            "search_keywords": keywords,
            "search_intent": "AI视频、Remotion、内容创作、视觉化工作流",
            "target_reader": "想用 AI 做视频、图文或知识内容，但还停留在剪辑工具层面的人",
            "core_claim": title,
            "cognitive_conflict": "AI 视频的重点不是炫技剪辑，而是把抽象表达翻译成观众能看懂的视觉结构。",
            "source_evidence": sentence_fragments(source_text)[:3],
            "reader_payoff": "理解 AI 视频工作流的核心价值：自动判断哪里需要图、表、时间线或流程。",
            "format_rationale": "适合做轻 PPT 化图文，因为主题本身是视觉化表达；但卡片仍要服务搜索和收藏。",
            "card_chain": ["封面", "误区", "Remotion价值", "旧流程痛点", "AI判断", "分工变化", "规则沉淀", "收束"],
        }
    if kind == "agent_cost_analysis":
        keywords = prioritize_keywords(["AI Agent", "Token", "工作流", "返工率"], keywords)
        return {
            "search_keywords": keywords or ["AI Agent", "Token", "工作流"],
            "search_intent": "AI Agent 对比、token 成本、coding agent 选择和工作流评估",
            "target_reader": "正在比较 Codex、Claude、Gemini 等 AI 编程工具，并想把它们用于真实生产的人",
            "core_claim": title,
            "cognitive_conflict": "很多人只看 agent 聪不聪明，实际更应该看成本、返工率、稳定性和可复用性。",
            "source_evidence": sentence_fragments(source_text)[:3],
            "reader_payoff": "学会用生产指标而不是一次演示结果来判断 AI Agent 是否值得长期使用。",
            "format_rationale": "适合做搜索型知识图文；用户会搜索 AI Agent 对比、token 消耗、Codex/Claude/Gemini 选择。",
            "card_chain": ["封面", "误区", "听话程度", "token成本", "返工率", "测试指标", "workflow价值", "收束"],
        }
    if "交易" in keywords or "石油" in source_text or "战争" in source_text:
        keywords = prioritize_keywords(["交易", "明牌", "预期差", "石油"], keywords)
        return {
            "search_keywords": keywords,
            "search_intent": "交易复盘、风险管理、预期差判断",
            "target_reader": "做交易或关注资产价格，但容易被碎片信息带着走的人",
            "core_claim": title,
            "cognitive_conflict": "很多人以为自己缺信息，实际是没有先找出主导变量。",
            "source_evidence": sentence_fragments(source_text)[:3],
            "reader_payoff": "学会先找出当下最大的变量，再判断市场预期和真实变化之间的差。",
            "format_rationale": "适合做搜索型知识图文；封面负责关键词和反差，正文负责交易逻辑。",
            "card_chain": ["封面", "误区", "房间里的大象", "战争例子", "primary/secondary", "预期差", "操作边界", "收束"],
        }
    if is_content_business_case(source_text):
        keywords = prioritize_keywords(["小红书", "内容复用", "自媒体", "内容工作流"], keywords)
        return {
            "search_keywords": keywords,
            "search_intent": "小红书运营、内容复用、自媒体生产流程",
            "target_reader": "想把短视频内容复用到小红书、公众号和 X 的内容创作者",
            "core_claim": title,
            "cognitive_conflict": "很多人以为内容复用就是搬运，实际要先把内容拆成可搜索的产品单元。",
            "source_evidence": sentence_fragments(source_text)[:3],
            "reader_payoff": "学会把一条视频拆成多个可发布、可质检、可复用的内容资产。",
            "format_rationale": "适合做搜索型知识图文；不是 PPT 汇报，而是内容生产方法论卡片。",
            "card_chain": ["封面", "误区", "搜索意图", "主题拆分", "卡片脚本", "文件结构", "SOP", "收束"],
        }
    if is_ai_workflow_case(source_text) or "AI" in keywords:
        keywords = prioritize_keywords(["AI", "工作流", "SOP", "自动化"], keywords)
        return {
            "search_keywords": keywords,
            "search_intent": "AI时代、工作流升级、个人成长",
            "target_reader": "正在用 AI 工具，但还停留在技巧和工具清单层面的人",
            "core_claim": title,
            "cognitive_conflict": "很多人以为会用工具就够了，实际更重要的是升级判断框架。",
            "source_evidence": sentence_fragments(source_text)[:3],
            "reader_payoff": "把具体工具使用，升级成一套可复用的工作和判断方式。",
            "format_rationale": "适合做轻 PPT 化知识卡；每张卡推进一个工作流判断。",
            "card_chain": ["封面", "误区", "工作流定义", "内容生产例子", "护城河", "SOP", "检查问题", "收束"],
        }
    if is_life_choice_case(source_text):
        keywords = prioritize_keywords(["个人成长", "专注", "复利", "判断力"], keywords)
        return {
            "search_keywords": keywords,
            "search_intent": "个人成长、职业选择、长期主义和复利",
            "target_reader": "很努力但不确定自己方向是否正确的人",
            "core_claim": title,
            "cognitive_conflict": "很多人以为努力本身会带来结果，实际更重要的是方向和判断。",
            "source_evidence": sentence_fragments(source_text)[:3],
            "reader_payoff": "学会判断自己投入的事情是在复利，还是只是在消耗时间。",
            "format_rationale": "适合做搜索型个人成长图文；用观点链条承接，不直接搬运口播。",
            "card_chain": ["封面", "误区", "方向", "判断", "复利", "专注", "行动问题", "收束"],
        }
    return {
        "search_keywords": keywords,
        "search_intent": "认知框架、个人成长、决策复盘",
        "target_reader": "想把复杂问题想清楚，并形成稳定行动判断的人",
        "core_claim": title,
        "cognitive_conflict": "普通人容易把表面动作当成核心问题。",
        "source_evidence": sentence_fragments(source_text)[:3],
        "reader_payoff": "带走一个可复盘、可收藏、能反复使用的判断框架。",
        "format_rationale": "适合做搜索型知识图文；卡片要比 transcript 更结构化。",
        "card_chain": ["封面", "误区", "重构", "论证", "例子", "方法", "边界", "收束"],
    }


def deterministic_cards(title: str, source_text: str, brief: dict, kind: str | None = None) -> list[str]:
    kind = kind or template_kind(source_text)
    if kind == "ai_adoption_mindset":
        return ai_adoption_mindset_cards(title)
    if kind == "agent_architecture":
        return agent_architecture_cards(title)
    if kind == "focus_ant_theory":
        return focus_ant_cards(title)
    if kind == "decision_framework":
        return decision_framework_cards(title)
    if kind == "ai_visual_workflow":
        return ai_visual_workflow_cards(title)
    if kind == "agent_cost_analysis":
        return agent_cost_cards(title)
    if kind == "trading_expectation":
        return trading_expectation_cards(title)
    if kind == "content_business":
        return content_business_cards(title)
    if kind == "ai_workflow":
        return ai_workflow_cards(title)
    if kind == "life_choice":
        return life_choice_cards(title)
    fragments = sentence_fragments(clean_oral_text(source_text))
    conflict = brief.get("cognitive_conflict") or ""
    keywords = brief.get("search_keywords") or []
    keyword = str(keywords[0]) if keywords else ""
    cards = [
        card_script_line(title, conflict or "这篇只解决一个问题：普通人到底错在哪里。", keyword=keyword, limit=190),
    ]
    if conflict:
        cards.append(card_script_line("误区", f"很多人卡住，不是因为不努力，而是因为一开始就问错了问题。{conflict}", limit=210))
    evidence = brief.get("source_evidence") or fragments[:3]
    for idx, item in enumerate(evidence, start=1):
        cards.append(card_script_line(f"来源证据 {idx}", item, limit=210))
    keyword_cards = []
    if any(word in source_text for word in ["战争", "石油", "黄金", "风险资产"]):
        keyword_cards.extend(
            [
                "先找房间里的大象\n这一阶段真正主导资产重定价的变量是什么？先回答这个，再看技术位。",
                "不要用 secondary 问题替代 primary 问题\n板块轮动、技术位置都要服从最大变量。",
                "交易赚的不是新闻本身\n交易赚的是预期差：真实发生的事，和市场以为会发生的事之间的差。",
            ]
        )
    if any(word in source_text for word in ["AI", "工具", "工作流"]):
        keyword_cards.extend(
            [
                "AI 不是多一个工具\n它会改变你判断、生产和分发内容的整套工作流。",
                "不要只问工具怎么用\n先问这个工具改变了哪一个关键环节，再决定要不要沉淀成 SOP。",
            ]
        )
    cards.extend(keyword_cards)
    cards.append("最后只问一个问题\n我现在做的，是最重要的变量，还是看起来很聪明的噪音？")

    cleaned: list[str] = []
    seen: set[str] = set()
    for card in cards:
        card = card_line(card, 220)
        if chinese_len(card) < 24 or card in seen:
            continue
        seen.add(card)
        cleaned.append(card)
        if len(cleaned) >= 10:
            break
    while len(cleaned) < 7 and fragments:
        cleaned.append(card_line(fragments[len(cleaned) % len(fragments)], 120))
    return cleaned[:10]


def deterministic_body(title: str, source_text: str, brief: dict, kind: str | None = None) -> str:
    kind = kind or template_kind(source_text)
    if kind == "ai_adoption_mindset":
        return ai_adoption_mindset_body(title, brief)
    if kind == "agent_architecture":
        return agent_architecture_body(title, brief)
    if kind == "focus_ant_theory":
        return focus_ant_body(title, brief)
    if kind == "decision_framework":
        return decision_framework_body(title, brief)
    if kind == "ai_visual_workflow":
        return ai_visual_workflow_body(title, brief)
    if kind == "agent_cost_analysis":
        return agent_cost_body(title, brief)
    if kind == "trading_expectation":
        return trading_expectation_body(title, brief)
    if kind == "content_business":
        return content_business_body(title, brief)
    if kind == "ai_workflow":
        return ai_workflow_body(title, brief)
    if kind == "life_choice":
        return life_choice_body(title, brief)
    fragments = sentence_fragments(clean_oral_text(source_text))
    paragraphs = [
        f"{title}，这件事看起来很简单，但正因为简单，很多人反而不愿意信。",
        str(brief.get("cognitive_conflict") or ""),
    ]
    paragraphs.extend(card_line(item, 120) for item in fragments[:14])
    paragraphs.append(str(brief.get("reader_payoff") or "这不是一句口号，而是一套可以反复检查自己的判断框架。"))
    tags = " ".join(f"#{tag}" for tag in (brief.get("search_keywords") or [])[:6])
    body = "\n\n".join(item for item in paragraphs if item).strip()
    if tags:
        body = f"{body}\n\n{tags}"
    return body


def deterministic_polish(record: dict) -> dict:
    topic_text, source_text, _combined = record_context(record)
    # Classify a Xiaohongshu note from its selected topic unit, not the whole
    # source transcript. One Douyin video can produce several independent
    # notes; using the full transcript here makes every child note collapse into
    # the dominant topic of the parent video.
    kind = template_kind(f"{topic_text}\n{source_text}")
    title = shorten_title(planned_title(record, kind))
    brief = deterministic_note_brief(title, source_text, kind)
    brief = align_keywords_to_title(title, brief)
    cards = deterministic_cards(title, source_text, brief, kind)
    cards = enrich_cards(cards, kind, source_text, brief)
    return {
        "title": title,
        "note_brief": brief,
        "body": deterministic_body(title, source_text, brief, kind),
        "image_cards": cards,
        "card_plan": card_plan(cards, kind),
        "xhs_format": {
            "format": "search_knowledge_cards",
            "visual_mode": "light_ppt_text_cards",
            "source_policy": "organized transcript is source; image_cards are rewritten card scripts, not transcript chunks",
            "best_for": "Xiaohongshu search, saves, and review before draft push",
        },
        "quality_notes": ["claude structured output failed; used local search-card workflow fallback"],
        "polish_engine": "local-search-card-v2",
        "template_kind": kind,
    }


def validate_polished(polished: dict) -> None:
    if not isinstance(polished, dict):
        raise ValueError("polish output is not an object")
    if not str(polished.get("title") or "").strip():
        raise ValueError("missing title")
    if not isinstance(polished.get("note_brief"), dict) or not polished["note_brief"].get("core_claim"):
        raise ValueError("missing note_brief.core_claim")
    if chinese_len(str(polished.get("body") or "")) < 500:
        raise ValueError("body too short")
    cards = polished.get("image_cards") or []
    if not isinstance(cards, list) or len([card for card in cards if str(card).strip()]) < 7:
        raise ValueError("not enough image_cards")


def polish_with_claude(record: dict) -> dict:
    source_excerpt = str(record.get("source_excerpt") or record.get("body") or "")
    prompt = f"""来源视频标题：{record.get("source_unit_title") or record.get("title")}
来源抖音：{record.get("source_url")}
当前草稿标题：{record.get("title")}
当前草稿正文：
{str(record.get("body") or "")[:3000]}

source_excerpt:
{source_excerpt[:9000]}

请重写成一篇真正可发布的小红书图文笔记文字层。

输出前请自检：
- 标题是否有明确冲突或判断？
- 正文是否有“主张 -> 误区 -> 推理 -> 例子 -> 行动”的顺序？
- 图片卡片连起来是否像一篇完整文章，而不是零散金句？
- 有没有只根据标题发挥？如果 source_excerpt 不足，请明确保守处理，不要编造。
"""
    result = subprocess.run(
        [
            "claude",
            "-p",
            "--model",
            "sonnet",
            "--max-budget-usd",
            "0.80",
            "--output-format",
            "json",
            "--no-session-persistence",
            "--json-schema",
            JSON_SCHEMA,
            "--system-prompt",
            SYSTEM_PROMPT,
            prompt,
        ],
        text=True,
        capture_output=True,
        timeout=240,
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout).strip())
    if not result.stdout.strip():
        raise RuntimeError(f"empty claude stdout: {(result.stderr or '').strip()[:500]}")
    try:
        polished = extract_json(result.stdout)
    except Exception:
        try:
            polished = extract_markdown_output(result.stdout)
            return polished
        except Exception:
            pass
        debug_dir = ROOT / "work/content-ops/.runs/debug/xiaohongshu-polish"
        debug_dir.mkdir(parents=True, exist_ok=True)
        debug_path = debug_dir / f"claude-output-{datetime.now().strftime('%Y%m%d%H%M%S')}.txt"
        debug_path.write_text(result.stdout + "\n\n--- STDERR ---\n" + (result.stderr or ""), encoding="utf-8")
        raise RuntimeError(f"invalid claude json; saved={debug_path}")
    validate_polished(polished)
    return polished


def shorten_title(title: str) -> str:
    title = re.sub(r"^[>#\\-\\s]+", "", title or "")
    title = re.sub(r"[*_`「」\"“”]", "", title)
    title = clean_platform_suffix(title)
    title = re.sub(r"\s+", "", title).strip()
    replacements = [
        ("有了仓位就没有理智，所以止损要提前设", "有仓位前先设止损"),
        ("底层框架决定你的上限", "底层框架决定上限"),
        ("用AI别憋完美问题", "用AI别憋完美问题"),
        ("100件事99件不赚钱", "100件事99件不赚钱"),
    ]
    for old, new in replacements:
        if title == old:
            return new
    return title[:20]


def clean_platform_suffix(text: str) -> str:
    text = text or ""
    # Draft filenames include suffixes like --xiaohongshu-596096-02. Strip
    # them before title truncation; otherwise the 20-char title limit can turn
    # the platform slug into visible garbage such as "--xiaohong".
    text = re.sub(r"--xiaohongshu-[^-]+-\d+(?=$|[^\d])", "", text)
    text = re.sub(r"--xiaohongshu-\d+(?=$|[^\d])", "", text)
    text = re.sub(r"--xiaohongshu(?:-[^-\\s，。；;：:、]*)?", "", text)
    text = re.sub(r"--xiaohon\w*", "", text)
    text = re.sub(r"--xiaohong\w*", "", text)
    return text.strip()


def draft_topic_from_filename(name: str) -> str:
    stem = Path(name).stem
    stem = re.sub(r"^\d{4}-\d{2}-\d{2}--", "", stem)
    stem = clean_platform_suffix(stem)
    stem = stem.replace("｜", "|")
    stem = re.sub(r"\|拆条\d+$", "", stem)
    return shorten_title(stem)


def clean_body(body: str) -> str:
    body = re.sub(r"^（可直接发布）\\s*", "", body or "").strip()
    body = body.replace("`#", "#").replace("`", "")
    return body


def write_markdown(md_path: Path, record: dict) -> None:
    cards = record.get("image_cards") or []
    brief = record.get("note_brief") or {}
    lines = [
        "---",
        "platform: xiaohongshu",
        f"status: {record.get('status') or 'draft'}",
        f"intended_publish_at: {record.get('intended_publish_at') or ''}",
        f"local_id: {record.get('local_id') or ''}",
        "source_platform: douyin",
        f"source_content_id: {record.get('source_content_id') or ''}",
        f"source_url: {record.get('source_url') or ''}",
        "review_required: true",
        "---",
        "",
        f"# {record.get('title') or ''}",
        "",
        "## 小红书 Note Brief",
        "",
        f"- 搜索关键词：{'、'.join(brief.get('search_keywords') or [])}",
        f"- 搜索意图：{brief.get('search_intent') or ''}",
        f"- 目标读者：{brief.get('target_reader') or ''}",
        f"- 核心主张：{brief.get('core_claim') or ''}",
        f"- 认知冲突：{brief.get('cognitive_conflict') or ''}",
        f"- 读者收益：{brief.get('reader_payoff') or ''}",
        f"- 图文形态：{(record.get('xhs_format') or {}).get('visual_mode') or 'light_ppt_text_cards'}",
        f"- 形态理由：{brief.get('format_rationale') or ''}",
        "",
        "### 来源证据",
        "",
    ]
    lines.extend(f"- {item}" for item in brief.get("source_evidence") or [])
    lines.extend(
        [
            "",
        "## 发布正文",
        "",
        record.get("body") or "",
        "",
        "## 图文卡片文案",
        "",
        ]
    )
    plan_by_index = {
        int(item.get("index") or 0): item
        for item in record.get("card_plan") or []
        if isinstance(item, dict)
    }
    for idx, card in enumerate(cards, start=1):
        plan = plan_by_index.get(idx) or {}
        prefix = f"{idx}. "
        if plan.get("purpose"):
            prefix += f"【{plan.get('purpose')}】"
        lines.append(f"{prefix}{card}")
    if record.get("source_excerpt"):
        lines.extend(["", "## 来源片段", "", str(record.get("source_excerpt") or "")])
    md_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def polish_one(json_path: Path, force: bool = False, engine: str = "auto") -> dict:
    record = load_json(json_path)
    if not record:
        return {"path": str(json_path), "status": "bad_json"}
    if record.get("polish_engine") and not force:
        return {"path": str(json_path), "status": "exists", "title": record.get("title"), "cards": len(record.get("image_cards") or [])}
    record["_draft_file_topic"] = draft_topic_from_filename(json_path.name)
    if engine == "local":
        raise ValueError("local polish engine is disabled for production Xiaohongshu copy")
    polished = polish_with_claude(record)
    polish_engine = "claude-sonnet"
    record["title"] = shorten_title(str(polished.get("title") or record.get("title") or "").strip())
    record["body"] = clean_body(str(polished.get("body") or record.get("body") or "").strip())
    record["note_brief"] = polished.get("note_brief") or record.get("note_brief") or {}
    record["image_cards"] = [str(card).strip() for card in polished.get("image_cards") or [] if str(card).strip()]
    record["card_plan"] = polished.get("card_plan") or card_plan(record["image_cards"], polished.get("template_kind") or "")
    record["xhs_format"] = polished.get("xhs_format") or {
        "format": "search_knowledge_cards",
        "visual_mode": "light_ppt_text_cards",
        "source_policy": "image_cards are rewritten card scripts, not transcript chunks",
    }
    record["quality_notes"] = polished.get("quality_notes") or []
    record["template_kind"] = polished.get("template_kind") or template_kind(record_context(record)[2])
    record.pop("_draft_file_topic", None)
    validate_polished(record)
    record["status"] = "draft_ready"
    record["polished_at"] = datetime.now().isoformat(timespec="seconds")
    record["polish_engine"] = polish_engine
    record["xhs_workflow_version"] = "search-card-v2"
    write_json(json_path, record)
    write_markdown(json_path.with_suffix(".md"), record)
    return {"path": str(json_path), "status": "polished", "title": record["title"], "cards": len(record["image_cards"])}


def main() -> None:
    parser = argparse.ArgumentParser(description="Polish Xiaohongshu text drafts into publishable notes.")
    parser.add_argument("draft", nargs="?", help="Optional Xiaohongshu draft JSON path.")
    parser.add_argument("--source-content-id")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--engine", choices=["auto", "claude"], default="auto")
    args = parser.parse_args()

    if args.draft:
        paths = [Path(args.draft).expanduser()]
    else:
        paths = sorted(DRAFT_DIR.glob("*.json"))
    if args.source_content_id and not args.draft:
        paths = [p for p in paths if load_json(p).get("source_content_id") == args.source_content_id]
    if args.limit:
        paths = paths[: args.limit]

    report = []
    for path in paths:
        print(f"polishing={path.name}", flush=True)
        try:
            row = polish_one(path, args.force, args.engine)
        except Exception as exc:
            row = {"path": str(path), "status": "failed", "error": str(exc)[:500]}
        report.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)

    report_path = ROOT / "work/content-ops/.runs/reports/xiaohongshu-polish-report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(report_path, {"generated_at": datetime.now().isoformat(timespec="seconds"), "items": report})
    print(f"wrote={report_path}")


if __name__ == "__main__":
    main()
