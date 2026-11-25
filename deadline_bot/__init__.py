"""deadline-bot：把学校/公司的通知变成可追踪、会提醒的任务。

这是一个基于 nanobot 工作区 skill 机制的二次开发示例项目。
"""

__version__ = "0.1.0"

from .models import Task, Reminder
from .parser import parse_notice, parse_due
from .store import TaskStore
from .reminder import build_report, build_plan, build_daily, make_reminder

__all__ = [
    "Task", "Reminder", "parse_notice", "parse_due",
    "TaskStore", "build_report", "build_plan", "build_daily", "make_reminder",
]
