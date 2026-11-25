"""提醒引擎：把任务列表变成「人愿意读」的分级提醒。

分级策略（对应 models.Task.urgency）：
  逾期 / 24 小时内 / 3 天内 / 7 天内 / 无截止日
nanobot 的 automation 每天定时调用 build_report()，把结果发回聊天窗口。
"""

from __future__ import annotations

from datetime import datetime

from .models import LEVELS, Reminder, Task, now_local


_LEVEL_META = {name: (icon, label) for name, icon, label in LEVELS}
_ORDER = [name for name, _, _ in LEVELS]
_DAY_HOURS = {0: "凌晨", 1: "凌晨", 7: "早上", 8: "早上", 9: "上午", 10: "上午",
              11: "上午", 12: "中午", 13: "下午", 14: "下午", 15: "下午",
              16: "下午", 17: "傍晚", 18: "傍晚", 19: "晚上", 20: "晚上"}


def make_reminder(task: Task, now: datetime | None = None) -> Reminder:
    now = now or now_local()
    grade, _ = task.urgency(now)
    level = _ORDER[grade]
    icon, label = _LEVEL_META[level]
    remaining = task.days_left(now)

    if remaining is None:
        detail = "没有明确截止日，建议补一个时间"
    elif remaining < 0:
        detail = f"已逾期 {abs(remaining):.1f} 天"
    elif remaining < 1:
        detail = f"还剩 {remaining * 24:.1f} 小时"
    else:
        detail = f"还剩 {remaining:.1f} 天"

    prefix = "【加急】" if task.priority == "high" else ""
    message = f"{icon} {prefix}{task.title} —— {detail}（截止 {task.due_text()}，来源：{task.source}）"
    return Reminder(level=level, icon=icon, task=task, message=message)


def build_report(tasks: list[Task], now: datetime | None = None, title: str = "deadline 日报") -> str:
    """生成一份可直接发到聊天窗口的提醒报告。"""
    now = now or now_local()
    pending = [t for t in tasks if t.status == "pending"]
    reminders = sorted(pending, key=lambda t: t.urgency(now))

    lines = [f"## {title}", f"生成时间：{now.strftime('%Y-%m-%d %H:%M')}　待办 {len(pending)} 条", ""]

    if not reminders:
        lines.append("当前没有待办任务。把学校或公司的通知贴给我就行。")
        return "\n".join(lines)

    buckets: dict[str, list[Reminder]] = {name: [] for name in _ORDER}
    for task in reminders:
        reminder = make_reminder(task, now)
        buckets[reminder.level].append(reminder)

    labels = {name: label for name, _, label in LEVELS}
    for level in _ORDER:
        items = buckets[level]
        if not items:
            continue
        lines.append(f"### {labels[level]}（{len(items)}）")
        for item in items:
            lines.append(f"- {item.message}")
        lines.append("")

    return "\n".join(lines).rstrip()


def greeting(now: datetime | None = None) -> str:
    hour = (now or now_local()).hour
    period = _DAY_HOURS.get(hour, "白天")
    return f"早上好" if period == "早上" else f"{period}好"


# --------------------------------------------------------------------------
# 按内容排序 + 每日进度
# --------------------------------------------------------------------------

def build_plan(tasks: list[Task], now: datetime | None = None, top: int | None = None) -> str:
    """按任务内容给出「先做什么」的顺序，并说明为什么。"""
    now = now or now_local()
    pending = [t for t in tasks if t.status in ("pending", "in_progress")]
    ranked = []
    for task in pending:
        score, reason = task.work_score(now)
        ranked.append((score, reason, task))
    ranked.sort(key=lambda row: (-row[0], row[2].due_at or datetime.max))

    lines = [
        "## 今日执行顺序（按任务内容排序）",
        f"生成时间：{now.strftime('%Y-%m-%d %H:%M')}　待办 {len(pending)} 条",
        "排序依据：优先级 + 类别提前量 + 截止紧迫度 + 是否已经开始",
        "",
    ]
    if not ranked:
        lines.append("没有待办任务。")
        return "\n".join(lines)

    shown = ranked[:top] if top else ranked
    for idx, (score, reason, task) in enumerate(shown, 1):
        lines.append(
            f"{idx}. [{score:>4}] {task.title}　| {task.due_text()}　| {task.status}"
        )
        lines.append(f"      理由：{reason}")
        if task.notes:
            lines.append(f"      备注：{task.notes.splitlines()[-1]}")
    if top and len(ranked) > top:
        lines.append(f"\n……还有 {len(ranked) - top} 条，用 cli.py plan 查看全部")
    return "\n".join(lines)


def _progress_bar(progress: int, width: int = 10) -> str:
    filled = int(progress / 100 * width)
    return "█" * filled + "░" * (width - filled)


def build_daily(tasks: list[Task], now: datetime | None = None) -> str:
    """每日进度报告：完成率、状态分布、今日聚焦。"""
    now = now or now_local()
    total = len(tasks)
    done = [t for t in tasks if t.status == "done"]
    doing = [t for t in tasks if t.status == "in_progress"]
    pending = [t for t in tasks if t.status == "pending"]
    overdue = [t for t in pending if (t.days_left(now) or 1e9) < 0]

    rate = len(done) / total * 100 if total else 0.0
    lines = [
        "## 每日进度",
        f"{now.strftime('%Y-%m-%d')}　{greeting(now)}",
        "",
        f"- 全部任务：{total}",
        f"- 已完成：{len(done)}　进行中：{len(doing)}　待开始：{len(pending)}",
        f"- 已逾期：{len(overdue)}",
        f"- 完成率：{rate:.0f}%  {_progress_bar(int(rate))}",
        "",
    ]

    if doing:
        lines.append("### 正在进行")
        for task in doing:
            lines.append(f"- {_progress_bar(task.progress)} {task.progress:>3}%　{task.title}")
        lines.append("")

    focus = doing + pending
    if focus:
        lines.append("### 今日建议先做（按内容排序）")
        ranked = []
        for task in focus:
            score, reason = task.work_score(now)
            ranked.append((score, reason, task))
        ranked.sort(key=lambda row: (-row[0], row[2].due_at or datetime.max))
        for score, reason, task in ranked[:5]:
            lines.append(f"- [{score:>4}] {task.title} —— {reason}")
        lines.append("")
    else:
        lines.append("今天没有待办，很好。\n")

    if overdue:
        lines.append("### 需要立刻处理")
        for task in overdue:
            lines.append(f"- {task.title}（逾期 {abs(task.days_left(now) or 0):.1f} 天）")

    return "\n".join(lines).rstrip()
