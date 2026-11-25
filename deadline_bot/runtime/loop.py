"""AgentLoop：多轮 tool-calling 主循环。

设计来源：nanobot ``agent/runner.py::_run_core``：
    for iteration in range(max_iterations):
        response = model.chat(messages, tools)
        if response.has_tool_calls:
            execute_tool_calls(...)      # 结果回填 messages
            continue
        return response.content         # 没有工具调用 = 可以给最终回复

这里保留同样的骨架与护栏：
- max_iterations 兜底，防止模型陷入无限工具调用
- 工具错误不中断循环，作为文本回喂给模型（由 ToolRegistry 保证）
- 每一轮都记 Trace，可回放「模型为什么这么选」
- 结束后写回 OutboundMessage 与会话记忆

Loop 完全不知道消息来自 CLI、HTTP 还是定时任务——渠道差异由 MessageBus 吸收。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from .context import ContextBuilder
from .llm import LLM
from .memory import SessionMemory
from .messages import InboundMessage, MessageBus, OutboundMessage
from .tools import ToolRegistry
from .trace import Trace


@dataclass
class AgentResult:
    reply: str
    session_key: str
    trace: Trace
    tools_used: list[str] = field(default_factory=list)
    iterations: int = 0
    stop_reason: str = "completed"


class AgentLoop:
    def __init__(
        self,
        bus: MessageBus,
        registry: ToolRegistry,
        llm: LLM,
        context: ContextBuilder,
        memory: SessionMemory,
        *,
        max_iterations: int = 6,
        max_tool_chars: int = 4000,
    ) -> None:
        self.bus = bus
        self.registry = registry
        self.llm = llm
        self.context = context
        self.memory = memory
        self.max_iterations = max_iterations
        self.max_tool_chars = max_tool_chars

    def run(
        self,
        text: str,
        *,
        channel: str = "cli",
        chat_id: str = "local",
        sender_id: str = "user",
    ) -> AgentResult:
        """普通入口：一句用户输入 → 一轮完整 turn。"""
        inbound = InboundMessage(
            channel=channel, sender_id=sender_id, chat_id=chat_id, content=text
        )
        return self.submit(inbound)

    def submit(self, inbound: InboundMessage) -> AgentResult:
        """投递到总线、立即认领、再处理。

        publish 让订阅者能看到事件；consume 保证 inbound 队列不会无限堆积——
        真实渠道（飞书/HTTP 长连接）则是自己 consume 后交给 handle()。
        """
        self.bus.publish_inbound(inbound)
        self.bus.consume_inbound()
        return self.handle(inbound)

    def handle(self, inbound: InboundMessage) -> AgentResult:
        """统一入口：无论来自渠道还是定时任务，都走同一套循环。"""
        key = inbound.session_key
        messages = self.context.build(inbound.content, self.memory.history(key))
        trace = Trace()
        tools_used: list[str] = []
        reply = ""
        stop_reason = "completed"
        iterations = 0

        for step in range(1, self.max_iterations + 1):
            iterations = step
            trace.add(step, "model", self.llm.name,
                      f"{len(messages)} 条消息 / {len(self.registry.definitions())} 个工具")
            response = self.llm.chat(messages, self.registry.definitions())

            if response.has_tool_calls:
                messages.append({
                    "role": "assistant",
                    "content": response.content or "",
                    "tool_calls": response.tool_calls,
                })
                for call in response.tool_calls:
                    fn = call.get("function", {}) or {}
                    name = str(fn.get("name", ""))
                    raw_args = fn.get("arguments", "{}")
                    if isinstance(raw_args, str):
                        try:
                            args = json.loads(raw_args)
                        except json.JSONDecodeError:
                            args = {}
                    else:
                        args = raw_args if isinstance(raw_args, dict) else {}
                    trace.add(step, "tool_call", name, json.dumps(args, ensure_ascii=False))
                    result = self.registry.execute(name, args)
                    body = str(result)[: self.max_tool_chars]
                    trace.add(step, "tool_result", name, body)
                    tools_used.append(name)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": call.get("id") or name,
                        "name": name,
                        "content": body,
                    })
                continue

            reply = response.content or "（这一轮没有生成回复）"
            trace.add(step, "final", "", reply)
            break
        else:
            reply = "工具调用轮数已达上限，先停在这里。可以说「看看当前执行顺序」继续。"
            stop_reason = "max_iterations"
            trace.add(iterations, "final", "", reply)

        self.bus.publish_outbound(OutboundMessage(
            channel=inbound.channel, chat_id=inbound.chat_id, content=reply,
            metadata={"session_key": key, "tools_used": tools_used},
        ))
        self.memory.extend(key, [
            {"role": "user", "content": inbound.content},
            {"role": "assistant", "content": reply},
        ])
        return AgentResult(
            reply=reply, session_key=key, trace=trace,
            tools_used=tools_used, iterations=iterations, stop_reason=stop_reason,
        )
