# Copyright (c) 2026, eCentric and contributors
"""Phieu DA DONG (Huy / Tu choi) -> ERP tu don phan ky so cua no (12/11/2026, Hoan chot).

11/11, EC-PAYR-2026-00641: Thu tu huy phieu 10/11 15:02. Chan ky nguoi de nghi van o Manual
Review, ToDo dead-letter van mo, trang van hanh van bao "can xu ly"; bam "Gui lai co kiem" thi
chi nhan `request_not_pending:Cancelled`.

Chot o day:
  1. chi phieu Cancelled / Rejected; phieu Approved / dang mo KHONG bi dong vao;
  2. chan huy duoc -> Cancelled (qua may trang thai, KHONG them canh moi); chan dang chay KHONG
     bi huy; chan Approval Completed (chu ky that) KHONG bi cham;
  3. ToDo dead-letter cua chan bi huy / nam yen duoc dong;
  4. goi ky KHONG bi huy (trang chi tiet bo qua goi Cancelled -> mat phan ky so, QC 12/11);
     trang thai chan doc lai CO KHOA truoc khi quyet (worker co the vua doi no);
  5. chay lai khong lam gi them (idempotent);
  6. cron moi gio don, mot phieu loi khong chan phieu khac, cong tat van tat;
  7. trang van hanh an chan NAM YEN (Permanent Failure / Verification Mismatch) cua phieu da
     dong, nhung VAN hien chan Manual Review (con nut huy / doi soat trong luc cho cron).
"""
import ast
import io
import os
import sys
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_APP = os.path.abspath(os.path.join(_HERE, "..", "..", "..", ".."))
_ESIGN = os.path.join(_APP, "ecentric_workspace", "platform", "esign")


def _read(name):
    with io.open(os.path.join(_ESIGN, name), encoding="utf-8") as fh:
        return fh.read()


class _D(dict):
    __getattr__ = dict.get


def _state():
    m = types.ModuleType("st")
    fk = types.ModuleType("frappe")
    fk._ = lambda s: s
    saved = sys.modules.get("frappe")
    sys.modules["frappe"] = fk
    try:
        exec(compile(_read("state.py"), "state.py", "exec"), m.__dict__)
    finally:
        if saved is None:
            sys.modules.pop("frappe", None)
        else:
            sys.modules["frappe"] = saved
    return m


SM = _state()


class _World(object):
    """Bang gia: DSR, goi, phieu, ToDo. Ghi lai moi lan ghi."""

    def __init__(self, legs, pkgs, req_status, todos=()):
        self.legs = {l["name"]: dict(l) for l in legs}
        #: trang thai THAT luc doc co khoa - khac snapshot neu worker vua chay (QC 12/11)
        self.live = {}
        self.pkgs = {p["name"]: dict(p) for p in pkgs}
        self.req_status = dict(req_status)
        self.todos = {t["name"]: dict(t) for t in todos}
        self.dsr_writes = []
        self.pkg_writes = []

    # frappe.get_all
    def get_all(self, dt, filters=None, fields=None, pluck=None, limit_page_length=None, **kw):
        f = filters or {}

        def match(row):
            for k, v in f.items():
                if isinstance(v, list) and v and v[0] == "in":
                    if row.get(k) not in v[1]:
                        return False
                elif isinstance(v, list) and v and v[0] == "is":
                    if not row.get(k):
                        return False
                elif isinstance(v, list) and v and v[0] == "not in":
                    if row.get(k) in v[1]:
                        return False
                elif row.get(k) != v:
                    return False
            return True
        if dt == "EC Digital Signature Request":
            rows = list(self.legs.values())
        elif dt == "EC Digital Signature Package":
            rows = list(self.pkgs.values())
        elif dt == "EC Approval Request":
            rows = [{"name": k, "approval_status": v} for k, v in self.req_status.items()]
        elif dt == "ToDo":
            rows = list(self.todos.values())
        else:
            rows = []
        rows = [r for r in rows if match(r)]
        if pluck:
            return [r.get(pluck) for r in rows]
        return [_D(r) for r in rows]

    def get_value(self, dt, name, field=None, **kw):
        if dt == "EC Approval Request":
            return self.req_status.get(name)
        return None

    def set_value(self, dt, name, field, value=None, **kw):
        if dt == "ToDo":
            self.todos[name][field] = value

    def current_status(self, dt, name):
        if name in self.live:
            self.legs[name]["status"] = self.live.pop(name)
        return self.legs[name]["status"]

    def set_dsr_status(self, name, to, **kw):
        SM.assert_transition(SM.DSR, self.legs[name]["status"], to)
        self.legs[name]["status"] = to
        self.dsr_writes.append((name, to))

    def set_package_status(self, name, to, **kw):
        SM.assert_transition(SM.PACKAGE, self.pkgs[name]["status"], to)
        self.pkgs[name]["status"] = to
        self.pkg_writes.append((name, to))


def _lifecycle(world):
    fk = types.ModuleType("frappe")
    fk._ = lambda s: s
    fk.get_all = world.get_all
    fk.db = types.SimpleNamespace(get_value=world.get_value, set_value=world.set_value,
                                  count=lambda *a, **k: 0, exists=lambda *a, **k: False)
    fk.throw = lambda m, *a, **k: (_ for _ in ()).throw(Exception(m))
    ev = types.ModuleType("events")
    ev.set_dsr_status = world.set_dsr_status
    ev.set_package_status = world.set_package_status
    ev.current_status = world.current_status
    ev.emit = lambda *a, **k: None
    pkg = types.ModuleType("ecentric_workspace.platform.esign")
    pkg.events, pkg.state = ev, SM
    pkg.hashing = types.ModuleType("hashing")
    pkg.package = types.ModuleType("package")
    mods = {"frappe": fk, "ecentric_workspace.platform.esign": pkg,
            "ecentric_workspace.platform.esign.events": ev,
            "ecentric_workspace.platform.esign.state": SM,
            "ecentric_workspace.platform.esign.hashing": pkg.hashing,
            "ecentric_workspace.platform.esign.package": pkg.package}
    saved = {k: sys.modules.get(k) for k in mods}
    sys.modules.update(mods)
    try:
        m = types.ModuleType("lifecycle")
        exec(compile(_read("lifecycle.py"), "lifecycle.py", "exec"), m.__dict__)
        return m
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v


def _leg(name, status, ar="AR-1", pkg="PKG-1"):
    return {"name": name, "status": status, "approval_request": ar, "package": pkg}


def _todo(name, dsr, status="Open"):
    return {"name": name, "reference_type": "EC Digital Signature Request",
            "reference_name": dsr, "status": status}


class TestDonPhieuDaDong(unittest.TestCase):
    def _world(self, status="Cancelled"):
        return _World(
            legs=[_leg("MR", "Manual Review"), _leg("RF", "Retryable Failure"),
                  _leg("PF", "Permanent Failure"), _leg("VM", "Verification Mismatch"),
                  _leg("OK", "Approval Completed"), _leg("DR", "Draft")],
            pkgs=[{"name": "PKG-1", "status": "Active", "approval_request": "AR-1"}],
            req_status={"AR-1": status},
            todos=[_todo("T-MR", "MR"), _todo("T-PF", "PF"), _todo("T-OK", "OK", "Closed")])

    def test_huy_dung_chan_huy_duoc(self):
        w = self._world()
        out = _lifecycle(w).on_request_closed("AR-1")
        self.assertEqual(sorted(out["cancelled_legs"]), ["DR", "MR", "RF"])
        self.assertEqual(sorted(out["parked_legs"]), ["PF", "VM"])
        self.assertEqual(w.legs["PF"]["status"], "Permanent Failure", "khong them canh moi")
        self.assertEqual(w.legs["OK"]["status"], "Approval Completed", "chu ky that khong cham")

    def test_dong_ToDo(self):
        w = self._world()
        out = _lifecycle(w).on_request_closed("AR-1")
        self.assertEqual(w.todos["T-MR"]["status"], "Cancelled")
        self.assertEqual(w.todos["T-PF"]["status"], "Cancelled")
        self.assertEqual(w.todos["T-OK"]["status"], "Closed")
        self.assertEqual(out["closed_todos"], 2)

    def test_KHONG_huy_goi(self):
        """Trang chi tiet bo qua goi Cancelled -> phieu da dong mat het phan ky so (QC 12/11)."""
        w = self._world()
        _lifecycle(w).on_request_closed("AR-1")
        self.assertEqual(w.pkg_writes, [])
        self.assertEqual(w.pkgs["PKG-1"]["status"], "Active")

    def test_worker_vua_gui_thi_khong_huy(self):
        """Snapshot: Retryable Failure. Luc khoa: worker da dua sang Provider Accepted."""
        w = self._world()
        w.todos["T-RF"] = _todo("T-RF", "RF")
        w.live["RF"] = "Provider Accepted"
        out = _lifecycle(w).on_request_closed("AR-1")
        self.assertNotIn("RF", out["cancelled_legs"])
        self.assertEqual(w.legs["RF"]["status"], "Provider Accepted")
        self.assertEqual(w.todos["T-RF"]["status"], "Open", "chan dang chay: chua dong viec")

    def test_binding_vua_dua_sang_permanent_failure_khong_nem(self):
        """Snapshot: Retryable Failure. Luc khoa: Permanent Failure (binding tu choi). Truoc ban
        sua: InvalidTransition, ca phieu do bo do, Error Log moi gio."""
        w = self._world()
        w.live["RF"] = "Permanent Failure"
        out = _lifecycle(w).on_request_closed("AR-1")
        self.assertIn("RF", out["parked_legs"])

    def test_tu_choi_cung_don(self):
        w = self._world("Rejected")
        self.assertTrue(_lifecycle(w).on_request_closed("AR-1")["cancelled_legs"])

    def test_phieu_mo_hoac_da_duyet_KHONG_dong_vao(self):
        for st in ("Pending", "Information Required", "Approved"):
            w = self._world(st)
            out = _lifecycle(w).on_request_closed("AR-1")
            self.assertEqual(out.get("skipped"), "request_not_closed", st)
            self.assertEqual(w.dsr_writes, [], st)
            self.assertEqual(w.pkg_writes, [], st)

    def test_chan_dang_chay_khong_huy(self):
        w = _World(legs=[_leg("Q", "Queued"), _leg("V", "Verifying"), _leg("MR", "Manual Review")],
                   pkgs=[], req_status={"AR-1": "Cancelled"})
        out = _lifecycle(w).on_request_closed("AR-1")
        self.assertEqual(out["cancelled_legs"], ["MR"])
        self.assertEqual(w.legs["Q"]["status"], "Queued")
        self.assertEqual(w.legs["V"]["status"], "Verifying")

    def test_chay_lai_khong_lam_gi_them(self):
        w = self._world()
        lc = _lifecycle(w)
        lc.on_request_closed("AR-1")
        n_dsr = len(w.dsr_writes)
        out = lc.on_request_closed("AR-1")
        self.assertEqual(len(w.dsr_writes), n_dsr)
        self.assertEqual(out["closed_todos"], 0)

    def test_moi_trang_thai_huy_deu_co_canh_huy(self):
        """Khong them canh moi vao may trang thai: moi trang thai CANCEL_ON_CLOSE da co ->
        Cancelled; moi trang thai PARK_ON_CLOSE KHONG co (neu co thi phai huy chu khong de yen)."""
        for s in SM.CANCEL_ON_CLOSE:
            self.assertIn("Cancelled", SM.DSR_TRANSITIONS[s], s)
        for s in SM.PARK_ON_CLOSE:
            self.assertNotIn("Cancelled", SM.DSR_TRANSITIONS[s], s)
        for s in ("Queued", "Provider Accepted", "Verifying", "Signed", "Approval Completed"):
            self.assertNotIn(s, SM.CANCEL_ON_CLOSE)


class TestTimPhieuCanDon(unittest.TestCase):
    def test_chi_phieu_dong_con_viec(self):
        w = _World(legs=[_leg("A1", "Manual Review", ar="AR-H"),
                         _leg("B1", "Permanent Failure", ar="AR-T"),
                         _leg("C1", "Permanent Failure", ar="AR-X"),
                         _leg("D1", "Manual Review", ar="AR-M")],
                   pkgs=[], req_status={"AR-H": "Cancelled", "AR-T": "Rejected",
                                        "AR-X": "Cancelled", "AR-M": "Pending"},
                   todos=[_todo("T-B1", "B1")])
        need = _lifecycle(w).closed_requests_needing_cleanup()
        # AR-H: chan huy duoc; AR-T: PF con ToDo mo; AR-X: PF da het viec; AR-M: phieu mo.
        self.assertEqual(need, ["AR-H", "AR-T"])


_TASKS = _read("tasks.py")


def _fn(src, name):
    tree = ast.parse(src)
    return [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name][0]


class TestCron(unittest.TestCase):
    def test_sweep_stale_goi_don_SAU_cong_tat(self):
        fn = _fn(_TASKS, "sweep_stale")
        seg = ast.get_source_segment(_TASKS, fn)
        self.assertIn("_cleanup_closed_requests()", seg)
        self.assertLess(seg.index("if _disabled():"), seg.index("_cleanup_closed_requests()"),
                        "cong tat khan cap phai tat ca viec don")

    def test_mot_phieu_loi_khong_chan_phieu_khac(self):
        fn = _fn(_TASKS, "_cleanup_closed_requests")
        g = {"frappe": types.SimpleNamespace(log_error=lambda *a, **k: None,
                                             get_traceback=lambda: ""),
             "_commit_step": lambda: None}
        done = []

        def on_closed(ar):
            if ar == "AR-LOI":
                raise RuntimeError("hong")
            done.append(ar)
        lc = types.SimpleNamespace(closed_requests_needing_cleanup=lambda: ["AR-1", "AR-LOI", "AR-2"],
                                   on_request_closed=on_closed)
        pkg = types.ModuleType("ecentric_workspace.platform.esign")
        pkg.lifecycle = lc
        saved = {k: sys.modules.get(k) for k in ("ecentric_workspace.platform.esign",
                                                 "ecentric_workspace.platform.esign.lifecycle")}
        sys.modules["ecentric_workspace.platform.esign"] = pkg
        sys.modules["ecentric_workspace.platform.esign.lifecycle"] = lc
        try:
            exec(compile(ast.get_source_segment(_TASKS, fn), "t", "exec"), g)
            g["_cleanup_closed_requests"]()
        finally:
            for k, v in saved.items():
                if v is None:
                    sys.modules.pop(k, None)
                else:
                    sys.modules[k] = v
        self.assertEqual(done, ["AR-1", "AR-2"])


_OPS = _read("ops.py")


class TestTrangVanHanh(unittest.TestCase):
    def _closed_legs(self, world):
        fn = _fn(_OPS, "_closed_legs")
        pkg = types.ModuleType("ecentric_workspace.platform.esign")
        pkg.state = SM
        saved = {k: sys.modules.get(k) for k in ("ecentric_workspace.platform.esign",
                                                 "ecentric_workspace.platform.esign.state")}
        sys.modules["ecentric_workspace.platform.esign"] = pkg
        sys.modules["ecentric_workspace.platform.esign.state"] = SM
        try:
            g = {"frappe": types.SimpleNamespace(get_all=world.get_all),
                 "DSR": "EC Digital Signature Request", "AR": "EC Approval Request"}
            exec(compile(ast.get_source_segment(_OPS, fn), "o", "exec"), g)
            return g["_closed_legs"]()
        finally:
            for k, v in saved.items():
                if v is None:
                    sys.modules.pop(k, None)
                else:
                    sys.modules[k] = v

    def test_an_chan_nam_yen_cua_phieu_dong_giu_manual_review(self):
        w = _World(legs=[_leg("PF-DONG", "Permanent Failure", ar="AR-H"),
                         _leg("VM-DONG", "Verification Mismatch", ar="AR-T"),
                         _leg("MR-DONG", "Manual Review", ar="AR-H"),
                         _leg("PF-MO", "Permanent Failure", ar="AR-M")],
                   pkgs=[], req_status={"AR-H": "Cancelled", "AR-T": "Rejected", "AR-M": "Pending"})
        self.assertEqual(sorted(self._closed_legs(w)), ["PF-DONG", "VM-DONG"])

    def test_inbox_tinh_mot_lan(self):
        seg = ast.get_source_segment(_OPS, _fn(_OPS, "inbox"))
        self.assertEqual(seg.count("_closed_legs()"), 1, "inbox chi tinh danh sach an mot lan")
        self.assertIn("stuck_legs(hidden=", seg)
        self.assertIn("closed_legs=", seg)

    def test_dem_phieu_dong_trong_summary(self):
        fn = _fn(_OPS, "summary")
        g = {"stuck_legs": None, "unretrieved_bundles": None, "hash_mismatch_reviews": None,
             "signature_debts": None, "provider_drift": None,
             "_closed_legs": lambda: self.fail("da truyen closed_legs thi khong duoc hoi lai")}
        exec(compile(ast.get_source_segment(_OPS, fn), "s", "exec"), g)
        s = g["summary"](legs=[], bundles=[], mismatches=[], debts=[], drift=[],
                         closed_legs=["A", "B"])
        self.assertEqual(s["closed_request_legs"], 2)

    def test_loc_truoc_khi_cat_limit(self):
        seg = ast.get_source_segment(_OPS, _fn(_OPS, "stuck_legs"))
        self.assertIn('filters["name"] = ["not in", hidden]', seg)


if __name__ == "__main__":
    unittest.main()
