"""消息信封与消息总线。

设计来源：nanobot 的 ``bus/queue.py`` + ``bus/events.py``。
它用两个 asyncio.Queue 把「渠道」和「agent 内核」彻底解耦：渠道只负责投递
InboundMessage、取走 OutboundMessage，内核完全不知道消息来自 CLI 还是飞书。
这里用同步 deque 实现同样契约，保持零依赖、便于单测和教学讲解。

最关键的字段是 ``session_key = f"{channel}:{chat_id}"``——不同入口共享
同一套内核，但会话记忆按这个 key 隔离。
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

EventHandler = Callable[[str, Any], None]


@dataclass
class InboundMessage:
    """从某个渠道进入 agent 的消息。"""

    channel: str
    sender_id: str
    chat_id: str
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def session_key(self) -> str:
        return f"{self.channel}:{self.chat_id}"

    @property
    def is_user_input(self) -> bool:
        return self.channel != "system"


@dataclass
class OutboundMessage:
    """agent 回复给某个渠道的消息。"""

    channel: str
    chat_id: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


class MessageBus:
    """inbound / outbound 双队列 + 事件订阅。

    ``subscribe`` 用于可观测性（日志、trace、UI 进度事件），订阅者异常不会
    影响主流程——这也是 nanobot ``publish`` 里的处理方式。
    """

    def __init__(self) -> None:
        self.inbound: deque[InboundMessage] = deque()
        self.outbound: deque[OutboundMessage] = deque()
        self._handlers: list[EventHandler] = []

    def subscribe(self, handler: EventHandler) -> EventHandler:
        self._handlers.append(handler)
        return handler

    def _emit(self, kind: str, payload: Any) -> None:
        for handler in list(self._handlers):
            try:
                handler(kind, payload)
            except Exception:
                # 观测链路不能拖垮主流程
                continue

    def publish_inbound(self, msg: InboundMessage) -> None:
        self.inbound.append(msg)
        self._emit("inbound", msg)

    def consume_inbound(self) -> InboundMessage | None:
        return self.inbound.popleft() if self.inbound else None

    def publish_outbound(self, msg: OutboundMessage) -> None:
        self.outbound.append(msg)
        self._emit("outbound", msg)

    def consume_outbound(self) -> OutboundMessage | None:
        return self.outbound.popleft() if self.outbound else None

    @property
    def inbound_size(self) -> int:
        return len(self.inbound)

    @property
    def outbound_size(self) -> int:
        return len(self.outbound)
