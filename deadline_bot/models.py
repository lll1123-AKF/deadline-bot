"""数据模型：通知里抽出来的任务，以及提醒结果。

这一层故意做得很薄——只有数据结构和纯函数，不碰文件、不碰网络。
好处是容易测试，也容易讲清楚：agent 的记忆最终就落在一个 Task 列表上。
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from typing import Optional


def now_local() -> datetime:
    return datetime.now()


def new_id() -> str:
    return "t_" + uuid.uuid4().hex[:8]


@dataclass
class Task:
    """一条从通知中抽取出来的待办任务。"""

    id: str
    title: str
    due_at: Optional[datetime]
    source: str = ""            # 谁发的通知：教务处 / 班主任 / HR / 部门
    category: str = "其他"       # 作业 / 资料提交 / 会议 / 审批 ...
    raw_notice: str = ""         # 原始通知，便于回溯和复核
    created_at: datetime = field(default_factory=now_local)
    status: str = "pending"      # pending / in_progress / done / cancelled
    priority: str = "normal"     # high / normal / low
    tags: list[str] = field(default_factory=list)
    progress: int = 0            # 完成进度 0-100
    estimate_hours: float = 0.0  # 预计耗时，用于内容排序
    notes: str = ""              # 用户随时补充的备注/变更记录
    updated_at: datetime = field(default_factory=now_local)

    def to_dict(self) -> dict:
        d = asdict(self)
        for key in ("due_at", "created_at", "updated_at"):
            value = d.get(key)
            if isinstance(value, datetime):
                d[key] = value.isoformat()
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "Task":
        data = dict(data)
        for key in ("due_at", "created_at", "updated_at"):
            value = data.get(key)
            if isinstance(value, str) and value:
                try:
                    data[key] = datetime.fromisoformat(value)
                except ValueError:
                    data[key] = None
        known = cls.__dataclass_fields__.keys()
        return cls(**{k: v for k, v in data.items() if k in known})

    def days_left(self, now: Optional[datetime] = None) -> Optional[float]:
        """距离截止还有多少天；没有截止日返回 None。"""
        if self.due_at is None:
            return None
        return (self.due_at - (now or now_local())).total_seconds() / 86400

    def urgency(self, now: Optional[datetime] = None) -> tuple[int, float]:
        """紧急度：(等级, 排序键)。等级越小越急，用于排序和分级提醒。"""
        remaining = self.days_left(now)
        if remaining is None:
            return 5, 1e9
        if remaining < 0:
            return 0, remaining        # 已逾期
        if remaining <= 1:
            return 1, remaining        # 24 小时内
        if remaining <= 3:
            return 2, remaining        # 3 天内
        if remaining <= 7:
            return 3, remaining        # 7 天内
        return 4, remaining            # 7 天以上

    def due_text(self) -> str:
        if self.due_at is None:
            return "无明确截止日"
        return self.due_at.strftime("%Y-%m-%d %H:%M")

    # ---------- 内容排序 ----------

    # 不同类别的任务「该提前多久开始」不同：考试要复习，会议到点就去，
    # 审批要留流程时间。这个表就是 agent 的领域知识，后续可配置化。
    LEAD_DAYS = {
        "考试": 3.0,
        "作业": 1.5,
        "资料提交": 1.0,
        "审批": 1.0,
        "汇报": 0.5,
        "会议": 0.0,
        "其他": 0.5,
    }
    PRIORITY_WEIGHT = {"high": 3.0, "normal": 1.5, "low": 0.0}

    def work_score(self, now: Optional[datetime] = None) -> tuple[float, str]:
        """按「任务内容」算一个该先做的分数，返回 (分数, 理由)。

        综合四类信号：
          1. 用户/通知标出的优先级
          2. 任务类别的提前量（考试 > 作业 > 提交 > 会议）
          3. 距离截止的紧迫度（越近越先做）
          4. 进行中的任务轻微加权（避免半途而废）
        """
        now = now or now_local()
        remaining = self.days_left(now)

        priority_w = self.PRIORITY_WEIGHT.get(self.priority, 1.5)
        lead_w = self.LEAD_DAYS.get(self.category, 0.5)

        if remaining is None:
            urgency_w = 0.0
        elif remaining < 0:
            urgency_w = 10.0 + min(abs(remaining), 10.0) * 0.1  # 逾期最优先
        elif remaining < 1:
            urgency_w = 8.0 - remaining * 2.0     # 8.0 ~ 6.0
        elif remaining < 3:
            urgency_w = 6.0 - (remaining - 1.0) * 1.0  # 6.0 ~ 4.0
        elif remaining < 7:
            urgency_w = 4.0 - (remaining - 3.0) * 0.5  # 4.0 ~ 2.0
        else:
            urgency_w = max(0.0, 2.0 - (remaining - 7.0) * 0.2)

        # 提前量：离截止不足 lead_days 时，分数随「该开始程度」上升
        lead_bonus = 0.0
        if remaining is not None and 0 <= remaining <= lead_w:
            lead_bonus = (lead_w - remaining) / max(lead_w, 1.0)

        doing_w = 0.5 if self.status == "in_progress" else 0.0
        score = round(priority_w + urgency_w + lead_bonus + doing_w, 2)

        reasons = [f"优先级{self.priority}"]
        if lead_w > 0:
            reasons.append(f"{self.category}需提前{lead_w:g}天")
        if remaining is not None:
            reasons.append(f"剩余{remaining:.1f}天")
        if doing_w:
            reasons.append("已开始")
        return score, "、".join(reasons)


@dataclass
class Reminder:
    """一条提醒：面向人看的文本 + 面向机器的元数据。"""

    level: str          # overdue / urgent / soon / upcoming / unscheduled
    icon: str
    task: Task
    message: str

    def to_dict(self) -> dict:
        return {
            "level": self.level,
            "task_id": self.task.id,
            "message": self.message,
            "due_at": self.task.due_at.isoformat() if self.task.due_at else None,
        }


LEVELS = [
    ("overdue", "!!", "已逾期"),
    ("urgent", "**", "24 小时内"),
    ("soon", "* ", "3 天内"),
    ("upcoming", "  ", "7 天内"),
    ("later", "  ", "7 天以上"),
    ("unscheduled", "??", "无截止日"),
]
