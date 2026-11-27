# Copyright (c) 2026, eCentric and contributors
"""Gop phan CSV -> Excel va nhom file theo lan xuat - khong can bench.

    python -m unittest ecentric_workspace.shared_tools.tests.test_merge
"""
import datetime as dt
import io
import os
import sys
import types
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, ROOT)
if "frappe" not in sys.modules:
    sys.modules["frappe"] = types.ModuleType("frappe")
fu = sys.modules.get("frappe.utils") or types.ModuleType("frappe.utils")
fu.add_days = getattr(fu, "add_days", lambda d, n: d)
fu.now_datetime = getattr(fu, "now_datetime", dt.datetime.now)
sys.modules["frappe.utils"] = fu
if "requests" not in sys.modules:
    _rq = types.ModuleType("requests")
    _rq.RequestException = Exception
    sys.modules["requests"] = _rq

from openpyxl import load_workbook  # noqa: E402

from ecentric_workspace.shared_tools import merge as M  # noqa: E402
from ecentric_workspace.shared_tools import views as V  # noqa: E402

BOM = "﻿"


class MergeTest(unittest.TestCase):
    def test_parts_in_order_bom_and_header_once(self):
        p1 = (BOM + "Tên,Doanh thu\nSP 1,100\nSP 2,200\n").encode()
        p2 = "Tên,Doanh thu\nSP 3,300\n"
        h, rows = M.merge([(2, p2), (1, p1)])
        self.assertEqual(h, ["Tên", "Doanh thu"])
        self.assertEqual([r[0] for r in rows], ["SP 1", "SP 2", "SP 3"])
        wb = load_workbook(io.BytesIO(M.to_xlsx(h, rows)))
        ws = wb.active
        self.assertEqual(ws["A1"].value, "Tên")
        self.assertEqual(ws["A4"].value, "SP 3")
        self.assertEqual(ws.max_row, 4)

    def test_part_with_different_columns_is_realigned(self):
        h, rows = M.merge([(1, "A,B\n1,2\n"), (2, "B,C\n3,4\n")])
        self.assertEqual(h, ["A", "B"])
        self.assertEqual(rows, [["1", "2"], ["", "3"]])


class GroupTest(unittest.TestCase):
    def test_parts_grouped_singles_kept(self):
        now = dt.datetime(2026, 11, 27, 15, 0)
        rows = [
            {"name": "E3", "run_id": "r1", "part": 2, "rows": 20, "pages": 2, "page_title": "Sản phẩm (phần 2)",
             "source": "extension", "exported_at": now, "downloaded_at": None},
            {"name": "E2", "run_id": "r1", "part": 1, "rows": 50, "pages": 5, "page_title": "Sản phẩm (phần 1)",
             "source": "extension", "exported_at": now, "downloaded_at": now},
            {"name": "E1", "run_id": None, "part": 0, "rows": 10, "pages": 1, "page_title": "Cửa hàng",
             "source": "extension", "exported_at": now, "downloaded_at": now, "file_name": "a.csv"},
        ]
        out = V.group_exports(rows, now)
        self.assertEqual(len(out), 2)
        g = out[0]
        self.assertEqual((g["kind"], g["page"], g["rows"], g["pages"]), ("run", "Sản phẩm", 70, 7))
        self.assertEqual([p["part"] for p in g["parts"]], [1, 2])
        self.assertTrue(g["new"])
        self.assertEqual(out[1]["kind"], "file")
        self.assertEqual((g["day"], g["time"]), ("Hôm nay", "15:00"))

    def test_day_label(self):
        from ecentric_workspace.shared_tools import views as V
        now = dt.datetime(2026, 11, 27, 9, 0)
        self.assertEqual(V._day(dt.datetime(2026, 11, 26, 19, 5), now), {"day": "Hôm qua", "time": "19:05"})
        self.assertEqual(V._day(dt.datetime(2026, 11, 24, 8, 1), now)["day"], "24/11")
        self.assertEqual(V._day(None, now), {"day": "", "time": ""})


if __name__ == "__main__":
    unittest.main()


class StatsTest(unittest.TestCase):
    def test_compute(self):
        from ecentric_workspace.shared_tools import stats as ST
        now = dt.datetime(2026, 11, 27, 15, 0)
        t = lambda h, m=0, d=0: dt.datetime(2026, 11, 27 - d, h, m)
        entries = [
            {"user": "a", "status": "Completed", "end_reason": "time", "joined_at": t(9), "ready_at": t(9, 10),
             "started_at": t(9, 11), "ended_at": t(9, 41)},
            {"user": "b", "status": "Expired", "end_reason": "idle", "joined_at": t(10), "ready_at": t(10),
             "started_at": t(10, 1), "ended_at": t(10, 21), "d": 0},
            {"user": "c", "status": "Skipped", "end_reason": "no_show", "joined_at": t(11), "ready_at": t(11, 30),
             "started_at": None, "ended_at": t(11, 33)},
            {"user": "a", "status": "Active", "end_reason": None, "joined_at": t(14, 40), "ready_at": t(14, 40),
             "started_at": t(14, 40), "ended_at": None},
        ]
        exports = [
            {"name": "x1", "user": "a", "rows": 50, "pages": 5, "run_id": "r", "part": 1, "exported_at": t(9, 20)},
            {"name": "x2", "user": "a", "rows": 20, "pages": 2, "run_id": "r", "part": 2, "exported_at": t(9, 25)},
            {"name": "x3", "user": "b", "rows": 10, "pages": 1, "run_id": None, "part": 0, "exported_at": t(10, 5)},
        ]
        r = ST.compute(entries, exports, {"a": {"full_name": "An"}}, now, 30)
        k = r["kpi"]
        self.assertEqual((k["sessions"], k["users"], k["exports"], k["rows"], k["pages"], k["idle_end"]), (3, 2, 2, 80, 8, 1))
        self.assertEqual(k["hours"], round((30 + 20 + 20) / 60, 1))
        self.assertEqual(k["no_show_pct"], 25)
        self.assertEqual(r["by_hour"][9], 1)
        self.assertEqual(r["top"][0]["name"], "An")
        self.assertEqual((r["top"][0]["exports"], r["top"][0]["rows"], r["top"][0]["minutes"]), (1, 70, 50))
        self.assertEqual(len(r["by_day"]), 14)
