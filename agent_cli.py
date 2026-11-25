#!/usr/bin/env python3
"""交互式 Agent 入口：直接和 Agent Runtime 对话（区别于 cli.py 的命令式子命令）。

    python agent_cli.py                      # 进入对话
    python agent_cli.py --trace             # 每次显示工具调用链
    python agent_cli.py --once "今天先做什么"  # 跑一轮就退出
    python agent_cli.py --demo              # 自动跑一段完整演示
    python agent_cli.py --data-dir /tmp/x    # 用独立数据目录，不污染真实任务

cli.py 是「确定性命令工具」，agent_cli.py 走的是完整的
MessageBus → ContextBuilder → AgentLoop → ToolRegistry → 回复 链路。
两者共用同一份 core 代码和同一份数据。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from deadline_bot.runtime import DeadlineAgent  # noqa: E402
from deadline_bot.runtime.channels import CLIChannel  # noqa: E402

DEMO_TURNS = [
    "帮我记一下：1. 地理信息系统课程设计 12月5日前交；2. Java语言大作业 12月19日前交；3. 遥感地学分析课程论文 17周前交",
    "今天先做什么？",
    "进度怎么样？",
    "每天早上 8 点提醒我生成今日任务进度与截止提醒",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="DeadlineBot Agent Runtime 交互式入口")
    parser.add_argument("--data-dir", default=None, help="数据目录，默认仓库 data/")
    parser.add_argument("--prefer-rule", action="store_true", help="强制离线 RulePlanner，不调用真实模型")
    parser.add_argument("--trace", action="store_true", help="显示每轮的工具调用链")
    parser.add_argument("--once", default=None, help="只跑一轮对话后退出")
    parser.add_argument("--demo", action="store_true", help="自动演示多轮工具调用")
    args = parser.parse_args()

    agent = DeadlineAgent(
        data_dir=args.data_dir or str(ROOT / "data"),
        prefer_rule=args.prefer_rule,
    )
    channel = CLIChannel(show_trace=args.trace)

    if args.once:
        result = agent.chat(args.once, channel="cli")
        print(channel.format_reply(result))
        return

    if args.demo:
        print("=== DeadlineBot Agent Runtime 演示 ===\n")
        for turn in DEMO_TURNS:
            print(f"你 > {turn}")
            result = agent.chat(turn, channel="cli", chat_id="demo")
            print(f"agent > {result.reply}")
            print(f"[tools: {', '.join(result.tools_used) or '无'} | {result.iterations} 轮]\n")
        print("=== trace（最后一轮）===")
        print(agent.last_trace.text())
        print("\n=== 定时任务 ===")
        for job in agent.scheduler.list():
            print(f"  {job.job_id}  {job.cron_expr}  {job.message}")
        print("\n=== 会话记忆 ===")
        print(f"  cli:demo 共 {len(agent.memory.load('cli:demo'))} 条")
        return

    channel.run(agent)


if __name__ == "__main__":
    main()
