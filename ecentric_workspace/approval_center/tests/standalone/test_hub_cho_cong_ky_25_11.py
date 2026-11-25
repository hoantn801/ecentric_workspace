# Copyright (c) 2026, eCentric and contributors
"""25/11/2026 (anh Lam, EC-CTR-2026-00135 / EC-DSR-2026-02797): cua so xem nhanh /approvals/all-requests
van hien "Duyet & Ky" khi buoc ky cua nguoi dang xem dang cho cong. get_request_detail._apply_esign_wait
hoi platform.esign.service.in_flight_leg (cung nguon form 27 p557) -> tat nut + esign_wait.
Chay: python -m unittest ecentric_workspace.approval_center.tests.standalone.test_hub_cho_cong_ky_25_11
"""
import ast
import os
import sys
import types
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SRC = open(os.path.join(ROOT, "reporting", "actions.py"), encoding="utf-8").read()


EW = "ecentric_workspace.approval_center.shared.requests.esign_wait"


def _fn(calls, leg=None, boom=False):
    """Chay _apply_esign_wait voi esign_wait gia (helper chung da tu boc loi + doi leg -> wait)."""
    tree = ast.parse(SRC)
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_apply_esign_wait")
    fake = types.SimpleNamespace(session=types.SimpleNamespace(user="lam@ec"))
    ew = types.ModuleType(EW)

    def in_flight(ar, level, user):
        calls.append((ar, level, user))
        if boom or not leg:
            if boom:
                calls.append(("log",))
            return None
        return {"status": leg.get("status"), "accepted_at": str(leg.get("accepted_at") or ""),
                "manual": leg.get("status") == "Manual Review"}
    ew.in_flight = in_flight
    pkg_name = EW.rpartition(".")[0]
    ns = {"frappe": fake}
    exec(compile(ast.Module(body=[node], type_ignores=[]), "actions.py", "exec"), ns)
    f = ns["_apply_esign_wait"]

    def run(data, name):
        saved = sys.modules.get(EW)
        pkg = sys.modules.get(pkg_name)
        had = pkg is not None and hasattr(pkg, "esign_wait")
        old = getattr(pkg, "esign_wait", None) if pkg is not None else None
        sys.modules[EW] = ew
        if pkg is not None:
            pkg.esign_wait = ew
        try:
            return f(data, name)
        finally:
            if saved is None:
                sys.modules.pop(EW, None)
            else:
                sys.modules[EW] = saved
            if pkg is not None:
                if had:
                    pkg.esign_wait = old
                else:
                    delattr(pkg, "esign_wait")
    return run


def _data(**cap):
    c = {"can_approve": True, "can_reject": True, "can_request_information": True, "requires_signature": True}
    c.update(cap)
    return {"capabilities": c, "approval": {"approval_status": "Pending", "current_level": 5}}


class ApplyEsignWait(unittest.TestCase):
    def test_dang_bay_tat_nut(self):
        calls = []
        f = _fn(calls, {"name": "DSR-1", "status": "Accepted", "accepted_at": "2026-11-25 14:05:10"})
        d = _data()
        f(d, "EC-APR-1")
        self.assertEqual(calls, [("EC-APR-1", 5, "lam@ec")])
        c = d["capabilities"]
        self.assertFalse(c["can_approve"] or c["can_reject"] or c["can_request_information"])
        self.assertEqual(d["esign_wait"], {"status": "Accepted", "accepted_at": "2026-11-25 14:05:10", "manual": False})

    def test_manual_review(self):
        d = _data()
        _fn([], {"status": "Manual Review", "accepted_at": None})(d, "EC-APR-1")
        self.assertTrue(d["esign_wait"]["manual"])
        self.assertEqual(d["esign_wait"]["accepted_at"], "")

    def test_khong_bay_giu_nguyen(self):
        d = _data()
        _fn([], None)(d, "EC-APR-1")
        self.assertTrue(d["capabilities"]["can_approve"])
        self.assertNotIn("esign_wait", d)

    def test_cap_khong_ky_khong_hoi(self):
        calls = []
        d = _data(requires_signature=False)
        _fn(calls, {"status": "Accepted"})(d, "EC-APR-1")
        self.assertEqual(calls, [])
        self.assertTrue(d["capabilities"]["can_approve"])

    def test_khong_duoc_duyet_khong_hoi(self):
        calls = []
        _fn(calls, {"status": "Accepted"})(_data(can_approve=False), "EC-APR-1")
        self.assertEqual(calls, [])

    def test_loi_nen_tang_giu_nguyen(self):
        calls = []
        d = _data()
        _fn(calls, boom=True)(d, "EC-APR-1")
        self.assertTrue(d["capabilities"]["can_approve"])
        self.assertIn(("log",), calls)

    def test_get_request_detail_goi(self):
        i = SRC.index("def get_request_detail(")
        self.assertIn("_apply_esign_wait(data, request_name)", SRC[i:i + 900])


if __name__ == "__main__":
    unittest.main()
