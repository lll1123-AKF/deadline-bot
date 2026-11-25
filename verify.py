#!/usr/bin/env python3
"""一键自检：验证项目是否处于健康状态。

运行：python verify.py
检查项：语法、单元测试、CLI 可用性、核心场景、持久化、去重。
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

RESULTS: list[tuple[bool, str, str]] = []


def record(ok: bool, name: str, detail: str = "") -> None:
    RESULTS.append((ok, name, detail))
    mark = "PASS" if ok else "FAIL"
    print(f"[{mark}] {name}" + (f" — {detail}" if detail else ""))


def run_cmd(args: list[str]) -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable] + args, cwd=ROOT, capture_output=True, text=True, encoding="utf-8"
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def main() -> None:
    print("=" * 68)
    print("deadline-bot 自检")
    print("=" * 68)

    # 1. 语法编译
    code, out = run_cmd(["-m", "compileall", "-q", "."])
    record(code == 0, "Python 语法编译", out.strip()[:80])

    # 2. 单元测试
    code, out = run_cmd(["-m", "unittest", "discover", "-s", "tests"])
    tail = out.strip().splitlines()
    summary = next((line for line in reversed(tail) if "Ran " in line), "")
    record(code == 0 and "OK" in out, "单元测试", summary)

    # 3. CLI 帮助（曾因 % 字符崩溃，专门测）
    for sub in ["--help", "add --help", "update --help", "plan --help", "daily --help"]:
        code, out = run_cmd(["cli.py"] + sub.split())
        record(code == 0 and "Traceback" not in out, f"CLI {sub}")

    # 4. 核心场景：解析 -> 存储 -> 重排 -> 完成
    from deadline_bot import TaskStore, build_plan, parse_notice, parse_due
    from deadline_bot.models import now_local

    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "tasks.json"
        store = TaskStore(db)
        notice = "教务处通知：2026年11月30日前提交选课确认表"
        task = parse_notice(notice, now_local())
        added, info = store.add(task)
        record(added and store.get(info) is not None, "解析并写入任务")

        again, _ = store.add(parse_notice(notice, now_local()))
        record(not again, "重复任务去重")

        due, raw = parse_due("下周二下午3点", now_local())
        record(due is not None and due.hour == 15, "自然语言改期解析", raw)

        store.update(info, priority="high", progress=40, status="in_progress")
        t = store.get(info)
        record(t.priority == "high" and t.progress == 40 and t.status == "in_progress",
               "动态修改字段")

        plan = build_plan(store.load(), now=now_local())
        record(task.title in plan and "理由" in plan, "内容排序含理由")

        store.update(info, status="done", progress=99)
        record(store.get(info).progress == 100, "完成状态一致性")

    # 5. 数据文件完整性
    sample = ROOT / "data" / "sample_notices.txt"
    record(sample.exists() and len([l for l in sample.read_text(encoding="utf-8").splitlines()
                                    if l.strip() and not l.startswith("#")]) >= 8,
           "示例通知完整")

    passed = sum(1 for ok, _, _ in RESULTS if ok)
    total = len(RESULTS)
    print("=" * 68)
    print(f"结果：{passed}/{total} 通过")
    if passed == total:
        print("项目状态健康。")
    else:
        print("有检查未通过，请按上面的 FAIL 项修复。")
    print("=" * 68)
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
