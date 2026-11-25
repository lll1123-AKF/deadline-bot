"""通知解析器：把一段中文通知变成结构化任务。

提供两种模式：
  rule  —— 纯正则规则，零依赖、离线可用（默认，demo 用这个）
  llm   —— 调用 OpenAI-compatible 接口，适合长文本和复杂表达

面试时最值得讲的就是这个文件：日期抽取是 agent 从「文本」走向「可执行任务」
的第一步，规则版解决 80% 常见表达，LLM 版兜住长尾。

另外支持「一条通知里含多个事项」的拆分（编号清单 / 多行清单），
这是真实场景里最常见的输入形式，例如教务处一次发 4 个作业截止日。
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from typing import Optional

from .models import Task, new_id

WEEKDAYS = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}

CATEGORY_KEYWORDS = [
    ("作业", ["作业", "习题", "论文", "小测"]),
    ("考试", ["考试", "测验", "月考", "期末", "quiz"]),
    ("资料提交", ["提交", "上交", "材料", "资料", "表格", "申请表", "报名", "登记表", "报告"]),
    ("会议", ["会议", "开会", "例会", "培训", "讲座", "班会"]),
    ("审批", ["审批", "报销", "申请", "盖章", "签字"]),
    ("汇报", ["周报", "日报", "月报", "报表", "汇报", "总结"]),
]

SOURCE_PATTERNS = [
    r"(教务处|学生处|班主任|辅导员|学院|学校|系里|班委)",
    r"(人力资源部|HR|人事部|行政部|财务部|部门|主管|领导|项目组|HRBP)",
]


# --------------------------------------------------------------------------
# 日期时间解析
# --------------------------------------------------------------------------

def _combine(day: datetime, hour: int, minute: int) -> datetime:
    return day.replace(hour=hour, minute=minute, second=0, microsecond=0)


def _apply_clock(day: datetime, clock_text: str, default_hour: int = 23, default_minute: int = 59) -> datetime:
    """把「下午5点」「18:30」「下班前」这样的时间片段贴到日期上。"""
    text = clock_text.strip()
    hour, minute = default_hour, default_minute
    if "下班前" in text:
        hour, minute = 18, 0
    elif "中午" in text:
        hour, minute = 12, 0
    m = re.search(r"(\d{1,2})\s*[:：]\s*(\d{2})", text)
    if m:
        hour, minute = int(m.group(1)), int(m.group(2))
    else:
        m = re.search(r"(\d{1,2})\s*[点时]", text)
        if m:
            hour = int(m.group(1))
            m2 = re.search(r"[点时]\s*(\d{1,2})\s*分?", text)
            minute = int(m2.group(1)) if m2 else 0
    if "下午" in text or "晚上" in text or "傍晚" in text:
        if hour < 12:
            hour += 12
    elif "上午" in text or "早上" in text:
        if hour == 12:
            hour = 0
    return _combine(day, hour, minute)


def parse_due(text: str, now: Optional[datetime] = None) -> tuple[Optional[datetime], str]:
    """从通知文本中解析截止时间，返回 (datetime, 命中的原文片段)。

    支持的表达：
      2026-11-30 / 2026年11月30日 / 11月30日 / 11/30
      今天 / 明天 / 后天 / 大后天
      本周五 / 下周一 / 周五 / 星期三
      3天内 / 5天后 / 一周内 / 两周内
      月底前 / 本月底
    """
    now = now or datetime.now()
    matches: list[tuple[datetime, str, int]] = []  # (结果, 原文, 优先级)

    # 完整年月日 / 标准日期
    for m in re.finditer(r"(20\d{2})\s*[年\-/\.]\s*(\d{1,2})\s*[月\-/\.]\s*(\d{1,2})\s*日?", text):
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            day = now.replace(year=y, month=mo, day=d)
            whole = m.group(0)
            tail = text[m.end():m.end() + 12]
            matches.append((_apply_clock(day, m.group(0) + tail, 23, 59), whole, 100))
        except ValueError:
            pass

    # 月日（无年份，按今年算；若已过去则按明年）
    for m in re.finditer(r"(?<!\d)(\d{1,2})\s*月\s*(\d{1,2})\s*日?(?!\d)", text):
        mo, d = int(m.group(1)), int(m.group(2))
        try:
            day = now.replace(month=mo, day=d)
            if day < now.replace(hour=0, minute=0, second=0, microsecond=0):
                day = day.replace(year=day.year + 1)
            tail = text[m.end():m.end() + 12]
            matches.append((_apply_clock(day, m.group(0) + tail, 23, 59), m.group(0), 90))
        except ValueError:
            pass

    # 今天 / 明天 / 后天 / 大后天
    rel = {"今天": 0, "当日": 0, "明日": 1, "明天": 1, "后天": 2, "大后天": 3}
    for word, offset in rel.items():
        for m in re.finditer(word, text):
            day = now + timedelta(days=offset)
            tail = text[m.end():m.end() + 14]
            matches.append((_apply_clock(day, word + tail, 18, 0), m.group(0), 80))

    # 本周X / 下周X / 周X / 星期X
    week_re = r"(本|下|下下)?\s*(周|星期|礼拜)\s*([一二三四五六日天])"
    for m in re.finditer(week_re, text):
        prefix, _, cn = m.group(1), m.group(2), m.group(3)
        target = WEEKDAYS[cn]
        monday = now - timedelta(days=now.weekday())
        offset = 7 * (2 if prefix == "下下" else 1 if prefix == "下" else 0)
        day = monday + timedelta(days=target + offset)
        tail = text[m.end():m.end() + 12]
        matches.append((_apply_clock(day, m.group(0) + tail, 18, 0), m.group(0), 70))

    # N天内 / N天后 / N周内
    for m in re.finditer(r"(\d+|[一二三四五六七八九十两])\s*(天|周|个?星期)\s*(内|后|之前?)", text):
        num_cn = m.group(1)
        num = int(num_cn) if num_cn.isdigit() else {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}.get(num_cn, 1)
        unit = 7 if ("周" in m.group(2) or "星期" in m.group(2)) else 1
        day = now + timedelta(days=num * unit)
        matches.append((day.replace(second=0, microsecond=0), m.group(0), 60))

    # 月底 / 本月底
    for m in re.finditer(r"(本?月底|月末)", text):
        if now.month == 12:
            day = now.replace(month=12, day=31)
        else:
            day = now.replace(month=now.month + 1, day=1) - timedelta(days=1)
        matches.append((_apply_clock(day, m.group(0), 23, 59), m.group(0), 50))

    if not matches:
        return None, ""

    # 优先级高的胜出；同优先级取文本中更早出现的（matches 已按出现顺序）
    matches.sort(key=lambda item: (-item[2], text.find(item[1])))
    due, raw, _ = matches[0]
    return due, raw


# --------------------------------------------------------------------------
# 多任务拆分
# --------------------------------------------------------------------------

# 「1.」「1、」「1)」「（1）」「一、」等编号标记。标记前的换行/分号属于分隔符，
# 会被消耗掉，因此切片时上一段自然截止在分隔符之前。
_ITEM_MARKER = re.compile(
    r"(?:^|[\n;；，,、:：])\s*(?:"
    r"\d{1,2}\s*[.、．)）:：](?!\d)"   # (?!\d) 避免把「12:30」当成编号
    r"|[一二三四五六七八九十]{1,3}\s*[、.．]"
    r"|[（(]\s*\d{1,2}\s*[)）]"
    r")\s*"
)

_ACTION_HINT = re.compile(r"(交|提交|完成|参加|报销|填写|截止|前|月|日|周)")


def split_notices(text: str) -> list[str]:
    """把一条含多个事项的通知拆成独立条目。

    支持「1. xxx; 2. xxx」「一、xxx 二、xxx」以及无编号的多行清单。
    编号可以跟在行首、分号、逗号、顿号或冒号后——真实通知经常写成
    「帮我记一下：1. xxx；2. xxx」这种单行形式，首个条目前有引导语。
    引导语本身不是任务，会被丢弃；只有识别到 >= 2 个条目才拆，
    否则原样返回。这是「不确定就别乱拆」原则：宁可少拆，也不要切碎。
    """
    if not text:
        return []
    cleaned = text.strip()

    markers = list(_ITEM_MARKER.finditer(cleaned))
    if len(markers) >= 2:
        items: list[str] = []
        for i, m in enumerate(markers):
            end = markers[i + 1].start() if i + 1 < len(markers) else len(cleaned)
            chunk = cleaned[m.end():end].strip(" \n\t;；，,")
            if chunk:
                items.append(chunk)
        if items:
            return items

    lines = [ln.strip(" \t;；，,") for ln in cleaned.splitlines() if ln.strip()]
    if len(lines) >= 2 and sum(1 for ln in lines if _ACTION_HINT.search(ln)) >= 2:
        if len(lines[0]) <= 8 and lines[0].rstrip("：:") in ("注意", "通知", "提醒", "各位同学", "各位同事"):
            lines = lines[1:]
        return lines or [cleaned]

    return [cleaned]


# --------------------------------------------------------------------------
# 标题 / 来源 / 类别
# --------------------------------------------------------------------------

_WEEK_TAG = re.compile(r"第?\s*\d{1,2}\s*周(?:次)?")          # 教学周次，不是「N周内」
_EMPTY_PAREN = re.compile(r"[（(]\s*[)）]")                     # 日期被摘走后留下的空括号
_TAIL_BEFORE = re.compile(r"(?:截止)?\s*前\s*(?:交|提交|完成|上交|报送|上传|寄出)?\s*[;；，,。]?\s*$")
_TAIL_VERB = re.compile(r"(?:交|提交|完成)\s*[;；，,。]?\s*$")


def _clean_title(text: str, date_raw: str) -> str:
    cleaned = text.replace(date_raw, " ") if date_raw else text
    # 编号前缀 / 来源前缀 / 称呼
    cleaned = re.sub(r"^\s*\d{1,2}\s*[.、．)）]\s*", "", cleaned)
    cleaned = re.sub(r"^[\u4e00-\u9fa5A-Za-z]{2,10}(通知|提醒|公告)\s*[:：]\s*", "", cleaned)
    cleaned = re.sub(r"^(各位同学|同学们|大家好|各位同事|【[^】]*】|注意)\s*[:：]?\s*", " ", cleaned)
    # 时间附件：具体钟点
    cleaned = re.sub(r"(上午|下午|晚上|中午)?\s*\d{1,2}\s*[:点时]\s*\d{0,2}\s*分?(前|之前)?", " ", cleaned)
    # 教学周次、空括号、尾部「前交」「前提交」
    cleaned = _WEEK_TAG.sub(" ", cleaned)
    cleaned = _EMPTY_PAREN.sub(" ", cleaned)
    cleaned = _TAIL_BEFORE.sub(" ", cleaned)
    cleaned = _TAIL_VERB.sub(" ", cleaned)
    cleaned = re.sub(r"^\s*(交|提交|完成|上交)\s*", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ，。；;：:、\n\t（）()")
    if not cleaned:
        return "待处理通知"
    return cleaned[:80]


def _detect_source(text: str) -> str:
    for pattern in SOURCE_PATTERNS:
        m = re.search(pattern, text)
        if m:
            return m.group(1)
    return "未知来源"


def _detect_category(text: str) -> str:
    # 「报告厅」里的「报告」不是文件，先排除掉这个高频误判
    normalized = text.replace("报告厅", "").replace("会议室", "会议")
    for category, keywords in CATEGORY_KEYWORDS:
        if any(k in normalized for k in keywords):
            return category
    return "其他"


def _detect_priority(text: str) -> str:
    if any(k in text for k in ("紧急", "务必", "重要", "加急", "立即")):
        return "high"
    if any(k in text for k in ("可选", "自愿", "建议")):
        return "low"
    return "normal"


def parse_notices(text: str, now: Optional[datetime] = None, mode: str = "rule") -> list[Task]:
    """把一段通知解析成一条或多条 Task；编号清单会自动拆成多条。

    每条任务都保留 raw_notice（自己那一段原文），便于在详情页回溯复核。
    """
    if not text or not text.strip():
        raise ValueError("通知内容不能为空")
    now = now or datetime.now()
    tasks: list[Task] = []
    for chunk in split_notices(text):
        if mode == "llm":
            tasks.append(_parse_with_llm(chunk))
            continue
        due, date_raw = parse_due(chunk, now)
        tasks.append(Task(
            id=new_id(),
            title=_clean_title(chunk, date_raw),
            due_at=due,
            source=_detect_source(chunk),
            category=_detect_category(chunk),
            raw_notice=chunk.strip(),
            priority=_detect_priority(chunk),
            tags=["auto-parsed", mode],
        ))
    return tasks


def parse_notice(text: str, now: Optional[datetime] = None, mode: str = "rule") -> Task:
    """向后兼容的入口：只返回第一条。需要处理多事项时请用 parse_notices。"""
    return parse_notices(text, now, mode)[0]


# --------------------------------------------------------------------------
# LLM 兜底模式
# --------------------------------------------------------------------------

LLM_PROMPT = """你是一个通知解析助手。从下面的通知中抽取任务信息，只输出 JSON，不要输出其他内容。
字段：title(字符串，任务标题)，due_at(字符串，格式 YYYY-MM-DD HH:MM，无法判断则为 null)，
source(字符串，发布者)，category(字符串：作业/考试/资料提交/会议/审批/汇报/其他)，
priority(字符串：high/normal/low)。
当前时间：{now}
通知：{text}"""


def _parse_with_llm(text: str) -> Task:
    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    if not api_key:
        raise RuntimeError("LLM 模式需要设置 OPENAI_API_KEY（可用任意 OpenAI-compatible 服务）")

    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": LLM_PROMPT.format(
            now=datetime.now().isoformat(timespec="minutes"), text=text)}],
        "temperature": 0,
    }).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/chat/completions",
        data=payload,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = json.loads(response.read().decode("utf-8"))
        content = body["choices"][0]["message"]["content"]
        # 去掉可能存在的 markdown 代码块围栏
        content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip())
        data = json.loads(content)
    except (urllib.error.URLError, KeyError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"LLM 解析失败：{exc}") from exc

    due = None
    if data.get("due_at"):
        try:
            due = datetime.fromisoformat(str(data["due_at"]).replace("T", " "))
        except ValueError:
            due = None
    return Task(
        id=new_id(),
        title=str(data.get("title") or text[:60]),
        due_at=due,
        source=str(data.get("source") or "未知来源"),
        category=str(data.get("category") or "其他"),
        raw_notice=text.strip(),
        priority=str(data.get("priority") or "normal"),
        tags=["auto-parsed", "llm"],
    )
