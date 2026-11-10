# Copyright (c) 2026, eCentric and contributors
"""Trung tam Du lieu DOT 3 - sua + duyet quy tac thoi han, chuyen phieu Data Request cu, the Approval
Center tro /du-lieu, deep link ma cu. Chay THAT rules_service / migration / legacy / service tren repo gia
(fake.py + fake_d3.py), render trang quy tac bang jinja2 (khong can bench).

    python -m unittest ecentric_workspace.data_hub.tests.test_data_hub_d3

Fixture jsdom cua trang quy tac (tests/js/fixtures/rules_*.html + rules_api.json) sinh tu CHINH bo mau nay;
TestRulesFixtures kiem khong cu. Sinh lai: EDH_UPDATE_FIXTURES=1 python -m unittest ...test_data_hub_d3
"""
import ast
import datetime as dt
import importlib
import io
import json
import os
import re
import types
import unittest

from ecentric_workspace.data_hub.tests import fake as F  # noqa: E402  (dat frappe gia neu thieu)
from ecentric_workspace.data_hub.tests import fake_d3 as F3
from ecentric_workspace.data_hub.tests.test_data_hub import EVIL, render
from ecentric_workspace.data_hub import constants as C
from ecentric_workspace.data_hub import domain as D
from ecentric_workspace.data_hub import legacy as L
from ecentric_workspace.data_hub import migration as M
from ecentric_workspace.data_hub import ops_service as O
from ecentric_workspace.data_hub import rules_domain as RD
from ecentric_workspace.data_hub import rules_service as R
from ecentric_workspace.data_hub import service as S

APP = os.path.join(F.ROOT, "ecentric_workspace")
HERE = os.path.dirname(os.path.abspath(__file__))
FIX = os.path.join(HERE, "js", "fixtures")
d = dt.date
ts = F3.ts


def new_repo(**kw):
    r = F.FakeRepo(**kw)
    return r, F.FakePM(r)


def active_view(r):
    return RD.view(r.rule_set())


def propose(r, user=F.LINH, days=None, mult=None, reason="Dashboard mới hay cần 3+ nguồn", submit=0):
    return R.save_draft(user, {"days": days if days is not None else {"pbi_new": 10}, "mult": mult or {},
                               "reason": reason, "submit": submit}, repo=r)


# ====================================================================== quy tac: thuan ==========
class TestRulesDomain(unittest.TestCase):
    def setUp(self):
        self.av = active_view(F.FakeRepo())

    def test_normalize_partial_keeps_active_and_parses_comma(self):
        v = RD.normalize_input({"days": {"pbi_new": "10", "intake": 2}, "mult": {C.PRI_URGENT: "0,6"}, "reason": " x "},
                               self.av)
        self.assertEqual(v["days"]["pbi_new"], 10)
        self.assertEqual(v["days"]["intake"], 2)
        self.assertEqual(v["days"]["crawl_new"], 7, "khoa khong gui -> giu dang ap dung")
        self.assertEqual(v["mult"][C.PRI_URGENT], 0.6)
        self.assertEqual(v["mult"][C.PRI_LOW], 1.5)
        self.assertEqual(v["reason"], "x")

    def test_limits_table(self):
        cases = [
            ({"days": {"pbi_new": 0}}, "số ngày từ 1 đến 60"),
            ({"days": {"pbi_new": 61}}, "số ngày từ 1 đến 60"),
            ({"days": {"pbi_new": "7.5"}}, "số nguyên"),
            ({"days": {"pbi_new": 7.5}}, "số nguyên"),
            ({"days": {"pbi_new": True}}, "số nguyên"),
            ({"days": {"pbi_new": "abc"}}, "số nguyên"),
            ({"mult": {C.PRI_HIGH: "0,2"}}, "từ 0,25 đến 3"),
            ({"mult": {C.PRI_HIGH: 3.01}}, "từ 0,25 đến 3"),
            ({"mult": {C.PRI_HIGH: "x"}}, "phải là số"),
            ({"mult": {C.PRI_HIGH: "0,333"}}, "2 chữ số thập phân"),
            ({"days": {"bogus": 3}}, "Không có mục quy tắc: bogus"),
            ({"reason": "x" * 1001}, "Lý do dài quá"),
        ]
        for data, msg in cases:
            with self.assertRaises(D.Invalid, msg=str(data)) as cm:
                RD.normalize_input(data, self.av)
            self.assertIn(msg, " ".join(cm.exception.errors), data)
        for ok in ({"days": {"pbi_new": 1}}, {"days": {"pbi_new": 60}}, {"mult": {C.PRI_HIGH: 0.25}},
                   {"mult": {C.PRI_HIGH: "3"}}, {"days": {"pbi_new": 7.0}}):
            RD.normalize_input(ok, self.av)

    def test_diff_and_summary(self):
        new = RD.normalize_input({"days": {"crawl_new": 5}, "mult": {C.PRI_URGENT: 0.6}}, self.av)
        ch = RD.diff(self.av, new)
        self.assertEqual([(c["key"], c["old"], c["new"]) for c in ch], [("crawl_new", 7, 5), (C.PRI_URGENT, 0.5, 0.6)])
        self.assertEqual(RD.summary(ch), "Crawl data mới 7 → 5 ngày; Hệ số Khẩn ×0,5 → ×0,6")
        self.assertEqual(RD.diff(self.av, self.av), [])
        self.assertEqual(RD.summary([]), "Không đổi so với bộ trước")
        many = [{"text": str(i)} for i in range(6)]
        self.assertEqual(RD.summary(many), "0; 1; 2; 3; và 2 thay đổi khác")

    def test_to_doc_roundtrip(self):
        new = RD.normalize_input({"days": {"pbi_new": 9}}, self.av)
        doc = dict(RD.to_doc(new, self.av["labels"]), name="X", version_no=9)
        back = RD.view(doc)
        self.assertEqual(back["days"], new["days"])
        self.assertEqual(back["mult"], new["mult"])
        self.assertEqual([i["rule_key"] for i in doc["items"]], [r[0] for r in C.RULE_DEFAULTS])


# ====================================================================== quy tac: luong ==========
class TestRulesFlow(unittest.TestCase):
    def setUp(self):
        self.r, self.pm = new_repo()

    def test_draft_created_by_team_with_version_and_base(self):
        out = propose(self.r)
        self.assertEqual(out, {"name": "SLA-v2", "version": 2, "status": C.RULE_DRAFT})
        rs = self.r.rule_doc("SLA-v2")
        self.assertEqual((rs["proposed_by"], rs["supersedes"], rs["status"]), (F.LINH, "SLA-v1", C.RULE_DRAFT))
        self.assertEqual(RD.view(rs)["days"]["pbi_new"], 10)
        self.assertEqual(self.r.settings()["active_rule_set"], "SLA-v1", "nhap khong doi bo dang ap dung")
        self.assertGreaterEqual(self.r.rule_locks, 1, "ghi quy tac luon khoa truoc")
        self.assertEqual(self.r.notes, [], "luu nhap khong bao ai")

    def test_permissions_to_propose(self):
        for user in (F.THU, F.OUTSIDER):
            with self.assertRaises(S.Forbidden):
                propose(self.r, user=user)
        self.r.role_map[F.HOAN].discard(C.DEFAULT_DATA_TEAM_ROLE)
        with self.assertRaises(S.Forbidden, msg="nguoi duyet khong o team Data thi khong tu de xuat"):
            propose(self.r, user=F.HOAN)
        self.assertEqual(propose(self.r, user=F.ADMIN)["status"], C.RULE_DRAFT, "System Manager duoc de xuat")

    def test_single_open_change(self):
        propose(self.r)
        with self.assertRaises(S.DataHubError) as cm:
            propose(self.r, user=F.DUNG, days={"pbi_edit": 4})
        self.assertIn("Linh Vương đang có bản nháp v2", str(cm.exception))
        again = propose(self.r, days={"pbi_new": 12})
        self.assertEqual(again["name"], "SLA-v2", "nguoi tao sua lai CHINH ban nhap, khong tao ban moi")
        self.assertEqual(RD.view(self.r.rule_doc("SLA-v2"))["days"]["pbi_new"], 12)
        R.submit(F.LINH, "SLA-v2", repo=self.r)
        with self.assertRaises(S.DataHubError) as cm:
            propose(self.r, days={"pbi_new": 8})
        self.assertIn("chờ duyệt", str(cm.exception))

    def test_validation_reaches_service(self):
        with self.assertRaises(S.DataHubError) as cm:
            propose(self.r, days={"pbi_new": 0, "intake": "x"})
        self.assertIn("số ngày từ 1 đến 60", str(cm.exception))
        self.assertIn("số nguyên", str(cm.exception))
        with self.assertRaises(S.DataHubError) as cm:
            propose(self.r, days={"pbi_new": 7})
        self.assertIn("Chưa có gì thay đổi", str(cm.exception))
        self.assertEqual(R.open_change(self.r), None, "loi -> khong de lai ban nhap")

    def test_submit_requires_reason_and_notifies_approver_from_settings(self):
        propose(self.r, reason="")
        with self.assertRaises(S.DataHubError) as cm:
            R.submit(F.LINH, "SLA-v2", repo=self.r)
        self.assertIn("Ghi lý do", str(cm.exception))
        self.r.settings_["rule_approver"] = F.DUNG          # doi nguoi duyet trong Settings -> bao dung nguoi moi
        out = R.submit(F.LINH, "SLA-v2", "Dashboard mới cần 3+ nguồn", repo=self.r)
        self.assertEqual((out["status"], out["approver"]), (C.RULE_PENDING, F.DUNG))
        rs = self.r.rule_doc("SLA-v2")
        self.assertEqual((rs["status"], rs["reason"]), (C.RULE_PENDING, "Dashboard mới cần 3+ nguồn"))
        self.assertTrue(rs["submitted_at"])
        sent = self.r.sent(code="SLA-v2")
        self.assertEqual([(n["event"], n["to"]) for n in sent], [("approval_required", F.DUNG)])
        self.assertEqual((sent[0]["url"], sent[0]["doctype"]), ("/du-lieu/quy-tac", C.RULE_DT))
        self.assertIn("Power BI mới 7 → 10 ngày", sent[0]["message"])
        self.assertIn("v2", sent[0]["title"])

    def test_submit_without_approver_configured(self):
        self.r.settings_["rule_approver"] = ""
        with self.assertRaises(S.DataHubError) as cm:
            propose(self.r, submit=1)
        self.assertIn("Chưa cấu hình người duyệt", str(cm.exception))

    def test_submit_only_own_draft(self):
        propose(self.r)
        with self.assertRaises(S.Forbidden):
            R.submit(F.DUNG, "SLA-v2", "x", repo=self.r)
        R.submit(F.ADMIN, "SLA-v2", "x", repo=self.r)    # System Manager ho tro
        with self.assertRaises(S.DataHubError):
            R.submit(F.LINH, "SLA-v2", "x", repo=self.r)  # da cho duyet

    def test_approve_activates_new_expires_old(self):
        propose(self.r, submit=1)
        self.r.advance(days=1)
        for user in (F.LINH, F.DUNG, F.THU, F.ADMIN):
            with self.assertRaises(S.Forbidden, msg=user):
                R.decide(user, "SLA-v2", "approve", repo=self.r)
        self.r.notes.clear()
        out = R.decide(F.HOAN, "SLA-v2", "approve", "OK", repo=self.r)
        self.assertEqual(out, {"name": "SLA-v2", "status": C.RULE_ACTIVE, "previous": "SLA-v1"})
        new, old = self.r.rule_doc("SLA-v2"), self.r.rule_doc("SLA-v1")
        self.assertEqual((new["status"], new["effective_from"], new["decided_by"], new["decision_note"]),
                         (C.RULE_ACTIVE, d(2026, 11, 10), F.HOAN, "OK"))
        self.assertEqual(old["status"], C.RULE_EXPIRED)
        self.assertEqual(self.r.settings()["active_rule_set"], "SLA-v2")
        self.assertEqual(S.rules(self.r)["days"]["pbi_new"], 10)
        self.assertEqual(sorted(n["to"] for n in self.r.notes), sorted([F.LINH, F.DUNG]),
                         "bao nguoi de xuat + team Data, khong bao chinh nguoi duyet")
        self.assertIn("yêu cầu MỚI", self.r.notes[0]["message"])
        with self.assertRaises(S.DataHubError):
            R.decide(F.HOAN, "SLA-v2", "approve", repo=self.r)     # bam lan 2

    def test_admin_decides_only_when_no_approver(self):
        propose(self.r, submit=1)
        self.r.settings_["rule_approver"] = ""
        self.assertTrue(R.can_decide(self.r, F.ADMIN))
        self.assertFalse(R.can_decide(self.r, F.HOAN))
        R.decide(F.ADMIN, "SLA-v2", "approve", repo=self.r)
        self.assertEqual(self.r.settings()["active_rule_set"], "SLA-v2")

    def test_reject_needs_reason_and_keeps_active(self):
        propose(self.r, submit=1)
        with self.assertRaises(S.DataHubError) as cm:
            R.decide(F.HOAN, "SLA-v2", "reject", "  ", repo=self.r)
        self.assertIn("lý do từ chối", str(cm.exception))
        self.r.notes.clear()
        R.decide(F.HOAN, "SLA-v2", "reject", "7 ngày vẫn đủ", repo=self.r)
        rs = self.r.rule_doc("SLA-v2")
        self.assertEqual((rs["status"], rs["decision_note"], rs["decided_by"]), (C.RULE_REJECTED, "7 ngày vẫn đủ", F.HOAN))
        self.assertEqual(self.r.settings()["active_rule_set"], "SLA-v1")
        self.assertEqual(self.r.rule_doc("SLA-v1")["status"], C.RULE_ACTIVE)
        self.assertEqual([(n["to"], n["event"]) for n in self.r.notes], [(F.LINH, "mention")])
        self.assertIn("7 ngày vẫn đủ", self.r.notes[0]["message"])
        self.assertEqual(propose(self.r, days={"pbi_new": 9})["name"], "SLA-v3", "tu choi xong -> de xuat moi la v3")
        with self.assertRaises(S.DataHubError):
            R.decide(F.HOAN, "SLA-v2", "maybe", repo=self.r)

    def test_cancel_draft_and_withdraw_pending(self):
        propose(self.r)
        with self.assertRaises(S.Forbidden):
            R.cancel(F.DUNG, "SLA-v2", repo=self.r)
        R.cancel(F.LINH, "SLA-v2", "đổi ý", repo=self.r)
        self.assertEqual(self.r.rule_doc("SLA-v2")["status"], C.RULE_CANCELLED)
        self.assertEqual(self.r.notes, [], "huy ban nhap chua gui -> khong bao ai")
        propose(self.r, submit=1)
        self.r.notes.clear()
        R.cancel(F.LINH, "SLA-v3", repo=self.r)
        self.assertEqual([(n["to"], n["title"]) for n in self.r.notes], [(F.HOAN, "Đã rút lại đề xuất quy tắc v3")])
        with self.assertRaises(S.DataHubError):
            R.cancel(F.LINH, "SLA-v3", repo=self.r)
        with self.assertRaises(S.DataHubError):
            R.cancel(F.LINH, "SLA-v1", repo=self.r)
        with self.assertRaises(S.DataHubError):
            R.cancel(F.LINH, "SLA-v99", repo=self.r)

    def test_new_rules_apply_to_new_tickets_only(self):
        old = S.create(F.THU, F.req(), repo=self.r)["code"]                        # Power BI moi, v1: 7 ngay
        propose(self.r, days={"pbi_new": 10, "intake": 2}, submit=1)
        R.decide(F.HOAN, "SLA-v2", "approve", repo=self.r)
        new = S.create(F.HIEN, F.req(), repo=self.r)["code"]
        t_old, t_new = self.r.get(old), self.r.get(new)
        self.assertEqual((t_old["rule_version"], t_old["sla_days"], t_old["intake_due_date"]), ("SLA-v1", 7, d(2026, 11, 10)))
        self.assertEqual((t_new["rule_version"], t_new["sla_days"], t_new["intake_due_date"]), ("SLA-v2", 10, d(2026, 11, 11)))
        self.assertEqual(S.accept_defaults(self.r, t_old)["sla_days"], 7, "goi y han khi nhan: theo bo cua yeu cau")
        O.accept(F.LINH, old, F.LINH, repo=self.r, pm=self.pm)
        O.accept(F.LINH, new, F.LINH, repo=self.r, pm=self.pm)
        t_old, t_new = self.r.get(old), self.r.get(new)
        self.assertEqual((t_old["due_date"], t_old["sla_days"], t_old["rule_version"]), (d(2026, 11, 18), 7, "SLA-v1"),
                         "yeu cau cu nhan SAU khi doi quy tac van giu han cu")
        self.assertEqual((t_new["due_date"], t_new["sla_days"], t_new["rule_version"]), (d(2026, 11, 24), 10, "SLA-v2"))
        page = S.index_page(F.THU, repo=self.r)
        self.assertEqual(page["type_hints"]["Power BI mới"][C.PRI_NORMAL], 10, "form tao hien quy tac moi")

    def test_ticket_rules_fallbacks(self):
        self.assertEqual(S.ticket_rules(self.r, {"rule_version": "SLA-v404"})["version"], "SLA-v1")
        self.assertEqual(S.ticket_rules(self.r, {})["version"], "SLA-v1")

    def test_history_with_diff(self):
        propose(self.r, days={"crawl_new": 5}, submit=1)
        R.decide(F.HOAN, "SLA-v2", "approve", repo=self.r)
        propose(self.r, days={"crawl_new": 7}, mult={C.PRI_LOW: 2}, submit=1)
        R.decide(F.HOAN, "SLA-v3", "reject", "giữ", repo=self.r)
        propose(self.r, days={"pbi_new": 8})                         # ban nhap: khong vao lich su
        h = R.history(self.r)
        self.assertEqual([(x["label"], x["status"]) for x in h],
                         [("v3", C.RULE_REJECTED), ("v2", C.RULE_ACTIVE), ("v1", C.RULE_EXPIRED)])
        self.assertEqual([c["text"] for c in h[0]["changes"]], ["Crawl data mới 5 → 7 ngày", "Hệ số Thấp ×1,5 → ×2"])
        self.assertEqual([(c["old_fmt"], c["new_fmt"]) for c in h[1]["changes"]], [("7 ngày", "5 ngày")])
        self.assertTrue(h[2]["first"])


# ====================================================================== quy tac: trang ==========
def rules_html(r, user):
    ctx = S.rules_page(user, repo=r)
    return render("quy_tac", dict(ctx, edh_rules_js="/r.js", edh_rules_css="/r.css")), ctx


def boot_of(out):
    m = re.search(r'<script type="application/json" id="edh-boot">(.*?)</script>', out, re.S)
    return json.loads(m.group(1))


class TestRulesPage(unittest.TestCase):
    def setUp(self):
        self.r, self.pm, self.c = F.sample()

    def test_team_can_propose(self):
        out, _ = rules_html(self.r, F.LINH)
        self.assertIn('data-edh-rules-edit>Sửa quy tắc</button>', out)
        self.assertIn("Gửi Hoàn Trần duyệt", out, "ten nguoi duyet lay tu Settings")
        self.assertNotIn("data-edh-rules-banner", out)
        self.assertNotIn("is-editing", out, "trang thai dau: che do xem")
        self.assertIn('<script src="/r.js" defer></script>', out)
        self.assertIn('<link rel="stylesheet" href="/r.css">', out)
        self.assertLess(out.index('src="/a.js"'), out.index('src="/r.js"'), "bundle chung nap truoc")
        b = boot_of(out)
        self.assertEqual((b["page"], b["can"]["propose"], b["draft"]), ("rules", True, None))
        self.assertEqual(b["active"]["days"]["pbi_new"], 7)

    def test_other_pages_do_not_load_rules_bundle(self):
        out = render("index", S.index_page(F.THU, repo=self.r))
        self.assertNotIn("ec_data_hub_rules", out)
        self.assertNotIn("/r.js", out)

    def test_draft_views(self):
        propose(self.r, reason=EVIL)
        out, _ = rules_html(self.r, F.LINH)
        self.assertIn("Bạn đang có bản nháp v2", out)
        self.assertIn('<span class="edh-chg">10 ngày</span>', out)
        self.assertIn("data-edh-rules-edit>Sửa bản nháp", out)
        self.assertIn('data-edh-rules-send="view" data-name="SLA-v2">Gửi Hoàn Trần duyệt', out)
        self.assertIn('data-edh-rules-ask="discard"', out)
        self.assertNotIn(EVIL, out)
        self.assertEqual(boot_of(out)["draft"]["days"]["pbi_new"], 10)
        other, _ = rules_html(self.r, F.DUNG)
        self.assertIn("Linh Vương đang có bản nháp v2", other)
        self.assertNotIn("data-edh-rules-edit", other)
        self.assertNotIn("data-edh-rules-days", other, "nguoi khac khong co o sua")
        self.assertIsNone(boot_of(other)["draft"])

    def test_pending_views_proposer_and_approver_without_team_role(self):
        propose(self.r, submit=1)
        out, _ = rules_html(self.r, F.LINH)
        self.assertIn("Đang chờ Hoàn Trần duyệt 1 thay đổi quy tắc (v2", out)
        self.assertIn('data-edh-rules-ask="withdraw"', out)
        self.assertNotIn('data-edh-rules-ask="approve"', out)
        self.r.role_map[F.HOAN].discard(C.DEFAULT_DATA_TEAM_ROLE)          # nguoi duyet KHONG o team Data
        out, _ = rules_html(self.r, F.HOAN)
        self.assertIn("Có 1 thay đổi quy tắc (v2) chờ bạn duyệt", out)
        self.assertIn('data-edh-rules-ask="approve" data-name="SLA-v2">Duyệt thay đổi', out)
        self.assertIn('data-edh-rules-ask="reject"', out)
        self.assertIn("Lý do của Linh Vương: “Dashboard mới hay cần 3+ nguồn”", out)
        self.assertNotIn('data-edh-rules-ask="withdraw"', out)
        self.assertIn('href="/du-lieu/quy-tac"', out, "tab Quy tac van hien cho nguoi duyet")
        self.assertNotIn('href="/du-lieu/dieu-phoi"', out)
        dung, _ = rules_html(self.r, F.DUNG)
        self.assertNotIn('data-edh-rules-ask=', dung, "team Data khac: chi xem")
        self.assertIn("Chờ xử lý thay đổi v2", dung)

    def test_history_rendered_with_diff_and_denied(self):
        propose(self.r, days={"crawl_new": 5}, submit=1)
        R.decide(F.HOAN, "SLA-v2", "approve", repo=self.r)
        out, _ = rules_html(self.r, F.LINH)
        self.assertIn("<b>v2 · 09/11/2026</b>", out)
        self.assertIn('Crawl data mới: <del>7 ngày</del> → <ins class="edh-chg">5 ngày</ins>', out)
        self.assertIn("Đề xuất: Linh Vương", out)
        self.assertIn("Duyệt: Hoàn Trần", out)
        self.assertIn("Đang áp dụng: <b>v2</b> · từ 09/11/2026", out)
        denied, _ = rules_html(self.r, F.THU)
        self.assertIn("Chỉ team Data và người duyệt quy tắc", denied)
        self.assertNotIn("data-edh-rules-form", denied)


# ====================================================================== phieu cu: bang chuyen ====
def legacy_rec(name="EC-DATA-2026-00001", approval="Approved", fulfill="Completed", **kw):
    rec = {"name": name, "request_title": "New BI report - 2026-07-20", "requested_by": F.THU,
           "department": "Commercial - EC", "detailed_description": "Cần báo cáo GMV theo ngày",
           "request_type": "New BI report", "urgency": "U2: within next 3 days",
           "importance": "I2: minor impact to >2 customers, possible workaround",
           "expected_resolution_date": d(2026, 7, 20), "request_attachment": "/private/files/brief.xlsx",
           "submitted_at": ts(2026, 7, 6, 9), "completed_at": ts(2026, 7, 15, 17),
           "approval_request": "EC-APR-2026-00001" if approval else None, "approval_status": approval,
           "approval_completed_at": ts(2026, 7, 7, 10), "fulfillment_status": fulfill,
           "assigned_fulfiller": F.LINH, "fulfillment_owner": F.LINH, "fulfillment_due_at": ts(2026, 7, 18, 18),
           "fulfillment_summary": "Đã làm dashboard", "output_link": "https://app.powerbi.com/x",
           "output_attachment": None, "completed_by": F.LINH, "creation": ts(2026, 7, 6, 8, 50)}
    rec.update(kw)
    return rec


def acts(*rows):
    out = []
    for i, (action, actor, when, comment) in enumerate(rows, 1):
        out.append({"name": "ACT-%d" % i, "seq": i, "actor": actor, "action": action, "comment": comment,
                    "action_time": when, "new_status": "", "level_no": 1 if action in ("Approved", "Rejected") else 0,
                    "level_name": "Data Review" if action in ("Approved", "Rejected") else ""})
    return out


class TestLegacyMapping(unittest.TestCase):
    RULES = D.rules_view(F.FakeRepo().rule_set())

    def test_type_table(self):
        table = {"Data accuracy, visualization, retrieval": "Xử lý dữ liệu", "New BI report": "Power BI mới",
                 "Historical data crawling": "Crawl data mới", "Client onboarding": "Khác", "Client offboarding": "Khác",
                 "Data training": "Khác", "Access": "Khác", "Other": "Khác", "": "Khác", None: "Khác", "Lạ": "Khác"}
        for old, new in table.items():
            self.assertEqual(L.map_type(old), new, old)
            self.assertIn(L.map_type(old), C.REQUEST_TYPES)

    def test_priority_table(self):
        table = [
            ("U0: as soon as possible", "I3: known bug", C.PRI_URGENT),
            ("U1: within next 24 hours", "I3: x", C.PRI_HIGH),
            ("U2: within next 3 days", "I2: x", C.PRI_NORMAL),
            ("U3: non-urgent / nice to have", "I3: x", C.PRI_LOW),
            ("U3: non-urgent / nice to have", "I0: large-scale impact", C.PRI_HIGH),
            ("U2: within next 3 days", "I1: major", C.PRI_NORMAL),
            ("U3: x", "I1: major", C.PRI_NORMAL),
            ("U1: x", "I0: x", C.PRI_HIGH),
            ("", "", C.PRI_NORMAL),
            (None, "I0: x", C.PRI_HIGH),
        ]
        for u, i, want in table:
            self.assertEqual(L.map_priority(u, i), want, (u, i))

    def test_status_table(self):
        table = [
            ("Pending", "Not Started", True, C.ST_WAITING),
            ("Information Required", None, True, C.ST_WAITING),
            ("Approved", "Assigned", True, C.ST_WAITING),
            ("Approved", "Not Started", True, C.ST_WAITING),
            ("Approved", "", True, C.ST_WAITING),
            ("Approved", "In Progress", True, C.ST_DOING),
            ("Approved", "Completed", True, C.ST_DONE),
            ("Rejected", "Not Started", True, C.ST_CANCELLED),
            ("Cancelled", "Assigned", True, C.ST_CANCELLED),
            (None, None, False, None),
            ("Pending", None, False, None),
            ("Weird", None, True, None),
            ("Approved", "Weird", True, None),
        ]
        for a, f, has, want in table:
            self.assertEqual(L.map_status(a, f, has)[0], want, (a, f, has))

    def build(self, rec, actions=()):
        return L.build_ticket(rec, list(actions), self.RULES, F.MON, F.HOLIDAYS, now=ts(2026, 11, 9, 9, 30))

    def test_done(self):
        p = self.build(legacy_rec(), acts(("Submitted", F.THU, ts(2026, 7, 6, 9), ""),
                                          ("Approved", F.HOAN, ts(2026, 7, 7, 10), "ok"),
                                          ("Started", F.LINH, ts(2026, 7, 8, 9), ""),
                                          ("Completed", F.LINH, ts(2026, 7, 15, 17), "")))
        v = p["values"]
        self.assertEqual((v["status"], v["request_type"], v["proposed_priority"], v["priority"]),
                         (C.ST_DONE, "Power BI mới", C.PRI_NORMAL, C.PRI_NORMAL))
        self.assertEqual((v["assignee"], v["acceptance"], v["done_at"], v["closed_at"]),
                         (F.LINH, C.ACC_OK, ts(2026, 7, 15, 17), ts(2026, 7, 15, 17)))
        self.assertEqual((v["start_date"], v["due_date"], v["legacy_ref"]), (d(2026, 7, 8), d(2026, 7, 18), "EC-DATA-2026-00001"))
        self.assertEqual((v["requester"], v["requester_department"], v["output_link"]),
                         (F.THU, "Commercial - EC", "https://app.powerbi.com/x"))
        self.assertTrue(D.on_time(v), "xong 15/07 <= han 18/07")
        self.assertIn("Loại cũ: New BI report", v["description"])
        self.assertIn("Kết quả xử lý: Đã làm dashboard", v["description"])
        self.assertTrue(v["description"].startswith("Cần báo cáo GMV theo ngày"))
        self.assertEqual(p["created"], ts(2026, 7, 6, 9))
        self.assertEqual([lg["event"] for lg in p["logs"]],
                         [C.EV_CREATED, C.EV_LEGACY_HISTORY, C.EV_LEGACY_HISTORY, C.EV_LEGACY_HISTORY, C.EV_LEGACY])
        self.assertEqual([lg["at"] for lg in p["logs"][:4]],
                         [ts(2026, 7, 6, 9), ts(2026, 7, 7, 10), ts(2026, 7, 8, 9), ts(2026, 7, 15, 17)], "giu gio goc")
        self.assertEqual((p["logs"][1]["from_value"], p["logs"][1]["to_value"], p["logs"][1]["note"]),
                         ("Approved", "Cấp 1 · Data Review", "ok"))

    def test_doing_waiting_cancelled(self):
        p = self.build(legacy_rec(fulfill="In Progress", fulfillment_due_at=None, expected_resolution_date=None),
                       acts(("Started", F.DUNG, ts(2026, 11, 2, 9), "")))
        v = p["values"]
        self.assertEqual((v["status"], v["assignee"], v["accepted_by"], v["start_date"]), (C.ST_DOING, F.LINH, F.LINH, d(2026, 11, 2)))
        self.assertEqual(v["due_date"], d(2026, 11, 11), "khong co han cu -> theo quy tac (7 ngay lam viec)")
        self.assertEqual(p["logs"][0]["event"], C.EV_CREATED, "khong co Submitted -> tu them dong Tao")
        p = self.build(legacy_rec(fulfill="In Progress", fulfillment_owner=None))
        self.assertEqual(p["values"]["status"], C.ST_WAITING, "dang xu ly ma khong co nguoi -> cho tiep nhan")
        self.assertIn("không có người nhận", p["logs"][-1]["note"])
        p = self.build(legacy_rec(approval="Pending", fulfill="Not Started", urgency="U0: as soon as possible"))
        v = p["values"]
        self.assertEqual((v["status"], v["priority"], v["proposed_priority"]), (C.ST_WAITING, "", C.PRI_URGENT))
        self.assertEqual(v["urgent_reason"], "Phiếu cũ: U0: as soon as possible")
        self.assertEqual(v["intake_due_date"], d(2026, 11, 10), "han nhan tinh tu NGAY CHUYEN")
        self.assertNotIn("assignee", v)
        p = self.build(legacy_rec(approval="Rejected", fulfill="Not Started"),
                       acts(("Rejected", F.HOAN, ts(2026, 7, 7, 10), "Trùng phiếu")))
        v = p["values"]
        self.assertEqual((v["status"], v["cancel_reason"], v["closed_at"]),
                         (C.ST_CANCELLED, "Phiếu cũ bị từ chối: Trùng phiếu", ts(2026, 7, 7, 10)))
        self.assertEqual(self.build(legacy_rec(approval=None)), {"skip": "Nháp chưa gửi duyệt"})
        long_title = self.build(legacy_rec(request_title="x" * 300, approval="Pending"))["values"]["title"]
        self.assertEqual(len(long_title), C.TITLE_MAX)
        self.assertEqual(self.build(legacy_rec(request_title="", approval="Pending"))["values"]["title"],
                         "Data Request EC-DATA-2026-00001")

    def test_timeline_text(self):
        self.assertEqual(L.timeline_text(C.EV_LEGACY, "Hệ thống", "EC-DATA-1", ""), "Chuyển từ Data Request EC-DATA-1 (Approval Center)")
        self.assertEqual(L.timeline_text(C.EV_LEGACY_HISTORY, "Hoàn Trần", "Approved", "Cấp 1 · Data Review"),
                         "Phiếu cũ · Hoàn Trần đã duyệt (Cấp 1 · Data Review)")
        self.assertIsNone(L.timeline_text(C.EV_DONE, "x", "", ""))


# ====================================================================== phieu cu: chuyen =========
def legacy_repo(sync=1):
    r = F.FakeRepo(sync=sync)
    r.legacy = [
        legacy_rec("EC-DATA-2026-00001"),                                                        # Hoan tat
        legacy_rec("EC-DATA-2026-00002", fulfill="In Progress", approval_request="EC-APR-2026-00002",
                   request_type="Historical data crawling", urgency="U1: within next 24 hours"),   # Dang xu ly
        legacy_rec("EC-DATA-2026-00003", approval="Pending", fulfill="Not Started", approval_request="EC-APR-2026-00003",
                   request_type="Access"),                                                        # Cho tiep nhan
        legacy_rec("EC-DATA-2026-00004", approval="Rejected", fulfill="Not Started", approval_request="EC-APR-2026-00004"),
        legacy_rec("EC-DATA-2026-00005", approval=None),                                          # nhap
        legacy_rec("EC-DATA-2026-00006", fulfill="In Progress", approval_request="EC-APR-2026-00006",
                   fulfillment_owner=F.DUNG),                                                     # co task /pm go tay
    ]
    r.legacy_acts = {
        "EC-APR-2026-00001": acts(("Submitted", F.THU, ts(2026, 7, 6, 9), ""), ("Approved", F.HOAN, ts(2026, 7, 7, 10), "ok"),
                                  ("Completed", F.LINH, ts(2026, 7, 15, 17), "")),
        "EC-APR-2026-00002": acts(("Submitted", F.THU, ts(2026, 10, 20, 9), ""), ("Approved", F.HOAN, ts(2026, 10, 21, 10), ""),
                                  ("Started", F.LINH, ts(2026, 10, 22, 9), "")),
        "EC-APR-2026-00004": acts(("Submitted", F.THU, ts(2026, 7, 6, 9), ""), ("Rejected", F.HOAN, ts(2026, 7, 7, 9), "Trùng")),
    }
    r.legacy_file_rows = {"EC-DATA-2026-00001": [
        {"file_url": "/private/files/brief.xlsx", "file_name": "brief.xlsx", "file_size": 2048, "owner": F.THU},
        {"file_url": "/private/files/ketqua.pbix", "file_name": "ketqua.pbix", "file_size": 4096, "owner": F.LINH}]}
    r.tasks_by_subject = {"[EC-DATA-2026-00006] Dashboard cũ": "TASK-2026-00777"}
    return r, F.FakePM(r)


class TestMigration(unittest.TestCase):
    def setUp(self):
        self.r, self.pm = legacy_repo()

    def run_(self, dry):
        return M.migrate_legacy(dry_run=dry, repo=self.r, pm=self.pm)

    def test_dry_run_reports_without_writing(self):
        rep = self.run_(1)
        self.assertTrue(rep["dry_run"])
        self.assertEqual((rep["total"], len(rep["created"]), len(rep["skipped"]), rep["errors"]), (6, 5, 1, []))
        self.assertEqual(rep["counts"], {C.ST_DONE: 1, C.ST_DOING: 2, C.ST_WAITING: 1, C.ST_CANCELLED: 1})
        self.assertEqual(rep["skipped"], [{"ref": "EC-DATA-2026-00005", "reason": "Nháp chưa gửi duyệt"}])
        first = rep["created"][0]
        self.assertEqual((first["ref"], first["status"], first["files"], first["logs"]), ("EC-DATA-2026-00001", C.ST_DONE, 2, 4))
        self.assertEqual(rep["created"][1]["pm_task"], "sẽ tạo")
        self.assertEqual((self.r.tickets, self.r.logs_, self.pm.calls, self.r.notes), ({}, [], [], []), "dry run khong ghi gi")

    def test_apply_creates_tickets_links_files_keeps_history(self):
        rep = self.run_(0)
        self.assertFalse(rep["dry_run"])
        self.assertEqual(len(rep["created"]), 5)
        by_ref = {t["legacy_ref"]: t for t in self.r.tickets.values()}
        done = by_ref["EC-DATA-2026-00001"]
        self.assertTrue(done["name"].startswith("DR-"))
        self.assertEqual((done["status"], done["creation"], done["requester"]), (C.ST_DONE, "2026-07-06 09:00:00", F.THU))
        files = [f for f in self.r.files.values() if f["parent"] == done["name"]]
        self.assertEqual(sorted(f["file_url"] for f in files), ["/private/files/brief.xlsx", "/private/files/ketqua.pbix"],
                         "gan lai File cu theo file_url (khong chep noi dung, khong trung o Attach)")
        logs = [lg for lg in self.r.logs_ if lg["ticket"] == done["name"]]
        self.assertEqual([(lg["event"], lg["creation"]) for lg in logs[:3]],
                         [(C.EV_CREATED, "2026-07-06 09:00:00"), (C.EV_LEGACY_HISTORY, "2026-07-07 10:00:00"),
                          (C.EV_LEGACY_HISTORY, "2026-07-15 17:00:00")])
        self.assertTrue(all(lg["source"] == C.SRC_SYSTEM for lg in logs))
        self.assertEqual(self.r.notes, [], "chuyen hang loat khong gui thong bao")
        # chi tiet hien tren Trung tam: dong thoi gian doc duoc, mo bang ma cu
        det = S.detail(F.HIEN, "EC-DATA-2026-00001", repo=self.r)
        self.assertEqual(det["code"], done["name"])
        texts = [x["text"] for x in det["timeline"]]
        self.assertIn("Chuyển từ Data Request EC-DATA-2026-00001 (Approval Center)", texts)
        self.assertIn("Phiếu cũ · Hoàn Trần đã duyệt (Cấp 1 · Data Review)", texts)
        self.assertIn("Thu Nguyễn gửi yêu cầu", texts)
        self.assertEqual(len(det["attachments"]), 2)

    def test_pm_task_only_for_open_in_progress_without_task(self):
        rep = self.run_(0)
        creates = [c for c in self.pm.calls if c[0] == "create"]
        self.assertEqual(len(creates), 1, "chi phieu Dang xu ly chua co task")
        doing = self.r.get(self.r.find_by_legacy("EC-DATA-2026-00002"))
        self.assertEqual((creates[0][3], doing["pm_task"]), (F.LINH, "TASK-2026-00001"))
        self.assertIn(("state", "TASK-2026-00001", "In Progress"), self.pm.calls)
        linked = self.r.get(self.r.find_by_legacy("EC-DATA-2026-00006"))
        self.assertEqual(linked["pm_task"], "TASK-2026-00777", "task go tay nhac ma cu -> gan, khong tao trung")
        self.assertEqual((rep["pm_tasks"], rep["pm_linked"]), (1, 1))
        for ref in ("EC-DATA-2026-00001", "EC-DATA-2026-00003", "EC-DATA-2026-00004"):
            self.assertFalse(self.r.get(self.r.find_by_legacy(ref))["pm_task"], ref)

    def test_pm_disabled_creates_no_task(self):
        self.r, self.pm = legacy_repo(sync=0)
        rep = self.run_(0)
        self.assertEqual((self.pm.calls, rep["pm_tasks"]), ([], 0))
        self.assertEqual(rep["created"][1]["pm_task"], "")

    def test_idempotent_rerun(self):
        self.run_(0)
        n_tickets, n_logs, n_calls = len(self.r.tickets), len(self.r.logs_), len(self.pm.calls)
        rep = self.run_(0)
        self.assertEqual((len(rep["created"]), len(rep["exists"])), (0, 5))
        self.assertEqual((len(self.r.tickets), len(self.r.logs_), len(self.pm.calls)), (n_tickets, n_logs, n_calls))
        rep = self.run_(1)
        self.assertEqual(len(rep["exists"]), 5, "dry run sau khi chuyen: thay da chuyen het")

    def test_failure_rolls_back_one_record_only(self):
        self.r.fail_insert = {"EC-DATA-2026-00003"}
        rep = self.run_(0)
        self.assertEqual([e["ref"] for e in rep["errors"]], ["EC-DATA-2026-00003"])
        self.assertEqual(len(rep["created"]), 4)
        self.assertNotIn("PARTIAL-EC-DATA-2026-00003", self.r.tickets, "savepoint: khong de ticket do dang")
        self.assertEqual(rep["counts"].get(C.ST_WAITING), 0)
        self.assertEqual(self.r.rollbacks, 1)
        del self.r.fail_insert
        rep = self.run_(0)
        self.assertEqual([c["ref"] for c in rep["created"]], ["EC-DATA-2026-00003"], "chay lai -> bu phieu loi")

    def test_no_legacy_doctype(self):
        self.r.legacy_on = False
        rep = self.run_(0)
        self.assertEqual(rep["total"], 0)
        self.assertIn("Không có DocType", rep["note"])

    def test_endpoint_admin_only(self):
        for user in (F.LINH, F.HOAN, F.THU):
            with self.assertRaises(S.Forbidden):
                M.run_for(user, dry_run=1, repo=self.r, pm=self.pm)
        rep = M.run_for(F.ADMIN, dry_run=1, repo=self.r, pm=self.pm)
        self.assertTrue(rep["dry_run"])
        self.assertEqual(self.r.tickets, {})

    def test_migrated_open_ticket_works_in_hub_flow(self):
        self.run_(0)
        waiting = self.r.find_by_legacy("EC-DATA-2026-00003")
        O.accept(F.LINH, waiting, F.LINH, repo=self.r, pm=self.pm)
        t = self.r.get(waiting)
        self.assertEqual((t["status"], t["sla_days"]), (C.ST_DOING, 3), "Khac 3 ngay - nhan nhu yeu cau moi")


# ====================================================================== deep link ma cu ==========
class TestLegacyDeepLink(unittest.TestCase):
    def setUp(self):
        self.r, self.pm = legacy_repo()
        M.migrate_legacy(dry_run=0, repo=self.r, pm=self.pm)
        self.code = self.r.find_by_legacy("EC-DATA-2026-00002")

    def test_index_opens_by_legacy_code(self):
        ctx = S.index_page(F.HIEN, code="ec-data-2026-00002", repo=self.r)
        self.assertEqual(ctx["open_code"], self.code)
        self.assertEqual(ctx["open_missing"], "")
        out = render("index", ctx)
        self.assertIn("data-edh-detail-ov>", out, "popup mo san")
        self.assertEqual(S.index_page(F.HIEN, code=self.code, repo=self.r)["open_code"], self.code)
        self.assertEqual(S.index_page(F.HIEN, code="EC-DATA-1999-00001", repo=self.r)["open_missing"], "EC-DATA-1999-00001")
        self.assertEqual(S.resolve_code(self.r, "EC-DATA-2026-00002"), self.code)
        self.assertEqual(S.resolve_code(self.r, ""), "")

    def test_www_index_reads_ma_or_id(self):
        src = io.open(os.path.join(APP, "www", "du_lieu", "index.py"), encoding="utf-8").read()
        self.assertIn('code=pages.arg("ma") or pages.arg("id")', src)

    def test_write_ops_still_need_real_code(self):
        with self.assertRaises(S.NotFound):
            O.update(F.LINH, "EC-DATA-2026-00002", {"priority": C.PRI_HIGH}, repo=self.r, pm=self.pm)


# ====================================================================== the Approval Center ======
class TestCatalogRedirect(unittest.TestCase):
    def test_route_updated_once_and_never_overwrites_custom(self):
        r = F.FakeRepo()
        out = M.redirect_catalog(repo=r)
        self.assertEqual(out, {"action": "updated", "before": "/approvals/data-request", "after": "/du-lieu"})
        self.assertEqual(r.approval_types["DATA_REQUEST"], "/du-lieu")
        self.assertIn("route cũ: /approvals/data-request", r.route_notes[0])
        self.assertEqual(M.redirect_catalog(repo=r)["action"], "unchanged")
        r.approval_types["DATA_REQUEST"] = "/approvals/data-request-v2"
        self.assertEqual(M.redirect_catalog(repo=r)["action"], "refused")
        self.assertEqual(r.approval_types["DATA_REQUEST"], "/approvals/data-request-v2")
        r.approval_types = {}
        self.assertEqual(M.redirect_catalog(repo=r)["action"], "skipped")
        r.approval_types = {"DATA_REQUEST": ""}
        self.assertEqual(M.redirect_catalog(repo=r)["action"], "updated")

    def _moved_route(self, route):
        src = io.open(os.path.join(APP, "approval_center", "features", "data_request", "application", "service.py"),
                      encoding="utf-8").read()
        tree = ast.parse(src)
        fn = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "moved_route"][0]
        fake = types.SimpleNamespace(db=types.SimpleNamespace(get_value=lambda dt_, name, field: route))
        ns = {"frappe": fake, "APPROVAL_TYPE": "DATA_REQUEST"}
        exec(compile(ast.Module(body=[fn], type_ignores=[]), "service.py", "exec"), ns)
        return ns["moved_route"](), src

    def test_approval_center_refuses_new_submission_when_card_moved(self):
        table = {"/du-lieu": "/du-lieu", "du-lieu": "/du-lieu", "/approvals/data-request": None,
                 "approvals/data-request": None, "": None, None: None}
        for route, want in table.items():
            self.assertEqual(self._moved_route(route)[0], want, route)
        src = self._moved_route("")[1]
        body = src[src.index("def submit(name):"):src.index("def resubmit(")]
        self.assertLess(body.index("moved_route()"), body.index("engine.submit("), "chan TRUOC khi tao EC Approval Request")
        self.assertIn("Data Request đã chuyển sang Trung tâm Dữ liệu", body)


# ====================================================================== patch / hooks / doctype ==
class TestPatchesAndModel(unittest.TestCase):
    def test_patches_registered_append_only(self):
        pt = io.open(os.path.join(APP, "patches.txt"), encoding="utf-8").read().splitlines()
        i1 = pt.index("ecentric_workspace.data_hub.patches.p001_seed_data_hub")
        i3 = pt.index("ecentric_workspace.data_hub.patches.p003_chuyen_phieu_data_request_cu")
        i358 = pt.index("ecentric_workspace.approval_center.patches.p358_resync_data_request_chuyen_trung_tam_du_lieu")
        self.assertTrue(i1 < i3 and i1 < i358)
        self.assertGreater(i3, pt.index("[post_model_sync]"), "chay SAU khi dong bo DocType (legacy_ref, su kien moi)")
        nums = [int(m.group(1)) for m in (re.search(r"approval_center\.patches\.p(\d+)_", x) for x in pt[:i358]) if m]
        self.assertGreater(358, max(nums), "so patch resync phai lon hon moi patch approval_center dung truoc")
        self.assertEqual(1, sum(1 for x in pt if re.search(r"approval_center\.patches\.p358_", x)), "khong trung so p358")
        man = json.load(io.open(os.path.join(APP, "approval_center", "patches", "resync_manifest.json"), encoding="utf-8"))
        rec = man["approval_center/features/data_request/ui/main_section.html"]
        self.assertEqual(rec["last_resync_patch"], "p358_resync_data_request_chuyen_trung_tam_du_lieu")

    def _load_patch(self, fake_frappe):
        import sys
        saved = sys.modules.get("frappe")
        sys.modules["frappe"] = fake_frappe
        try:
            mod = importlib.import_module("ecentric_workspace.data_hub.patches.p003_chuyen_phieu_data_request_cu")
            mod = importlib.reload(mod)
        finally:
            if saved is not None:
                sys.modules["frappe"] = saved
        return mod

    def test_patch_never_raises(self):
        errors, infos = [], []
        fake = types.SimpleNamespace(
            db=types.SimpleNamespace(exists=lambda *a, **k: True),
            log_error=lambda **kw: errors.append(kw.get("title")),
            get_traceback=lambda: "tb",
            logger=lambda name: types.SimpleNamespace(info=lambda m: infos.append(m)))
        mod = self._load_patch(fake)
        orig = (M.redirect_catalog, M.migrate_legacy)
        try:
            M.redirect_catalog = lambda: (_ for _ in ()).throw(RuntimeError("boom"))
            M.migrate_legacy = lambda dry_run=1: (_ for _ in ()).throw(RuntimeError("boom2"))
            mod.execute()
            self.assertEqual(len(errors), 2)
            M.migrate_legacy = lambda dry_run=1: {"dry_run": False, "total": 2, "created": [1], "errors": [{"ref": "X"}],
                                                  "skipped": [], "exists": []}
            M.redirect_catalog = lambda: {"action": "updated"}
            mod.execute()
            self.assertIn("1 phieu loi", errors[-1])
            self.assertIn('"created": 1', infos[-1])
        finally:
            M.redirect_catalog, M.migrate_legacy = orig
        self.assertNotIn(".delete(", io.open(mod.__file__, encoding="utf-8").read())

    def test_doctype_options_and_fields(self):
        j = json.load(io.open(os.path.join(APP, "data_hub", "doctype", "ec_data_sla_rule_set", "ec_data_sla_rule_set.json"),
                              encoding="utf-8"))
        f = {x["fieldname"]: x for x in j["fields"]}
        self.assertEqual(f["status"]["options"].split("\n"), list(C.RULE_STATUSES))
        self.assertIn("submitted_at", j["field_order"])
        self.assertEqual(f["version_no"].get("unique"), 1, "hai ban nhap cung so phien ban -> DB chan")
        t = json.load(io.open(os.path.join(APP, "data_hub", "doctype", "ec_data_ticket", "ec_data_ticket.json"), encoding="utf-8"))
        lf = {x["fieldname"]: x for x in t["fields"]}["legacy_ref"]
        self.assertEqual(lf.get("search_index"), 1)
        # doc AST (test_pm_gateway thay sys.modules["...repository"] bang repo gia - khong import lai)
        tree = ast.parse(io.open(os.path.join(APP, "data_hub", "repository.py"), encoding="utf-8").read())
        real = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
        for name in [fn.__name__ for fn in F3.METHODS]:
            self.assertIn(name, real, "repository that thieu %s (repo gia co)" % name)

    def test_api_whitelisted_post_for_writes(self):
        src = io.open(os.path.join(APP, "data_hub", "api.py"), encoding="utf-8").read()
        for fn in ("save_rule_draft", "submit_rule", "decide_rule", "cancel_rule", "run_legacy_migration"):
            self.assertRegex(src, r'@frappe\.whitelist\(methods=\["POST"\]\)\ndef %s\(' % fn)
        self.assertRegex(src, r'@frappe\.whitelist\(\)\ndef legacy_migration_report\(')
        self.assertNotIn("user=", src.split("DOT 3")[1].split("def _rules")[1].replace("_me()", ""),
                         "khong nhan tham so user tu HTTP")

    def test_no_hardcoded_email_in_new_code(self):
        for f in ("rules_service.py", "rules_domain.py", "legacy.py", "migration.py"):
            self.assertNotIn("@ecentric.vn", io.open(os.path.join(APP, "data_hub", f), encoding="utf-8").read(), f)
        self.assertNotIn("@ecentric", io.open(os.path.join(APP, "public", "js", "ec_data_hub_rules.bundle.js"),
                                              encoding="utf-8").read())


# ====================================================================== fixture jsdom ===========
VALIDATE_CASES = [
    {"days": {"pbi_new": "10"}, "mult": {}},
    {"days": {"pbi_new": "0"}, "mult": {}},
    {"days": {"pbi_new": "61"}, "mult": {}},
    {"days": {"pbi_new": "7.5"}, "mult": {}},
    {"days": {"pbi_new": "abc"}, "mult": {}},
    {"days": {"intake": "2"}, "mult": {"Khẩn": "0,6"}},
    {"days": {}, "mult": {"Cao": "0,2"}},
    {"days": {}, "mult": {"Cao": "3,5"}},
    {"days": {}, "mult": {"Cao": "0,333"}},
    {"days": {}, "mult": {"Cao": "x"}},
    {"days": {}, "mult": {"Thấp": "2"}},
    {"days": {"pbi_new": "", "crawl_new": "5"}, "mult": {"Bình thường": "1"}},
]


def rules_fixture_pages():
    r, pm, c = F.sample()
    out = {"rules_team": rules_html(r, F.LINH)[0]}
    propose(r)
    out["rules_draft"] = rules_html(r, F.LINH)[0]
    R.submit(F.LINH, "SLA-v2", repo=r)
    r.role_map[F.HOAN].discard(C.DEFAULT_DATA_TEAM_ROLE)
    out["rules_approver"] = rules_html(r, F.HOAN)[0]
    av = active_view(F.FakeRepo())
    cases = []
    for data in VALIDATE_CASES:
        try:
            v = RD.normalize_input(data, av)
            cases.append({"input": data, "ok": True, "days": v["days"], "mult": v["mult"],
                          "changes": len(RD.diff(av, v))})
        except D.Invalid as e:
            cases.append({"input": data, "ok": False, "errors": e.errors})
    return out, {"validate": cases}


class TestRulesFixtures(unittest.TestCase):
    def test_fixtures_current(self):
        pages, api = rules_fixture_pages()
        files = {name + ".html": html for name, html in pages.items()}
        files["rules_api.json"] = json.dumps(api, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
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
