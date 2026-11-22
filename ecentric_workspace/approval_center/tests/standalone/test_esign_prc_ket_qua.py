# Copyright (c) 2026, eCentric and contributors
"""PR-C (22/11/2026): bao ket qua ky ve nghiep vu (K6) + khoa goi khi gui cho ho so nguoi lap khong ky.

  1. outcomes.report: loai phieu khong khai hook -> khong lam gi; goi ham nghiep vu DUNG tham so
     (business_name, purpose, outcome, signed_file, detail); moi (goi, outcome) bao mot lan; ham
     loi -> rollback savepoint + Failed + khong nem ra ngoai; "signed" tu tim file_url PDF ky.
  2. "signed" cho phieu Approved + khong co ToDo soat PDF (khong tinh lan loi); khoa goi truoc khi
     doc vet; ham loi -> xoa msgprint cua no. sweep_unreported: loc trong SQL, commit tung goi.
  3. Diem goi: luu du PDF ky (signed), tai lieu chet (destroyed), nguoi ky tu choi (rejected),
     vong tai PDF goi sweep.
  4. requester.lock_on_submit: chi nguoi lap; ho so khong ky so -> khong lam gi; ho so can nguoi
     lap ky -> tu choi; da khoa -> tra lai; thieu goi / thieu o -> bao ro; du -> lock_package.
"""
import io
import os
import sys
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_APP = os.path.abspath(os.path.join(_HERE, "..", "..", "..", ".."))
_ESIGN = os.path.join(_APP, "ecentric_workspace", "platform", "esign")


def _read(*p):
    with io.open(os.path.join(_ESIGN, *p), encoding="utf-8") as fh:
        return fh.read()


class _D(dict):
    __getattr__ = dict.get


def _outcomes(handler=None, events_rows=(), dsf=(), files=None, pkgs=(), ar_status="Approved",
              review_open=False):
    w = {"events": [], "calls": [], "savepoints": [], "rollbacks": [], "logs": [], "locks": [],
         "sql": []}
    fk = types.ModuleType("frappe")
    fk.get_hooks = lambda name: ({"EC Contract Review Request": ["biz.on_outcome"]}
                                 if handler else {})
    fk.get_attr = lambda path: handler
    fk.log_error = lambda *a, **k: w["logs"].append(a)
    fk.get_traceback = lambda: ""
    rows = list(events_rows)

    def get_value(dt, name, fields=None, **k):
        if dt == "EC Digital Signature Package":
            if k.get("for_update"):
                w["locks"].append(name)
                return name
            return _D(name=name, business_doctype=w.get("bd", "EC Contract Review Request"),
                      business_name="CTR-1", approval_request="AR-1")
        if dt == "EC Approval Request":
            return ar_status
        if dt == "EC Digital Signature Event":
            w["evt_locked"] = w.get("evt_locked", 0) + (1 if k.get("for_update") else 0)
            f = name
            hit = [e for e in rows + w["events"] if e[0] == f.get("event_type")
                   and e[1] == f.get("verification_result") and e[2] == f.get("package")]
            return "E" if hit else None
        if dt == "File":
            return (files or {}).get(name)
        return None

    def get_all(dt, filters=None, **k):
        f = filters or {}
        if dt == "EC Digital Signature Event":
            vr = f.get("verification_result")
            return [_D(name="E") for e in rows + [x for x in w["events"]]
                    if e[0] == f.get("event_type") and e[1] == vr and e[2] == f.get("package")]
        if dt == "EC Digital Signature File":
            return [_D(x) for x in dsf]
        if dt == "EC Digital Signature Package":
            return [_D(x) for x in pkgs]
        return []

    def count(dt, f):
        return len([1 for e in rows + w["events"] if e[0] == f.get("event_type")
                    and e[1] == f.get("verification_result") and e[2] == f.get("package")])
    def sql(q, params=None, as_dict=False):
        w["sql"].append((q, params))
        return [_D(x) for x in pkgs]
    fk.local = types.SimpleNamespace(message_log=[])
    fk.db = types.SimpleNamespace(get_value=get_value, count=count, sql=sql,
                                  exists=lambda dt, f: review_open,
                                  savepoint=lambda n: w["savepoints"].append(n),
                                  rollback=lambda save_point=None: w["rollbacks"].append(save_point))
    fk.get_all = get_all
    ev = types.ModuleType("ev")
    ev.emit = lambda et, **k: w["events"].append((et, k.get("verification_result"),
                                                  k.get("package"), k))
    sa = types.ModuleType("sa")
    sa.safe_error = lambda e: str(e)
    mods = {"frappe": fk, "ecentric_workspace.platform.esign.events": ev,
            "ecentric_workspace.platform.esign.sanitize": sa}
    saved = {k: sys.modules.get(k) for k in mods}
    sys.modules.update(mods)
    try:
        m = types.ModuleType("_outcomes")
        exec(compile(_read("outcomes.py"), "outcomes.py", "exec"), m.__dict__)
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
    m._w = w
    return m


class TestReport(unittest.TestCase):
    def test_khong_khai_hook_thi_khong_lam_gi(self):
        m = _outcomes(handler=None)
        self.assertEqual(m.report("PKG-1", "signed", "/f.pdf")["reason"], "no_handler")
        self.assertEqual(m._w["events"], [])

    def test_goi_dung_tham_so_va_chi_mot_lan(self):
        calls = []
        m = _outcomes(handler=lambda bn, purpose, outcome, signed_file=None, detail=None:
                      calls.append((bn, purpose, outcome, signed_file, detail)) or {"changed": True})
        r = m.report("PKG-1", "signed", "/private/files/SIGNED-hd.pdf")
        self.assertTrue(r["ok"])
        self.assertEqual(calls, [("CTR-1", "contract", "signed", "/private/files/SIGNED-hd.pdf",
                                  None)])
        self.assertEqual(m._w["events"][-1][:2], ("Completed", "outcome_reported:signed"))
        r2 = m.report("PKG-1", "signed", "/private/files/SIGNED-hd.pdf")
        self.assertEqual(r2["reason"], "already_reported")
        self.assertEqual(len(calls), 1)
        m.report("PKG-1", "rejected", detail="x")
        self.assertEqual(len(calls), 2, "outcome khac bao rieng")

    def test_ham_loi_rollback_savepoint_khong_nem(self):
        def boom(*a, **k):
            raise ValueError("phieu chua duyet xong")
        m = _outcomes(handler=boom)
        r = m.report("PKG-1", "signed", "/f.pdf")
        self.assertFalse(r["ok"])
        self.assertEqual(m._w["savepoints"], ["esign_outcome"])
        self.assertEqual(m._w["rollbacks"], ["esign_outcome"])
        self.assertEqual(m._w["events"][-1][:2], ("Failed", "outcome_handler_failed:signed"))
        self.assertEqual(len(m._w["logs"]), 1)

    def test_signed_tu_tim_file_url(self):
        seen = []
        m = _outcomes(handler=lambda bn, p, o, signed_file=None, detail=None: seen.append(signed_file),
                      dsf=[{"signed_file": "F1"}, {"signed_file": None}],
                      files={"F1": "/private/files/SIGNED-a.pdf"})
        m.report("PKG-1", "signed")
        self.assertEqual(seen, ["/private/files/SIGNED-a.pdf"])
        m2 = _outcomes(handler=lambda *a, **k: None, dsf=[{"signed_file": None}])
        self.assertEqual(m2.report("PKG-1", "signed")["reason"], "no_signed_file")

    def test_outcome_la_va_loi_noi_bo_khong_nem(self):
        m = _outcomes(handler=lambda *a, **k: None)
        self.assertEqual(m.report("PKG-1", "approved")["reason"], "bad_outcome")
        m._report = lambda *a: 1 / 0
        self.assertEqual(m.report("PKG-1", "signed")["reason"], "internal_error")


class TestCho(unittest.TestCase):
    def test_signed_cho_phieu_approved_khong_tinh_lan_loi(self):
        calls = []
        m = _outcomes(handler=lambda *a, **k: calls.append(a), ar_status="Pending")
        self.assertEqual(m.report("PKG-1", "signed", "/f.pdf")["reason"], "request_not_approved")
        self.assertEqual((calls, m._w["events"]), ([], []))
        m2 = _outcomes(handler=lambda *a, **k: calls.append(a), ar_status="Pending")
        self.assertTrue(m2.report("PKG-1", "rejected", detail="x")["ok"],
                        "outcome khac 'signed' khong cho Approved")

    def test_signed_cho_soat_pdf(self):
        calls = []
        m = _outcomes(handler=lambda *a, **k: calls.append(a), review_open=True)
        self.assertEqual(m.report("PKG-1", "signed", "/f.pdf")["reason"],
                         "signed_file_review_open")
        self.assertEqual(calls, [])

    def test_khoa_goi_truoc_khi_doc_vet(self):
        m = _outcomes(handler=lambda *a, **k: {})
        m.report("PKG-1", "signed", "/f.pdf")
        self.assertEqual(m._w["locks"], ["PKG-1"])
        self.assertEqual(m._w.get("evt_locked"), 1, "vet 'da bao' doc CO KHOA")

    def test_ham_loi_xoa_msgprint_cua_no(self):
        m = _outcomes(handler=None)

        def boom(*a, **k):
            m.frappe.local.message_log.append("loi cua ham")
            raise ValueError("x")
        m = _outcomes(handler=boom)
        m.frappe.local.message_log.append("co tu truoc")
        m.report("PKG-1", "destroyed", detail="y")
        self.assertEqual(m.frappe.local.message_log, ["co tu truoc"])


class TestSweep(unittest.TestCase):
    def test_loc_trong_sql_va_commit_tung_goi(self):
        calls, commits = [], []
        h = lambda *a, **k: calls.append(a) or {}
        m = _outcomes(handler=h, dsf=[{"signed_file": "F1"}], files={"F1": "/f.pdf"},
                      pkgs=[{"name": "PKG-1"}, {"name": "PKG-4"}])
        n = m.sweep_unreported(commit=lambda: commits.append(1))
        self.assertEqual((n, len(calls), len(commits)), (2, 2, 2))
        q, params = m._w["sql"][0]
        self.assertIn("not exists", q)
        self.assertIn("'Rejected', 'Cancelled'", q)
        self.assertIn("outcome_reported:signed", q)
        self.assertIn("outcome_handler_failed:signed", q)
        self.assertEqual((params["max"], params["since"]), (m.MAX_ATTEMPTS, m.SWEEP_SINCE))
        self.assertEqual(params["dts"], ("EC Contract Review Request",))

    def test_khong_hook_thi_khong_quet(self):
        self.assertEqual(_outcomes(handler=None).sweep_unreported(), 0)


class TestWiring(unittest.TestCase):
    def test_diem_goi(self):
        sf = _read("signed_files.py")
        i = sf.index("def retrieve_and_store_for_package(")
        body = sf[i:sf.index("\ndef ", i + 10)]
        self.assertIn('_report_outcome(package_name, "signed")', body)
        self.assertIn("def _report_outcome(", sf)
        t = _read("tasks.py")
        d = t[t.index("def _mark_document_dead("):t.index("def _report_outcome(")]
        self.assertIn('_report_outcome(dsr.package, "destroyed", msg)', d)
        r = t[t.index('verification_result="signer_rejected_at_provider")'):]
        self.assertIn('_report_outcome(dsr.package, "rejected",', r[:900])
        b = t[t.index("def retrieve_signed_bundles("):]
        self.assertIn("outcomes.sweep_unreported(commit=_commit_step)", b[:4000])

    def test_bao_loi_khong_lam_hong_luong(self):
        for src in (_read("tasks.py"), _read("signed_files.py")):
            i = src.index("def _report_outcome(")
            body = src[i:i + 600]
            self.assertIn("except Exception:", body)


# --------------------------------------------------------------------------- lock_on_submit
def _requester(ar="AR-1", user="lap@x", requested_by="lap@x", profile="P", req_sig=False,
               signable=None, draft="PKG-D", missing=(), ar_status="Pending", draft_profile="P"):
    w = {"locks": []}
    fk = types.ModuleType("frappe")
    fk._ = lambda s: s
    fk.session = types.SimpleNamespace(user=user)

    class Perm(Exception):
        pass
    fk.PermissionError = Perm
    fk.throw = lambda m, exc=None: (_ for _ in ()).throw((exc or RuntimeError)(m))
    fk.db = types.SimpleNamespace(get_value=lambda dt, n, f=None, **k: (
        draft_profile if f == "profile" else _D(approval_type="KOL", requested_by=requested_by,
                                                approval_status=ar_status)))
    fu = types.ModuleType("frappe.utils")
    fu.now_datetime = lambda: None
    g = types.ModuleType("guard")
    g.get_enabled_profile = lambda *a: profile
    g.requester_signature_required = lambda *a: req_sig
    pk = types.ModuleType("pkg")
    pk.signable_package_for_request = lambda a: signable
    pk.draft_package_for_business = lambda bd, bn, for_update=False: draft
    pk.preflight_for_lock = lambda n: list(missing)
    pk.lock_package = lambda n, a: w["locks"].append((n, a)) or "HASH"
    root = types.ModuleType("ecentric_workspace.platform.esign")
    root.events, root.guard, root.hashing = types.ModuleType("e"), g, types.ModuleType("h")
    root.package, root.permissions = pk, types.ModuleType("p")
    mods = {"frappe": fk, "frappe.utils": fu, "ecentric_workspace.platform.esign": root,
            "ecentric_workspace.platform.esign.package": pk,
            "ecentric_workspace.platform.esign.permissions": root.permissions}
    saved = {k: sys.modules.get(k) for k in mods}
    sys.modules.update(mods)
    try:
        m = types.ModuleType("_req")
        exec(compile(_read("requester.py"), "requester.py", "exec"), m.__dict__)
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
    m._requester_ar = lambda bd, bn: ar
    m._w, m._Perm = w, Perm
    return m


class TestLockOnSubmit(unittest.TestCase):
    def test_khoa_goi_draft(self):
        m = _requester()
        r = m.lock_on_submit("EC Contract Review Request", "CTR-1")
        self.assertEqual((r["locked"], r["package"]), (True, "PKG-D"))
        self.assertEqual(m._w["locks"], [("PKG-D", "AR-1")])

    def test_chi_nguoi_lap(self):
        m = _requester(user="khac@x")
        with self.assertRaises(m._Perm):
            m.lock_on_submit("EC Contract Review Request", "CTR-1")

    def test_khong_ho_so_thi_khong_lam_gi(self):
        m = _requester(profile=None)
        self.assertEqual(m.lock_on_submit("X", "1")["reason"], "no_profile")
        self.assertEqual(m._w["locks"], [])

    def test_ho_so_can_nguoi_lap_ky_thi_tu_choi(self):
        m = _requester(req_sig=True)
        with self.assertRaises(RuntimeError):
            m.lock_on_submit("X", "1")

    def test_da_khoa_tra_lai(self):
        m = _requester(signable="PKG-L")
        r = m.lock_on_submit("X", "1")
        self.assertTrue(r["duplicate"])
        self.assertEqual(m._w["locks"], [])

    def test_thieu_goi_hoac_thieu_o(self):
        m = _requester(draft=None)
        with self.assertRaises(RuntimeError):
            m.lock_on_submit("X", "1")
        m = _requester(missing=["missing_placement:L4:hd.pdf"])
        with self.assertRaises(RuntimeError) as cm:
            m.lock_on_submit("X", "1")
        self.assertIn("thiếu vị trí ký", str(cm.exception))
        self.assertEqual(m._w["locks"], [])

    def test_yeu_cau_khong_cho_duyet_thi_tu_choi(self):
        m = _requester(ar_status="Rejected")
        with self.assertRaises(RuntimeError):
            m.lock_on_submit("X", "1")
        self.assertEqual(m._w["locks"], [])

    def test_luong_ky_doi_sau_khi_dat_o_thi_tu_choi(self):
        m = _requester(draft_profile="P-CU")
        with self.assertRaises(RuntimeError) as cm:
            m.lock_on_submit("X", "1")
        self.assertIn("Luồng ký", str(cm.exception))
        self.assertEqual(m._w["locks"], [])


if __name__ == "__main__":
    unittest.main()
