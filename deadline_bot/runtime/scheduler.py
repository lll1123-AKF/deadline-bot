"""定时调度：让 agent 能主动发起对话，而不只是被动回答。

设计来源：nanobot ``agent/tools/cron.py`` + ``AgentLoop.submit_cron_turn``。
最重要的设计不是 cron 表达式解析得多完整，而是：**触发时往消息总线注入一条
InboundMessage**，于是定时提醒走的是和普通对话完全相同的 AgentLoop，
不需要另写一套逻辑。这也是「助手」和「聊天机器人」的分界线。

支持的写法（够用且可讲清楚）：
  "0 8 * * *"  每天 8:00（分 时 日 月 周）
  "08:00"      每天 8:00 简写
  "every:3600" 每 3600 秒一次
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .messages import InboundMessage, MessageBus

if TYPE_CHECKING:
    from .loop import AgentLoop


@dataclass
class CronJob:
    job_id: str
    cron_expr: str
    message: str
    enabled: bool = True
    last_run: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CronJob":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    def matches(self, now: datetime) -> bool:
        if not self.enabled:
            return False
        expr = self.cron_expr.strip()

        if expr.startswith("every:"):
            try:
                seconds = int(expr.split(":", 1)[1])
            except ValueError:
                return False
            if not self.last_run:
                return True
            try:
                elapsed = (now - datetime.fromisoformat(self.last_run)).total_seconds()
            except ValueError:
                return True
            return elapsed >= seconds

        target: tuple[int, int] | None = None
        m = re.match(r"^(\d{1,2})\s+(\d{1,2})\s+\*\s+\*\s+\*$", expr)
        if m:
            target = (int(m.group(2)), int(m.group(1)))  # (时, 分)
        else:
            m = re.match(r"^(\d{1,2}):(\d{2})$", expr)
            if m:
                target = (int(m.group(1)), int(m.group(2)))
        if target is None:
            return False
        if (now.hour, now.minute) != target:
            return False
        if self.last_run:
            try:
                if datetime.fromisoformat(self.last_run).date() == now.date():
                    return False  # 今天已经跑过
            except ValueError:
                pass
        return True


class CronService:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _read(self) -> list[CronJob]:
        if not self.path.exists():
            return []
        try:
            with self.path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
            return [CronJob.from_dict(item) for item in data] if isinstance(data, list) else []
        except (json.JSONDecodeError, OSError):
            return []

    def _write(self, jobs: list[CronJob]) -> None:
        payload = json.dumps([asdict(j) for j in jobs], ensure_ascii=False, indent=2)
        fd, tmp = tempfile.mkstemp(dir=str(self.path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(payload)
            os.replace(tmp, self.path)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise

    def add(self, cron_expr: str, message: str) -> CronJob:
        job = CronJob(job_id="job_" + uuid.uuid4().hex[:6], cron_expr=cron_expr, message=message)
        jobs = self._read()
        jobs.append(job)
        self._write(jobs)
        return job

    def list(self, include_disabled: bool = True) -> list[CronJob]:
        jobs = self._read()
        return jobs if include_disabled else [j for j in jobs if j.enabled]

    def remove(self, job_id: str) -> bool:
        jobs = self._read()
        kept = [j for j in jobs if j.job_id != job_id]
        if len(kept) == len(jobs):
            return False
        self._write(kept)
        return True

    def set_enabled(self, job_id: str, enabled: bool) -> bool:
        jobs = self._read()
        for job in jobs:
            if job.job_id == job_id:
                job.enabled = enabled
                self._write(jobs)
                return True
        return False

    def due_jobs(self, now: datetime | None = None) -> list[CronJob]:
        current = now or datetime.now()
        return [j for j in self._read() if j.matches(current)]

    def trigger(self, job: CronJob, now: datetime | None = None) -> InboundMessage:
        """把定时任务变成一条普通入站消息——这是主动性的关键。"""
        current = now or datetime.now()
        jobs = self._read()
        for item in jobs:
            if item.job_id == job.job_id:
                item.last_run = current.isoformat(timespec="seconds")
        self._write(jobs)
        return InboundMessage(
            channel="cron",
            sender_id="scheduler",
            chat_id=job.job_id,
            content=job.message,
            metadata={"job_id": job.job_id, "cron_expr": job.cron_expr},
        )

    def tick(
        self,
        bus: MessageBus,
        loop: "AgentLoop | None" = None,
        now: datetime | None = None,
    ) -> list[str]:
        """检查到期任务；给了 loop 就直接跑一轮，返回回复列表。"""
        current = now or datetime.now()
        replies: list[str] = []
        for job in self.due_jobs(current):
            inbound = self.trigger(job, current)
            bus.publish_inbound(inbound)
            bus.consume_inbound()  # 与普通 turn 一致：投递即认领，队列不留残留
            if loop is not None:
                replies.append(loop.handle(inbound).reply)
        return replies
