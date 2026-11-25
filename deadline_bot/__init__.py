"""deadline-bot：面向通知管理场景的独立 Agent 应用。

分层：
  core    —— models / parser / store / reminder，确定性的领域能力
  runtime —— messages / tools / context / loop / memory / scheduler，Agent 运行时
  channels—— CLI / HTTP / nanobot 适配器，多种接入方式
"""

__version__ = "0.2.0"

from .models import Task, Reminder
from .parser import parse_notice, parse_notices, split_notices, parse_due
from .store import TaskStore
from .reminder import build_report, build_plan, build_daily, make_reminder

__all__ = [
    "Task", "Reminder", "parse_notice", "parse_notices", "split_notices", "parse_due",
    "TaskStore", "build_report", "build_plan", "build_daily", "make_reminder",
]
