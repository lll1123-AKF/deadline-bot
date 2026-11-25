"""解析器测试：用固定时间做断言，保证日期解析可回归。

运行：python -m unittest discover -s tests -v
"""

from __future__ import annotations

import sys
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deadline_bot import (
    build_report, build_plan, build_daily, parse_due, parse_notice, TaskStore,
)
from deadline_bot.models import Task

NOW = datetime(2026, 11, 25, 10, 0)


class ParseDueTests(unittest.TestCase):
    def test_full_date(self):
        due, raw = parse_due("11月30日前提交选课表", NOW)
        self.assertEqual(due.date().isoformat(), "2026-11-30")
        self.assertEqual(due.hour, 23)

    def test_full_iso_date(self):
        due, _ = parse_due("请在 2026-12-05 之前完成", NOW)
        self.assertEqual(due.date().isoformat(), "2026-12-05")

    def test_tomorrow_with_clock(self):
        due, _ = parse_due("明天下午6点前提交", NOW)
        self.assertEqual(due.date().isoformat(), "2026-11-26")
        self.assertEqual((due.hour, due.minute), (18, 0))

    def test_this_weekday(self):
        due, _ = parse_due("本周五下午5点前交报告", NOW)
        self.assertEqual(due.date().isoformat(), "2026-11-27")

    def test_next_weekday(self):
        due, _ = parse_due("下周三前完成评审", NOW)
        self.assertEqual(due.date().isoformat(), "2026-12-02")

    def test_relative_days(self):
        due, _ = parse_due("3天内报销差旅费", NOW)
        self.assertEqual(due.date().isoformat(), "2026-11-28")

    def test_no_date(self):
        due, raw = parse_due("记得买牛奶", NOW)
        self.assertIsNone(due)
        self.assertEqual(raw, "")


class ParseNoticeTests(unittest.TestCase):
    def test_student_notice(self):
        task = parse_notice("教务处通知：2026年11月30日前提交本学期选课确认表，逾期视为放弃。", NOW)
        self.assertEqual(task.source, "教务处")
        self.assertEqual(task.category, "资料提交")
        self.assertIn("选课确认表", task.title)
        self.assertNotIn("教务处通知", task.title)
        self.assertNotIn("日期", task.title)

    def test_work_notice(self):
        task = parse_notice("HR通知：明天下午6点前提交本月工作总结", NOW)
        self.assertEqual(task.source, "HR")
        self.assertEqual(task.priority, "normal")
        self.assertEqual(task.due_at.hour, 18)

    def test_urgent_keyword(self):
        task = parse_notice("紧急通知：下周一务必完成系统上线", NOW)
        self.assertEqual(task.priority, "high")

    def test_lecture_not_misclassified(self):
        task = parse_notice("学院通知：下周一上午9点在报告厅参加AI讲座", NOW)
        self.assertEqual(task.category, "会议")


class ReportTests(unittest.TestCase):
    def test_urgency_levels(self):
        overdue = Task(id="a", title="逾期", due_at=NOW.replace(day=24), status="pending")
        today = Task(id="b", title="今天", due_at=NOW.replace(hour=19), status="pending")
        later = Task(id="c", title="以后", due_at=datetime(2026, 12, 20), status="pending")
        report = build_report([later, today, overdue], now=NOW)
        self.assertIn("已逾期", report)
        self.assertIn("24 小时内", report)
        self.assertLess(report.index("逾期"), report.index("今天"))

    def test_empty_report(self):
        report = build_report([], now=NOW)
        self.assertIn("没有待办", report)


class SmartPlanTests(unittest.TestCase):
    def test_urgent_ranked_first(self):
        urgent = Task(id="u", title="明天交", due_at=datetime(2026, 11, 26, 18),
                      category="资料提交", status="pending")
        later = Task(id="l", title="下周交", due_at=datetime(2026, 12, 5, 18),
                     category="资料提交", status="pending")
        plan = build_plan([later, urgent], now=NOW)
        self.assertLess(plan.index("明天交"), plan.index("下周交"))
        self.assertIn("理由", plan)

    def test_high_priority_boost(self):
        normal = Task(id="n", title="普通", due_at=datetime(2026, 11, 27),
                      category="其他", priority="normal")
        high = Task(id="h", title="加急", due_at=datetime(2026, 11, 27),
                    category="其他", priority="high")
        s_high, _ = high.work_score(NOW)
        s_normal, _ = normal.work_score(NOW)
        self.assertGreater(s_high, s_normal)

    def test_in_progress_gets_boost(self):
        task = Task(id="t", title="任务", due_at=datetime(2026, 12, 1), category="作业")
        s_pending, _ = task.work_score(NOW)
        task.status = "in_progress"
        s_doing, _ = task.work_score(NOW)
        self.assertGreater(s_doing, s_pending)


class DynamicUpdateTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self.tmp.close()
        self.store = TaskStore(self.tmp.name)
        self.task = Task(id="t1", title="选课表", due_at=datetime(2026, 11, 30),
                         status="pending", progress=0)

    def tearDown(self):
        import os
        os.unlink(self.tmp.name)

    def test_update_fields(self):
        self.store.add(self.task)
        ok = self.store.update("t1", priority="high", progress=40, status="in_progress")
        self.assertTrue(ok)
        updated = self.store.get("t1")
        self.assertEqual(updated.priority, "high")
        self.assertEqual(updated.progress, 40)
        self.assertEqual(updated.status, "in_progress")

    def test_finish_sets_100(self):
        self.store.add(self.task)
        self.store.update("t1", status="done", progress=99)
        self.assertEqual(self.store.get("t1").progress, 100)

    def test_progress_clamped(self):
        self.store.add(self.task)
        self.store.update("t1", progress=999)
        self.assertEqual(self.store.get("t1").progress, 100)

    def test_note_append(self):
        self.store.add(self.task)
        self.store.add_note("t1", "已联系老师")
        self.assertIn("已联系老师", self.store.get("t1").notes)

    def test_unknown_field_rejected(self):
        with self.assertRaises(ValueError):
            self.store.update("t1", typo_field="x")

    def test_daily_report(self):
        done = Task(id="d", title=" done ", due_at=None, status="done", progress=100)
        report = build_daily([self.task, done], now=NOW)
        self.assertIn("完成率：50%", report)
        self.assertIn("每日进度", report)


if __name__ == "__main__":
    unittest.main(verbosity=2)
