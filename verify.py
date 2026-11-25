#!/usr/bin/env python3
"""一键自检：验证项目是否处于健康状态。

运行：python verify.py
检查项：语法、单元测试、CLI 可用性、core 核心场景、Agent Runtime 工具循环、
        定时主动性、渠道适配、前端脚本语法、交付文档完整性。
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

    # 6. Agent Runtime：组装、多轮工具调用、定时任务、渠道适配
    from datetime import datetime
    from deadline_bot.runtime import DeadlineAgent
    from deadline_bot.runtime.channels import HTTPChannel

    with tempfile.TemporaryDirectory() as tmp:
        agent = DeadlineAgent(Path(tmp) / "runtime", prefer_rule=True)
        info = agent.info()
        record(info.llm == "rule-planner" and len(info.tools) == 7,
               "Runtime 组装", f"{info.llm} / {len(info.tools)} 个工具")

        multi = ("注意：\n"
                 "1.《地理信息系统设计与应用》课程设计14周（12月5日）前交;\n"
                 "2.《地理信息系统设计与应用》实验报告14周（12月13日）前交;\n"
                 "3.Java语言大作业16周前（12月19日）交;\n"
                 "4.遥感地学分析课程论文17周前交;")
        result = agent.chat("帮我记一下：" + multi, channel="cli", chat_id="verify")
        record("add_notices" in result.tools_used and len(agent.store.load()) == 4,
               "Runtime 多事项通知入库", f"{len(agent.store.load())} 条 / {result.iterations} 轮")

        kinds = {e.kind for e in result.trace.events}
        record({"model", "tool_call", "tool_result", "final"} <= kinds,
               "Runtime 工具调用链可回放")

        plan = agent.chat("今天先做什么？", channel="cli", chat_id="verify")
        record("get_plan" in plan.tools_used and "理由" in plan.reply,
               "Runtime 内容排序工具")

        agent.scheduler.add("every:3600", "生成今日任务进度与截止提醒")
        replies = agent.tick(now=datetime(2026, 1, 5, 8, 0))
        record(len(replies) == 1 and agent.bus.inbound_size == 0,
               "Runtime 定时主动触发")

        payload, status = HTTPChannel().handle(agent, {"text": "有哪些任务", "chat_id": "verify"})
        record(status == 200 and payload["session_key"] == "http:verify" and payload["trace"],
               "Runtime HTTP 渠道适配")

        memory = agent.memory
        for i in range(30):
            memory.append("cli:verify", {"role": "user", "content": f"msg{i}"})
        record(memory.compact("cli:verify") > 0 and memory.load("cli:verify")[0]["role"] == "system",
               "Runtime 会话历史压缩")

    # 7. 新入口脚本可运行
    for script in ["agent_cli.py", "server.py"]:
        code, out = run_cmd([script, "--help"])
        record(code == 0 and "Traceback" not in out, f"{script} 入口")

    # 8. 前端脚本语法（node 存在才检查）
    import shutil
    if shutil.which("node"):
        proc = subprocess.run(["node", "--check", "docs/app.js"], cwd=ROOT,
                              capture_output=True, text=True)
        record(proc.returncode == 0, "前端 JS 语法", (proc.stderr or "").strip()[:80])

    # 9. 交付文档齐备
    docs_needed = ["README.md", "ARCHITECTURE.md", "RESUME_GUIDE.md", "VALIDATION.md"]
    missing = [name for name in docs_needed if not (ROOT / name).is_file()]
    record(not missing, "交付文档齐备", "缺少 " + ", ".join(missing) if missing else "4 份")

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
