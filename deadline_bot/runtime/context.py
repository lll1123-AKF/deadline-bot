"""上下文构建：把身份、工具契约、任务快照、技能摘要、会话历史组装成 messages。

设计来源：nanobot ``agent/context.py`` 的 ``ContextBuilder.build_system_prompt``。
它把 system prompt 拆成多个来源（identity / bootstrap / memory / skills summary），
并且**只注入技能摘要、用到才加载全文**，控制上下文长度。

这里做同样的分层，额外注入「当前任务快照」——让模型在决定调哪个工具之前
就知道库里大概有什么，避免无意义的 list 调用。
"""

from __future__ import annotations

from typing import Any

from .. import TaskStore
from .skills import SkillsLoader

IDENTITY = """你是 DeadlineBot，一个面向学生和上班族的通知任务助手。
把散落在班级群、教务处公告、公司邮件里的通知，变成可追踪、会提醒、能排序的任务。

工作原则：
- 用户粘贴一段通知时，用 add_notices 入库；一段通知含多个事项时它会自动拆成多条。
- 用户问「先做什么」用 get_plan，问「今天进度」用 get_daily，问「要交什么」用 get_due。
- 修改任务前先用 list_tasks 拿到 id；改截止日支持自然语言。
- 不确定的日期如实说「无截止日」，绝不编造。
- 回答简洁，先给结论，再列要点。"""

TOOL_CONTRACT = """# 工具使用约定
你可以调用下面注册的工具，而不是自己猜测结果。
如果工具返回错误，读错误提示，判断是重试、换参数还是换一个工具，不要直接放弃。
如果一次请求需要多步（例如「记下通知并告诉我先做什么」），可以在同一轮里按顺序调用多个工具。
工具结果回来后，把结果整理成自然语言回复给用户，不要把原始 JSON 丢给用户。"""


class ContextBuilder:
    def __init__(self, store: TaskStore, skills: SkillsLoader) -> None:
        self.store = store
        self.skills = skills

    def snapshot(self) -> str:
        tasks = self.store.load()
        active = [t for t in tasks if t.status not in ("done", "cancelled")]
        overdue = [t for t in active if (t.days_left() is not None and t.days_left() < 0)]
        lines = [
            f"当前共 {len(tasks)} 条任务，待办 {len(active)} 条，逾期 {len(overdue)} 条。"
        ]
        for task in active[:5]:
            lines.append(f"- {task.id} | {task.due_text()} | {task.category} | {task.title}")
        if len(active) > 5:
            lines.append(f"（还有 {len(active) - 5} 条未列出，需要时用 list_tasks）")
        return "\n".join(lines)

    def system_prompt(self) -> str:
        return "\n\n".join([
            IDENTITY,
            TOOL_CONTRACT,
            "# 当前任务快照\n" + self.snapshot(),
            "# 可用技能\n" + self.skills.summary(),
        ])

    def build(self, current_input: str, history: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = [{"role": "system", "content": self.system_prompt()}]
        messages.extend(history or [])
        messages.append({"role": "user", "content": current_input})
        return messages
