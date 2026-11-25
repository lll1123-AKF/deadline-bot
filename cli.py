#!/usr/bin/env python3
"""deadline-bot 命令行入口。

常用命令：
    python cli.py add "班主任通知：本周五前提交社会实践表"
    python cli.py list
    python cli.py due
    python cli.py done <task_id>
    python cli.py import data/sample_notices.txt
    python cli.py report
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from deadline_bot import (
    TaskStore, build_report, build_plan, build_daily, parse_notice, parse_due,
)
from deadline_bot.models import now_local

DEFAULT_DB = Path(__file__).resolve().parent / "data" / "tasks.json"


def cmd_add(args: argparse.Namespace, store: TaskStore) -> None:
    task = parse_notice(args.text, now=now_local(), mode=args.mode)
    added, info = store.add(task)
    if added:
        print(f"[ok] 已创建任务 {info}")
        print(f"     标题：{task.title}")
        print(f"     截止：{task.due_text()}")
        print(f"     来源：{task.source}　类别：{task.category}　优先级：{task.priority}")
    else:
        print(f"[skip] {info}")


def cmd_list(args: argparse.Namespace, store: TaskStore) -> None:
    tasks = store.load()
    if not tasks:
        print("还没有任务。用 add 命令添加一条通知。")
        return
    for task in tasks:
        flag = "x" if task.status == "done" else " "
        print(f"[{flag}] {task.id}  {task.due_text():>16}  {task.category:<6} {task.title}")


def cmd_due(args: argparse.Namespace, store: TaskStore) -> None:
    print(build_report(store.pending(), title="即将到期"))


def cmd_done(args: argparse.Namespace, store: TaskStore) -> None:
    ok = store.set_status(args.task_id, "done")
    print("[ok] 已标记完成" if ok else f"[error] 找不到任务 {args.task_id}")


def cmd_remove(args: argparse.Namespace, store: TaskStore) -> None:
    ok = store.remove(args.task_id)
    print("[ok] 已删除" if ok else f"[error] 找不到任务 {args.task_id}")


def cmd_import(args: argparse.Namespace, store: TaskStore) -> None:
    """从文本文件批量导入，一行一条通知；空行和 # 开头跳过。"""
    path = Path(args.file)
    if not path.exists():
        print(f"[error] 文件不存在：{path}")
        return
    added = skipped = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        task = parse_notice(line, now=now_local(), mode=args.mode)
        ok, _ = store.add(task)
        added += int(ok)
        skipped += int(not ok)
    print(f"[ok] 导入完成：新增 {added} 条，跳过重复 {skipped} 条")


def cmd_report(args: argparse.Namespace, store: TaskStore) -> None:
    print(build_report(store.load(), title=args.title))


def cmd_clear(args: argparse.Namespace, store: TaskStore) -> None:
    removed = store.clear_done()
    print(f"[ok] 清理了 {removed} 条已完成任务")


def cmd_plan(args: argparse.Namespace, store: TaskStore) -> None:
    print(build_plan(store.load(), top=args.top))


def cmd_daily(args: argparse.Namespace, store: TaskStore) -> None:
    print(build_daily(store.load()))


def cmd_update(args: argparse.Namespace, store: TaskStore) -> None:
    """随时改任务：cd cli.py update <id> --due '下周一' --priority high ..."""
    fields = {}
    for key in ("title", "source", "category", "priority", "notes"):
        value = getattr(args, key, None)
        if value is not None:
            fields[key] = value
    if args.progress is not None:
        fields["progress"] = args.progress
    if args.status is not None:
        fields["status"] = args.status
    if args.due is not None:
        due, raw = parse_due(args.due, now_local())
        if due is None:
            print(f"[error] 没识别出新时间：{args.due}（试试 '下周三下午5点'）")
            return
        fields["due_at"] = due
        print(f"      截止日改为 {due.strftime('%Y-%m-%d %H:%M')}（识别到：{raw}）")
    ok = store.update(args.task_id, **fields)
    if not ok:
        print(f"[error] 找不到任务 {args.task_id}")
        return
    task = store.get(args.task_id)
    print(f"[ok] 已更新：{task.title}")
    print(f"     {task.due_text()}　{task.status}　进度 {task.progress}%　优先级 {task.priority}")


def cmd_start(args: argparse.Namespace, store: TaskStore) -> None:
    task = store.get(args.task_id)
    if task is None:
        print(f"[error] 找不到任务 {args.task_id}")
        return
    progress = max(task.progress, 5)
    store.update(args.task_id, status="in_progress", progress=progress)
    print(f"[ok] 已开始：{task.title}（进度 {progress}%）")


def cmd_finish(args: argparse.Namespace, store: TaskStore) -> None:
    ok = store.update(args.task_id, status="done", progress=100)
    print("[ok] 已完成，进度 100%" if ok else f"[error] 找不到任务 {args.task_id}")


def cmd_note(args: argparse.Namespace, store: TaskStore) -> None:
    ok = store.add_note(args.task_id, args.text)
    print("[ok] 备注已追加" if ok else f"[error] 找不到任务 {args.task_id}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="deadline-bot", description="通知转任务助手")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="任务库 JSON 路径")
    sub = parser.add_subparsers(dest="command", required=True)

    p_add = sub.add_parser("add", help="从一条通知创建任务")
    p_add.add_argument("text", help="通知原文")
    p_add.add_argument("--mode", choices=["rule", "llm"], default="rule")
    p_add.set_defaults(func=cmd_add)

    p_list = sub.add_parser("list", help="列出所有任务")
    p_list.set_defaults(func=cmd_list)

    p_due = sub.add_parser("due", help="分级提醒（只看待办）")
    p_due.set_defaults(func=cmd_due)

    p_done = sub.add_parser("done", help="标记任务完成")
    p_done.add_argument("task_id")
    p_done.set_defaults(func=cmd_done)

    p_remove = sub.add_parser("remove", help="删除任务")
    p_remove.add_argument("task_id")
    p_remove.set_defaults(func=cmd_remove)

    p_import = sub.add_parser("import", help="从文本文件批量导入通知")
    p_import.add_argument("file")
    p_import.add_argument("--mode", choices=["rule", "llm"], default="rule")
    p_import.set_defaults(func=cmd_import)

    p_report = sub.add_parser("report", help="生成日报文本")
    p_report.add_argument("--title", default="deadline 日报")
    p_report.set_defaults(func=cmd_report)

    p_clear = sub.add_parser("clear", help="清理已完成任务")
    p_clear.set_defaults(func=cmd_clear)

    p_plan = sub.add_parser("plan", help="按任务内容给出执行顺序")
    p_plan.add_argument("--top", type=int, help="只显示前 N 条")
    p_plan.set_defaults(func=cmd_plan)

    p_daily = sub.add_parser("daily", help="每日进度报告")
    p_daily.set_defaults(func=cmd_daily)

    p_update = sub.add_parser("update", help="随时修改任务")
    p_update.add_argument("task_id")
    p_update.add_argument("--title")
    p_update.add_argument("--due", help="新截止日，支持自然语言如 '下周三下午5点'")
    p_update.add_argument("--priority", choices=["high", "normal", "low"])
    p_update.add_argument("--status", choices=["pending", "in_progress", "done", "cancelled"])
    p_update.add_argument("--progress", type=int, help="进度 0-100 %%")
    p_update.add_argument("--category")
    p_update.add_argument("--source")
    p_update.add_argument("--notes")
    p_update.set_defaults(func=cmd_update)

    p_start = sub.add_parser("start", help="标记开始（进度至少 5%%）")
    p_start.add_argument("task_id")
    p_start.set_defaults(func=cmd_start)

    p_finish = sub.add_parser("finish", help="标记完成（进度 100%%）")
    p_finish.add_argument("task_id")
    p_finish.set_defaults(func=cmd_finish)

    p_note = sub.add_parser("note", help="追加备注")
    p_note.add_argument("task_id")
    p_note.add_argument("text")
    p_note.set_defaults(func=cmd_note)

    return parser


def main() -> None:
    args = build_parser().parse_args()
    store = TaskStore(args.db)
    args.func(args, store)


if __name__ == "__main__":
    main()
