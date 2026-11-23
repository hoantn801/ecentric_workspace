# Copyright (c) 2026, eCentric and contributors
"""Ky luat - TIEU DE the vang / ho so (Hoan chot 23/11/2026).

  1. Bat buoc tieu de khi TAO MOI (gui the vang / de xuat / lap ho so) - kiem o service.
  2. Ban ghi cu chua co tieu de: sua / luu lai khong loi, man hinh hien tieu de du phong.
  3. Sua tieu de: the vang khi NV chua phan hoi (nguoi gui / HR); ho so khi chua ban hanh (HR) -
     ghi nhat ky cu -> moi; dang trinh CEO thi doi ca tieu de phieu quyet dinh.
  4. Tieu de hien o danh sach, chi tiet, tab Ky luat ho so NV, thong bao NV / LM; quyen xem giu nguyen.
  5. gen_title phieu Quyet dinh: "Quyet dinh ky luat - <hinh thuc> - <ten NV> - <tieu de ho so>".

    python3 -m unittest ecentric_workspace.hr.tests.test_ky_luat_tieu_de
"""
import ast
import datetime as dt
import io
import os
import types
import unittest

from ecentric_workspace.hr.tests.ky_luat_fake import CEO, HR, LM, NV, OUT, FakeRepo
from ecentric_workspace.hr.ky_luat import constants as C
from ecentric_workspace.hr.ky_luat.application import (
    case_service as CS, notice_service as NS, procedure_service as PS, views as V)
from ecentric_workspace.hr.ky_luat.domain import rules as R
from ecentric_workspace.hr.ky_luat.domain.errors import FieldErrors, KyLuatError, KyLuatForbidden

d = dt.date
APP = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def ctx(repo, user):
    return V.make_ctx(repo, user)


def notice_payload(**kw):
    p = {"title": "Đi trễ nhiều lần tháng 11", "employee": "EMP-NV", "behavior": "Di muon",
         "content": "Nhac lan 1", "incident_date": "2026-11-20"}
    p.update(kw)
    return p


def case_payload(**kw):
    p = {"title": "Vắng không phép tháng 11", "employee": "EMP-NV", "card": C.CARD_RED,
         "penalty": C.P_REPRIMAND, "rule": "R1", "violation_date": "2026-11-10",
         "description": "Vang 2 ngay khong phep", "violation_record": "/private/files/bb.pdf"}
    p.update(kw)
    return p


class Base(unittest.TestCase):
    def setUp(self):
        self.r = FakeRepo()

    def at(self, day):
        self.r._today = day

    def old_notice(self, status=C.NOTICE_PENDING):
        """Ban ghi tao TRUOC khi co truong tieu de (khong co khoa `title`)."""
        name = self.r._id("TV")
        self.r.notices_[name] = {"name": name, "employee": "EMP-NV", "employee_name": "Nhan Vien",
                                 "employee_user": NV, "issued_by": LM, "behavior": "Ve som",
                                 "incident_date": d(2026, 11, 18), "status": status,
                                 "reply_due": d(2026, 11, 21), "logs": []}
        return name

    def old_case(self, status=C.S_DRAFT, **kw):
        name = self.r._id("KL")
        row = {"name": name, "employee": "EMP-NV", "employee_name": "Nhan Vien", "employee_user": NV,
               "line_manager_user": LM, "card": C.CARD_RED, "penalty": C.P_REPRIMAND, "rule": "R1",
               "violation_date": d(2026, 11, 10), "description": "Vang", "status": status,
               "violation_record": "/private/files/bb.pdf", "hr_owner": HR, "logs": []}
        row.update(kw)
        self.r.cases_[name] = row
        return name


# ------------------------------------------------------------------------ tao moi --
class TestBatBuocKhiTaoMoi(Base):
    def test_notice_requires_title(self):
        for blank in ("", "   ", None):
            with self.assertRaises(FieldErrors) as e:
                NS.issue(self.r, ctx(self.r, LM), notice_payload(title=blank))
            self.assertIn("title", e.exception.errors)
        self.assertEqual(self.r.notices_, {})

    def test_notice_title_saved_clean_and_capped(self):
        out = NS.issue(self.r, ctx(self.r, LM), notice_payload(title="  Đi   trễ  " + "x" * 200))
        t = self.r.get_notice(out["name"])["title"]
        self.assertTrue(t.startswith("Đi trễ x"))
        self.assertEqual(len(t), C.TITLE_MAX)

    def test_case_create_and_propose_require_title(self):
        with self.assertRaises(FieldErrors) as e:
            CS.create(self.r, ctx(self.r, HR), case_payload(title=""))
        self.assertIn("title", e.exception.errors)
        with self.assertRaises(FieldErrors) as e:
            CS.propose(self.r, ctx(self.r, LM), case_payload(title=" ", rule=None, violation_record=None))
        self.assertIn("title", e.exception.errors)
        self.assertEqual(self.r.cases_, {})
        name = CS.create(self.r, ctx(self.r, HR), case_payload())["name"]
        self.assertEqual(self.r.get_case(name)["title"], "Vắng không phép tháng 11")

    def test_permission_checked_before_title(self):
        # Nguoi ngoai khong duoc biet gi them (loi quyen, khong phai loi truong).
        with self.assertRaises(KyLuatForbidden):
            NS.issue(self.r, ctx(self.r, OUT), notice_payload(title=""))
        with self.assertRaises(KyLuatForbidden):
            CS.propose(self.r, ctx(self.r, OUT), case_payload(title=""))


# ----------------------------------------------------------------------- ban ghi cu --
class TestBanGhiCu(Base):
    def test_fallback_titles(self):
        self.assertEqual(R.notice_title({"behavior": "Ve som", "incident_date": d(2026, 11, 18)}),
                         "Thẻ vàng - Ve som - 18/11/2026")
        self.assertEqual(R.case_title({"penalty": C.P_REPRIMAND, "violation_date": "2026-11-10"}),
                         "Hồ sơ kỷ luật - Khiển trách - 10/11/2026")
        self.assertEqual(R.case_title({"card": C.CARD_BLACK}), "Hồ sơ kỷ luật - Thẻ đen")
        self.assertEqual(R.case_title({"title": "  Tieu  de  ", "penalty": "x"}), "Tieu de")
        self.assertLessEqual(len(R.notice_title({"behavior": "y" * 300, "incident_date": "2026-11-18"})), C.TITLE_MAX)

    def test_old_case_saves_without_title(self):
        name = self.old_case()
        CS.update(self.r, ctx(self.r, HR), name, {"description": "Vang 3 ngay", "title": ""})
        c = self.r.get_case(name)
        self.assertEqual(c["description"], "Vang 3 ngay")
        self.assertFalse(c.get("title"))
        self.assertEqual(V.case_detail(self.r, ctx(self.r, HR), name)["display_title"],
                         "Hồ sơ kỷ luật - Khiển trách - 10/11/2026")

    def test_update_blank_title_keeps_existing(self):
        name = CS.create(self.r, ctx(self.r, HR), case_payload())["name"]
        CS.update(self.r, ctx(self.r, HR), name, {"title": "   "})
        self.assertEqual(self.r.get_case(name)["title"], "Vắng không phép tháng 11")

    def test_update_title_change_is_logged(self):
        name = CS.create(self.r, ctx(self.r, HR), case_payload())["name"]
        CS.update(self.r, ctx(self.r, HR), name, {"title": "Vắng 3 ngày"})
        c = self.r.get_case(name)
        self.assertEqual(c["title"], "Vắng 3 ngày")
        self.assertIn("Vắng không phép tháng 11", c["logs"][-1]["note"])
        self.assertIn("Vắng 3 ngày", c["logs"][-1]["note"])

    def test_old_rows_in_lists_and_profile_tab(self):
        self.old_notice()
        self.old_case(status=C.S_ISSUED, decision_date=d(2026, 11, 20))
        page = V.index_page(self.r, ctx(self.r, HR))
        self.assertEqual(page["notices"][0]["title"], "Thẻ vàng - Ve som - 18/11/2026")
        self.assertEqual(page["notices"][0]["title_auto"], 1)
        self.assertEqual(page["cases"][0]["title"], "Hồ sơ kỷ luật - Khiển trách - 10/11/2026")
        tab = V.employee_discipline(self.r, ctx(self.r, HR), "EMP-NV")
        self.assertTrue(tab["notices"][0]["title"].startswith("Thẻ vàng - "))
        self.assertTrue(tab["cases"][0]["title"].startswith("Hồ sơ kỷ luật - "))

    def test_new_rows_show_entered_title(self):
        NS.issue(self.r, ctx(self.r, LM), notice_payload())
        page = V.index_page(self.r, ctx(self.r, LM))
        self.assertEqual(page["notices"][0]["title"], "Đi trễ nhiều lần tháng 11")
        self.assertEqual(page["notices"][0]["title_auto"], 0)
        self.assertEqual(page["boot"]["title_max"], C.TITLE_MAX)


# ---------------------------------------------------------------- sua tieu de the vang --
class TestSuaTieuDeTheVang(Base):
    def test_issuer_or_hr_retitle_pending_with_audit(self):
        name = NS.issue(self.r, ctx(self.r, LM), notice_payload())["name"]
        out = NS.retitle(self.r, ctx(self.r, LM), name, "Đi trễ 4 lần tháng 11")
        self.assertTrue(out["changed"])
        n = self.r.get_notice(name)
        self.assertEqual(n["title"], "Đi trễ 4 lần tháng 11")
        self.assertEqual(n["logs"][-1]["action"], "Sửa tiêu đề")
        self.assertEqual(n["logs"][-1]["actor"], LM)
        self.assertIn("Đi trễ nhiều lần tháng 11", n["logs"][-1]["note"])
        NS.retitle(self.r, ctx(self.r, HR), name, "HR sửa")
        self.assertEqual(self.r.get_notice(name)["title"], "HR sửa")
        self.assertEqual(self.r.get_notice(name)["status"], C.NOTICE_PENDING)    # khong doi trang thai

    def test_same_title_no_log(self):
        name = NS.issue(self.r, ctx(self.r, LM), notice_payload())["name"]
        before = len(self.r.get_notice(name)["logs"])
        self.assertFalse(NS.retitle(self.r, ctx(self.r, LM), name, " Đi trễ nhiều  lần tháng 11 ")["changed"])
        self.assertEqual(len(self.r.get_notice(name)["logs"]), before)

    def test_employee_and_outsider_cannot_retitle(self):
        name = NS.issue(self.r, ctx(self.r, LM), notice_payload())["name"]
        for u in (NV, OUT, CEO):
            with self.subTest(user=u), self.assertRaises(KyLuatForbidden):
                NS.retitle(self.r, ctx(self.r, u), name, "Khac")

    def test_locked_after_employee_responds(self):
        a = NS.issue(self.r, ctx(self.r, LM), notice_payload())["name"]
        NS.mark_read(self.r, ctx(self.r, NV), a)
        with self.assertRaises(KyLuatError):
            NS.retitle(self.r, ctx(self.r, LM), a, "Khac")
        b = NS.issue(self.r, ctx(self.r, LM), notice_payload())["name"]
        NS.reply(self.r, ctx(self.r, NV), b, "Da hieu")
        with self.assertRaises(KyLuatError):
            NS.retitle(self.r, ctx(self.r, HR), b, "Khac")

    def test_blank_rejected(self):
        name = NS.issue(self.r, ctx(self.r, LM), notice_payload())["name"]
        with self.assertRaises(FieldErrors):
            NS.retitle(self.r, ctx(self.r, LM), name, "  ")

    def test_old_notice_gets_title_and_log_shows_fallback(self):
        name = self.old_notice()
        NS.retitle(self.r, ctx(self.r, HR), name, "Về sớm 18/11")
        n = self.r.get_notice(name)
        self.assertEqual(n["title"], "Về sớm 18/11")
        self.assertIn("Thẻ vàng - Ve som - 18/11/2026", n["logs"][-1]["note"])

    def test_detail_action_flag(self):
        name = NS.issue(self.r, ctx(self.r, LM), notice_payload())["name"]
        self.assertTrue(V.notice_detail(self.r, ctx(self.r, LM), name)["actions"]["retitle"])
        self.assertFalse(V.notice_detail(self.r, ctx(self.r, NV), name)["actions"]["retitle"])
        self.assertEqual(V.notice_detail(self.r, ctx(self.r, NV), name)["display_title"], "Đi trễ nhiều lần tháng 11")
        NS.mark_read(self.r, ctx(self.r, NV), name)
        self.assertFalse(V.notice_detail(self.r, ctx(self.r, LM), name)["actions"]["retitle"])


# ----------------------------------------------------------------- sua tieu de ho so --
class TestSuaTieuDeHoSo(Base):
    def make(self, **kw):
        return CS.create(self.r, ctx(self.r, HR), case_payload(**kw))["name"]

    def to_at_ceo(self, name):
        PS.notify_meeting(self.r, ctx(self.r, HR), name, "2026-11-30")
        self.at(d(2026, 11, 30))
        PS.record_meeting(self.r, ctx(self.r, HR), name, {"employee_present": C.PRESENT_YES,
                                                          "employee_statement": "Xin loi",
                                                          "meeting_minutes": "/private/files/hop.pdf"})
        PS.submit_to_ceo(self.r, ctx(self.r, HR), name, {"decision_draft": "/private/files/qd.pdf"})

    def test_hr_retitle_open_statuses_with_audit(self):
        name = self.make()
        PS.notify_meeting(self.r, ctx(self.r, HR), name, "2026-11-30")
        out = CS.retitle(self.r, ctx(self.r, HR), name, "Vắng 2 ngày không phép")
        self.assertTrue(out["changed"])
        c = self.r.get_case(name)
        self.assertEqual(c["title"], "Vắng 2 ngày không phép")
        self.assertEqual(c["status"], C.S_NOTIFIED)
        self.assertEqual(c["logs"][-1]["action"], "Sửa tiêu đề")
        self.assertEqual(c["logs"][-1]["actor"], HR)

    def test_lm_and_employee_cannot_retitle(self):
        name = self.make()
        for u in (LM, NV, OUT, CEO):
            with self.subTest(user=u), self.assertRaises(KyLuatForbidden):
                CS.retitle(self.r, ctx(self.r, u), name, "Khac")

    def test_locked_after_issue(self):
        name = self.make()
        self.to_at_ceo(name)
        self.r.decisions[self.r.get_case(name)["decision_request"]] = "Approved"
        from ecentric_workspace.hr.ky_luat.application import decision_service as DS
        DS.reconcile(self.r, name)
        self.assertEqual(self.r.get_case(name)["status"], C.S_ISSUED)
        with self.assertRaises(KyLuatError):
            CS.retitle(self.r, ctx(self.r, HR), name, "Khac")
        self.assertFalse(V.case_detail(self.r, ctx(self.r, HR), name)["actions"]["retitle"])

    def test_at_ceo_retitle_updates_decision_and_failure_not_blocking(self):
        name = self.make()
        self.to_at_ceo(name)
        CS.retitle(self.r, ctx(self.r, HR), name, "Tiêu đề mới")
        self.assertIn(("retitle", name, "Tiêu đề mới"), self.r.decision_calls)
        self.r.retitle_fail = True
        CS.retitle(self.r, ctx(self.r, HR), name, "Tiêu đề mới 2")
        self.assertEqual(self.r.get_case(name)["title"], "Tiêu đề mới 2")
        self.assertTrue(self.r.errors)

    def test_submit_to_ceo_passes_case_title(self):
        seen = []
        orig = self.r.create_decision
        self.r.create_decision = lambda case, actor: seen.append(case.get("case_title")) or orig(case, actor)
        name = self.make()
        self.to_at_ceo(name)
        self.assertEqual(seen, ["Vắng không phép tháng 11"])
        seen.clear()
        old = self.old_case(status=C.S_MET, meeting_date=d(2026, 11, 30), employee_present=C.PRESENT_YES)
        self.at(d(2026, 12, 1))
        PS.submit_to_ceo(self.r, ctx(self.r, HR), old, {"decision_draft": "/private/files/qd.pdf"})
        self.assertEqual(seen, ["Hồ sơ kỷ luật - Khiển trách - 10/11/2026"])

    def test_detail_retitle_flag_only_when_no_edit(self):
        name = self.make()
        det = V.case_detail(self.r, ctx(self.r, HR), name)
        self.assertTrue(det["actions"]["edit"])
        self.assertFalse(det["actions"]["retitle"])            # buoc lap: sua trong form day du
        PS.notify_meeting(self.r, ctx(self.r, HR), name, "2026-11-30")
        det = V.case_detail(self.r, ctx(self.r, HR), name)
        self.assertTrue(det["actions"]["retitle"])
        self.assertEqual(det["display_title"], "Vắng không phép tháng 11")


# ---------------------------------------------------------------- thong bao + quyen --
class TestThongBaoVaQuyen(Base):
    def test_notifications_carry_title(self):
        NS.issue(self.r, ctx(self.r, LM), notice_payload())
        self.assertTrue(any("Đi trễ nhiều lần tháng 11" in s for _u, s, _e in self.r.to(NV)))
        name = CS.create(self.r, ctx(self.r, HR), case_payload())["name"]
        self.r.sent.clear()
        PS.notify_meeting(self.r, ctx(self.r, HR), name, "2026-11-30")
        # NV + LM nhan thong bao hop co tieu de ho so (subject hoac message)
        self.assertTrue(self.r.to(NV) and self.r.to(LM))

    def test_meeting_message_has_title(self):
        msgs = []
        orig = self.r.notify
        self.r.notify = lambda users, subject, *a, **k: msgs.append((tuple(users), subject, k.get("message", ""))) or orig(users, subject, *a, **k)
        name = CS.create(self.r, ctx(self.r, HR), case_payload())["name"]
        PS.notify_meeting(self.r, ctx(self.r, HR), name, "2026-11-30")
        to_nv = [m for m in msgs if NV in m[0]]
        self.assertTrue(to_nv and "Vắng không phép tháng 11" in to_nv[0][2])
        to_lm = [m for m in msgs if LM in m[0]]
        self.assertTrue(to_lm and ("Vắng không phép tháng 11" in to_lm[0][1] or "Vắng không phép tháng 11" in to_lm[0][2]))

    def test_title_not_leaked_to_employee_before_meeting_notice(self):
        CS.create(self.r, ctx(self.r, HR), case_payload())
        page = V.index_page(self.r, ctx(self.r, NV))
        self.assertEqual(page["cases"], [])
        self.assertEqual(V.employee_discipline(self.r, ctx(self.r, NV), "EMP-NV")["cases"], [])
        self.assertEqual(V.index_page(self.r, ctx(self.r, OUT))["cases"], [])
        self.assertEqual(V.index_page(self.r, ctx(self.r, OUT))["notices"], [])


# ---------------------------------------------------- gen_title phieu quyet dinh --
def _load_decision_fns(fake_frappe):
    """Nap gen_title / _fill / doi_tieu_de_tu_ho_so tu file service (khong import frappe that)."""
    path = os.path.join(APP, "approval_center", "features", "discipline_decision", "application", "service.py")
    with io.open(path, encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    keep = {"gen_title", "_fill", "doi_tieu_de_tu_ho_so"}
    nodes = [n for n in tree.body if (isinstance(n, ast.FunctionDef) and n.name in keep) or
             (isinstance(n, ast.Assign) and any(getattr(t, "id", "") in ("BUSINESS_DT", "GROUND_LABELS", "SNAPSHOT")
                                                for t in n.targets))]
    ns = {"frappe": fake_frappe}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), path, "exec"), ns)
    return ns


class _Doc(dict):
    def __getattr__(self, k):
        return self.get(k)

    def __setattr__(self, k, v):
        self[k] = v

    def set(self, k, v):
        self[k] = v

    def db_set(self, vals):
        self.update(vals)
        self.saved = dict(vals)


class TestTieuDeQuyetDinh(unittest.TestCase):
    def setUp(self):
        self.doc = _Doc(approval_request="REQ-1")
        self.status = "Pending"
        fr = types.SimpleNamespace()
        fr.get_attr = lambda p: C.DISMISS_GROUNDS
        fr.db = types.SimpleNamespace(exists=lambda dt_, n: n == "QD-1",
                                      get_value=lambda dt_, n, f: self.status)
        fr.get_doc = lambda dt_, n: self.doc
        self.ns = _load_decision_fns(fr)

    def test_gen_title_format_and_cap(self):
        g = self.ns["gen_title"]
        self.assertEqual(g({"penalty": "Khiển trách", "employee_name": "Nguyễn Văn A", "case_title": "Đi trễ tháng 11"}),
                         "Quyết định kỷ luật - Khiển trách - Nguyễn Văn A - Đi trễ tháng 11")
        self.assertEqual(g({"penalty": "Khiển trách", "employee": "EMP-1"}), "Quyết định kỷ luật - Khiển trách - EMP-1")
        self.assertEqual(len(g({"penalty": "Sa thải", "employee_name": "x" * 200, "case_title": "y" * 140})), 255)

    def test_fill_takes_case_title(self):
        doc = _Doc()
        self.ns["_fill"](doc, {"name": "KL-1", "penalty": "Khiển trách", "employee_name": "A",
                               "case_title": "Tiêu đề hồ sơ", "title": "khac"})
        self.assertEqual(doc.case_title, "Tiêu đề hồ sơ")
        self.assertEqual(doc.request_title, "Quyết định kỷ luật - Khiển trách - A - Tiêu đề hồ sơ")

    def test_retitle_only_while_open(self):
        self.doc.update(penalty="Khiển trách", employee_name="A", case_title="Cũ")
        fn = self.ns["doi_tieu_de_tu_ho_so"]
        self.assertEqual(fn({"decision_request": "QD-1", "case_title": "Mới"}), "QD-1")
        self.assertEqual(self.doc.request_title, "Quyết định kỷ luật - Khiển trách - A - Mới")
        self.status = "Approved"
        self.assertIsNone(fn({"decision_request": "QD-1", "case_title": "Mới hơn"}))
        self.assertEqual(self.doc.case_title, "Mới")
        self.assertIsNone(fn({"decision_request": "QD-X", "case_title": "x"}))


# ------------------------------------------------------------------------- khoa tinh --
class TestKhoaTinh(unittest.TestCase):
    def test_doctype_title_not_reqd(self):
        import json
        for rel in ("ecentric_workspace/doctype/ec_hr_notice/ec_hr_notice.json",
                    "ecentric_workspace/doctype/ec_discipline_case/ec_discipline_case.json"):
            with io.open(os.path.join(APP, rel), encoding="utf-8") as fh:
                d = json.load(fh)
            f = next(x for x in d["fields"] if x["fieldname"] == "title")
            self.assertEqual(f["fieldtype"], "Data")
            self.assertEqual(f.get("length"), C.TITLE_MAX)
            self.assertFalse(f.get("reqd"), rel)          # ban ghi cu luu lai khong loi

    def test_api_endpoints_post(self):
        with io.open(os.path.join(APP, "hr", "ky_luat", "controllers", "api.py"), encoding="utf-8") as fh:
            src = fh.read()
        for fn in ("notice_retitle", "case_retitle"):
            i = src.index("def %s(" % fn)
            self.assertIn('@frappe.whitelist(methods=["POST"])', src[i - 60:i])


if __name__ == "__main__":
    unittest.main()
