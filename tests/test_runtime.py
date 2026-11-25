"""Agent Runtime 回归测试。

这一组测试针对的是「内核」而不是「解析」：消息总线、工具契约、多轮循环、
定时主动性、会话记忆、渠道适配。所有测试都在临时目录跑，不碰真实任务数据，
也完全不需要 OPENAI_API_KEY——这正是 RulePlanner 存在的意义。

运行：python -m unittest discover -s tests -v
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from deadline_bot.runtime import (  # noqa: E402
    AgentLoop, CronService, DeadlineAgent, InboundMessage, LLM, LLMResponse,
    MessageBus, OutboundMessage, RulePlanner, SessionMemory, ToolRegistry,
    ToolResult, ToolSpec, build_agent,
)
from deadline_bot.runtime.channels import (  # noqa: E402
    HTTPChannel, NanobotChannel,
)
from deadline_bot.runtime.tools import _obj  # noqa: E402

FOUR_ITEMS = """帮我记一下这条通知：
注意：
1.《地理信息系统设计与应用》课程设计14周（12月5日）前交;
2.《地理信息系统设计与应用》实验报告14周（12月13日）前交;
3.Java语言大作业16周前（12月19日）交;
4.遥感地学分析课程论文17周前交;"""


class RuntimeTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.data_dir = Path(self._tmp.name)
        self.agent = DeadlineAgent(
            self.data_dir, prefer_rule=True, skill_roots=(self.data_dir / "SKILL.md",)
        )


class TestMessageBus(RuntimeTestCase):
    def test_session_key_is_channel_scoped(self):
        a = InboundMessage("cli", "u1", "chat1", "hi")
        b = InboundMessage("http", "u1", "chat1", "hi")
        self.assertEqual(a.session_key, "cli:chat1")
        self.assertEqual(b.session_key, "http:chat1")
        self.assertNotEqual(a.session_key, b.session_key)
        self.assertTrue(a.is_user_input)

    def test_queues_are_independent(self):
        bus = MessageBus()
        bus.publish_inbound(InboundMessage("cli", "u", "c", "in"))
        bus.publish_outbound(OutboundMessage("cli", "c", "out"))
        self.assertEqual(bus.inbound_size, 1)
        self.assertEqual(bus.outbound_size, 1)
        self.assertEqual(bus.consume_inbound().content, "in")
        self.assertEqual(bus.consume_outbound().content, "out")
        self.assertIsNone(bus.consume_inbound())
        self.assertEqual(bus.inbound_size, 0)

    def test_subscriber_exception_does_not_break_publish(self):
        bus = MessageBus()
        seen: list[str] = []

        def bad(kind, payload):
            raise RuntimeError("observer down")

        bus.subscribe(bad)
        bus.subscribe(lambda kind, payload: seen.append(kind))
        bus.publish_inbound(InboundMessage("cli", "u", "c", "hi"))
        self.assertEqual(seen, ["inbound"])
        self.assertEqual(bus.inbound_size, 1)


class TestToolRegistry(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = ToolRegistry()
        self.registry.register(ToolSpec(
            name="echo", description="echo", parameters=_obj(
                {"text": {"type": "string"}}, ["text"]
            ), handler=lambda text: f"ok:{text}",
        ))
        self.registry.register(ToolSpec(
            name="boom", description="boom", parameters=_obj({}),
            handler=lambda: 1 / 0,
        ))

    def test_definitions_sorted_and_cached(self):
        first = self.registry.definitions()
        self.assertEqual(self.registry.tool_names, ["boom", "echo"])
        self.assertIs(first, self.registry.definitions())
        self.assertEqual([d["function"]["name"] for d in first], ["boom", "echo"])

    def test_missing_required_arg_is_recoverable_text(self):
        result = self.registry.execute("echo", {})
        self.assertTrue(result.is_error)
        self.assertIn("缺少必填参数 text", result)
        self.assertIn("[请结合", result)

    def test_unknown_tool_suggests_close_match(self):
        result = self.registry.execute("ech", {"text": "x"})
        self.assertTrue(result.is_error)
        self.assertIn("是否想用 'echo'", result)

    def test_handler_exception_is_not_raised(self):
        result = self.registry.execute("boom", {})
        self.assertIsInstance(result, ToolResult)
        self.assertTrue(result.is_error)
        self.assertIn("执行失败", result)

    def test_string_arguments_are_coerced(self):
        self.assertEqual(self.registry.execute("echo", '{"text":"hi"}'), "ok:hi")
        # 非 JSON 的纯文本会兜底成 {"text": "..."}，兼容模型偶尔漏传 JSON 的情况
        self.assertEqual(self.registry.execute("echo", "hi"), "ok:hi")
        self.assertTrue(self.registry.execute("echo", 123).is_error)

    def test_wrong_type_is_rejected(self):
        result = self.registry.execute("echo", {"text": 123})
        self.assertTrue(result.is_error)
        self.assertIn("应为字符串", result)


class TestRulePlanner(unittest.TestCase):
    def setUp(self) -> None:
        self.planner = RulePlanner()

    def test_add_intent_produces_tool_call(self):
        response = self.planner.chat([{"role": "user", "content": FOUR_ITEMS}], [])
        self.assertTrue(response.has_tool_calls)
        self.assertEqual(response.tool_calls[0]["function"]["name"], "add_notices")

    def test_compound_intent_produces_two_calls(self):
        text = "帮我记一下：1.课程设计 12月5日前交；2.Java大作业 12月19日前交，排一下先做什么"
        response = self.planner.chat([{"role": "user", "content": text}], [])
        names = [c["function"]["name"] for c in response.tool_calls]
        self.assertEqual(names, ["add_notices", "get_plan"])

    def test_tool_results_become_final_text(self):
        messages = [
            {"role": "user", "content": "x"},
            {"role": "assistant", "content": "", "tool_calls": []},
            {"role": "tool", "content": "结果一"},
            {"role": "tool", "content": "结果二"},
        ]
        response = self.planner.chat(messages, [])
        self.assertFalse(response.has_tool_calls)
        self.assertIn("共执行了 2 个工具", response.content)
        self.assertIn("结果一", response.content)
        self.assertIn("结果二", response.content)

    def test_error_result_is_reported_as_retry(self):
        response = self.planner.chat([{"role": "tool", "content": "[请结合] 错误：缺少参数"}], [])
        self.assertIn("换一种方式", response.content)


class TestAgentLoop(RuntimeTestCase):
    def test_multi_turn_tool_calling(self):
        result = self.agent.chat(FOUR_ITEMS, channel="cli", chat_id="t1")
        self.assertIn("add_notices", result.tools_used)
        self.assertGreaterEqual(result.iterations, 2)  # 工具轮 + 回复轮
        self.assertEqual(result.stop_reason, "completed")
        self.assertIn("拆出 4 项", result.reply)
        self.assertEqual(result.session_key, "cli:t1")

    def test_trace_contains_full_chain(self):
        result = self.agent.chat(FOUR_ITEMS, channel="cli", chat_id="t1")
        kinds = {event.kind for event in result.trace.events}
        self.assertTrue({"model", "tool_call", "tool_result", "final"} <= kinds)
        self.assertIn("add_notices", result.trace.tool_names())
        self.assertGreater(len(result.trace.text()), 20)

    def test_compound_intent_executes_two_tools_in_one_turn(self):
        text = "帮我记一下：1.课程设计 12月5日前交；2.Java大作业 12月19日前交，排一下先做什么"
        result = self.agent.chat(text, channel="cli", chat_id="t2")
        self.assertEqual(result.tools_used, ["add_notices", "get_plan"])
        self.assertIn("共执行了 2 个工具", result.reply)

    def test_inbound_queue_does_not_accumulate(self):
        for i in range(5):
            self.agent.chat(f"有哪些任务 {i}", channel="cli", chat_id="t1")
        self.assertEqual(self.agent.bus.inbound_size, 0)

    def test_outbound_message_is_published(self):
        self.agent.chat("有哪些任务", channel="http", chat_id="w1")
        out = self.agent.drain_outbound()
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].channel, "http")
        self.assertEqual(out[0].metadata["session_key"], "http:w1")

    def test_memory_isolated_by_session_key(self):
        self.agent.chat("有哪些任务", channel="cli", chat_id="a")
        self.agent.chat("有哪些任务", channel="http", chat_id="a")
        self.assertEqual(len(self.agent.memory.load("cli:a")), 2)
        self.assertEqual(len(self.agent.memory.load("http:a")), 2)
        self.agent.memory.clear("cli:a")
        self.assertEqual(self.agent.memory.load("cli:a"), [])
        self.assertEqual(len(self.agent.memory.load("http:a")), 2)  # 另一个渠道不受影响

    def test_max_iterations_guard(self):
        class LoopForever(LLM):
            name = "fake-loop"

            def chat(self, messages, tools):
                return LLMResponse(tool_calls=[{
                    "id": "c1", "type": "function",
                    "function": {"name": "list_tasks", "arguments": "{}"},
                }])

        agent = DeadlineAgent(
            self.data_dir / "guard", llm=LoopForever(), max_iterations=3,
            skill_roots=(self.data_dir / "SKILL.md",),
        )
        result = agent.chat("随便", channel="cli")
        self.assertEqual(result.stop_reason, "max_iterations")
        self.assertEqual(result.iterations, 3)
        self.assertIn("轮数已达上限", result.reply)


class TestCron(RuntimeTestCase):
    def test_trigger_injects_an_inbound_message(self):
        service = CronService(self.data_dir / "cron.json")
        job = service.add("08:00", "生成今日任务进度与截止提醒")
        now = datetime(2026, 1, 5, 8, 0)
        inbound = service.trigger(job, now)
        self.assertIsInstance(inbound, InboundMessage)
        self.assertEqual(inbound.channel, "cron")
        self.assertEqual(inbound.session_key, "cron:" + job.job_id)
        self.assertEqual(inbound.metadata["job_id"], job.job_id)

    def test_tick_runs_the_same_agent_loop(self):
        self.agent.scheduler.add("every:3600", "生成今日任务进度与截止提醒")
        replies = self.agent.tick(now=datetime(2026, 1, 5, 8, 0))
        self.assertEqual(len(replies), 1)
        self.assertIn("处理好了", replies[0])
        self.assertEqual(self.agent.bus.inbound_size, 0)

    def test_daily_job_runs_only_once_per_day(self):
        service = CronService(self.data_dir / "cron2.json")
        job = service.add("08:00", "生成今日任务进度")
        now = datetime(2026, 1, 5, 8, 0)
        self.assertEqual(len(service.due_jobs(now)), 1)
        service.trigger(job, now)
        self.assertEqual(len(service.due_jobs(now)), 0)
        self.assertEqual(len(service.due_jobs(datetime(2026, 1, 6, 8, 0))), 1)

    def test_disable_and_remove(self):
        service = CronService(self.data_dir / "cron3.json")
        job = service.add("every:60", "提醒")
        self.assertTrue(service.set_enabled(job.job_id, False))
        self.assertEqual(service.due_jobs(datetime(2026, 1, 5, 8, 0)), [])
        self.assertTrue(service.remove(job.job_id))
        self.assertFalse(service.remove(job.job_id))

    def test_schedule_reminder_through_agent_tool(self):
        result = self.agent.chat("每天早上 8 点提醒我生成今日任务进度", channel="cli")
        self.assertIn("schedule_reminder", result.tools_used)
        self.assertEqual(len(self.agent.scheduler.list()), 1)


class TestSessionMemory(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.memory = SessionMemory(Path(self._tmp.name) / "sessions.json", keep_last=5)

    def test_compact_keeps_summary_instead_of_dropping(self):
        for i in range(20):
            self.memory.append("cli:c", {"role": "user", "content": f"msg{i}"})
        history = self.memory.load("cli:c")
        self.assertEqual(len(history), 6)  # 1 摘要 + 最近 5
        self.assertEqual(history[0]["role"], "system")
        self.assertIn("简要记录", history[0]["content"])
        self.assertEqual(history[-1]["content"], "msg19")

    def test_history_only_exposes_model_fields(self):
        self.memory.append("cli:c", {"role": "user", "content": "hi", "ts": "x", "debug": 1})
        item = self.memory.history("cli:c")[0]
        self.assertEqual(set(item), {"role", "content"})

    def test_clear(self):
        self.memory.append("cli:c", {"role": "user", "content": "hi"})
        self.memory.clear("cli:c")
        self.assertEqual(self.memory.load("cli:c"), [])


class TestChannels(RuntimeTestCase):
    def test_http_channel_returns_reply_and_trace(self):
        channel = HTTPChannel()
        payload, status = channel.handle(self.agent, {"text": "有哪些任务", "chat_id": "w1"})
        self.assertEqual(status, 200)
        self.assertEqual(payload["session_key"], "http:w1")
        self.assertIn("trace", payload)
        self.assertIsInstance(payload["trace"], list)

    def test_http_channel_rejects_empty_text(self):
        payload, status = HTTPChannel().handle(self.agent, {"text": "  "})
        self.assertEqual(status, 400)
        self.assertIn("error", payload)

    def test_nanobot_channel_is_just_another_channel(self):
        reply = NanobotChannel().invoke(self.agent, "due")
        self.assertIsInstance(reply, str)
        self.assertGreater(len(reply), 10)
        self.assertEqual(self.agent.last_result.session_key.startswith("nanobot:"), True)

    def test_to_inbound_defaults(self):
        inbound = HTTPChannel().to_inbound({"text": "hi"})
        self.assertEqual(inbound.channel, "http")
        self.assertEqual(inbound.chat_id, "web")


class TestEndToEnd(RuntimeTestCase):
    def test_notice_to_plan_pipeline(self):
        result = self.agent.chat(FOUR_ITEMS, channel="cli", chat_id="e2e")
        tasks = self.agent.store.load()
        self.assertEqual(len(tasks), 4)
        titles = [t.title for t in tasks]
        self.assertTrue(any("课程设计" in t for t in titles))
        self.assertTrue(any("Java" in t for t in titles))
        self.assertIn("拆出 4 项", result.reply)

        plan = self.agent.chat("今天先做什么？", channel="cli", chat_id="e2e")
        self.assertIn("get_plan", plan.tools_used)
        self.assertIn("理由", plan.reply)

    def test_update_task_via_natural_language(self):
        self.agent.chat(FOUR_ITEMS, channel="cli", chat_id="upd")
        task = self.agent.store.load()[0]
        result = self.agent.chat(f"{task.id} 做完了", channel="cli", chat_id="upd")
        self.assertIn("update_task", result.tools_used)
        self.assertEqual(self.agent.store.get(task.id).status, "done")
        self.assertEqual(self.agent.store.get(task.id).progress, 100)

    def test_runtime_info(self):
        info = self.agent.info()
        self.assertEqual(info.llm, "rule-planner")
        self.assertIn("add_notices", info.tools)
        self.assertIn("get_plan", info.tools)
        self.assertEqual(len(self.agent.registry.definitions()), len(info.tools))

    def test_factory_builds_in_custom_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            agent = build_agent(tmp, prefer_rule=True)
            self.assertEqual(Path(agent.info().data_dir), Path(tmp))


if __name__ == "__main__":
    unittest.main(verbosity=2)
