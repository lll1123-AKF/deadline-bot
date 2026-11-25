"""渠道适配器：同一套 AgentLoop，三种接入方式。

设计来源：nanobot 的 ``channels/``（CLI / WebUI / 飞书 / Discord / Email）。
每个渠道只做两件事：把外部输入变成 InboundMessage、把 OutboundMessage 变回
外部能理解的格式。内核完全不知道消息来自哪里——这正是 MessageBus 的价值。

本项目的渠道：
    CLIChannel      可交互命令行（本地开发、面试现场演示）
    HTTPChannel     把 HTTP 请求转成一轮 turn，供 server.py 与网页调用
    NanobotChannel 可选适配器：让外部 agent 框架把本项目当工具能力接入
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .messages import InboundMessage, OutboundMessage

if TYPE_CHECKING:
    from .app import DeadlineAgent
    from .loop import AgentResult


class Channel:
    """渠道协议：name + to_inbound + format_reply。"""

    name = "base"

    def to_inbound(self, payload: Any, **kwargs: Any) -> InboundMessage:
        raise NotImplementedError

    def format_reply(self, result: "AgentResult", **kwargs: Any) -> Any:
        raise NotImplementedError


def _result_dict(result: "AgentResult", *, include_trace: bool = True) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "reply": result.reply,
        "session_key": result.session_key,
        "tools_used": result.tools_used,
        "iterations": result.iterations,
        "stop_reason": result.stop_reason,
    }
    if include_trace:
        payload["trace"] = result.trace.to_list()
    return payload


class CLIChannel(Channel):
    """交互式命令行。支持 slash 命令查看运行时内部状态。"""

    name = "cli"

    def __init__(self, chat_id: str = "cli", show_trace: bool = False) -> None:
        self.chat_id = chat_id
        self.show_trace = show_trace

    def to_inbound(self, payload: Any, **kwargs: Any) -> InboundMessage:
        return InboundMessage(
            channel=self.name, sender_id="user", chat_id=self.chat_id, content=str(payload)
        )

    def format_reply(self, result: "AgentResult", **kwargs: Any) -> str:
        lines = [result.reply]
        if self.show_trace or kwargs.get("force_trace"):
            lines.append("\n--- trace ---\n" + result.trace.text())
        return "\n".join(lines)

    def run(self, agent: "DeadlineAgent") -> None:
        print("DeadlineBot Agent Runtime 已启动。输入 /help 看命令，/quit 退出。\n")
        runtime = agent.info()
        print(f"[runtime] 模型={runtime.llm}  工具={len(runtime.tools)} 个  技能={runtime.skills}\n")
        while True:
            try:
                text = input("你 > ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n再见。")
                break
            if not text:
                continue
            if text in ("/quit", "/exit", "quit", "exit"):
                print("再见。")
                break
            if text == "/help":
                print("  /help     查看命令\n  /trace    切换显示工具调用链"
                      "\n  /tick     手动检查定时任务\n  /health   运行时信息\n  /quit     退出"
                      "\n其余输入直接发给 agent。")
                continue
            if text == "/trace":
                self.show_trace = not self.show_trace
                print(f"[trace 显示] {'开' if self.show_trace else '关'}")
                continue
            if text == "/health":
                print(agent.info().to_dict())
                continue
            if text == "/tick":
                replies = agent.tick()
                print("\n".join(replies) if replies else "[没有到期的定时任务]")
                continue
            result = agent.chat(text, channel=self.name, chat_id=self.chat_id)
            print("\nagent > " + self.format_reply(result) + "\n")


class HTTPChannel(Channel):
    """HTTP 请求适配器。server.py 只需要把 JSON body 交给 handle()。"""

    name = "http"

    def to_inbound(self, payload: Any, **kwargs: Any) -> InboundMessage:
        body = payload if isinstance(payload, dict) else {}
        return InboundMessage(
            channel=str(body.get("channel") or self.name),
            sender_id=str(body.get("sender_id") or "web"),
            chat_id=str(body.get("chat_id") or "web"),
            content=str(body.get("text") or ""),
        )

    def format_reply(self, result: "AgentResult", **kwargs: Any) -> dict[str, Any]:
        return _result_dict(result, include_trace=bool(kwargs.get("include_trace", True)))

    def handle(self, agent: "DeadlineAgent", payload: dict[str, Any]) -> tuple[dict[str, Any], int]:
        text = str(payload.get("text") or "").strip()
        if not text:
            return {"error": "text 不能为空"}, 400
        inbound = self.to_inbound(payload)
        result = agent.handle(inbound)
        return self.format_reply(result), 200


class NanobotChannel(Channel):
    """可选适配器：外部 agent 框架（如 nanobot）如何把本项目当能力接入。

    注意定位：nanobot 在这里是「渠道之一」，不是项目主体。本项目自带
    MessageBus / Loop / Memory / Scheduler，不依赖外部框架也能独立运行。
    适配器的作用只是把外部 skill 的命令翻译成一轮普通对话。
    """

    name = "nanobot"

    _COMMAND_TEXT = {
        "due": "有哪些任务快要到期？给我截止提醒",
        "plan": "今天先做什么？按内容排一下执行顺序并说明理由",
        "daily": "今天的进度怎么样？给我每日进度报告",
        "list": "列出全部任务",
        "add": "帮我记一下这条通知：{text}",
        "start": "开始做 {text}",
        "finish": "{text} 做完了，标记完成",
        "note": "给 {text} 加一条备注",
    }

    def to_inbound(self, payload: Any, **kwargs: Any) -> InboundMessage:
        command = kwargs.get("command", "due")
        text = str(payload or "")
        template = self._COMMAND_TEXT.get(str(command), "{text}")
        return InboundMessage(
            channel=self.name,
            sender_id=str(kwargs.get("sender_id") or "nanobot"),
            chat_id=str(kwargs.get("chat_id") or "nanobot"),
            content=template.format(text=text),
        )

    def format_reply(self, result: "AgentResult", **kwargs: Any) -> str:
        return result.reply

    def invoke(self, agent: "DeadlineAgent", command: str, text: str = "", **kwargs: Any) -> str:
        inbound = self.to_inbound(text, command=command, **kwargs)
        return self.format_reply(agent.handle(inbound))


def default_channels() -> list[Channel]:
    return [CLIChannel(), HTTPChannel(), NanobotChannel()]
