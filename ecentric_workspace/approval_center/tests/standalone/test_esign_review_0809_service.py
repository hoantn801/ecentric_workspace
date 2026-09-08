# Copyright (c) 2026, eCentric and contributors
"""Ra soat SCTS dem 08/09 - tang DICH VU (events / service / requester / signed_files /
placement_service / file_guard / api).

  1. events.set_dsr_status / set_package_status doc trang thai bang LOCKING READ (mot lenh
     get_value(..., for_update=True)), khong "khoa name roi doc thuong" (snapshot cu).
  2. service.retire_dead_leg: chan chet CHUA TUNG gui -> nhuong khoa (LegRetired), tao dong moi;
     da tung gui -> tu choi than thien (khong 500, khong ghi); dang doi soat -> tu choi; con song
     / chua xep hang -> tra False de nguoi goi dung lai dong.
  3. approve_and_sign: khong con canh X -> Prepared bat hop phap; requester_submit_and_sign
     khong con insert trung khoa unique.
  4. signed_files._expected_signer_pairs: chi chan Signed / Approval Completed.
  5. placement_service._ensure_signable_dsf: lien ket File goc (source_file), khong sao chep.
  6. file_guard: cot that `signed_review_candidate`.
  7. api: authorize_resend / provider_document_shape / signature_geometry_check chon Settings
     theo provider/environment cua goi, khong lay hang "dang bat" dau tien.
  8. service.get_signing_status: goi theo approval_request phai KHONG terminal + moi nhat.
"""
import ast
import io
import os
import sys
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_APP = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))


def _read(*p):
    with io.open(os.path.join(_APP, *p), encoding="utf-8") as fh:
        return fh.read()


def _fn(src, name):
    for n in ast.walk(ast.parse(src)):
        if isinstance(n, ast.FunctionDef) and n.name == name:
            return n
    raise AssertionError("khong thay ham %s" % name)


def _state():
    m = types.ModuleType("sm")
    exec(compile(_read("platform", "esign", "state.py"), "state.py", "exec"), m.__dict__)
    return m


class _Throw(Exception):
    pass


# --------------------------------------------------------------------------- #
# 1. events: locking read
# --------------------------------------------------------------------------- #
def _events(status_by_name):
    fk = types.ModuleType("frappe"); fk.reads = []; fk.writes = []; fk.inserted = []
    def get_value(dt, name, fields=None, for_update=False, **k):
        fk.reads.append((dt, name, fields, for_update))
        if fields == "status":
            return status_by_name.get(name)
        return name
    fk.db = types.SimpleNamespace(get_value=get_value, count=lambda *a, **k: 0,
                                  set_value=lambda dt, n, v, *a, **k: fk.writes.append((dt, n, v)))
    fk.get_doc = lambda d: types.SimpleNamespace(insert=lambda **k: fk.inserted.append(d))
    fk.flags = types.SimpleNamespace(); fk.as_json = lambda x: str(x)
    fk.session = types.SimpleNamespace(user="u")
    utils = types.ModuleType("frappe.utils"); utils.now_datetime = lambda: "now"
    san = types.ModuleType("sanitize"); san.AUDIT_SUMMARY_LIMIT = 140
    san.error_digest = lambda s: s; san.sanitize = lambda x: x
    mods = {"frappe": fk, "frappe.utils": utils, "ecentric_workspace.platform.esign.state": _state(),
            "ecentric_workspace.platform.esign.sanitize": san}
    saved = {k: sys.modules.get(k) for k in mods}
    sys.modules.update(mods)
    try:
        m = types.ModuleType("_events_under_test")
        exec(compile(_read("platform", "esign", "events.py"), "events.py", "exec"), m.__dict__)
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
    m._fk = fk
    return m


class TestEventsLockingRead(unittest.TestCase):
    def test_trang_thai_doc_co_khoa_mot_lenh(self):
        m = _events({"DSR-1": "Queued", "PKG-1": "Locked"})
        m.set_dsr_status("DSR-1", "Provider Accepted", extra_fields={"accepted_at": "x"})
        m.set_package_status("PKG-1", "Active")
        status_reads = [r for r in m._fk.reads if r[2] == "status"]
        self.assertEqual(len(status_reads), 2)
        for r in status_reads:
            self.assertTrue(r[3], "doc status phai for_update=True (locking read): %s" % (r,))
        plain = [r for r in m._fk.reads if not r[3]]
        self.assertEqual(plain, [], "khong con lenh doc thuong nao truoc khi ghi trang thai")
        self.assertEqual(m._fk.writes[0], ("EC Digital Signature Request", "DSR-1",
                                           {"status": "Provider Accepted", "accepted_at": "x"}))

    def test_canh_bat_hop_le_van_bi_chan_tren_gia_tri_moi(self):
        # snapshot cu noi Queued, ban commit moi noi Approval Completed -> phai CHAN
        m = _events({"DSR-1": "Approval Completed"})
        with self.assertRaises(ValueError):
            m.set_dsr_status("DSR-1", "Queued")
        self.assertEqual(m._fk.writes, [])

    def test_cac_cho_khoa_roi_doc_thuong_da_het(self):
        """Mau `get_value(X, name, "name", for_update=True)` + doc thuong ngay sau: 0 cho con lai
        trong cac module tren duong ky (events/binding/guard/service/signed_files)."""
        import re
        for f in ("events.py", "binding.py", "guard.py", "service.py", "signed_files.py"):
            src = _read("platform", "esign", f)
            bare = re.findall(r'get_value\([^\n]*?"name",\s*for_update=True\)', src)
            self.assertEqual(bare, [], "%s van con khoa-ten-roi-doc-thuong: %s" % (f, bare))


# --------------------------------------------------------------------------- #
# 2. service.retire_dead_leg (ham that, cat bang AST)
# --------------------------------------------------------------------------- #
def _retire_env(row):
    fk = types.ModuleType("frappe"); fk.writes = []; fk.reads = []
    fk._ = lambda s: s
    def throw(msg, *a, **k):
        raise _Throw(msg)
    fk.throw = throw
    def get_value(dt, name, fields=None, as_dict=False, for_update=False, **k):
        fk.reads.append(for_update)
        return types.SimpleNamespace(**row) if row else None
    fk.db = types.SimpleNamespace(get_value=get_value,
                                  set_value=lambda dt, n, f, v=None, **k: fk.writes.append((n, f, v)))
    ev = types.ModuleType("events"); ev.emitted = []
    ev.emit = lambda et, **k: ev.emitted.append((et, k))
    hashing = types.ModuleType("hashing")
    exec(compile(_read("platform", "esign", "hashing.py"), "hashing.py", "exec"), hashing.__dict__)
    src = _read("platform", "esign", "service.py")
    tree = ast.parse(src)
    keep = [n for n in tree.body
            if (isinstance(n, ast.Assign) and any(getattr(t, "id", "") in
                ("LIVE_OR_DONE", "_REUSABLE_PRE_QUEUE", "_DEAD", "_WAITING_HUMAN_VI", "DSR")
                for t in n.targets))
            or (isinstance(n, ast.FunctionDef) and n.name == "retire_dead_leg")]
    g = {"frappe": fk, "_": fk._, "events": ev, "sm": _state()}
    sys.modules["ecentric_workspace.platform.esign.hashing"] = hashing
    exec(compile(ast.Module(body=keep, type_ignores=[]), "service.py", "exec"), g)
    g["_fk"] = fk; g["_ev"] = ev
    return g


def _row(status, **kw):
    r = {"name": "DSR-OLD", "status": status, "accepted_at": None, "bulk_job_transaction_id": None,
         "request_attempt": 1, "idempotency_key": "k" * 64, "package": "PKG-1"}
    r.update(kw)
    return r


class TestRetireDeadLeg(unittest.TestCase):
    def test_chet_chua_gui_thi_nhuong_khoa_va_ghi_su_kien(self):
        for st in ("Permanent Failure", "Cancelled"):
            g = _retire_env(_row(st))
            ex = types.SimpleNamespace(name="DSR-OLD", status=st)
            self.assertTrue(g["retire_dead_leg"](ex, "sep@ec.vn"))
            self.assertEqual(len(g["_fk"].writes), 1)
            n, f, v = g["_fk"].writes[0]
            self.assertEqual((n, f), ("DSR-OLD", "idempotency_key"))
            self.assertEqual(len(v), 64); self.assertNotEqual(v, "k" * 64)
            self.assertEqual(g["_ev"].emitted[0][0], "LegRetired")
            meta = g["_ev"].emitted[0][1]["request_meta"]
            self.assertEqual(meta["original_key"], "k" * 64); self.assertEqual(meta["prior_status"], st)
            self.assertTrue(g["_fk"].reads and g["_fk"].reads[0], "doc dong cu phai co khoa")

    def test_chet_nhung_co_the_da_gui_thi_tu_choi_khong_ghi(self):
        for sig in ({"accepted_at": "2026-09-08"}, {"bulk_job_transaction_id": "T1"},
                    {"request_attempt": 2}):
            g = _retire_env(_row("Permanent Failure", **sig))
            with self.assertRaises(_Throw) as cm:
                g["retire_dead_leg"](types.SimpleNamespace(name="DSR-OLD", status="Permanent Failure"), "u")
            self.assertIn("ký đúp", str(cm.exception))
            self.assertEqual(g["_fk"].writes, []); self.assertEqual(g["_ev"].emitted, [])

    def test_dang_doi_soat_thi_tu_choi_than_thien(self):
        for st in ("Manual Review", "Retryable Failure", "Verification Mismatch"):
            g = _retire_env(_row(st))
            with self.assertRaises(_Throw) as cm:
                g["retire_dead_leg"](types.SimpleNamespace(name="DSR-OLD", status=st), "u")
            self.assertIn("chưa kết thúc", str(cm.exception))
            self.assertEqual(g["_fk"].writes, [])

    def test_terminal_khac_tu_choi(self):
        for st in ("Rejected", "Superseded"):
            g = _retire_env(_row(st))
            with self.assertRaises(_Throw):
                g["retire_dead_leg"](types.SimpleNamespace(name="DSR-OLD", status=st), "u")
            self.assertEqual(g["_fk"].writes, [])

    def test_con_song_hoac_chua_xep_hang_thi_tra_False(self):
        for st in ("Queued", "Approval Completed", "Draft", "Mapping Required"):
            g = _retire_env(_row(st))
            self.assertFalse(g["retire_dead_leg"](types.SimpleNamespace(name="DSR-OLD", status=st), "u"))
            self.assertEqual(g["_fk"].writes, [])

    def test_approve_and_sign_khong_con_canh_bat_hop_phap(self):
        body = ast.unparse(_fn(_read("platform", "esign", "service.py"), "approve_and_sign"))
        self.assertNotIn("request_attempt", body,
                         "approve_and_sign khong duoc tang request_attempt (lam may_have_sent True)")
        self.assertIn("retire_dead_leg(existing, actor)", body)
        self.assertIn("_REUSABLE_PRE_QUEUE", body)
        # kiem canh: moi trang thai "chet" deu KHONG the -> Prepared
        sm = _state()
        for st in ("Permanent Failure", "Cancelled", "Manual Review", "Retryable Failure"):
            self.assertNotIn("Prepared", sm.DSR_TRANSITIONS[st])
        for st in ("Draft", "Mapping Required", "Placement Required"):
            self.assertIn("Prepared", sm.DSR_TRANSITIONS[st])

    def test_requester_submit_dung_lai_helper(self):
        body = ast.unparse(_fn(_read("platform", "esign", "requester.py"), "requester_submit_and_sign"))
        self.assertIn("retire_dead_leg(existing, requester", body)
        i = body.index("idempotency_key': idem}")
        self.assertIn("for_update=True", body[i - 100:i + 200], "tra khoa idempotency phai locking read")


# --------------------------------------------------------------------------- #
# 4-8. cac diem con lai
# --------------------------------------------------------------------------- #
class TestExpectedSignersOnlySigned(unittest.TestCase):
    def test_filter_theo_trang_thai(self):
        src = _read("platform", "esign", "signed_files.py")
        fk = types.ModuleType("frappe"); fk.filters = []
        fk.get_all = lambda dt, filters=None, fields=None, **k: fk.filters.append(filters) or []
        g = {"frappe": fk, "DSR": "EC Digital Signature Request"}
        exec(compile(ast.Module(body=[_fn(src, "_expected_signer_pairs")], type_ignores=[]),
                     "sf.py", "exec"), g)
        g["_expected_signer_pairs"]("PKG-1")
        flt = fk.filters[0]
        self.assertEqual(flt.get("action"), "Sign")
        self.assertEqual(flt.get("status"), ["in", ("Signed", "Approval Completed")],
                         "chan Permanent Failure/Cancelled khong duoc dem la nguoi ky ky vong")


class TestPlacementLinksSourceFile(unittest.TestCase):
    def test_ensure_signable_dsf_lien_ket(self):
        body = ast.unparse(_fn(_read("platform", "esign", "placement_service.py"), "_ensure_signable_dsf"))
        self.assertIn("source_file=f['name']", body,
                      "thieu source_file -> add_file chep them mot File y het vao phieu (bug 05/09 tai dien)")


class TestFileGuardColumn(unittest.TestCase):
    def test_dung_cot_that(self):
        src = _read("platform", "esign", "file_guard.py")
        self.assertNotIn('"review_file"', src)
        self.assertIn('"signed_review_candidate"', src)
        dsf = _read("approval_center", "doctype", "ec_digital_signature_file",
                    "ec_digital_signature_file.json")
        self.assertIn('"signed_review_candidate"', dsf)
        # ham that: File la ban REVIEW -> is_signed_file True
        fk = types.ModuleType("frappe"); fk._ = lambda s: s
        def exists(dt, flt):
            return "REVIEW" in str(flt.get("signed_review_candidate", ""))
        fk.db = types.SimpleNamespace(exists=exists, has_column=lambda dt, c: c == "signed_review_candidate")
        g = {"frappe": fk, "DSF": "EC Digital Signature File", "SIGNED_PREFIX": "SIGNED-"}
        exec(compile(ast.Module(body=[_fn(src, "is_signed_file")], type_ignores=[]), "fg.py", "exec"), g)
        doc = types.SimpleNamespace(name="F-REVIEW-1", get=lambda k: "REVIEW-abc-x.pdf")
        self.assertTrue(g["is_signed_file"](doc))
        doc2 = types.SimpleNamespace(name="F-2", get=lambda k: "hoa-don.pdf")
        self.assertFalse(g["is_signed_file"](doc2))


class TestApiSettingsByPackage(unittest.TestCase):
    def test_ba_diem_khong_con_lay_hang_dang_bat_dau_tien(self):
        src = _read("platform", "esign", "api.py")
        for name in ("authorize_resend", "provider_document_shape", "signature_geometry_check"):
            body = ast.unparse(_fn(src, name))
            self.assertNotIn("'integration_enabled': 1}", body, name)
            self.assertIn("_settings_of(", body, name)
        helper = ast.unparse(_fn(src, "_settings_of"))
        self.assertIn("'provider'", helper); self.assertIn("'environment'", helper)
        self.assertIn("integration_enabled", helper, "cong tat thi phai tu choi")


class TestSigningStatusPackagePick(unittest.TestCase):
    def test_goi_theo_ar_khong_terminal_moi_nhat(self):
        body = ast.unparse(_fn(_read("platform", "esign", "service.py"), "get_signing_status"))
        i = body.index("'approval_request': ar")
        seg = body[i:i + 200]
        self.assertIn("PACKAGE_TERMINAL", seg)
        self.assertIn("order_by='creation desc'", seg)


class TestReadinessStoppedLeg(unittest.TestCase):
    def test_signing_readiness_tra_stopped(self):
        src = _read("platform", "esign", "service.py")
        body = ast.unparse(_fn(src, "signing_readiness"))
        self.assertIn("'stopped': stopped_leg(ar, req.current_level, user)", body)
        st = ast.unparse(_fn(src, "stopped_leg"))
        self.assertIn("may_have_sent", st)
        self.assertIn("'can_resign'", st)
        self.assertIn('"Verification Mismatch"', src[src.index("_IN_FLIGHT = ("):src.index("_IN_FLIGHT = (") + 200])

    def test_event_LegRetired_co_trong_doctype(self):
        ev = _read("approval_center", "doctype", "ec_digital_signature_event",
                   "ec_digital_signature_event.json")
        self.assertIn("LegRetired", ev)


class TestOneDraftPerBusinessUnderLock(unittest.TestCase):
    def test_khoa_phieu_roi_tim_draft_bang_locking_read(self):
        src = _read("platform", "esign", "package.py")
        fk = types.ModuleType("frappe"); fk.calls = []; fk._ = lambda s: s
        def throw(m, *a, **k):
            raise _Throw(m)
        fk.throw = throw
        def get_value(dt, flt, fields=None, for_update=False, **k):
            fk.calls.append((dt, fields, for_update))
            if dt == "EC Digital Signature Package":
                return "PKG-EXISTING"
            return "EC-PAYR-1"
        fk.db = types.SimpleNamespace(get_value=get_value)
        g = {"frappe": fk, "_": fk._, "get_package": lambda n: {"name": n},
             "perms": types.SimpleNamespace(business_approval_request=lambda *a: None),
             "events": types.SimpleNamespace(emit=lambda *a, **k: None)}
        body = [_fn(src, "draft_package_for_business"), _fn(src, "get_or_create_draft")]
        exec(compile(ast.Module(body=body, type_ignores=[]), "pkg.py", "exec"), g)
        out = g["get_or_create_draft"]("EC Payment Request", "EC-PAYR-1", "PROF")
        self.assertEqual(out, {"name": "PKG-EXISTING"})
        self.assertEqual(fk.calls[0], ("EC Payment Request", "name", True), "khoa hang phieu TRUOC")
        self.assertEqual(fk.calls[1][0], "EC Digital Signature Package")
        self.assertTrue(fk.calls[1][2], "tim Draft phai la locking read (thay Draft vua commit)")


if __name__ == "__main__":
    unittest.main()
