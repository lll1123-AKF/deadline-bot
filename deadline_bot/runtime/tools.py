"""工具系统：Tool 契约 + 注册表 + 参数校验 + 错误回喂。

设计来源：nanobot 的 ``agent/tools/base.py`` 与 ``agent/tools/registry.py``。
三个照搬的关键决策：

1. 每个工具自己声明 JSON Schema（name / description / parameters），
   ``definitions()`` 缓存并**稳定排序**，避免每轮 prompt 变化导致 cache 失效。
2. ``prepare_call()`` 在执行前做参数校验和名称纠错建议。
3. 异常**不抛给循环**，而是包成带提示的 ToolResult 文本回填给模型，
   让模型自己决定重试还是换路——这是 agent 能自愈的核心。

工具是「函数」，SKILL.md 是「说明书」，两者分开才能热插拔。
"""

from __future__ import annotations

import difflib
import json
from dataclasses import dataclass
from typing import Any, Callable

from .. import TaskStore, build_daily, build_plan, build_report, parse_due, parse_notices
from ..models import now_local

_ERROR_HINT = "\n[请结合用户目标判断是否需要重试或换一种做法。]"


class ToolResult(str):
    """字符串结果 + 结构化错误标记。"""

    is_error: bool

    def __new__(cls, content: str, *, is_error: bool = False) -> "ToolResult":
        obj = str.__new__(cls, content)
        obj.is_error = is_error
        return obj


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[..., str]
    read_only: bool = False

    def to_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


def _obj(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required or []}


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}
        self._cache: list[dict[str, Any]] | None = None

    def register(self, spec: ToolSpec) -> None:
        self._tools[spec.name] = spec
        self._cache = None

    @property
    def tool_names(self) -> list[str]:
        return sorted(self._tools)

    def definitions(self) -> list[dict[str, Any]]:
        if self._cache is None:
            self._cache = [self._tools[name].to_schema() for name in self.tool_names]
        return self._cache

    @staticmethod
    def _coerce(args: Any) -> Any:
        if isinstance(args, str):
            stripped = args.strip()
            if stripped.startswith("{"):
                try:
                    return json.loads(stripped)
                except json.JSONDecodeError:
                    pass
            return {"text": stripped}
        return args if isinstance(args, dict) else {}

    def _validate(self, spec: ToolSpec, args: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        schema = spec.parameters or {}
        for key in schema.get("required", []):
            if key not in args:
                errors.append(f"缺少必填参数 {key}")
        props = schema.get("properties", {})
        for key, value in args.items():
            rule = props.get(key)
            if rule is None:
                errors.append(f"未知参数 {key}")
                continue
            expected = rule.get("type")
            if expected == "string" and not isinstance(value, str):
                errors.append(f"{key} 应为字符串")
            elif expected == "integer" and (not isinstance(value, int) or isinstance(value, bool)):
                errors.append(f"{key} 应为整数")
            if "enum" in rule and value not in rule["enum"]:
                errors.append(f"{key} 只能是 {rule['enum']}")
        return errors

    def prepare_call(self, name: str, args: Any) -> tuple[ToolSpec | None, dict[str, Any], str | None]:
        spec = self._tools.get(name)
        if spec is None:
            close = difflib.get_close_matches(name, self.tool_names, n=1)
            hint = f" 是否想用 '{close[0]}'？" if close else ""
            return None, {}, (
                f"错误：工具 '{name}' 不存在。{hint}可用工具：{', '.join(self.tool_names)}"
            )
        args = self._coerce(args)
        errors = self._validate(spec, args)
        if errors:
            return spec, args, f"错误：工具 '{name}' 参数不合法：{'；'.join(errors)}"
        return spec, args, None

    def execute(self, name: str, args: Any) -> ToolResult:
        spec, args, error = self.prepare_call(name, args)
        if error:
            return ToolResult(error + _ERROR_HINT, is_error=True)
        assert spec is not None
        try:
            return ToolResult(str(spec.handler(**args)))
        except Exception as exc:  # 关键：异常转成可恢复的文本
            return ToolResult(f"工具 {name} 执行失败：{exc}" + _ERROR_HINT, is_error=True)


def build_default_registry(store: TaskStore, scheduler: Any = None) -> ToolRegistry:
    """把 core 层的确定性能力包装成 agent 可调用的工具。"""

    registry = ToolRegistry()

    def add_notices(text: str) -> str:
        tasks = parse_notices(text, now=now_local())
        added = skipped = 0
        for task in tasks:
            ok, _ = store.add(task)
            added += int(ok)
            skipped += int(not ok)
        lines = [f"从 1 条通知中拆出 {len(tasks)} 项任务：新增 {added}，重复跳过 {skipped}"]
        for task in tasks[:10]:
            lines.append(f"- {task.title} | 截止 {task.due_text()} | {task.category} | id={task.id}")
        return "\n".join(lines)

    def list_tasks() -> str:
        tasks = store.load()
        if not tasks:
            return "当前没有任务。"
        return "\n".join(
            f"- {t.id} | {t.due_text()} | {t.status} | {t.progress}% | {t.title}"
            for t in tasks
        )

    def update_task(
        task_id: str,
        priority: str | None = None,
        progress: int | None = None,
        status: str | None = None,
        due_text: str | None = None,
        notes: str | None = None,
        title: str | None = None,
    ) -> str:
        fields: dict[str, Any] = {}
        if priority is not None:
            fields["priority"] = priority
        if progress is not None:
            fields["progress"] = max(0, min(100, progress))
        if status is not None:
            fields["status"] = status
        if title is not None:
            fields["title"] = title
        if notes is not None:
            existing = store.get(task_id)
            stamp = now_local().strftime("%m-%d %H:%M")
            fields["notes"] = ((existing.notes + "\n") if existing and existing.notes else "") + f"[{stamp}] {notes}"
        if due_text is not None:
            due, _ = parse_due(due_text, now_local())
            if due is None:
                return f"没识别出日期：{due_text}。可以换成「12月5日」「下周三」这类写法。"
            fields["due_at"] = due
        if not fields:
            return "没有指定要修改的字段。"
        if not store.update(task_id, **fields):
            return f"找不到任务 {task_id}，请先用 list_tasks 查看 id。"
        updated = store.get(task_id)
        return f"已更新 {task_id}：{updated.title} | 截止 {updated.due_text()} | {updated.status} | {updated.progress}%"

    def get_plan(top: int = 5) -> str:
        return build_plan(store.load(), now=now_local(), top=top)

    def get_daily() -> str:
        return build_daily(store.load(), now=now_local())

    def get_due() -> str:
        return build_report(store.load(), now=now_local(), title="截止提醒")

    def schedule_reminder(cron_expr: str, message: str) -> str:
        if scheduler is None:
            return "调度器未启用，无法创建定时任务。"
        job = scheduler.add(cron_expr, message)
        return f"已创建定时任务 {job.job_id}：{cron_expr} → {message}"

    registry.register(ToolSpec(
        name="add_notices",
        description="把一段通知文本解析成一条或多条任务并入库。编号清单会自动拆成多条。",
        parameters=_obj({"text": {"type": "string", "description": "通知原文"}}, ["text"]),
        handler=add_notices,
    ))
    registry.register(ToolSpec(
        name="list_tasks",
        description="列出全部任务及其 id、截止日、状态与进度。修改任务前先用它拿 id。",
        parameters=_obj({}),
        handler=list_tasks,
        read_only=True,
    ))
    registry.register(ToolSpec(
        name="update_task",
        description="修改任务：优先级、进度、状态、标题、备注，或自然语言改截止日。",
        parameters=_obj({
            "task_id": {"type": "string", "description": "任务 id，形如 t_xxxxxxxx"},
            "priority": {"type": "string", "enum": ["high", "normal", "low"]},
            "progress": {"type": "integer", "description": "0-100"},
            "status": {"type": "string", "enum": ["pending", "in_progress", "done", "cancelled"]},
            "due_text": {"type": "string", "description": "自然语言日期，如 下周三下午5点 / 12月5日 / 3天内"},
            "notes": {"type": "string"},
            "title": {"type": "string"},
        }, ["task_id"]),
        handler=update_task,
    ))
    registry.register(ToolSpec(
        name="get_plan",
        description="按任务内容算执行顺序，输出综合打分与理由。回答「先做什么」。",
        parameters=_obj({"top": {"type": "integer", "description": "最多列几条，默认 5"}}),
        handler=get_plan,
        read_only=True,
    ))
    registry.register(ToolSpec(
        name="get_daily",
        description="生成每日进度报告：完成率、状态分布、今日建议先做。",
        parameters=_obj({}),
        handler=get_daily,
        read_only=True,
    ))
    registry.register(ToolSpec(
        name="get_due",
        description="按剩余时间分级列出即将到期与已逾期的任务。",
        parameters=_obj({}),
        handler=get_due,
        read_only=True,
    ))
    registry.register(ToolSpec(
        name="schedule_reminder",
        description="创建定时提醒，让 agent 到点主动发起一轮对话。cron_expr 形如 '0 8 * * *'（每天 8 点）。",
        parameters=_obj({
            "cron_expr": {"type": "string"},
            "message": {"type": "string", "description": "触发时要执行的指令"},
        }, ["cron_expr", "message"]),
        handler=schedule_reminder,
    ))
    return registry
