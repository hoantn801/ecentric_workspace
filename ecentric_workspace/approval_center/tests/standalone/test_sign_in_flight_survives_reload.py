# Copyright (c) 2026, eCentric and contributors
"""Chan ky dang bay phai duoc suy ra tu SERVER, khong tu bien JS (06/09, chi Lien / 00043).

  1. service.in_flight_leg (code THAT, frappe gia): chi chan cua DUNG nguoi + DUNG cap, khong
     tinh chan Requester, tra None khi khong co / cap khac / da xong.
  2. signing_readiness tra khoa in_flight (AST).
  3. HTML: actionPanelHTML an nut khi in_flight, Manual Review bao rieng, poll goi
     loadSignReady(true); startSignWait khong reset dong ho khi dang doi; patch p145.
"""
import ast
import io
import os
import sys
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_APP = os.path.abspath(os.path.join(_HERE, "..", "..", "..", ".."))
_PKG = os.path.join(_APP, "ecentric_workspace")


def _read(*parts):
    with io.open(os.path.join(_PKG, *parts), encoding="utf-8") as fh:
        return fh.read()


def _service(dsr_rows, level_of):
    fk = types.ModuleType("frappe"); fk._ = lambda s: s
    fk.PermissionError = type("PermissionError", (Exception,), {})
    fk.ValidationError = type("ValidationError", (Exception,), {})
    fk.session = types.SimpleNamespace(user="lien.vu@ecentric.vn")
    fk.throw = lambda msg, exc=None: (_ for _ in ()).throw((exc or Exception)(msg))
    fk.db = types.SimpleNamespace(get_value=lambda dt, name, f=None, **k: level_of.get(name),
                                  count=lambda *a, **k: 0, exists=lambda *a, **k: None,
                                  set_value=lambda *a, **k: None)
    fk.get_all = lambda dt, filters=None, fields=None, **k: [
        types.SimpleNamespace(**r) for r in dsr_rows
        if r["approver"] == filters.get("approver") and r["status"] in filters["status"][1]
        and ("actor_type" not in filters or r["actor_type"] != filters["actor_type"][1])]
    fk.log_error = lambda *a, **k: None
    fk.get_traceback = lambda: ""
    utils = types.ModuleType("frappe.utils"); utils.now_datetime = lambda: None
    utils.add_to_date = lambda *a, **k: None; utils.get_datetime = lambda x: x
    names = ["binding", "events", "guard", "hashing", "package", "permissions", "state",
             "signed_files", "sanitize", "next_handler", "user_link", "lifecycle"]
    mods = {"frappe": fk, "frappe.utils": utils}
    for n in names:
        mods["ecentric_workspace.platform.esign." + n] = types.ModuleType(n)
    prov = types.ModuleType("ecentric_workspace.platform.esign.providers"); prov.get_adapter = lambda s: None
    base = types.ModuleType("ecentric_workspace.platform.esign.providers.base")
    for cls in ("ProviderError", "SignatureProviderAdapter", "VerificationResult", "NormalizedDocState"):
        setattr(base, cls, type(cls, (Exception,), {}))
    mods["ecentric_workspace.platform.esign.providers"] = prov
    mods["ecentric_workspace.platform.esign.providers.base"] = base
    mods["ecentric_workspace.platform.esign.sanitize"].safe_error = lambda e: str(e)
    saved = {k: sys.modules.get(k) for k in mods}
    sys.modules.update(mods)
    try:
        m = types.ModuleType("_service_under_test")
        src = _read("platform", "esign", "service.py")
        # chi can ham in_flight_leg + hang so: cat phan sau de khong keo theo import lac
        tree = ast.parse(src)
        keep = [n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))
                or (isinstance(n, ast.Assign) and any(getattr(t, "id", "") == "_IN_FLIGHT" for t in n.targets))
                or (isinstance(n, ast.FunctionDef) and n.name == "in_flight_leg")]
        exec(compile(ast.Module(body=keep, type_ignores=[]), "service.py", "exec"), m.__dict__)
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
    return m


ROWS = [{"name": "DSR-L", "approver": "lien.vu@ecentric.vn", "actor_type": "Approval Level",
         "status": "Verifying", "accepted_at": "2026-09-06 01:41:00", "request_level": "LVL-2",
         "manual_review_reason": None},
        {"name": "DSR-LR", "approver": "lien.vu@ecentric.vn", "actor_type": "Requester",
         "status": "Verifying", "accepted_at": "x", "request_level": None, "manual_review_reason": None},
        {"name": "DSR-R", "approver": "hien.nguyen@ecentric.vn", "actor_type": "Requester",
         "status": "Verifying", "accepted_at": "x", "request_level": None, "manual_review_reason": None}]


class TestInFlight(unittest.TestCase):
    def test_dung_nguoi_dung_cap(self):
        m = _service(ROWS, {"LVL-2": 2})
        out = m.in_flight_leg("AR-1", 2, "lien.vu@ecentric.vn")
        self.assertEqual(out["name"], "DSR-L"); self.assertEqual(out["status"], "Verifying")

    def test_cap_khac_thi_khong(self):
        m = _service(ROWS, {"LVL-2": 2})
        self.assertIsNone(m.in_flight_leg("AR-1", 3, "lien.vu@ecentric.vn"))

    def test_chan_requester_cua_chinh_minh_khong_tinh(self):
        m = _service([ROWS[1]], {})
        self.assertIsNone(m.in_flight_leg("AR-1", 2, "lien.vu@ecentric.vn"))

    def test_nguoi_khac_hoac_chan_requester_thi_khong(self):
        m = _service(ROWS, {"LVL-2": 2})
        self.assertIsNone(m.in_flight_leg("AR-1", 2, "hien.nguyen@ecentric.vn"))
        self.assertIsNone(m.in_flight_leg("AR-1", 2, "vinh.vu@ecentric.vn"))

    def test_da_xong_thi_khong(self):
        rows = [dict(ROWS[0], status="Approval Completed")]
        m = _service(rows, {"LVL-2": 2})
        self.assertIsNone(m.in_flight_leg("AR-1", 2, "lien.vu@ecentric.vn"))

    def test_thieu_tham_so_thi_None(self):
        m = _service(ROWS, {"LVL-2": 2})
        self.assertIsNone(m.in_flight_leg(None, 2, "lien.vu@ecentric.vn"))
        self.assertIsNone(m.in_flight_leg("AR-1", None, "lien.vu@ecentric.vn"))


class TestWiring(unittest.TestCase):
    def test_readiness_tra_in_flight(self):
        fn = [n for n in ast.walk(ast.parse(_read("platform", "esign", "service.py")))
              if isinstance(n, ast.FunctionDef) and n.name == "signing_readiness"][0]
        self.assertIn("'in_flight': in_flight_leg(ar, req.current_level, user)", ast.unparse(fn))

    def test_html(self):
        h = _read("approval_center", "features", "payment_request", "ui", "main_section.html")
        i = h.index("function actionPanelHTML")
        body = h[i:i + 1500]
        self.assertIn("var infl = state._signReady && state._signReady.in_flight;", body)
        self.assertIn('if (infl && cap.can_approve) {', body)
        self.assertIn('infl.status === "Manual Review"', body)
        self.assertIn("startSignWait(state.id, ap.current_level);", body)
        j = h.index("function startSignWait")
        self.assertIn("Date.now() < SIGNWAIT.until) return;", h[j:j + 400])
        self.assertIn("loadSignReady(true);                                     // in_flight tu server", h)
        k = h.index("function markSignWait")
        self.assertIn('!(infl && infl.status !== "Manual Review")', h[k:k + 400])
        self.assertIn("p145_resync_payment_request_sign_in_flight", _read("patches.txt"))
        self.assertIn('"state._signReady.in_flight"',
                      _read("approval_center", "patches", "p145_resync_payment_request_sign_in_flight.py"))


if __name__ == "__main__":
    unittest.main()
