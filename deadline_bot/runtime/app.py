"""统一组装入口：把 Runtime 各层拼成一个可直接使用的 DeadlineAgent。

设计来源：nanobot 启动时在 ``AgentLoop`` 之外组装 bus / session manager /
tool registry / cron service，然后把它们注入内核。这里把同样的装配过程收进
一个类，做到「渠道只依赖一个 agent 对象」：

    agent = build_agent()                 # 一行组装
    result = agent.chat("帮我记一下……")   # 一轮完整 turn
    agent.tick()                          # 定时任务检查（会注入 inbound）

装配顺序刻意固定：store → scheduler → registry → skills → context → llm → loop。
后面的组件依赖前面的，方向单一，方便讲清楚和替换实现。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from .. import TaskStore
from .context import ContextBuilder
from .llm import LLM, build_llm
from .loop import AgentLoop, AgentResult
from .memory import SessionMemory
from .messages import InboundMessage, MessageBus, OutboundMessage
from .scheduler import CronService
from .skills import SkillsLoader
from .tools import ToolRegistry, build_default_registry
from .trace import Trace

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = PROJECT_ROOT / "data"


@dataclass
class RuntimeInfo:
    """给 /api/health 与日志用的一份运行时自述。"""

    llm: str
    tools: list[str]
    data_dir: str
    skills: list[str]
    version: str = "0.2.0"

    def to_dict(self) -> dict[str, Any]:
        return {
            "llm": self.llm,
            "tools": self.tools,
            "data_dir": self.data_dir,
            "skills": self.skills,
            "version": self.version,
        }


class DeadlineAgent:
    """整个应用的门面。渠道层只需要调用 chat / tick / state。"""

    def __init__(
        self,
        data_dir: str | Path = DEFAULT_DATA_DIR,
        *,
        llm: LLM | None = None,
        prefer_rule: bool = False,
        skill_roots: tuple[str | Path, ...] | None = None,
        max_iterations: int = 6,
    ) -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # 1. 领域状态（任务记忆）
        self.store = TaskStore(self.data_dir / "tasks.json")

        # 2. 会话记忆 / 主动调度
        self.memory = SessionMemory(self.data_dir / "sessions.json")
        self.scheduler = CronService(self.data_dir / "cron.json")

        # 3. 消息总线（渠道解耦）
        self.bus = MessageBus()

        # 4. 工具注册表（把 core 能力暴露给模型）
        self.registry: ToolRegistry = build_default_registry(self.store, self.scheduler)

        # 5. 技能说明书 + 上下文构建
        roots = skill_roots or (PROJECT_ROOT / "SKILL.md", PROJECT_ROOT / "skills")
        self.skills = SkillsLoader(*[Path(r) for r in roots])
        self.context = ContextBuilder(self.store, self.skills)

        # 6. 模型层（无 key 自动降级 RulePlanner）
        self.llm: LLM = llm or build_llm(prefer_rule=prefer_rule)

        # 7. 主循环
        self.loop = AgentLoop(
            self.bus, self.registry, self.llm, self.context, self.memory,
            max_iterations=max_iterations,
        )

        self.last_result: AgentResult | None = None
        self._turn_count = 0

    # ---------- 对外主接口 ----------

    def chat(
        self,
        text: str,
        *,
        channel: str = "cli",
        chat_id: str = "local",
        sender_id: str = "user",
    ) -> AgentResult:
        result = self.loop.run(
            text, channel=channel, chat_id=chat_id, sender_id=sender_id
        )
        self.last_result = result
        self._turn_count += 1
        return result

    def handle(self, inbound: InboundMessage) -> AgentResult:
        """渠道层拿到原生消息后可直接调这个，不必自己拼 run 参数。"""
        result = self.loop.handle(inbound)
        self.last_result = result
        self._turn_count += 1
        return result

    def tick(self, now: datetime | None = None) -> list[str]:
        """检查定时任务；到点就注入 inbound 并跑一轮完整 AgentLoop。"""
        return self.scheduler.tick(self.bus, self.loop, now=now)

    def drain_outbound(self) -> list[OutboundMessage]:
        """取走待发给渠道的回复（HTTP / 飞书适配器用）。"""
        out: list[OutboundMessage] = []
        while True:
            msg = self.bus.consume_outbound()
            if msg is None:
                break
            out.append(msg)
        return out

    def state(self) -> dict[str, Any]:
        return {"tasks": [t.to_dict() for t in self.store.load()]}

    def info(self) -> RuntimeInfo:
        return RuntimeInfo(
            llm=self.llm.name,
            tools=self.registry.tool_names,
            data_dir=str(self.data_dir),
            skills=[s.name for s in self.skills.list_skills()],
        )

    @property
    def last_trace(self) -> Trace:
        return self.last_result.trace if self.last_result else Trace()

    @property
    def turn_count(self) -> int:
        return self._turn_count


def build_agent(data_dir: str | Path | None = None, **kwargs: Any) -> DeadlineAgent:
    """工厂函数：默认落在仓库 data/，测试可传临时目录避免污染真实数据。"""
    return DeadlineAgent(data_dir or DEFAULT_DATA_DIR, **kwargs)
