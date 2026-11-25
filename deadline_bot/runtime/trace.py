"""可观测性：把一次 turn 的模型调用 / 工具调用 / 工具结果记成一条链。

nanobot 用 hooks 做这件事（``agent/hook.py``、``turn_hooks.py``）。这里保持
最小实现：Trace 只负责记录，不参与决策，方便面试时回放「模型为什么这么选」。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass
class TraceEvent:
    step: int
    kind: str                 # model / tool_call / tool_result / final
    name: str = ""
    payload: str = ""

    def line(self) -> str:
        text = self.payload.replace("\n", " ")
        if len(text) > 160:
            text = text[:160] + "…"
        prefix = f"[{self.step}] {self.kind}"
        if self.name:
            prefix += f" · {self.name}"
        return f"{prefix}  {text}" if text else prefix


class Trace:
    def __init__(self) -> None:
        self.events: list[TraceEvent] = []

    def add(self, step: int, kind: str, name: str = "", payload: str = "") -> None:
        self.events.append(TraceEvent(step=step, kind=kind, name=name, payload=str(payload)))

    def text(self) -> str:
        if not self.events:
            return "（本次没有工具调用）"
        return "\n".join(event.line() for event in self.events)

    def tool_names(self) -> list[str]:
        return [e.name for e in self.events if e.kind == "tool_call"]

    def to_list(self) -> list[dict]:
        return [asdict(e) for e in self.events]

    def __len__(self) -> int:
        return len(self.events)
