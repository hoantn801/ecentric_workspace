# Copyright (c) 2026, eCentric and contributors
"""Bang "Viec cua ban" (Tien trinh phe duyet A, 24/11/2026): khoi `viewer` + co levels[i].mine tinh o
SERVER (shared/requests/viewer_task.py). Kiem: dung nguoi duoc danh dau, nguoi khac KHONG; khong lo
them du lieu; loi -> khong ve bang.
    python -m pytest ecentric_workspace/approval_center/tests/standalone/test_viewer_task.py
"""
import datetime as dt
import importlib
import os
import sys
import types
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
sys.path.insert(0, ROOT)
NOW = dt.datetime(2026, 11, 24, 9, 40)
NAMES = {"ha@x": "Lê Thu Hà", "bao@x": "Nguyễn Quốc Bảo", "duc@x": "Phạm Minh Đức", "op@x": "Đỗ Văn Nam"}


def _vt():
    sys.modules.pop("ecentric_workspace.approval_center.shared.requests.viewer_task", None)
    return importlib.import_module("ecentric_workspace.approval_center.shared.requests.viewer_task")


def levels_pending_l2():
    return [
        {"level_no": 1, "level_name": "Line Manager", "level_status": "Skipped", "activated_at": None, "completed_at": None},
        {"level_no": 2, "level_name": "CnB/HR", "level_status": "In Progress",
         "activated_at": dt.datetime(2026, 11, 23, 16, 40), "completed_at": None, "due_at": "2026-11-25 17:00:00"},
        {"level_no": 3, "level_name": "HOF", "level_status": "Skipped", "activated_at": None, "completed_at": None},
        {"level_no": 4, "level_name": "CEO", "level_status": "Not Started", "activated_at": None, "completed_at": None},
    ]


APPROVERS = [
    {"level_no": 2, "approver": "ha@x", "status": "Pending"},
    {"level_no": 2, "approver": "Role: EC CnB", "status": "Pending"},
    {"level_no": 4, "approver": "bao@x", "status": "Pending"},
]


def run(user, status="Pending", caps=None, levels=None, approvers=APPROVERS, ff=None, watchers=(), journey=(),
        current=2):
    vt = _vt()
    lv = levels if levels is not None else levels_pending_l2()
    out = vt.compute(user, status, current, lv, approvers, caps or {}, requested_by="duc@x", fulfillment=ff,
                     watchers=watchers, journey=journey, now=NOW, display=lambda u: NAMES.get(u, u))
    return out, lv


class Approve(unittest.TestCase):
    def test_nguoi_duyet_cap_hien_tai(self):
        out, lv = run("ha@x", caps={"can_approve": True})
        self.assertEqual(out["kind"], "approve")
        self.assertEqual(out["role"], "approver")
        self.assertEqual((out["level_no"], out["level_name"]), (2, "CnB/HR"))
        self.assertEqual(out["waiting_seconds"], 17 * 3600)
        self.assertEqual(out["waiting_since"], "2026-11-23 16:40:00")
        self.assertEqual((out["next_level_no"], out["next_level_name"]), (4, "CEO"), "bo qua cap Skipped")
        self.assertEqual([r["mine"] for r in lv], [False, True, False, False], "chi cap hien tai la mine")
        self.assertEqual(out["waiting_on"], [], "nguoi duyet khong can danh sach nguoi khac")

    def test_dong_pending_nhung_mat_quyen_khong_phai_mine(self):
        # caps.can_approve = luat cua nut Duyet (_pending_row + still_holds_role). Dong Pending con
        # nam do ma role da mat -> KHONG duoc hien "Cho ban duyet".
        out, lv = run("ha@x", caps={"can_approve": False})
        self.assertNotEqual(out["kind"], "approve")
        self.assertFalse(any(r["mine"] for r in lv))

    def test_nguoi_duyet_cap_sau_chi_theo_doi(self):
        out, lv = run("bao@x", caps={})
        self.assertEqual((out["kind"], out["role"]), ("watch", "approver"))
        self.assertFalse(any(r["mine"] for r in lv))
        self.assertEqual(out["waiting_on"], ["Lê Thu Hà", "nhóm EC CnB"])

    def test_nguoi_gui_theo_doi(self):
        out, _ = run("duc@x")
        self.assertEqual((out["kind"], out["role"]), ("watch", "requester"))
        self.assertEqual(out["waiting_seconds"], 17 * 3600)

    def test_nguoi_theo_doi(self):
        out, _ = run("cc@x", watchers=["cc@x"])
        self.assertEqual((out["kind"], out["role"]), ("watch", "follower"))

    def test_khong_lien_quan_khong_co_bang(self):
        # vd System Manager mo phieu qua quyen doc: khong viec, khong theo doi -> khong ve bang,
        # va KHONG nhan danh sach nguoi dang duyet qua khoi viewer.
        out, lv = run("admin@x", caps={"can_admin_approve_current_level": True})
        self.assertEqual(out["kind"], "")
        self.assertEqual(out["waiting_on"], [])
        self.assertFalse(any(r["mine"] for r in lv))

    def test_cap_duyet_cuoi(self):
        lv = levels_pending_l2()
        lv[3]["level_status"] = "Skipped"
        out, _ = run("ha@x", caps={"can_approve": True}, levels=lv)
        self.assertIsNone(out["next_level_no"])


class TraLai(unittest.TestCase):
    def test_nguoi_gui_bo_sung(self):
        out, lv = run("duc@x", status="Information Required", caps={"can_resubmit": True})
        self.assertEqual(out["kind"], "resubmit")
        self.assertEqual(out["level_name"], "CnB/HR")
        self.assertFalse(any(r["mine"] for r in lv))

    def test_nguoi_duyet_cho_nguoi_gui(self):
        out, _ = run("ha@x", status="Information Required", caps={"can_approve": False})
        self.assertEqual(out["kind"], "watch")
        self.assertEqual(out["waiting_on"], ["Phạm Minh Đức"])


class Fulfill(unittest.TestCase):
    J = ({"label": "Operation xử lý", "meta": "x", "kind": "fulfillment"},)

    def done_levels(self):
        lv = levels_pending_l2()
        for r in lv:
            r["level_status"] = "Approved"
            r["completed_at"] = dt.datetime(2026, 11, 24, 7, 40)
        return lv

    def test_nguoi_giu_viec(self):
        out, lv = run("op@x", status="Approved", levels=self.done_levels(), journey=self.J,
                      ff={"status": "In Progress", "owner": "op@x", "due_at": "2026-11-28"})
        self.assertEqual((out["kind"], out["role"], out["claimable"]), ("fulfill", "fulfiller", False))
        self.assertEqual(out["step_label"], "Operation xử lý")
        self.assertEqual(out["waiting_seconds"], 2 * 3600)
        self.assertFalse(any(r["mine"] for r in lv))

    def test_nguoi_nhan_duoc_viec(self):
        out, _ = run("op2@x", status="Approved", levels=self.done_levels(), journey=self.J,
                     caps={"can_claim": True}, ff={"status": "Assigned", "owner": None})
        self.assertEqual((out["kind"], out["claimable"]), ("fulfill", True))

    def test_quan_tri_nhan_ho_khong_phai_viec_cua_minh(self):
        out, _ = run("admin@x", status="Approved", levels=self.done_levels(), journey=self.J,
                     caps={"can_claim": True, "claim_is_admin_override": True}, ff={"status": "Assigned"})
        self.assertEqual(out["kind"], "")

    def test_nguoi_gui_cho_xu_ly(self):
        out, _ = run("duc@x", status="Approved", levels=self.done_levels(), journey=self.J,
                     ff={"status": "In Progress", "owner": "op@x"})
        self.assertEqual(out["kind"], "watch")
        self.assertEqual(out["waiting_on"], ["Đỗ Văn Nam"])

    def test_xong_het_khong_bang(self):
        for st, ff in (("Approved", {"status": "Completed", "owner": "op@x"}), ("Approved", {}),
                       ("Rejected", {}), ("Cancelled", {}), ("Draft", {}), (None, {})):
            out, lv = run("op@x", status=st, levels=self.done_levels(), ff=ff, caps={"can_approve": True})
            self.assertEqual(out["kind"], "", st)
            self.assertFalse(any(r["mine"] for r in lv), st)


class Build(unittest.TestCase):
    def setUp(self):
        self.saved = dict(sys.modules)

    def tearDown(self):
        sys.modules.clear()
        sys.modules.update(self.saved)

    def _stub(self, boom=False):
        fk = types.ModuleType("frappe")
        fk.logged = []
        fk.log_error = lambda *a, **k: fk.logged.append(a)
        fk.get_traceback = lambda: "tb"
        ut = types.ModuleType("frappe.utils")
        ut.now_datetime = lambda: NOW
        def get_datetime(v):
            if boom:
                raise ValueError("bad")
            return v
        ut.get_datetime = get_datetime
        fk.utils = ut
        qs = types.ModuleType("ecentric_workspace.approval_center.shared.requests.query_service")
        qs.requester_display = lambda u: NAMES.get(u, u)
        sys.modules.update({"frappe": fk, "frappe.utils": ut,
                            "ecentric_workspace.approval_center.shared.requests.query_service": qs})
        return fk

    def _args(self):
        biz = types.SimpleNamespace(requested_by="duc@x")
        req = types.SimpleNamespace(approval_status="Pending", current_level=2)
        return biz, req

    def test_build_that(self):
        self._stub()
        vt = _vt()
        biz, req = self._args()
        lv = levels_pending_l2()
        out = vt.build("cc@x", types.SimpleNamespace(code="X"), biz, req, lv, APPROVERS, {}, {},
                       {"watchers": [{"user": "cc@x", "name": "CC"}]}, [])
        self.assertEqual((out["kind"], out["role"]), ("watch", "follower"))

    def test_loi_thi_khong_ve_bang(self):
        fk = self._stub(boom=True)
        vt = _vt()
        biz, req = self._args()
        lv = levels_pending_l2()
        out = vt.build("ha@x", types.SimpleNamespace(code="X"), biz, req, lv, APPROVERS, {}, {"can_approve": True},
                       None, [])
        self.assertEqual(out["kind"], "")
        self.assertFalse(any(r["mine"] for r in lv))
        self.assertTrue(fk.logged)


class Wiring(unittest.TestCase):
    def read(self, rel):
        with open(os.path.join(ROOT, "ecentric_workspace", rel), encoding="utf-8") as fh:
            return fh.read()

    def test_detail_tra_viewer(self):
        src = self.read("approval_center/shared/requests/query_service.py")
        body = src[src.index("def detail(definition, name):"):src.index("def _privacy_block")]
        self.assertIn("viewer_task.build(user, definition, business, request, levels, approvers, fulfillment,", body)
        self.assertIn('"viewer": viewer,', body)
        self.assertIn('"capabilities": caps,', body)
        self.assertIn('"fulfillment": fulfillment,', body)

    def test_ai_topup_tra_viewer(self):
        src = self.read("approval_center/features/ai_topup/controllers/api.py")
        self.assertIn('"viewer": _viewer_task.build(user, _DEFINITION, biz, req, levels, approvers, ff, caps,', src)


if __name__ == "__main__":
    unittest.main()
