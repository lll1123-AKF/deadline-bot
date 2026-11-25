"""DeadlineBot Agent Runtime。

这是本项目的「内核」，与具体渠道、具体领域能力解耦：

    channels/  →  messages.py  →  loop.py  →  tools.py  →  core/
      CLI/HTTP                   AgentLoop     ToolRegistry   parser/store
                     ↑                ↑
                 scheduler.py    context.py / memory.py / skills.py

模块一览：
    messages   InboundMessage / OutboundMessage / MessageBus，session_key 隔离
    trace      一次 turn 的模型调用 / 工具调用 / 结果回放
    llm        LLM 契约、OpenAI-compatible 实现、离线 RulePlanner
    memory     SessionMemory，按会话持久化 + 历史压缩
    skills     SkillsLoader，把 SKILL.md 变成可注入的能力说明书
    tools      ToolSpec / ToolRegistry + 默认工具集，含参数校验与错误回喂
    scheduler  CronService，定时触发时注入 InboundMessage（主动性）
    context    ContextBuilder，组装 system prompt + 快照 + 技能 + 历史
    loop       AgentLoop，多轮 tool-calling 主循环
    channels   CLI / HTTP / nanobot 三种渠道适配器
    app        DeadlineAgent，一行代码组装整个运行时

设计对应关系见仓库根目录 ARCHITECTURE.md。
"""

from .app import DeadlineAgent, build_agent
from .context import ContextBuilder
from .llm import LLM, LLMResponse, OpenAICompatLLM, RulePlanner, build_llm
from .loop import AgentLoop, AgentResult
from .memory import SessionMemory
from .messages import InboundMessage, MessageBus, OutboundMessage
from .scheduler import CronJob, CronService
from .skills import Skill, SkillsLoader
from .tools import ToolRegistry, ToolResult, ToolSpec, build_default_registry
from .trace import Trace, TraceEvent

__all__ = [
    "DeadlineAgent", "build_agent",
    "MessageBus", "InboundMessage", "OutboundMessage",
    "AgentLoop", "AgentResult",
    "ContextBuilder", "SessionMemory", "SkillsLoader", "Skill",
    "ToolRegistry", "ToolSpec", "ToolResult", "build_default_registry",
    "LLM", "LLMResponse", "OpenAICompatLLM", "RulePlanner", "build_llm",
    "CronService", "CronJob", "Trace", "TraceEvent",
]
