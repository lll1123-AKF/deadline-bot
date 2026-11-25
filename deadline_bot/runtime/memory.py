"""会话记忆：按 session_key 持久化对话历史，并提供历史压缩。

设计来源：nanobot 的 ``session/manager.py`` + ``agent/memory.py`` +
``agent/autocompact.py``。它把「长期记忆文件」和「会话历史」分开，历史过长时
用 Consolidator 压成摘要。这里对应实现两层：

  1. TaskStore      —— 任务记忆（结构化、可查询）
  2. SessionMemory  —— 对话记忆（按 channel:chat_id 隔离、可压缩）

压缩策略刻意保持简单可讲：超过 keep_last 条时，把更早的消息合并成一条
system 摘要，而不是丢弃——既控制 prompt 长度，又不丢掉「之前做过什么」。
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any


class SessionMemory:
    def __init__(self, path: Path, keep_last: int = 12) -> None:
        self.path = Path(path)
        self.keep_last = keep_last
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _read_all(self) -> dict[str, list[dict[str, Any]]]:
        if not self.path.exists():
            return {}
        try:
            with self.path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, OSError):
            return {}

    def _write_all(self, data: dict[str, list[dict[str, Any]]]) -> None:
        payload = json.dumps(data, ensure_ascii=False, indent=2)
        fd, tmp = tempfile.mkstemp(dir=str(self.path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(payload)
            os.replace(tmp, self.path)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise

    def load(self, session_key: str) -> list[dict[str, Any]]:
        return list(self._read_all().get(session_key, []))

    def append(self, session_key: str, message: dict[str, Any]) -> None:
        data = self._read_all()
        history = list(data.get(session_key, []))
        history.append({**message, "ts": datetime.now().isoformat(timespec="seconds")})
        data[session_key] = history
        self._write_all(data)
        self.compact(session_key)

    def extend(self, session_key: str, messages: list[dict[str, Any]]) -> None:
        data = self._read_all()
        history = list(data.get(session_key, []))
        for message in messages:
            history.append({**message, "ts": datetime.now().isoformat(timespec="seconds")})
        data[session_key] = history
        self._write_all(data)
        self.compact(session_key)

    def history(self, session_key: str, limit: int | None = None) -> list[dict[str, Any]]:
        """返回可塞进 prompt 的历史（只保留 role/content/tool_calls 等模型字段）。"""
        allowed = {"role", "content", "tool_calls", "tool_call_id", "name"}
        items = [{k: v for k, v in m.items() if k in allowed} for m in self.load(session_key)]
        return items[-(limit or self.keep_last):]

    def compact(self, session_key: str, keep_last: int | None = None) -> int:
        """把较早的消息合成一条摘要，返回被压缩的消息数。"""
        keep = keep_last or self.keep_last
        data = self._read_all()
        history = list(data.get(session_key, []))
        if len(history) <= keep:
            return 0
        old, recent = history[:-keep], history[-keep:]
        lines = []
        for message in old:
            role = message.get("role", "")
            content = str(message.get("content", "")).replace("\n", " ")
            if role in ("user", "assistant") and content:
                lines.append(f"{role}: {content[:100]}")
            elif role == "tool":
                lines.append(f"工具结果: {content[:80]}")
        summary = {
            "role": "system",
            "content": "以下是本次会话较早的简要记录：\n" + "\n".join(lines[-8:]),
            "ts": datetime.now().isoformat(timespec="seconds"),
        }
        data[session_key] = [summary] + recent
        self._write_all(data)
        return len(old)

    def clear(self, session_key: str) -> None:
        data = self._read_all()
        data.pop(session_key, None)
        self._write_all(data)
