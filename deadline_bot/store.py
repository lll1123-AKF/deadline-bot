"""任务持久化：用 JSON 文件当「agent 的记忆」。

为什么不用数据库？因为这是一个演示项目，JSON 足够：
  - 人能直接打开看
  - git 能 diff
  - 零依赖、零配置
真实产品里这一层会换成 SQLite + 索引，接口保持不变即可。
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Optional

from .models import Task, now_local


class TaskStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    # ---------- 基础读写 ----------

    def load(self) -> list[Task]:
        if not self.path.exists():
            return []
        try:
            with self.path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (json.JSONDecodeError, OSError):
            return []
        if not isinstance(data, list):
            return []
        return [Task.from_dict(item) for item in data]

    def save(self, tasks: list[Task]) -> None:
        """原子写：先写临时文件再替换，避免中途崩溃留下半个 JSON。"""
        payload = json.dumps([t.to_dict() for t in tasks], ensure_ascii=False, indent=2)
        fd, tmp_name = tempfile.mkstemp(dir=str(self.path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(payload)
            os.replace(tmp_name, self.path)
        except BaseException:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)
            raise

    # ---------- 业务操作 ----------

    def add(self, task: Task) -> tuple[bool, str]:
        """返回 (是否新增, 说明)。相同标题+截止日视为重复。"""
        tasks = self.load()
        for existing in tasks:
            if existing.status == "cancelled":
                continue
            same_title = existing.title.strip() == task.title.strip()
            same_due = (existing.due_at == task.due_at)
            if same_title and same_due:
                return False, f"已存在相同任务：{existing.id}"
        tasks.append(task)
        self.save(tasks)
        return True, task.id

    def get(self, task_id: str) -> Optional[Task]:
        for task in self.load():
            if task.id == task_id:
                return task
        return None

    def set_status(self, task_id: str, status: str) -> bool:
        return self.update(task_id, status=status)

    def update(self, task_id: str, **fields) -> bool:
        """随时修改任务属性：标题、截止日、优先级、状态、进度、类别、来源、备注。

        只允许改 Task 已有的字段，避免拼错字段名静默失败。
        """
        allowed = set(Task.__dataclass_fields__.keys()) - {"id", "created_at"}
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(f"不允许修改的字段：{', '.join(sorted(unknown))}")
        tasks = self.load()
        for task in tasks:
            if task.id == task_id:
                for key, value in fields.items():
                    if value is not None:
                        setattr(task, key, value)
                # 进度与状态的一致性约束
                if task.progress is not None:
                    task.progress = max(0, min(100, int(task.progress)))
                if task.status == "done":
                    task.progress = 100
                elif task.status == "pending" and task.progress == 100:
                    task.status = "done"
                task.updated_at = now_local()
                self.save(tasks)
                return True
        return False

    def add_note(self, task_id: str, note: str) -> bool:
        task = self.get(task_id)
        if task is None:
            return False
        stamp = now_local().strftime("%m-%d %H:%M")
        merged = f"{task.notes}\n[{stamp}] {note}".strip()
        return self.update(task_id, notes=merged)

    def remove(self, task_id: str) -> bool:
        tasks = self.load()
        remaining = [t for t in tasks if t.id != task_id]
        if len(remaining) == len(tasks):
            return False
        self.save(remaining)
        return True

    def pending(self) -> list[Task]:
        return [t for t in self.load() if t.status == "pending"]

    def clear_done(self) -> int:
        tasks = self.load()
        remaining = [t for t in tasks if t.status != "done"]
        removed = len(tasks) - len(remaining)
        if removed:
            self.save(remaining)
        return removed
