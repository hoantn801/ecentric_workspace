# Copyright (c) 2026, eCentric and contributors
"""Dang giu MOT viec khong mo duoc MOI phieu cung loai.

Lo hong (ra soat 01/09). `can_view_request` co nam duong; duong cuoi cung hoi:

    "Nguoi nay co dang giu mot ToDo mo tren LOAI phieu nay khong?"

Hoi LOAI, khong hoi PHIEU NAO. Nen mot truong bo phan dang co dung mot phieu cua nhan vien
minh cho duyet thi trong ca khoang thoi gian do doc duoc MOI De nghi thanh toan cua toan
cong ty - so tien, nguoi nhan, so tai khoan ngan hang cua phong khac. Chi can mot viec bat
ky la mo ca loai.

Hoan chot: khong chap nhan, siet lai. Nhung siet DUNG CHO - hai duong con lai la vai tro
that su, giu nguyen:
  * System Manager;
  * Fulfiller duoc CAU HINH trong quy trinh (Ke toan...) - ho xu ly moi phieu loai do.

Bo test nay giu ca hai chieu: duong ToDo bi buoc vao dung phieu, VA hai duong vai tro khong
bi siet oan (siet qua tay thi Ke toan mat quyen doc, con te hon).
"""
import io
import os
import sys
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))


def _root():
    root = _HERE
    for _i in range(8):
        if os.path.isdir(os.path.join(root, "approval_center", "shared")):
            return root
        parent = os.path.dirname(root)
        if parent == root:
            break
        root = parent
    raise AssertionError("khong tim thay goc ecentric_workspace")


_ROOT = _root()
_SRC = io.open(os.path.join(_ROOT, "approval_center", "shared", "workflow",
                            "permissions.py"), encoding="utf-8").read()


def _load(todos, roles=(), fulfiller_of=(), approvers=()):
    """Nap permissions.py THAT voi mot CSDL gia nho.

    `todos`     : danh sach dict ToDo that su ton tai;
    `roles`     : vai tro cua nguoi dang hoi;
    `fulfiller_of`: cac approval_type ma nguoi nay duoc cau hinh lam Fulfiller;
    `approvers` : cac (approval_request, user) co dong approver.
    """
    seen = {"todo_filters": []}

    class _DB(object):
        @staticmethod
        def exists(dt, filters=None):
            f = filters or {}
            if dt == "ToDo":
                seen["todo_filters"].append(dict(f))
                for t in todos:
                    if all(t.get(k) == v for k, v in f.items()):
                        return "TODO-1"
                return None
            if dt == "EC Approval Participant":
                return "PART-1" if f.get("user") in fulfiller_of else None
            if dt == "EC Approval Request Approver":
                return ("APR-1" if (f.get("approval_request"), f.get("approver")) in approvers
                        else None)
            return None

        @staticmethod
        def get_value(*a, **k):
            return None

    fake = types.ModuleType("frappe")
    fake.db = _DB
    fake.session = types.SimpleNamespace(user="ai@x.vn")
    fake.get_roles = lambda user=None: list(roles)
    # Quy trinh Active cua loai duoc hoi - de _is_configured_fulfiller co cai de duyet.
    fake.get_all = lambda dt, filters=None, pluck=None, **k: (
        ["PROC-1"] if dt == "EC Approval Process" else [])

    saved = sys.modules.get("frappe")
    sys.modules["frappe"] = fake
    env = {}
    try:
        exec(compile(_SRC, "permissions.py", "exec"), env)
        return env, seen
    finally:
        if saved is None:
            sys.modules.pop("frappe", None)
        else:
            sys.modules["frappe"] = saved


_BIZ = "EC Payment Request"
_TRUONG_PHONG = "truong.phong@ec.vn"


def _todo(name):
    return {"reference_type": _BIZ, "reference_name": name,
            "allocated_to": _TRUONG_PHONG, "status": "Open"}


class TestOneTaskDoesNotOpenEveryRecord(unittest.TestCase):
    def test_doc_duoc_dung_phieu_minh_duoc_giao(self):
        env, _ = _load(todos=[_todo("PAYR-001")])
        self.assertTrue(env["can_view_request"](
            "AR-1", _TRUONG_PHONG, business_doctype=_BIZ, approval_type="PAYMENT_REQUEST",
            business_name="PAYR-001"))

    def test_KHONG_doc_duoc_phieu_phong_khac(self):
        """Trai tim cua ban siet: cung loai phieu, khac phieu -> phai tu choi."""
        env, _ = _load(todos=[_todo("PAYR-001")])
        self.assertFalse(env["can_view_request"](
            "AR-9", _TRUONG_PHONG, business_doctype=_BIZ, approval_type="PAYMENT_REQUEST",
            business_name="PAYR-999"),
            "dang giu viec tren PAYR-001 KHONG duoc mo PAYR-999 - do la so tien va so tai "
            "khoan ngan hang cua phong khac")

    def test_bo_loc_todo_co_ten_phieu(self):
        """Chan cach: neu ai do bo `reference_name` thi test tren van co the xanh nhe."""
        env, seen = _load(todos=[_todo("PAYR-001")])
        env["can_view_request"]("AR-9", _TRUONG_PHONG, business_doctype=_BIZ,
                                approval_type="PAYMENT_REQUEST", business_name="PAYR-999")
        todo_filters = [f for f in seen["todo_filters"]]
        self.assertTrue(todo_filters, "khong he tra ToDo - duong nay da bi go mat")
        self.assertTrue(all("reference_name" in f for f in todo_filters),
                        "bo loc ToDo phai co reference_name, neu khong la mo ca loai: %s"
                        % todo_filters)


class TestRoleBasedPathsAreNotNarrowed(unittest.TestCase):
    """Siet qua tay con te hon lo hong: Ke toan mat quyen doc thi he thong dung."""

    def test_system_manager_van_doc_duoc_het(self):
        env, _ = _load(todos=[], roles=("System Manager",))
        self.assertTrue(env["can_view_request"](
            "AR-9", "sm@ec.vn", business_doctype=_BIZ, approval_type="PAYMENT_REQUEST",
            business_name="PAYR-999"))

    def test_fulfiller_duoc_cau_hinh_van_doc_duoc_moi_phieu_cung_loai(self):
        """Ke toan xu ly moi De nghi thanh toan - do la vai tro, khong phai lo hong."""
        env, _ = _load(todos=[], fulfiller_of=("ketoan@ec.vn",))
        self.assertTrue(env["can_view_request"](
            "AR-9", "ketoan@ec.vn", business_doctype=_BIZ, approval_type="PAYMENT_REQUEST",
            business_name="PAYR-999"),
            "Fulfiller duoc cau hinh KHONG duoc bi siet - ho that su xu ly moi phieu loai do")

    def test_nguoi_de_nghi_van_doc_duoc_phieu_cua_minh(self):
        env, _ = _load(todos=[])
        self.assertTrue(env["can_view_request"](
            "AR-9", "nhanvien@ec.vn", business_doctype=_BIZ, requested_by="nhanvien@ec.vn",
            approval_type="PAYMENT_REQUEST", business_name="PAYR-999"))

    def test_nguoi_duyet_cua_CHINH_phieu_do_van_doc_duoc(self):
        env, _ = _load(todos=[], approvers=(("AR-9", "sep@ec.vn"),))
        self.assertTrue(env["can_view_request"](
            "AR-9", "sep@ec.vn", business_doctype=_BIZ, approval_type="PAYMENT_REQUEST",
            business_name="PAYR-999"))

    def test_nguoi_ngoai_van_bi_chan(self):
        env, _ = _load(todos=[])
        self.assertFalse(env["can_view_request"](
            "AR-9", "nguoi.la@ec.vn", business_doctype=_BIZ, approval_type="PAYMENT_REQUEST",
            business_name="PAYR-999"))


class TestBackwardCompatibleWhenNoRecordGiven(unittest.TestCase):
    """Vai cho hoi "co the la nguoi xu ly loai nay khong" khi chua co phieu cu the."""

    def test_khong_truyen_ten_phieu_thi_giu_hanh_vi_cu(self):
        env, _ = _load(todos=[_todo("PAYR-001")])
        self.assertTrue(env["is_eligible_fulfiller"](
            _TRUONG_PHONG, "PAYMENT_REQUEST", _BIZ),
            "khong co ten phieu thi van tra loi theo LOAI - co y, de khong pha cac cho "
            "chi hoi 'co hien menu/bao cao khong'")


class TestEveryCallSitePassesTheRecordName(unittest.TestCase):
    """Ban siet vo dung neu noi goi khong truyen ten phieu xuong.

    Go `business_name=` o capabilities.py ma khong mot phep kiem nao do - nghia la ban siet
    co the bi thao ra trong im lang. Doc CAY CU PHAP cua tung noi goi, khong grep chu.
    """

    #: (duong dan, ten ham chua loi goi) - moi cho DOC MOT PHIEU deu phai truyen ten phieu.
    SITES = [
        (("approval_center", "shared", "requests", "capabilities.py"), "can_view"),
        (("approval_center", "features", "ai_topup", "controllers", "api.py"), "_can_view"),
    ]

    def test_moi_noi_goi_deu_truyen_ten_phieu(self):
        import ast
        for parts, fname in self.SITES:
            src = io.open(os.path.join(_ROOT, *parts), encoding="utf-8").read()
            tree = ast.parse(src)
            fn = None
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and node.name == fname:
                    fn = node
            self.assertIsNotNone(fn, "khong tim thay ham %s trong %s" % (fname, parts[-1]))
            calls = [c for c in ast.walk(fn) if isinstance(c, ast.Call)
                     and (getattr(c.func, "attr", None) or getattr(c.func, "id", None))
                     == "can_view_request"]
            self.assertTrue(calls, "%s khong con goi can_view_request" % fname)
            for c in calls:
                kw = {k.arg for k in c.keywords}
                self.assertIn("business_name", kw,
                              "%s/%s goi can_view_request MA KHONG truyen business_name -> "
                              "duong 'dang giu viec' lai mo ca loai phieu"
                              % (parts[-1], fname))

    def test_action_center_feed_cung_truyen(self):
        import ast
        src = io.open(os.path.join(_ROOT, "action_center", "feed.py"),
                      encoding="utf-8").read()
        calls = [c for c in ast.walk(ast.parse(src)) if isinstance(c, ast.Call)
                 and (getattr(c.func, "attr", None) or getattr(c.func, "id", None))
                 == "can_view_request"]
        self.assertTrue(calls, "feed.py khong con goi can_view_request")
        for c in calls:
            self.assertIn("business_name", {k.arg for k in c.keywords},
                          "feed.py goi can_view_request khong kem business_name")


if __name__ == "__main__":
    unittest.main()
