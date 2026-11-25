#!/usr/bin/env python3
"""一键演示：不装 nanobot、不配 API key 也能看到完整效果。

运行：python demo.py
演示内容：解析示例通知 -> 展示结构化结果 -> 生成分级提醒日报
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from deadline_bot import build_report, build_plan, build_daily, parse_notice
from deadline_bot.models import now_local

SAMPLE = Path(__file__).resolve().parent / "data" / "sample_notices.txt"

NOTICES = [
    "教务处通知：2026年11月30日前提交本学期选课确认表，逾期视为放弃。",
    "班主任通知：本周五下午5点前交社会实践报告，请班长统一收齐。",
    "HR通知：明天下午6点前提交本月工作总结，邮件发送至hr@company.com。",
    "项目组通知：下周三前完成需求评审文档的填写和提交。",
    "财务部通知：3天内报销本季度差旅费用，逾期不予受理。",
]


def main() -> None:
    now = now_local()
    print("=" * 72)
    print("deadline-bot 演示：通知 -> 任务 -> 分级提醒")
    print("=" * 72)
    print(f"当前时间：{now.strftime('%Y-%m-%d %H:%M')}\n")

    tasks = []
    for i, notice in enumerate(NOTICES, 1):
        task = parse_notice(notice, now=now)
        tasks.append(task)
        print(f"[{i}] 原始通知：{notice}")
        print(f"    标题：{task.title}")
        print(f"    截止：{task.due_text()}   剩余：{task.days_left(now):.1f} 天")
        print(f"    来源：{task.source}   类别：{task.category}   优先级：{task.priority}\n")

    print("=" * 72)
    print("生成的提醒日报（可直接交给 nanobot 定时推送）")
    print("=" * 72)
    print(build_report(tasks, now=now))

    print("\n" + "=" * 72)
    print("按任务内容排执行顺序（不是只按截止日）")
    print("=" * 72)
    print(build_plan(tasks, now=now, top=3))

    print("\n" + "=" * 72)
    print("每日进度（模拟已完成 1 条、进行中 1 条）")
    print("=" * 72)
    tasks[0].status, tasks[0].progress = "done", 100
    tasks[1].status, tasks[1].progress = "in_progress", 40
    print(build_daily(tasks, now=now))

    if SAMPLE.exists():
        print("\n提示：data/sample_notices.txt 里有更多示例，可以用")
        print("  python cli.py import data/sample_notices.txt")
        print("批量导入，再用 python cli.py due 查看效果。")


if __name__ == "__main__":
    main()
