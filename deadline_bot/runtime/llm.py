"""模型层：OpenAI-compatible 客户端 + 零密钥规则规划器。

设计来源：nanobot 把模型抽象成 provider，``AgentRunner`` 只依赖一个契约——
「一次调用要么返回文本，要么返回 tool_calls」。这里保留同样契约。

``RulePlanner`` 不是模型，而是实现同一契约的可测试替身：没有 API key 时，
它用关键词识别意图并直接产出 tool_calls，因此**完整的工具调用循环依然能跑**，
离线演示和单元测试不受网络影响。有 key 时换成 ``OpenAICompatLLM`` 即可，
主循环一行都不用改。
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any


@dataclass
class LLMResponse:
    content: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)

    @property
    def has_tool_calls(self) -> bool:
        return bool(self.tool_calls)


class LLM:
    """所有模型实现都要满足的最小契约。"""

    name = "base"

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> LLMResponse:
        raise NotImplementedError


class OpenAICompatLLM(LLM):
    """标准 /chat/completions + tools，通用于 OpenAI / DeepSeek / 通义等兼容服务。"""

    name = "openai-compatible"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: int = 30,
    ) -> None:
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        self.base_url = (base_url or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")).rstrip("/")
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.timeout = timeout
        if not self.api_key:
            raise RuntimeError("需要设置 OPENAI_API_KEY")

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> LLMResponse:
        payload = {
            "model": self.model,
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
            "temperature": 0,
        }
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
            message = body["choices"][0]["message"]
        except (urllib.error.URLError, KeyError, json.JSONDecodeError) as exc:
            # 与工具错误一样：把失败变成可恢复的文本，而不是让循环崩掉
            return LLMResponse(content=f"模型调用失败：{exc}")
        return LLMResponse(
            content=message.get("content") or "",
            tool_calls=message.get("tool_calls") or [],
        )


def _call(name: str, args: dict[str, Any], seq: int = 0) -> dict[str, Any]:
    return {
        "id": f"call_{seq}_{name}",
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(args, ensure_ascii=False)},
    }


class RulePlanner(LLM):
    """离线意图规划器：关键词 → tool_calls，用于演示与回归测试。

    它不是「假装 AI」，而是把「模型决定调哪个工具」这一步替换成确定性规则，
    从而让 AgentLoop 的所有其他部分（上下文、注册表、错误回喂、trace、记忆）
    都能在没有密钥、没有网络的情况下被真实执行和验证。
    """

    name = "rule-planner"

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> LLMResponse:
        last = messages[-1] if messages else {}

        # 工具结果回来后，把本轮所有工具结果汇总成面向人的最终回复
        if last.get("role") == "tool":
            results: list[str] = []
            for message in reversed(messages):
                if message.get("role") != "tool":
                    break
                results.append(str(message.get("content", "")))
            results.reverse()
            return LLMResponse(content=self._summarize(results))

        user_text = self._last_user_text(messages)
        if not user_text:
            return LLMResponse(content="你好，我可以帮你记录通知、排执行顺序、看每日进度。")

        # 复合意图：一次 turn 里编排两个工具，用来演示多轮/多工具调用
        if self._wants_add(user_text) and re.search(r"先做|顺序|排一下|优先级", user_text):
            return LLMResponse(tool_calls=[
                _call("add_notices", {"text": user_text}, 0),
                _call("get_plan", {"top": 5}, 1),
            ])

        if self._wants_add(user_text):
            return LLMResponse(tool_calls=[_call("add_notices", {"text": user_text})])

        # 「每天早上 8 点提醒我……」必须排在「进度」「截止」等查询之前，
        # 否则会被当成一次普通日报请求，agent 就永远不会变得主动。
        if re.search(r"每天|定时|自动提醒|设置一个?提醒|提醒我", user_text):
            return LLMResponse(tool_calls=[_call("schedule_reminder", {
                "cron_expr": "0 8 * * *",
                "message": "生成今日任务进度与截止提醒",
            })])

        match = re.search(r"t_[0-9a-z]{6,10}", user_text)
        if match and re.search(r"完成|做完|开始|延后|改|删除|进度", user_text):
            args: dict[str, Any] = {"task_id": match.group(0)}
            if "完成" in user_text or "做完" in user_text:
                args.update(status="done", progress=100)
            elif "开始" in user_text:
                args.update(status="in_progress", progress=10)
            elif "延后" in user_text or "改" in user_text:
                tail = re.search(r"(?:延后|改(?:到|为)?)\s*([^\s，。]+)", user_text)
                if tail:
                    args["due_text"] = tail.group(1)
            if len(args) > 1:
                return LLMResponse(tool_calls=[_call("update_task", args)])

        if re.search(r"先做|顺序|优先级|plan|该做", user_text, re.I):
            return LLMResponse(tool_calls=[_call("get_plan", {"top": 5})])
        if re.search(r"进度|今天|日报|完成率|做得怎么样", user_text):
            return LLMResponse(tool_calls=[_call("get_daily", {})])
        if re.search(r"到期|截止|提醒|deadline|要交", user_text, re.I):
            return LLMResponse(tool_calls=[_call("get_due", {})])
        if re.search(r"有哪些|全部|列表|看看任务", user_text):
            return LLMResponse(tool_calls=[_call("list_tasks", {})])

        return LLMResponse(content=(
            "我可以帮你：把一段通知拆成多条任务、按内容排执行顺序、看每日进度和截止提醒。"
            "直接把通知粘给我，或者说「今天先做什么」。"
        ))

    @staticmethod
    def _last_user_text(messages: list[dict[str, Any]]) -> str:
        for message in reversed(messages):
            if message.get("role") == "user":
                content = message.get("content")
                return content if isinstance(content, str) else str(content or "")
        return ""

    @staticmethod
    def _wants_add(text: str) -> bool:
        if re.search(r"记一下|帮我记|添加|录入|导入|粘贴|收到通知", text):
            return True
        # 含明确日期表达的长文本，视为「一条通知」而不是提问
        return bool(re.search(r"\d{1,2}月\d{1,2}日|周[一二三四五]|明天|后天|\d+天内|20\d{2}年", text)
                    and len(text) >= 12
                    and not text.rstrip().endswith("?"))

    @staticmethod
    def _summarize(results: list[str]) -> str:
        bodies = [r.strip() for r in results if r.strip()]
        if not bodies:
            return "处理好了，但工具没有返回内容。"
        if any(b.startswith("[请结合") or "错误：" in b or "执行失败" in b for b in bodies):
            return "这一步没成功，我换一种方式再试。\n\n" + bodies[-1]
        if len(bodies) == 1:
            return f"处理好了，结果如下：\n\n{bodies[0]}"
        joined = "\n\n".join(f"（{i}）{b}" for i, b in enumerate(bodies, 1))
        return f"处理好了，这一步共执行了 {len(bodies)} 个工具：\n\n{joined}"


def build_llm(prefer_rule: bool = False) -> LLM:
    """有 key 用真模型，没有 key 自动降级到规则规划器——保证 demo 永远能跑。"""
    if prefer_rule or not os.getenv("OPENAI_API_KEY"):
        return RulePlanner()
    return OpenAICompatLLM()
