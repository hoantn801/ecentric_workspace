# Copyright (c) 2026, eCentric and contributors
"""Trung tam Du lieu - chay THAT domain / service / ops_service / pm_sync / notify tren repo gia + PM
gia, render 4 trang www bang jinja2 tu context that cua service (khong can bench).

    python -m unittest ecentric_workspace.data_hub.tests.test_data_hub

Fixture jsdom (tests/js/fixtures/*.html) duoc render tu CHINH bo mau nay; TestFixtures kiem chung
khong cu. Sinh lai:  EDH_UPDATE_FIXTURES=1 python -m unittest ecentric_workspace.data_hub.tests.test_data_hub
"""
import ast
import datetime as dt
import io
import json
import os
import re
import unittest

from ecentric_workspace.data_hub.tests import fake as F  # noqa: E402  (dat frappe gia neu thieu)
from ecentric_workspace.data_hub import constants as C
from ecentric_workspace.data_hub import domain as D
from ecentric_workspace.data_hub import notify as N
from ecentric_workspace.data_hub import ops_service as O
from ecentric_workspace.data_hub import pm_sync as P
from ecentric_workspace.data_hub import service as S

APP = os.path.join(F.ROOT, "ecentric_workspace")
HERE = os.path.dirname(os.path.abspath(__file__))
d = dt.date
HOL = F.HOLIDAYS


def new_repo(**kw):
    r = F.FakeRepo(**kw)
    return r, F.FakePM(r)


def create(r, user=F.THU, **kw):
    return S.create(user, F.req(**kw), repo=r)["code"]


# ====================================================================== domain =========
class TestWorkingDays(unittest.TestCase):
    def test_add_skips_weekend_and_holiday(self):
        self.assertEqual(D.add_working_days(d(2026, 11, 6), 1), d(2026, 11, 9))          # T6 + 1 -> T2
        self.assertEqual(D.add_working_days(d(2026, 11, 18), 3, HOL), d(2026, 11, 24))   # bo le 20/11 + T7/CN
        self.assertEqual(D.add_working_days(d(2026, 11, 7), 0), d(2026, 11, 9))          # 0 ngay tu T7 -> T2
        self.assertEqual(D.add_working_days(d(2026, 11, 9), 0), d(2026, 11, 9))

    def test_count_between(self):
        self.assertEqual(D.working_days_between(d(2026, 11, 6), d(2026, 11, 9)), 1)
        self.assertEqual(D.working_days_between(d(2026, 11, 9), d(2026, 11, 9)), 0)
        self.assertEqual(D.working_days_between(d(2026, 11, 19), d(2026, 11, 23), HOL), 1)
        self.assertEqual(D.working_days_between(d(2026, 11, 10), d(2026, 11, 9)), 0)

    def test_default_start(self):
        self.assertEqual(D.default_start(d(2026, 11, 8)), d(2026, 11, 9))
        self.assertEqual(D.default_start(d(2026, 11, 20), HOL), d(2026, 11, 23))


class TestRules(unittest.TestCase):
    def test_multiplier_rounding_min_one(self):
        self.assertEqual([D.sla_days(7, m) for m in (0.5, 0.8, 1, 1.5)], [4, 6, 7, 11])
        self.assertEqual([D.sla_days(3, m) for m in (0.5, 0.8, 1, 1.5)], [2, 3, 3, 5])
        self.assertEqual(D.sla_days(1, 0.5), 1)
        self.assertEqual(D.sla_days(0, 1), 1, "toi thieu 1 ngay ke ca quy tac hong")

    def test_rules_view_defaults_and_overrides(self):
        r = D.rules_view(None)
        self.assertEqual(r["days"]["pbi_new"], 7)
        self.assertEqual(r["mult"][C.PRI_LOW], 1.5)
        r = D.rules_view({"name": "SLA-v2", "mult_high": 0.75, "items": [{"rule_key": "pbi_new", "days": 10},
                                                                           {"rule_key": "khong-co", "days": 2},
                                                                           {"rule_key": "other", "days": 0}]})
        self.assertEqual((r["version"], r["days"]["pbi_new"], r["days"]["other"], r["mult"][C.PRI_HIGH]),
                         ("SLA-v2", 10, 3, 0.75))
        self.assertEqual(D.ticket_sla_days(r, "Power BI mới", C.PRI_HIGH), 8)
        self.assertEqual(D.ticket_sla_days(r, "loai la", C.PRI_NORMAL), 3, "loai la -> quy tac Khac")

    def test_type_hints_for_create_modal(self):
        h = D.type_hints(D.rules_view(None))
        self.assertEqual(h["Power BI mới"][C.PRI_URGENT], 4)
        self.assertEqual(h["Xử lý dữ liệu"][C.PRI_LOW], 5)
        self.assertEqual(set(h), set(C.REQUEST_TYPES))


class TestValidation(unittest.TestCase):
    def test_urgent_needs_reason(self):
        with self.assertRaises(D.Invalid) as cm:
            D.normalize_create(F.req(proposed_priority=C.PRI_URGENT))
        self.assertIn("Mức Khẩn cần ghi lý do", " ".join(cm.exception.errors))
        v = D.normalize_create(F.req(proposed_priority=C.PRI_URGENT, urgent_reason="BOD"))
        self.assertEqual(v["urgent_reason"], "BOD")
        self.assertEqual(D.normalize_create(F.req(urgent_reason="x"))["urgent_reason"], "", "khong Khan -> bo ly do")

    def test_errors(self):
        with self.assertRaises(D.Invalid) as cm:
            D.normalize_create({"request_type": "?", "title": "", "description": "", "reference_link": "javascript:x"})
        e = " ".join(cm.exception.errors)
        for s in ("Chọn loại", "Chưa có tiêu đề", "Chưa có mô tả", "http://"):
            self.assertIn(s, e)
        with self.assertRaises(D.Invalid):
            D.normalize_create(F.req(), sent_today=C.DAILY_LIMIT)

    def test_files(self):
        self.assertEqual(D.check_files([{"name": "a.pbix", "size": 10}]), [])
        self.assertTrue(D.check_files([{"name": "a.exe", "size": 10}]))
        self.assertTrue(D.check_files([{"name": "a.pdf", "size": C.FILE_MAX_BYTES + 1}]))
        self.assertTrue(D.check_files([{"name": "a.pdf", "size": 1}] * (C.MAX_FILES + 1)))

    def test_due_change_needs_reason(self):
        self.assertTrue(D.check_due_change(d(2026, 11, 10), d(2026, 11, 12), ""))
        self.assertEqual(D.check_due_change(d(2026, 11, 10), d(2026, 11, 12), "lý do"), [])
        self.assertEqual(D.check_due_change(d(2026, 11, 10), d(2026, 11, 10), ""), [])
        self.assertTrue(D.check_due_change(d(2026, 11, 10), d(2026, 11, 8), "x", start=d(2026, 11, 9)))

    def test_team_moves(self):
        self.assertTrue(D.can_team_move(C.ST_DOING, C.ST_PAUSED))
        self.assertTrue(D.can_team_move(C.ST_REVIEW, C.ST_DOING))
        self.assertFalse(D.can_team_move(C.ST_WAITING, C.ST_DOING), "Cho tiep nhan chi qua Nhan viec")
        self.assertFalse(D.can_team_move(C.ST_DOING, C.ST_DONE), "Hoan tat chi qua nghiem thu")


class TestPauseMath(unittest.TestCase):
    def test_paused_days_and_extension(self):
        self.assertEqual(D.paused_working_days(dt.datetime(2026, 11, 5, 14), dt.datetime(2026, 11, 9, 10)), 2)
        self.assertEqual(D.paused_working_days(dt.datetime(2026, 11, 9, 9), dt.datetime(2026, 11, 9, 17)), 0)
        self.assertEqual(D.extend_due(d(2026, 11, 12), 2), d(2026, 11, 16))
        self.assertEqual(D.extend_due(d(2026, 11, 19), 1, HOL), d(2026, 11, 23))


class TestQueue(unittest.TestCase):
    def rows(self):
        return [
            {"name": "A", "status": C.ST_DOING, "assignee": F.LINH, "due_date": "2026-11-12", "request_type": "Khác"},
            {"name": "B", "status": C.ST_PAUSED, "assignee": F.HOAN, "due_date": "2026-11-10", "request_type": "Khác"},
            {"name": "W1", "status": C.ST_WAITING, "proposed_priority": C.PRI_NORMAL, "request_type": "Khác",
             "creation": "2026-11-05 10:00:00"},
            {"name": "W2", "status": C.ST_WAITING, "proposed_priority": C.PRI_URGENT, "request_type": "Power BI mới",
             "creation": "2026-11-09 08:00:00"},
            {"name": "W3", "status": C.ST_WAITING, "proposed_priority": C.PRI_NORMAL, "request_type": "Khác",
             "creation": "2026-11-06 10:00:00"},
        ]

    def test_order_and_capacity(self):
        q = D.queue(self.rows(), [F.LINH, F.HOAN], F.MON)
        self.assertEqual([q[k]["position"] for k in ("W2", "W1", "W3")], [1, 2, 3], "Khan truoc, roi gui truoc")
        # Hoan ranh tu 10/11 (han viec dang tam dung), Linh tu 12/11 -> W2 vao Hoan, bat dau 10/11, 4 ngay -> 16/11
        self.assertEqual((q["W2"]["expected_start"], q["W2"]["expected_due"]), (d(2026, 11, 10), d(2026, 11, 16)))
        # W1 -> Linh (ranh 12/11 som hon Hoan 16/11), 3 ngay -> 17/11; W3 -> Hoan tu 16/11
        self.assertEqual(q["W1"]["expected_start"], d(2026, 11, 12))
        self.assertEqual(q["W3"]["expected_start"], d(2026, 11, 16))

    def test_overdue_member_is_free_today_and_no_team(self):
        rows = self.rows()
        rows[0]["due_date"] = "2026-11-02"
        q = D.queue(rows, [F.LINH, F.HOAN], F.MON)
        self.assertEqual(q["W2"]["expected_start"], F.MON)
        q = D.queue(rows, [], F.MON)
        self.assertEqual([q[k]["expected_start"] for k in ("W2", "W1")], [F.MON, d(2026, 11, 13)])


class TestKpiSortSla(unittest.TestCase):
    def test_kpis_on_sample(self):
        r, pm, c = F.sample()
        k = D.kpis(r.list_rows(), F.MON)
        self.assertEqual(k, {"doing": 3, "waiting": 3, "overdue": 2, "paused": 1, "review": 1, "done_month": 1,
                             "on_time_pct": 100})

    def test_on_time_percent_only_closed_in_month(self):
        rows = [{"status": C.ST_DONE, "closed_at": "2026-11-03 10:00", "done_at": "2026-11-02", "due_date": "2026-11-02"},
                {"status": C.ST_DONE, "closed_at": "2026-11-04 10:00", "done_at": "2026-11-04", "due_date": "2026-11-03"},
                {"status": C.ST_DONE, "closed_at": "2026-10-30 10:00", "done_at": "2026-10-01", "due_date": "2026-10-30"},
                {"status": C.ST_REVIEW, "done_at": "2026-11-05", "due_date": "2026-11-09"}]
        k = D.kpis(rows, F.MON)
        self.assertEqual((k["done_month"], k["on_time_pct"]), (2, 50))
        self.assertIsNone(D.kpis([], F.MON)["on_time_pct"])

    def test_sort_urgent_then_overdue_then_due(self):
        r, pm, c = F.sample()
        order = [t["name"] for t in D.sort_rows(r.list_rows(), F.MON)]
        self.assertEqual(order[:4], [c["voucher"], c["pnl"], c["tiktok"], c["clean"]])
        self.assertEqual(order[-3:], [c["aff"], c["dup"], c["stock"]][:1] + order[-2:], order)
        self.assertEqual(set(order[-2:]), {c["dup"], c["stock"]}, "da dong xuong cuoi")
        self.assertLess(order.index(c["misa"]), order.index(c["rating"]), "han gan truoc")

    def test_overdue_before_paused_with_older_due(self):
        rows = [{"name": "P", "status": C.ST_PAUSED, "priority": C.PRI_NORMAL, "due_date": "2026-11-04",
                 "creation": "2026-11-01 09:00:00"},
                {"name": "L", "status": C.ST_DOING, "priority": C.PRI_NORMAL, "due_date": "2026-11-05",
                 "creation": "2026-11-02 09:00:00"}]
        self.assertEqual([t["name"] for t in D.sort_rows(rows, F.MON)], ["L", "P"], "qua han (dang chay) truoc tam dung")

    def test_sla_labels(self):
        t = {"status": C.ST_DOING, "start_date": "2026-11-04", "due_date": "2026-11-10"}
        self.assertEqual(D.sla_view(t, F.MON)["label"], "10/11 · còn 1 ngày")
        self.assertEqual(D.sla_view(t, F.MON)["css"], "near")
        self.assertEqual(D.sla_view(dict(t, due_date="2026-11-09"), F.MON)["label"], "09/11 · hạn hôm nay")
        late = D.sla_view(dict(t, due_date="2026-11-05"), F.MON)
        self.assertEqual((late["label"], late["css"], late["pct"]), ("05/11 · quá hạn 2 ngày", "late", 100))
        self.assertIn("SLA tạm dừng", D.sla_view(dict(t, status=C.ST_PAUSED), F.MON)["label"])
        w = D.sla_view({"status": C.ST_WAITING, "intake_due_date": "2026-11-06"}, F.MON)
        self.assertEqual((w["label"], w["css"]), ("hạn nhận 06/11 · trễ", "late"))


class TestGantt(unittest.TestCase):
    def test_lanes_and_bars(self):
        r, pm, c = F.sample()
        g = S.gantt_data(F.THU, repo=r)
        self.assertEqual((g["start"], len(g["days"])), ("2026-11-02", C.GANTT_DAYS))
        self.assertEqual([x["date"] for x in g["days"] if x["today"]], ["2026-11-09"])
        self.assertTrue(next(x for x in g["days"] if x["date"] == "2026-11-20")["off"], "ngay le to xam")
        keys = [ln["key"] for ln in g["lanes"]]
        self.assertEqual(keys, [F.DUNG, F.HOAN, F.LINH, "__none", "__done"][:0] + keys)
        self.assertEqual(keys[-2:], ["__none", "__done"])
        self.assertEqual(set(keys[:-2]), {F.LINH, F.HOAN, F.DUNG})
        lanes = {ln["key"]: ln for ln in g["lanes"]}
        linh = {b["code"]: b for b in lanes[F.LINH]["bars"]}
        self.assertEqual(linh[c["pnl"]]["css"], "late")
        self.assertEqual(linh[c["pnl"]]["late_to"], "2026-11-09")
        self.assertEqual(linh[c["pnl"]]["original_due"], "2026-11-03")
        self.assertEqual(linh[c["live"]]["css"], "hold")
        self.assertEqual(lanes[F.LINH]["sub"], "3 yêu cầu")
        self.assertEqual({b["code"] for b in lanes["__none"]["bars"]}, {c["voucher"], c["clean"], c["tiktok"]})
        self.assertEqual(lanes["__none"]["sub"], "3 chờ nhận")
        self.assertEqual([b["code"] for b in lanes["__done"]["bars"]], [c["stock"]])
        self.assertEqual({b["code"] for b in lanes[F.DUNG]["bars"]}, {c["aff"]})
        self.assertNotIn(c["dup"], json.dumps(g), "huy khong len Gantt")

    def test_window_shift_and_clip(self):
        r, pm, c = F.sample()
        g = S.gantt_data(F.THU, start="2026-11-18", repo=r)
        self.assertEqual(g["start"], "2026-11-16", "keo ve thu Hai")
        lanes = {ln["key"]: ln for ln in g["lanes"]}
        self.assertNotIn("__done", lanes, "het viec xong trong cua so -> bo hang")
        self.assertNotIn(c["pnl"], [b["code"] for b in lanes[F.LINH]["bars"]], "thanh truoc cua so bi bo")

    def test_availability_counts(self):
        rows = [{"name": "DA-2026-0001", "kind": C.KIND_AVAILABILITY, "status": C.ST_DOING, "assignee": F.LINH,
                 "start_date": "2026-11-09", "due_date": "2026-11-17", "title": "Video"}]
        g = D.gantt(rows, [F.LINH], F.NAMES, F.MON)
        ln = g["lanes"][0]
        self.assertEqual((ln["sub"], ln["bars"][0]["css"]), ("0 yêu cầu + 1 bổ sung data", "da"))


class TestOpsColumns(unittest.TestCase):
    def test_columns(self):
        r, pm, c = F.sample()
        cols = D.ops_columns(r.list_rows(), F.MON)
        self.assertEqual([t["name"] for t in cols["waiting"]], [c["voucher"], c["tiktok"], c["clean"]])
        self.assertEqual({t["name"] for t in cols["doing"]}, {c["pnl"], c["rating"], c["misa"], c["aff"]})
        self.assertEqual([t["name"] for t in cols["paused"]], [c["live"]])
        self.assertEqual([t["name"] for t in cols["done"]], [c["stock"]])


# ====================================================================== luong ===========
class TestFlow(unittest.TestCase):
    def setUp(self):
        self.r, self.pm = new_repo()

    def test_create_waits_with_intake_due(self):
        code = create(self.r, proposed_priority=C.PRI_URGENT, urgent_reason="BOD")
        t = self.r.get(code)
        self.assertEqual((t["status"], t["priority"], t["proposed_priority"]), (C.ST_WAITING, "", C.PRI_URGENT))
        self.assertEqual(t["intake_due_date"], d(2026, 11, 10))
        self.assertEqual((t["sla_days"], t["requester_department"], t["rule_version"]), (4, "Commercial - EC", "SLA-v1"))
        self.assertEqual(self.r.events(code), [C.EV_CREATED])

    def test_accept_defaults_and_downgrade_urgent(self):
        code = create(self.r, proposed_priority=C.PRI_URGENT, urgent_reason="BOD")
        out = O.accept(F.LINH, code, F.HOAN, priority=C.PRI_HIGH, repo=self.r, pm=self.pm)
        t = self.r.get(code)
        self.assertEqual((t["status"], t["assignee"], t["priority"], t["priority_confirmed_by"]),
                         (C.ST_DOING, F.HOAN, C.PRI_HIGH, F.LINH))
        # Power BI moi 7 x 0.8 = 6 ngay tu 09/11 -> 17/11
        self.assertEqual((t["start_date"], t["due_date"], t["original_due_date"], t["sla_days"]),
                         (F.MON, d(2026, 11, 17), d(2026, 11, 17), 6))
        self.assertEqual(out["due"], "2026-11-17")
        pri = [lg for lg in self.r.logs_ if lg["event"] == C.EV_PRIORITY][0]
        self.assertEqual((pri["from_value"], pri["to_value"]), (C.PRI_URGENT, C.PRI_HIGH))
        self.assertIn("Hạ mức Khẩn", pri["note"])

    def test_accept_confirm_urgent_logged(self):
        code = create(self.r, proposed_priority=C.PRI_URGENT, urgent_reason="BOD")
        O.accept(F.LINH, code, repo=self.r, pm=self.pm)
        self.assertEqual(self.r.get(code)["priority"], C.PRI_URGENT)
        self.assertIn("Xác nhận Khẩn", [lg["note"] for lg in self.r.logs_])

    def test_accept_custom_due_needs_reason(self):
        code = create(self.r)
        with self.assertRaises(S.DataHubError):
            O.accept(F.LINH, code, F.LINH, due_date="2026-11-30", repo=self.r, pm=self.pm)
        self.assertEqual(self.r.get(code)["status"], C.ST_WAITING)
        O.accept(F.LINH, code, F.LINH, due_date="2026-11-30", reason="Chờ API sàn", repo=self.r, pm=self.pm)
        self.assertEqual(self.r.get(code)["due_date"], d(2026, 11, 30))

    def test_accept_guards(self):
        code = create(self.r)
        with self.assertRaises(S.DataHubError):
            O.accept(F.LINH, code, F.THU, repo=self.r, pm=self.pm)                      # khong phai team Data
        with self.assertRaises(S.DataHubError):
            O.accept(F.LINH, code, F.LINH, start_date="2026-11-02", repo=self.r, pm=self.pm)
        O.accept(F.LINH, code, F.LINH, repo=self.r, pm=self.pm)
        with self.assertRaises(S.DataHubError):
            O.accept(F.HOAN, code, F.HOAN, repo=self.r, pm=self.pm)                     # da co nguoi nhan
        self.assertIn(code, self.r.locks, "doc lai co khoa dong")

    def test_pause_resume_extends_due_by_paused_working_days(self):
        code = create(self.r, request_type="Khác")
        O.accept(F.LINH, code, F.LINH, repo=self.r, pm=self.pm)          # 09/11 + 3 -> 12/11
        self.r.at(d(2026, 11, 10), 15)
        O.pause(F.LINH, code, "Chờ quyền truy cập", repo=self.r, pm=self.pm)
        self.assertEqual(self.r.get(code)["status"], C.ST_PAUSED)
        self.r.at(d(2026, 11, 13), 10)                                    # dung 11, 12, 13 = 3 ngay
        O.resume(F.LINH, code, repo=self.r, pm=self.pm)
        t = self.r.get(code)
        self.assertEqual((t["status"], t["due_date"], t["paused_days"], t["paused_since"]),
                         (C.ST_DOING, d(2026, 11, 17), 3, None))
        self.assertEqual(t["paused_seconds"], int((dt.datetime(2026, 11, 13, 10) - dt.datetime(2026, 11, 10, 15)).total_seconds()))
        self.assertEqual(t["original_due_date"], d(2026, 11, 12), "han goc giu nguyen")
        self.assertIn(("update", t["pm_task"], {"exp_start_date": F.MON, "exp_end_date": d(2026, 11, 17)}), self.pm.calls)

    def test_done_while_paused_resumes_first(self):
        code = create(self.r, request_type="Khác")
        O.accept(F.LINH, code, F.LINH, repo=self.r, pm=self.pm)
        self.r.at(d(2026, 11, 10), 9)
        O.pause(F.LINH, code, repo=self.r, pm=self.pm)
        self.r.at(d(2026, 11, 11), 9)
        O.mark_done(F.LINH, code, output_link="https://x.vn/r", repo=self.r, pm=self.pm)
        t = self.r.get(code)
        self.assertEqual((t["status"], t["due_date"], t["output_link"]), (C.ST_REVIEW, d(2026, 11, 13), "https://x.vn/r"))
        self.assertEqual(self.r.events(code)[-2:], [C.EV_RESUME, C.EV_DONE])

    def test_review_reject_redo_accept(self):
        code = create(self.r)
        O.accept(F.LINH, code, F.LINH, repo=self.r, pm=self.pm)
        O.mark_done(F.LINH, code, repo=self.r, pm=self.pm)
        with self.assertRaises(S.DataHubError):
            S.respond(F.THU, code, C.ACC_FAIL, "", repo=self.r, pm=self.pm)   # Chua dat bat buoc ly do
        S.respond(F.THU, code, C.ACC_FAIL, "Thiếu cột voucher", repo=self.r, pm=self.pm)
        t = self.r.get(code)
        self.assertEqual((t["status"], t["acceptance"], t["reject_count"], t["done_at"]), (C.ST_DOING, C.ACC_FAIL, 1, None))
        self.assertEqual(self.pm.tasks[t["pm_task"]]["state"], "In Progress")
        O.mark_done(F.LINH, code, repo=self.r, pm=self.pm)
        S.respond(F.THU, code, C.ACC_OK, repo=self.r, pm=self.pm)
        t = self.r.get(code)
        self.assertEqual((t["status"], t["acceptance"]), (C.ST_DONE, C.ACC_OK))
        self.assertTrue(t["closed_at"])
        with self.assertRaises(S.DataHubError):
            S.respond(F.THU, code, C.ACC_OK, repo=self.r, pm=self.pm)

    def test_team_update_changes_logged_and_note_posted(self):
        code = create(self.r)
        O.accept(F.LINH, code, F.LINH, repo=self.r, pm=self.pm)
        with self.assertRaises(S.DataHubError):
            O.update(F.LINH, code, {"due_date": "2026-11-25"}, repo=self.r, pm=self.pm)
        out = O.update(F.LINH, code, {"due_date": "2026-11-25", "reason": "Brand đổi phạm vi", "priority": C.PRI_HIGH,
                                      "assignee": F.DUNG, "note": "Đã xong 50%"}, repo=self.r, pm=self.pm)
        t = self.r.get(code)
        self.assertEqual((t["due_date"], t["priority"], t["assignee"], t["due_change_count"]),
                         (d(2026, 11, 25), C.PRI_HIGH, F.DUNG, 1))
        self.assertEqual(len(out["changes"]), 3)
        self.assertEqual([m["body"] for m in self.r.messages(code)], ["Đã xong 50%"])
        due = [lg for lg in self.r.logs_ if lg["event"] == C.EV_DUE][0]
        self.assertEqual((due["from_value"], due["to_value"], due["note"]), ("2026-11-18", "2026-11-25", "Brand đổi phạm vi"))
        with self.assertRaises(S.DataHubError):
            O.update(F.LINH, code, {}, repo=self.r, pm=self.pm)
        with self.assertRaises(S.DataHubError):
            O.update(F.LINH, code, {"assignee": F.THU}, repo=self.r, pm=self.pm)
        with self.assertRaises(S.DataHubError):
            O.update(F.LINH, code, {"status": C.ST_DONE}, repo=self.r, pm=self.pm)

    def test_cancel_rules(self):
        a = create(self.r)
        S.cancel(F.THU, a, "", repo=self.r, pm=self.pm)
        self.assertEqual(self.r.get(a)["status"], C.ST_CANCELLED)
        b = create(self.r)
        O.accept(F.LINH, b, F.LINH, repo=self.r, pm=self.pm)
        with self.assertRaises(S.Forbidden):
            S.cancel(F.THU, b, "thôi", repo=self.r, pm=self.pm)
        with self.assertRaises(S.DataHubError):
            S.cancel(F.LINH, b, "", repo=self.r, pm=self.pm)
        S.cancel(F.LINH, b, "Brand dừng hợp đồng", repo=self.r, pm=self.pm)
        t = self.r.get(b)
        self.assertEqual((t["status"], t["cancel_reason"]), (C.ST_CANCELLED, "Brand dừng hợp đồng"))
        self.assertEqual(self.pm.tasks[t["pm_task"]]["state"], "Cancelled")

    def test_messages_mentions_files_follow(self):
        code = create(self.r)
        with self.assertRaises(S.Forbidden):
            S.send_message(F.HIEN, code, "hi", repo=self.r)
        S.follow(F.HIEN, code, True, repo=self.r)
        S.send_message(F.HIEN, code, "Mình cũng cần @Linh Vương", mentions=[F.LINH, "rác", "khong@co.vn"],
                       files=[{"name": "mau.xlsx", "content": b"abc", "size": 3}], repo=self.r)
        m = self.r.messages(code)[0]
        self.assertEqual(json.loads(m["mentions"]), [F.LINH])
        det = S.detail(F.THU, code, repo=self.r)
        self.assertEqual(det["messages"][0]["files"][0]["name"], "mau.xlsx")
        self.assertEqual(det["attachments"], [], "tep cua tin nhan khong nam o muc Tep cua yeu cau")
        self.assertEqual(S.download(F.DUYEN, code, det["messages"][0]["files"][0]["id"], repo=self.r), ("mau.xlsx", b"abc"))
        other = create(self.r)
        with self.assertRaises(S.NotFound):
            S.download(F.THU, other, det["messages"][0]["files"][0]["id"], repo=self.r)
        S.follow(F.HIEN, code, 0, repo=self.r)
        self.assertEqual(self.r.get(code)["followers"], [])
        with self.assertRaises(S.DataHubError):
            S.send_message(F.THU, code, "   ", repo=self.r)

    def test_detail_queue_and_capabilities(self):
        r, pm, c = F.sample()
        det = S.detail(F.HIEN, c["tiktok"], repo=r)
        self.assertEqual(det["queue"]["position"], 2)
        self.assertEqual(det["can"], {"message": True, "follow": True, "respond": False, "cancel": True,
                                      "cancel_needs_reason": False, "operate": False, "accept": False})
        team = S.detail(F.LINH, c["tiktok"], repo=r)
        self.assertTrue(team["can"]["accept"] and not team["can"]["operate"])
        self.assertEqual(team["accept_defaults"]["due"], "2026-11-18", "Power BI moi 7 ngay tu 09/11")
        self.assertEqual([m["user"] for m in team["team_members"]], [F.DUNG, F.HOAN, F.LINH])
        self.assertEqual(team["team"], "Service", "team = team nguoi gui (khong lan voi danh sach team Data)")
        pnl = S.detail(F.THU, c["pnl"], repo=r)
        self.assertEqual((pnl["due_fmt"], pnl["original_due_fmt"], pnl["due_change_count"]), ("06/11/2026", "03/11/2026", 1))
        self.assertEqual(pnl["pm_url"], "/pm#task/" + pnl["pm_task"])
        texts = [x["text"] for x in pnl["timeline"]]
        self.assertTrue(any("dời hạn 03/11 → 06/11" in s for s in texts), texts)
        self.assertTrue(any(x["note"] == "Chờ brand gửi file mapping SKU" for x in pnl["timeline"]))
        aff = S.detail(F.HIEN, c["aff"], repo=r)
        self.assertTrue(aff["can"]["respond"])
        self.assertFalse(S.detail(F.THU, c["aff"], repo=r)["can"]["respond"], "chi nguoi gui nghiem thu")


# ====================================================================== quyen ===========
class TestPermissionMatrix(unittest.TestCase):
    """Moi nhan vien DOC moi yeu cau; ghi: nguoi gui (yeu cau cua minh), team Data, System Manager."""

    def setUp(self):
        self.r, self.pm, self.c = F.sample()

    def call(self, op, user):
        r, pm, c = self.r, self.pm, self.c
        ops = {
            "read": lambda: S.detail(user, c["pnl"], repo=r),
            "list": lambda: S.list_rows(user, repo=r),
            "gantt": lambda: S.gantt_data(user, repo=r),
            "create": lambda: S.create(user, F.req(), repo=r),
            "follow": lambda: S.follow(user, c["pnl"], 1, repo=r),
            "message": lambda: S.send_message(user, c["rating"], "hỏi chút", repo=r),
            "respond": lambda: S.respond(user, c["aff"], C.ACC_OK, repo=r, pm=pm),
            "cancel_waiting": lambda: S.cancel(user, c["clean"], "không cần nữa", repo=r, pm=pm),
            "accept": lambda: O.accept(user, c["tiktok"], F.LINH, repo=r, pm=pm),
            "update": lambda: O.update(user, c["rating"], {"priority": C.PRI_HIGH}, repo=r, pm=pm),
            "pause": lambda: O.pause(user, c["misa"], repo=r, pm=pm),
            "preview": lambda: S.preview_due(user, c["tiktok"], repo=r),
        }
        try:
            ops[op]()
            return True
        except S.Forbidden:
            return False

    MATRIX = {
        # op:             THU(gui pnl/clean? clean la HIEN) HIEN(gui clean, aff)  DUYEN(gui rating) LINH(team) ADMIN OUTSIDER
        "read":           (True, True, True, True, True, False),
        "list":           (True, True, True, True, True, False),
        "gantt":          (True, True, True, True, True, False),
        "create":         (True, True, True, True, True, False),
        "follow":         (True, True, True, True, True, False),
        "message":        (False, False, True, True, True, False),
        "respond":        (False, True, False, False, True, False),
        "cancel_waiting": (False, True, False, True, True, False),
        "accept":         (False, False, False, True, True, False),
        "update":         (False, False, False, True, True, False),
        "pause":          (False, False, False, True, True, False),
        "preview":        (False, False, False, True, True, False),
    }
    USERS = (F.THU, F.HIEN, F.DUYEN, F.LINH, F.ADMIN, F.OUTSIDER)

    def test_matrix(self):
        for op, expect in self.MATRIX.items():
            for user, want in zip(self.USERS, expect):
                self.setUp()
                self.assertEqual(self.call(op, user), want, "%s / %s" % (op, user))

    def test_guest(self):
        for op in self.MATRIX:
            self.assertFalse(self.call(op, "Guest"), op)


# ====================================================================== /pm ============
class TestPmSync(unittest.TestCase):
    def setUp(self):
        self.r, self.pm = new_repo()
        self.code = create(self.r, title="PnL Friso")

    def accept(self, **kw):
        return O.accept(F.LINH, self.code, kw.pop("who", F.LINH), repo=self.r, pm=self.pm, **kw)

    def test_accept_creates_task_and_in_progress(self):
        out = self.accept(priority=C.PRI_HIGH)
        t = self.r.get(self.code)
        self.assertEqual(out["pm_task"], t["pm_task"])
        name, task = next(iter(self.pm.tasks.items()))
        self.assertEqual((task["project"], task["assignee"], task["exp_start_date"], task["exp_end_date"], task["priority"]),
                         ("PROJ-0042", F.LINH, F.MON, d(2026, 11, 17), "High"))
        self.assertEqual(task["subject"], "[%s] PnL Friso" % self.code)
        self.assertIn("/du-lieu?ma=" + self.code, task["description"])
        self.assertEqual(task["state"], "In Progress")
        self.assertTrue(all(self.pm.saw_flag), "moi lan ghi sang /pm deu dat co chong vong lap")
        self.assertFalse(P.busy(self.r), "co duoc tra lai sau khi ghi")

    def test_changes_push_due_assignee_priority_state(self):
        self.accept()
        task = self.r.get(self.code)["pm_task"]
        O.update(F.LINH, self.code, {"due_date": "2026-11-27", "reason": "x", "assignee": F.HOAN, "priority": C.PRI_LOW},
                 repo=self.r, pm=self.pm)
        kinds = [c[0] for c in self.pm.calls]
        self.assertEqual(kinds, ["create", "state", "assignee", "update", "update"])
        self.assertEqual(self.pm.tasks[task]["exp_end_date"], d(2026, 11, 27))
        self.assertEqual((self.pm.tasks[task]["assignee"], self.pm.tasks[task]["priority"]), (F.HOAN, "Low"))
        self.assertEqual(self.pm.calls[2], ("assignee", task, F.HOAN, F.LINH))
        O.mark_done(F.HOAN, self.code, repo=self.r, pm=self.pm)
        self.assertEqual(self.pm.tasks[task]["state"], "Done")

    def test_failures_never_break_main_action(self):
        self.pm.fail = {"create"}
        out = self.accept()
        t = self.r.get(self.code)
        self.assertEqual((t["status"], t["pm_task"]), (C.ST_DOING, None), "nhan viec van luu")
        self.assertIn("chưa đồng bộ được task /pm", out["warning"])
        self.assertIn(C.EV_PM_ERROR, self.r.events(self.code))
        self.assertTrue(self.r.errors)
        # lan cap nhat sau: tao bu task
        self.pm.fail = set()
        O.update(F.LINH, self.code, {"priority": C.PRI_HIGH}, repo=self.r, pm=self.pm)
        self.assertTrue(self.r.get(self.code)["pm_task"])
        # Task /pm khong dong duoc (con viec con) -> ticket van Cho nghiem thu, kem canh bao
        self.pm.fail = {"state"}
        out = O.mark_done(F.LINH, self.code, repo=self.r, pm=self.pm)
        self.assertEqual(self.r.get(self.code)["status"], C.ST_REVIEW)
        self.assertTrue(out["warnings"])

    def test_state_failure_after_create_keeps_link(self):
        self.pm.fail = {"state"}
        out = self.accept()
        self.assertTrue(out["pm_task"] and out["warning"])
        self.assertEqual(self.r.get(self.code)["pm_task"], out["pm_task"])

    def test_disabled_sync_does_nothing_and_assignee_notified_by_hub(self):
        self.r.settings_["pm_sync_enabled"] = 0
        self.accept(who=F.HOAN)
        self.assertEqual(self.pm.calls, [])
        self.assertTrue(self.r.sent(C.EV_ASSIGNED, self.code))
        self.assertFalse(P.enabled(F.FakeRepo(pm_project="")))

    # -- /pm -> ticket
    def test_task_done_moves_ticket_to_review_without_push_back(self):
        self.accept()
        task = self.r.get(self.code)["pm_task"]
        n = len(self.pm.calls)
        out = P.apply_task(self.r, self.code, {"workflow_state": "Done"}, F.LINH, pm=self.pm)
        t = self.r.get(self.code)
        self.assertEqual((out, t["status"]), (["done"], C.ST_REVIEW))
        self.assertEqual(len(self.pm.calls), n, "khong day nguoc sang /pm")
        self.assertEqual((self.r.errors, C.EV_PM_ERROR in self.r.events(self.code)), ([], False),
                         "khong co lan goi /pm nao (ke ca goi hong)")
        done = [lg for lg in self.r.logs_ if lg["event"] == C.EV_DONE][-1]
        self.assertEqual(done["source"], C.SRC_PM)
        self.assertTrue(self.r.sent(C.EV_REVIEW, self.code))
        # task mo lai -> ticket ve Dang xu ly
        self.assertEqual(P.apply_task(self.r, self.code, {"workflow_state": "In Progress"}, F.LINH), ["reopen"])
        self.assertEqual(self.r.get(self.code)["status"], C.ST_DOING)
        self.assertFalse(self.r.get(self.code)["acceptance"], "mo lai tu /pm khong tinh Chua dat")
        self.assertEqual(task, self.r.get(self.code)["pm_task"])

    def test_task_due_and_start_change(self):
        self.accept()
        out = P.apply_task(self.r, self.code, {"workflow_state": "In Progress", "exp_start_date": "2026-11-10",
                                               "exp_end_date": "2026-11-20"}, F.LINH)
        t = self.r.get(self.code)
        self.assertEqual((out, t["start_date"], t["due_date"], t["due_change_count"]),
                         (["start", "due"], d(2026, 11, 10), d(2026, 11, 20), 1))
        due = [lg for lg in self.r.logs_ if lg["event"] == C.EV_DUE][-1]
        self.assertEqual((due["source"], due["note"]), (C.SRC_PM, "Đổi hạn trên /pm"))
        self.assertTrue(any("(từ /pm)" in n["message"] for n in self.r.sent(C.EV_UPDATE, self.code)))
        self.assertEqual(P.apply_task(self.r, self.code, {"exp_end_date": "2026-11-20"}, F.LINH), [], "khong doi -> khong ghi")

    def test_task_cancel_only_logged_and_closed_ticket_ignored(self):
        self.accept()
        self.assertEqual(P.apply_task(self.r, self.code, {"workflow_state": "Cancelled"}, F.LINH), ["pm_cancelled"])
        self.assertEqual(self.r.get(self.code)["status"], C.ST_DOING)
        S.cancel(F.LINH, self.code, "x", repo=self.r, pm=self.pm)
        self.assertEqual(P.apply_task(self.r, self.code, {"workflow_state": "Done"}, F.LINH), [])
        w = create(self.r)
        self.assertEqual(P.apply_task(self.r, w, {"workflow_state": "Done"}, F.LINH), [], "chua nhan -> bo qua")

    def test_todo_reassign(self):
        self.accept()
        self.assertTrue(P.apply_todo(self.r, self.code, F.DUNG, F.HOAN))
        t = self.r.get(self.code)
        self.assertEqual(t["assignee"], F.DUNG)
        lg = [x for x in self.r.logs_ if x["event"] == C.EV_ASSIGNEE][-1]
        self.assertEqual((lg["from_value"], lg["to_value"], lg["source"]), (F.LINH, F.DUNG, C.SRC_PM))
        self.assertFalse(P.apply_todo(self.r, self.code, F.DUNG, F.HOAN), "cung nguoi -> khong ghi")
        self.assertEqual([c for c in self.pm.calls if c[0] == "assignee"], [], "khong day nguoc")

    def test_loop_guard_on_hooks(self):
        """Hook phia /pm thay co dang ghi cua Trung tam Du lieu -> bo qua (khong goi repository)."""
        import types
        fake_repo_mod = types.SimpleNamespace(flags=self.r.flags, find_by_pm_task=lambda t: (_ for _ in ()).throw(AssertionError("khong duoc tra")),
                                              log_error=self.r.log_error)
        import sys
        saved = sys.modules.get("ecentric_workspace.data_hub.repository")
        sys.modules["ecentric_workspace.data_hub.repository"] = fake_repo_mod
        import ecentric_workspace.data_hub as pkg
        saved_attr = getattr(pkg, "repository", None)
        pkg.repository = fake_repo_mod
        try:
            with P.guard(self.r):
                P.on_task_update(types.SimpleNamespace(name="TASK-1", get=lambda k: None))
                P.on_task_state("TASK-1", "To Do", "Done", F.LINH)
                P.on_todo_insert(types.SimpleNamespace(name="TD", get=lambda k: {"reference_type": "Task", "status": "Open"}.get(k)))
            self.assertEqual(self.r.errors, [], "khong tra cuu khi dang co co")
            # khong co co: tra cuu -> loi bi nuot + ghi Error Log, khong nem ra ngoai
            P.on_task_state("TASK-1", "To Do", "Done", F.LINH)
            self.assertEqual(len(self.r.errors), 1)
        finally:
            if saved is not None:
                sys.modules["ecentric_workspace.data_hub.repository"] = saved
            if saved_attr is not None:
                pkg.repository = saved_attr


# ====================================================================== thong bao =======
class TestNotify(unittest.TestCase):
    def setUp(self):
        self.r, self.pm = new_repo()

    def to(self, event=None, code=None):
        return sorted({n["to"] for n in self.r.sent(event, code)})

    def test_new_request_to_team_except_actor(self):
        code = create(self.r, user=F.LINH)
        self.assertEqual(self.to(C.EV_NEW, code), [F.DUNG, F.HOAN])
        self.assertTrue(all(n["url"] == "/du-lieu?ma=" + code for n in self.r.notes))

    def test_updates_to_requester_and_followers_not_actor(self):
        code = create(self.r)
        S.follow(F.HIEN, code, 1, repo=self.r)
        S.follow(F.LINH, code, 1, repo=self.r)
        self.r.notes = []
        O.accept(F.LINH, code, F.HOAN, repo=self.r, pm=self.pm)
        self.assertEqual(self.to(C.EV_UPDATE, code), [F.HIEN, F.THU])
        self.r.notes = []
        O.update(F.LINH, code, {"due_date": "2026-11-30", "reason": "x"}, repo=self.r, pm=self.pm)
        self.assertEqual(self.to(None, code), [F.HIEN, F.THU])
        self.r.notes = []
        O.mark_done(F.HOAN, code, repo=self.r, pm=self.pm)
        self.assertEqual(self.to(C.EV_REVIEW, code), [F.THU])
        self.assertEqual(self.to(C.EV_UPDATE, code), [F.HIEN, F.LINH])

    def test_message_mentions_and_audience(self):
        code = create(self.r)
        O.accept(F.LINH, code, F.HOAN, repo=self.r, pm=self.pm)
        self.r.notes = []
        S.send_message(F.THU, code, "@Dũng Phạm xem giúp", mentions=[F.DUNG], repo=self.r)
        self.assertEqual(self.to(C.EV_MENTION, code), [F.DUNG, F.HOAN])     # mention + tin moi (cung event type)
        self.assertEqual([n["to"] for n in self.r.notes if "nhắc bạn" in n["title"]], [F.DUNG])
        self.assertNotIn(F.THU, self.to(None, code))

    def test_reject_notifies_assignee(self):
        code = create(self.r)
        O.accept(F.LINH, code, F.HOAN, repo=self.r, pm=self.pm)
        O.mark_done(F.HOAN, code, repo=self.r, pm=self.pm)
        self.r.notes = []
        S.respond(F.THU, code, C.ACC_FAIL, "Thiếu cột", repo=self.r, pm=self.pm)
        self.assertEqual(self.to(None, code), [F.HOAN])

    def test_notify_failure_never_breaks(self):
        code = create(self.r)

        def boom(*a, **k):
            raise RuntimeError("notification down")
        self.r.notify = boom
        O.accept(F.LINH, code, F.LINH, repo=self.r, pm=self.pm)
        self.assertEqual(self.r.get(code)["status"], C.ST_DOING)
        self.assertTrue(any("notify" in e for e in self.r.errors))


class TestDailyJob(unittest.TestCase):
    def setUp(self):
        self.r, self.pm = new_repo(sync=0)    # khong co task /pm -> Trung tam tu nhac han

    def test_due_soon_overdue_skip_pm_and_off(self):
        a = create(self.r, request_type="Khác")
        O.accept(F.LINH, a, F.LINH, repo=self.r, pm=self.pm)              # han 12/11
        b = create(self.r, request_type="Khác")
        O.accept(F.LINH, b, F.HOAN, repo=self.r, pm=self.pm)
        self.r.at(d(2026, 11, 11), 9)
        self.r.off.add((F.HOAN, d(2026, 11, 11)))
        out = N.run_daily(self.r)
        self.assertEqual((out["due_soon"], out["overdue"]), (1, 0))
        self.assertEqual([n["to"] for n in self.r.sent(C.EV_DUE_SOON)], [F.LINH])
        self.r.at(d(2026, 11, 16), 9)
        out = N.run_daily(self.r)
        self.assertEqual(out["overdue"], 2)
        self.assertIn("Quá hạn 2 ngày", self.r.sent(C.EV_OVERDUE, a)[0]["title"])
        again = N.run_daily(self.r)
        self.assertEqual(len(self.r.sent(C.EV_OVERDUE, a)), 2, "fake khong dedupe; key co ngay de he that dedupe")
        self.assertIn("overdue|2026-11-16|" + a, self.r.sent(C.EV_OVERDUE, a)[0]["key"])
        self.r.tickets[a]["pm_task"] = "TASK-9"
        self.r.notes = []
        N.run_daily(self.r)
        self.assertEqual(self.r.sent(C.EV_OVERDUE, a), [], "co task /pm: PM tu nhac")
        self.assertEqual(again["overdue"], 2)

    def test_weekend_or_holiday_no_op(self):
        a = create(self.r, request_type="Khác")
        O.accept(F.LINH, a, F.LINH, repo=self.r, pm=self.pm)              # han 12/11 -> T7 14/11 da qua han
        b = create(self.r, request_type="Khác")
        O.accept(F.LINH, b, F.LINH, repo=self.r, pm=self.pm)
        O.mark_done(F.LINH, b, repo=self.r, pm=self.pm)
        self.r.notes = []
        self.r.at(d(2026, 11, 14), 9)
        self.assertEqual(N.run_daily(self.r), {"due_soon": 0, "overdue": 0, "review_reminded": 0, "auto_closed": 0})
        self.r.at(d(2026, 11, 20), 9)
        self.assertEqual(N.run_daily(self.r)["auto_closed"], 0)
        self.assertEqual(self.r.notes, [], "ngay nghi: khong nhac gi")

    def test_review_reminder_then_auto_close_after_three_working_days(self):
        code = create(self.r)
        O.accept(F.LINH, code, F.LINH, repo=self.r, pm=self.pm)
        self.r.at(d(2026, 11, 13), 16)                                     # T6
        O.mark_done(F.LINH, code, repo=self.r, pm=self.pm)
        self.r.at(d(2026, 11, 16), 9)                                      # +1
        self.assertEqual(N.run_daily(self.r)["review_reminded"], 1)
        self.r.at(d(2026, 11, 17), 9)                                      # +2
        self.assertEqual(N.run_daily(self.r)["auto_closed"], 0)
        self.r.at(d(2026, 11, 18), 9)                                      # +3 -> tu dong
        self.assertEqual(N.run_daily(self.r)["auto_closed"], 1)
        t = self.r.get(code)
        self.assertEqual((t["status"], t["acceptance"]), (C.ST_DONE, C.ACC_AUTO))
        lg = [x for x in self.r.logs_ if x["event"] == C.EV_AUTO_CLOSE][0]
        self.assertEqual((lg["actor"], lg["source"]), (C.SYSTEM_USER, C.SRC_SYSTEM))
        self.assertEqual(N.run_daily(self.r)["auto_closed"], 0)

    def test_holiday_counts_in_auto_close(self):
        code = create(self.r)
        O.accept(F.LINH, code, F.LINH, repo=self.r, pm=self.pm)
        self.r.at(d(2026, 11, 18), 16)
        O.mark_done(F.LINH, code, repo=self.r, pm=self.pm)
        self.r.at(d(2026, 11, 23), 9)                                      # 19, (20 le), 23 = 2 ngay
        self.assertEqual(N.run_daily(self.r)["auto_closed"], 0)
        self.r.at(d(2026, 11, 24), 9)
        self.assertEqual(N.run_daily(self.r)["auto_closed"], 1)


# ====================================================================== trang www =======
class _NS(dict):
    __getattr__ = dict.get


def _env():
    try:
        import jinja2
    except ImportError:
        raise unittest.SkipTest("thieu jinja2")
    from jinja2.sandbox import SandboxedEnvironment
    base = ("<!doctype html><html lang=\"vi\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            "<title>{% block title %}{% endblock %}</title>{% block style %}{% endblock %}</head>"
            "<body>{% block navbar %}NAVBAR{% endblock %}{% block content %}{% endblock %}"
            "{% block footer %}FOOTER{% endblock %}{% block script %}{% endblock %}</body></html>")
    loader = jinja2.ChoiceLoader([jinja2.DictLoader({"templates/base.html": base}), jinja2.FileSystemLoader(APP)])
    return SandboxedEnvironment(loader=loader, undefined=jinja2.StrictUndefined)


SHELL = "<aside>MENU</aside>"


def render(page, ctx, css="/a.css", js="/a.js"):
    full = {"base_template_path": "templates/base.html", "edh_shell_mount": SHELL, "edh_topbar": "<div>TOPBAR</div>",
            "edh_css": css, "edh_js": js, "title": "T", "open_code": ""}
    full.update(ctx)
    return _env().get_template("www/du_lieu/%s.html" % page).render(**full)


EVIL = '<script>alert("x")</script>'


class TestPages(unittest.TestCase):
    def setUp(self):
        self.r, self.pm, self.c = F.sample()

    def clean(self, out):
        self.assertNotIn(EVIL, out)
        self.assertNotIn("NAVBAR", out)
        self.assertNotIn("FOOTER", out)
        self.assertIn(SHELL, out)
        self.assertNotIn("/app/", out)

    def boot(self, out):
        m = re.search(r'<script type="application/json" id="edh-boot">(.*?)</script>', out, re.S)
        return json.loads(m.group(1))

    def test_index_employee(self):
        code = create(self.r, user=F.HIEN, title=EVIL, description=EVIL)
        out = render("index", S.index_page(F.THU, repo=self.r))
        self.clean(out)
        self.assertIn("&lt;script&gt;", out)
        self.assertNotIn('href="/du-lieu/dieu-phoi"', out, "nhan vien khong thay tab Dieu phoi")
        self.assertNotIn("data-edh-accept-ov", out, "khong co hop Nhan viec")
        self.assertIn('href="/du-lieu/san-co"', out)
        self.assertIn('<b>2</b></div>', out.replace("\n", ""))
        self.assertIn("100% đúng hạn", out)
        rows = re.findall(r'<tr class="edh-row[^"]*" tabindex="0" data-code="([^"]+)"[^>]*?( hidden)?>', out)
        self.assertEqual(rows[0][0], self.c["voucher"], "Khan len dau")
        self.assertEqual({c for c, h in rows if h}, {self.c["stock"], self.c["dup"]}, "mac dinh Dang mo: dong da dong an san")
        b = self.boot(out)
        self.assertEqual((b["page"], b["me"], b["open"], b["is_team"]), ("index", F.THU, None, False))
        self.assertEqual(b["type_hints"]["Power BI mới"][C.PRI_HIGH], 6)
        self.assertIn(code, [x["code"] for x in b["rows"]])
        self.assertNotIn("</script><script>", out)

    def test_index_team_and_deeplink(self):
        out = render("index", S.index_page(F.LINH, code=self.c["pnl"].lower(), repo=self.r))
        self.clean(out)
        self.assertIn('href="/du-lieu/dieu-phoi"', out)
        self.assertIn('href="/du-lieu/quy-tac"', out)
        self.assertIn("data-edh-accept-ov", out)
        self.assertIn("data-edh-detail-ov>", out, "?ma= -> popup mo san (khong hidden)")
        self.assertEqual(self.boot(out)["open"]["code"], self.c["pnl"])
        miss = render("index", S.index_page(F.LINH, code="DR-1999-0001", repo=self.r))
        self.assertIn("Không tìm thấy yêu cầu DR-1999-0001", miss)
        self.assertIn("data-edh-detail-ov hidden", miss)

    def test_gantt_view_server_state(self):
        out = render("index", S.index_page(F.THU, view="gantt", repo=self.r))
        self.assertRegex(out, r'data-edh-list hidden')
        self.assertNotRegex(out, r'data-edh-gantt hidden')
        self.assertTrue(self.boot(out)["gantt"]["lanes"])

    def test_ops_page(self):
        out = render("dieu_phoi", S.ops_page(F.LINH, repo=self.r))
        self.clean(out)
        for h in ("Chờ tiếp nhận <span>3</span>", "Đang xử lý <span>4</span>", "Chờ người gửi / Tạm dừng <span>1</span>",
                  "Xong (7 ngày) <span>1</span>"):
            self.assertIn(h, out)
        self.assertIn('data-edh-accept="%s"' % self.c["voucher"], out)
        self.assertIn("Hàng đợi #1", out)
        self.assertIn("“Cần số cho 12.12, họp BOD thứ Năm”", out)
        self.assertIn('data-edh-resume="%s"' % self.c["live"], out)
        b = self.boot(out)
        self.assertEqual(b["accept"][self.c["voucher"]]["due"], "2026-11-13", "Crawl 7 x Khan 0.5 = 4 ngay tu 09/11")
        denied = render("dieu_phoi", S.ops_page(F.THU, repo=self.r))
        self.assertIn("Chỉ team Data xem được trang này", denied)
        self.assertNotIn("data-edh-accept=", denied)

    def test_rules_and_avail_pages(self):
        out = render("quy_tac", S.rules_page(F.HOAN, repo=self.r))
        self.clean(out)
        self.assertIn("Power BI mới</td><td><b>7</b> ngày", out)
        self.assertIn("Khẩn ×0,5 · Cao ×0,8 · Bình thường ×1 · Thấp ×1,5", out)
        self.assertIn("SLA-v1", out)
        self.r.role_map[F.HOAN].discard(C.DEFAULT_DATA_TEAM_ROLE)
        self.assertIn("Quy tắc thời hạn", render("quy_tac", S.rules_page(F.HOAN, repo=self.r)), "nguoi duyet quy tac van xem")
        self.assertIn("Chỉ team Data và người duyệt quy tắc", render("quy_tac", S.rules_page(F.THU, repo=self.r)))
        out = render("san_co", S.avail_page(F.THU, repo=self.r))
        self.clean(out)
        self.assertIn("Sắp có", out)

    def test_outsider_forbidden(self):
        for fn in (S.index_page, S.ops_page, S.rules_page, S.avail_page):
            with self.assertRaises(S.Forbidden):
                fn(F.OUTSIDER, repo=self.r)

    def test_www_controllers_and_routes(self):
        hooks = io.open(os.path.join(APP, "hooks.py"), encoding="utf-8").read()
        for route, target in (("/du-lieu", "du_lieu"), ("/du-lieu/dieu-phoi", "du_lieu/dieu_phoi"),
                              ("/du-lieu/san-co", "du_lieu/san_co"), ("/du-lieu/quy-tac", "du_lieu/quy_tac")):
            self.assertIn('{"from_route": "%s", "to_route": "%s"}' % (route, target), hooks)
            src = io.open(os.path.join(APP, "www", target.replace("du_lieu", "du_lieu", 1) + ("/index.py" if target == "du_lieu" else ".py")), encoding="utf-8").read()
            self.assertIn("no_cache = 1", src)
            self.assertIn("pages.render", src)
        self.assertIn('setdefault("0 9 * * *", []).append("ecentric_workspace.data_hub.notify.daily")', hooks)
        self.assertIn('"ecentric_workspace.data_hub.pm_sync.on_task_state"', hooks)


class TestHooksAppendOnly(unittest.TestCase):
    """hooks.py: Task on_update / ToDo after_insert NOI THEM, hook cu van con; duong dan ton tai."""

    def exec_hooks(self):
        import types
        import sys
        src = io.open(os.path.join(APP, "hooks.py"), encoding="utf-8").read()
        fake_ver = types.ModuleType("ecentric_workspace.__version__")
        ns = {"__name__": "ecentric_workspace.hooks", "__package__": "ecentric_workspace"}
        import ecentric_workspace
        if not hasattr(ecentric_workspace, "__version__"):
            ecentric_workspace.__version__ = "0"
        exec(compile(src, "hooks.py", "exec"), ns)
        return ns

    def test_doc_events_appended(self):
        ns = self.exec_hooks()
        task = ns["doc_events"]["Task"]["on_update"]
        self.assertEqual(task, ["ecentric_workspace.pm.api.todo_lifecycle.pm_task_close_todos_on_terminal",
                                "ecentric_workspace.data_hub.pm_sync.on_task_update"])
        self.assertEqual(ns["doc_events"]["Task"]["before_save"], "ecentric_workspace.pm.api.tasks.pm_task_transition_guard")
        self.assertEqual(ns["doc_events"]["ToDo"]["validate"], "ecentric_workspace.weekly_report.events.validate_weekly_report_todo")
        self.assertEqual(ns["doc_events"]["ToDo"]["after_insert"], ["ecentric_workspace.data_hub.pm_sync.on_todo_insert"])
        self.assertEqual(ns["ec_pm_task_state_listeners"], ["ecentric_workspace.data_hub.pm_sync.on_task_state"])
        self.assertIn("ecentric_workspace.data_hub.notify.daily", ns["scheduler_events"]["cron"]["0 9 * * *"])
        self.assertNotIn("ec_data_hub.bundle.js", " ".join(ns["web_include_js"]), "asset chi nap tren 4 trang")
        for path in (task[-1], ns["doc_events"]["ToDo"]["after_insert"][0], ns["ec_pm_task_state_listeners"][0],
                     "ecentric_workspace.data_hub.notify.daily"):
            mod, fn = path.rsplit(".", 1)
            tree = ast.parse(io.open(os.path.join(F.ROOT, mod.replace(".", "/") + ".py"), encoding="utf-8").read())
            self.assertIn(fn, [n.name for n in tree.body if isinstance(n, ast.FunctionDef)], path)

    def test_pm_write_state_calls_listeners(self):
        src = io.open(os.path.join(APP, "pm", "task_flow.py"), encoding="utf-8").read()
        body = src[src.index("def write_state"):src.index("def add_comment")]
        self.assertIn("_state_listeners(name, cur, target, user)", body)
        self.assertIn('frappe.get_hooks("ec_pm_task_state_listeners")', src)

    def test_patch_registered_and_module(self):
        pt = io.open(os.path.join(APP, "patches.txt"), encoding="utf-8").read().splitlines()
        self.assertEqual(pt[-1], "ecentric_workspace.data_hub.patches.p001_seed_data_hub")
        self.assertIn("Data Hub", io.open(os.path.join(APP, "modules.txt"), encoding="utf-8").read().splitlines())
        src = io.open(os.path.join(APP, "data_hub", "patches", "p001_seed_data_hub.py"), encoding="utf-8").read()
        self.assertIn("def execute", src)
        self.assertNotIn("hoan.tran", "".join(io.open(os.path.join(APP, "data_hub", f), encoding="utf-8").read()
                                              for f in os.listdir(os.path.join(APP, "data_hub")) if f.endswith(".py")),
                         "khong hardcode email trong code (chi trong seed)")


class TestDoctypes(unittest.TestCase):
    def test_doctypes_system_manager_only(self):
        base = os.path.join(APP, "data_hub", "doctype")
        names = []
        for slug in sorted(os.listdir(base)):
            p = os.path.join(base, slug, slug + ".json")
            if not os.path.isfile(p):
                continue
            j = json.load(io.open(p, encoding="utf-8"))
            names.append(j["name"])
            self.assertEqual(j["module"], "Data Hub")
            self.assertEqual({x["role"] for x in j["permissions"]} - {"System Manager"}, set(), j["name"])
            self.assertFalse(any(x.get("create") or x.get("delete") for x in j["permissions"]), j["name"])
        self.assertEqual(set(names), {C.TICKET_DT, C.LOG_DT, C.MSG_DT, C.FOLLOWER_DT, C.FILE_DT, C.SETTINGS_DT,
                                      C.RULE_DT, C.RULE_ITEM_DT})

    def test_select_options_match_constants(self):
        j = json.load(io.open(os.path.join(APP, "data_hub", "doctype", "ec_data_ticket", "ec_data_ticket.json"), encoding="utf-8"))
        f = {x["fieldname"]: x for x in j["fields"]}
        self.assertEqual(f["status"]["options"].split("\n"), list(C.STATUSES))
        self.assertEqual(f["request_type"]["options"].split("\n")[1:], list(C.REQUEST_TYPES))
        self.assertEqual(f["priority"]["options"].split("\n")[1:], list(C.PRIORITIES))
        log = json.load(io.open(os.path.join(APP, "data_hub", "doctype", "ec_data_ticket_log", "ec_data_ticket_log.json"), encoding="utf-8"))
        ev = {x["fieldname"]: x for x in log["fields"]}["event"]["options"].split("\n")
        self.assertEqual(ev, list(C.LOG_EVENTS))
        from ecentric_workspace.data_hub import repository  # noqa: F401  (import duoc voi frappe gia)


# ====================================================================== nav =============
class TestNav(unittest.TestCase):
    def mods(self):
        from ecentric_workspace.shell.tests import test_server_nav as T
        import sys
        saved = sys.modules.get("frappe")
        sys.modules["frappe"] = T._fake_frappe()
        self.addCleanup(lambda: sys.modules.__setitem__("frappe", saved) if saved else sys.modules.pop("frappe", None))
        return T._mods()

    def test_routes_light_reports_section_with_data_group(self):
        _, nav, sn = self.mods()
        for route in ("/du-lieu", "/du-lieu/dieu-phoi", "/du-lieu/san-co", "/du-lieu/quy-tac"):
            self.assertEqual(nav.resolve_context(route), "data_hub", route)
        self.assertTrue(nav.validate_rail())
        sec = [s for s in nav.RAIL if "data_hub" in s["contexts"]]
        self.assertEqual([s["key"] for s in sec], ["reports"])
        page = ('<div><aside class="ec-shell-mount" data-ec-shell="1" aria-label="n"><nav>old</nav></aside><main>x</main></div>')
        html = sn.rebuild_mount(page, "/du-lieu")
        self.assertIn('data-ec-shell-rail="reports"', html.split("ec-shell-railon")[1][:80])
        self.assertIn('class="ec-shell-grouplabel">Dữ liệu<', html)
        self.assertIn('data-ec-shell-key="data_hub.requests" aria-current="page"', html)
        self.assertNotIn("data_hub.ops", html, "render chung (khong role) khong thay Dieu phoi")
        self.assertNotIn('grouplabel">Mục khác<', html)

    def test_role_gating(self):
        _, nav, _ = self.mods()
        keys = lambda roles: [i["key"] for i in nav.compose("data_hub", roles=roles)]
        self.assertNotIn("data_hub.ops", keys(["Employee"]))
        self.assertIn("data_hub.ops", keys(["Employee", C.DEFAULT_DATA_TEAM_ROLE]))
        self.assertIn("data_hub.rules", keys([C.DEFAULT_DATA_TEAM_ROLE]))
        lay = [s for s in nav.rail_spec([C.DEFAULT_DATA_TEAM_ROLE]) if s["key"] == "reports"][0]["layout"]
        grp = [b for b in lay if b.get("label") == "Dữ liệu"][0]
        self.assertEqual([i["key"] for i in grp["items"]], ["data_hub.requests", "data_hub.availability", "data_hub.ops",
                                                            "data_hub.rules"])


# ====================================================================== fixture jsdom ===
FIX = os.path.join(HERE, "js", "fixtures")


def fixture_pages():
    """HTML that cua 3 trang (bo mau) - nguon cho test jsdom + ban xem thu."""
    r, pm, c = F.sample()
    out = {
        "index_user": render("index", S.index_page(F.THU, repo=r)),
        "index_team": render("index", S.index_page(F.LINH, repo=r)),
        "ops_team": render("dieu_phoi", S.ops_page(F.LINH, repo=r)),
    }
    details = {code: {u: S.detail(u, code, repo=r) for u in (F.THU, F.HIEN, F.LINH)} for code in c.values()}
    api = {"details": details, "gantt": S.gantt_data(F.THU, repo=r), "codes": c,
           "gantt_next": S.gantt_data(F.THU, start="2026-11-09", repo=r),
           "preview": {code: S.accept_defaults(r, r.get(code), start="2026-11-10") for code in (c["voucher"], c["tiktok"], c["clean"])},
           "people": r.people("")}
    return out, api


class TestFixtures(unittest.TestCase):
    def test_fixtures_current(self):
        pages, api = fixture_pages()
        files = {name + ".html": html for name, html in pages.items()}
        files["api.json"] = json.dumps(api, ensure_ascii=False, indent=1, sort_keys=True, default=str) + "\n"
        if os.environ.get("EDH_UPDATE_FIXTURES"):
            os.makedirs(FIX, exist_ok=True)
            for name, text in files.items():
                with io.open(os.path.join(FIX, name), "w", encoding="utf-8") as fh:
                    fh.write(text)
        for name, text in files.items():
            p = os.path.join(FIX, name)
            self.assertTrue(os.path.isfile(p), "thieu fixture %s - chay voi EDH_UPDATE_FIXTURES=1" % name)
            self.assertEqual(io.open(p, encoding="utf-8").read(), text,
                             "fixture %s cu - chay lai voi EDH_UPDATE_FIXTURES=1" % name)


if __name__ == "__main__":
    unittest.main()
