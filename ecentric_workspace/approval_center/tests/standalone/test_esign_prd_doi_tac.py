# Copyright (c) 2026, eCentric and contributors
"""PR-D (22/11/2026): doi tac ky ngoai cho hop dong (WF09) - chi ho so bat allow_external_signers.

  1. scts._external_handlers_payload: dung khoa cong gui (add-document.js); thieu ten / email,
     kieu ky la -> ProviderError khong retry; mac dinh SignType "ekyc" (PR-F 23/11).
  2. tasks._external_handlers_for: ho so khong bat -> [] (DNTT khong doi); bat ma hook thieu /
     rong / loi -> partner_info_missing (khong tao tai lieu thieu doi tac).
  3. next_handler.plan_portal_step: buoc sang doi tac - ho so khong bat -> dung nhu cu; bat ->
     dung MOT nguoi cong chap nhan; 0 / nhieu / khong hoi duoc -> dung.
  4. signed_files._terminal_signed_ok: doi tac chua ky -> waiting_partner; tu choi ->
     partner_rejected; tra lai -> partner_returned; tai lieu huy -> document_dead; doi chieu ban
     doi tac DA GUI; ho so khong bat -> giu nguyen nhu cu.
  5. tasks.retrieve_signed_bundles: cho doi tac chi bao khi qua 7 ngay; tu choi can 2 vong lien
     tiep; khong bao duoc ve nghiep vu -> bao nguoi mot lan; goi da dong -> bo qua.
  6. user_link.signer_token_needed: buoc Approve dung token rieng CHI khi ho so co doi tac.
"""
import ast
import io
import json
import os
import sys
import textwrap
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


class _PE(Exception):
    def __init__(self, code, msg="", retryable=True):
        Exception.__init__(self, code)
        self.code, self.msg, self.retryable = code, msg, retryable


def _fns(src, names):
    """Lay nguyen van cac ham / hang so top-level theo ten (khong nap ca module)."""
    out = []
    for n in ast.parse(src).body:
        nm = getattr(n, "name", None)
        if nm is None and isinstance(n, ast.Assign):
            nm = getattr(n.targets[0], "id", None)
        if nm in names:
            out.append(textwrap.dedent(ast.get_source_segment(src, n)))
    assert len(out) == len(names), (names, len(out))
    return "\n\n".join(out)


def _fk(**kw):
    fk = types.SimpleNamespace(log_error=lambda *a, **k: None, get_traceback=lambda: "tb",
                               _dict=_D)
    for k, v in kw.items():
        setattr(fk, k, v)
    return fk


# =============================================================================== 1. payload
class TestPayload(unittest.TestCase):
    def setUp(self):
        g = {"ProviderError": _PE}
        exec(compile(_fns(_read("providers", "scts.py"),
                          ["PARTNER_SIGN_TYPES", "PARTNER_DEFAULT_SIGN_TYPE", "_external_handlers_payload"]), "s", "exec"), g)
        self.f = g["_external_handlers_payload"]

    def test_rong(self):
        self.assertEqual(self.f(None), [])
        self.assertEqual(self.f([]), [])

    def test_dung_khoa_cong(self):
        out = self.f([{"full_name": " Nguyen Van A ", "email": "a@kol.vn", "phone": "09",
                       "identity": "0791", "sign_type": "ekyc"}])
        self.assertEqual(set(out[0]), {"PartnerId", "FullName", "Email", "Phone",
                                       "IdentityNumber", "IdentityPlace", "IdentityDate", "Dob",
                                       "SignType"})
        self.assertEqual((out[0]["FullName"], out[0]["SignType"]), ("Nguyen Van A", "ekyc"))
        self.assertIsNone(out[0]["PartnerId"])

    def test_mac_dinh_ekyc(self):
        """Hoan chot 23/11 (PR-F): doi tac ky eKYC khi nghiep vu khong chi dinh."""
        self.assertEqual(self.f([{"full_name": "B", "email": "b@x.vn"}])[0]["SignType"], "ekyc")
        self.assertEqual(self.f([{"full_name": "B", "email": "b@x.vn", "sign_type": "image"}])[0]
                         ["SignType"], "image")

    def test_thieu_thong_tin_khong_retry(self):
        for row in ({"full_name": "", "email": "a@x"}, {"full_name": "A", "email": "khong-email"},
                    {"full_name": "A"}):
            with self.assertRaises(_PE) as cm:
                self.f([row])
            self.assertEqual(cm.exception.code, "partner_info_invalid")
            self.assertFalse(cm.exception.retryable)

    def test_kieu_ky_la(self):
        with self.assertRaises(_PE) as cm:
            self.f([{"full_name": "A", "email": "a@x", "sign_type": "usb"}])
        self.assertEqual(cm.exception.code, "partner_sign_type_invalid")

    def test_add_document_dung_ham(self):
        src = _read("providers", "scts.py")
        self.assertIn('handlers = _external_handlers_payload(package_ctx.get("external_handlers"))',
                      src)
        self.assertIn('"ExternalHandlers": handlers,', src)
        self.assertNotIn('"ExternalHandlers": [],', src)


# =============================================================================== 2. hook
class _VE(Exception):
    pass


def _ext(allow, hook=None, rows=None, boom=None, profile="P"):
    def get_attr(path):
        def f(bn):
            if boom:
                raise boom
            return rows
        return f
    fk = _fk(db=types.SimpleNamespace(get_value=lambda dt, n, f=None, **k: allow),
             get_hooks=lambda n: ({"EC Contract Review Request": [hook]} if hook else {}),
             get_attr=get_attr, ValidationError=_VE)
    g = {"frappe": fk, "ProviderError": _PE}
    exec(compile(_fns(_read("tasks.py"), ["EXTERNAL_HOOK", "_external_handlers_for"]),
                 "t", "exec"), g)
    sg = {"ProviderError": _PE}
    exec(compile(_fns(_read("providers", "scts.py"),
                      ["PARTNER_SIGN_TYPES", "PARTNER_DEFAULT_SIGN_TYPE", "_external_handlers_payload"]), "s", "exec"), sg)
    scts = types.ModuleType("scts")
    scts._external_handlers_payload = sg["_external_handlers_payload"]
    pkg = _D(name="PKG-1", profile=profile, business_doctype="EC Contract Review Request",
             business_name="CTR-1")

    def run():
        key = "ecentric_workspace.platform.esign.providers.scts"
        old = sys.modules.get(key)
        sys.modules[key] = scts
        try:
            return g["_external_handlers_for"](pkg)
        finally:
            if old is None:
                sys.modules.pop(key, None)
            else:
                sys.modules[key] = old
    return run


class TestHook(unittest.TestCase):
    def test_ho_so_khong_bat_thi_rong(self):
        self.assertEqual(_ext(0, hook="biz.f", rows=[{"x": 1}])(), [])
        self.assertEqual(_ext(1, hook="biz.f", rows=[{"x": 1}], profile=None)(), [])

    def test_bat_tra_dong_hook(self):
        rows = [{"full_name": "A", "email": "a@x"}]
        self.assertEqual(_ext(1, hook="biz.f", rows=rows)(), rows)

    def test_bat_ma_thieu_rong_loi_thi_chan(self):
        for f in (_ext(1), _ext(1, hook="biz.f", rows=[]),
                  _ext(1, hook="biz.f", boom=RuntimeError("x"))):
            with self.assertRaises(_PE) as cm:
                f()
            self.assertEqual(cm.exception.code, "partner_info_missing")
            self.assertFalse(cm.exception.retryable)

    def test_loi_nghiep_vu_giu_nguyen_cau(self):
        with self.assertRaises(_PE) as cm:
            _ext(1, hook="biz.f", boom=_VE("Hop dong chua co email doi tac"))()
        self.assertIn("chua co email doi tac", cm.exception.msg)

    def test_dong_sai_kieu_kiem_truoc(self):
        for rows in (["a@x"], [{"full_name": "A", "email": "khong-email"}]):
            with self.assertRaises(_PE) as cm:
                _ext(1, hook="biz.f", rows=rows)()
            self.assertEqual(cm.exception.code, "partner_info_invalid")

    def test_lay_truoc_khi_doi_trang_thai_va_chot_ban_gui(self):
        src = _read("tasks.py")
        fn = [n for n in ast.parse(src).body if getattr(n, "name", "") ==
              "_ensure_provider_document"][0]
        seg = ast.get_source_segment(src, fn)
        self.assertLess(seg.index("external = _external_handlers_for(pkg)"),
                        seg.index("events.set_package_status(pkg.name, \"Provider Creating\""))
        self.assertIn('"external_handlers": external', seg)
        self.assertIn("verification_result=PARTNERS_SENT", seg)


# =============================================================================== 3. next_handler
def _nh(allow, eligible, approvers=None, final=4, internal=()):
    fk = types.ModuleType("frappe")
    fk._ = lambda s: s
    fk.conf = {}
    rows = [_D(action="Sign", stage="level:4", transition_id=-5, transition_name="Chuyen doi tac",
               process_action="WfFunctionRunSignedA", sign_type="ky-chinh", terminal=0)]

    def gv(dt, n, f=None, **k):
        if f == "allow_external_signers":
            return allow
        if f == "current_level":
            return 4
        return None

    def get_all(dt, filters=None, **k):
        if dt == "EC Approval Request Approver":
            return [_D(level_no=final)] if final else []
        return []
    fk.db = types.SimpleNamespace(
        get_value=gv, exists=lambda dt, f=None, **k: (
            dt == "EC SCTS User Mapping" and str((f or {}).get("scts_user_id")) in internal))
    fk.get_all = get_all
    fk.get_doc = lambda dt, n: _D(transitions=rows)
    fk.log_error = lambda *a, **k: None
    fk.get_traceback = lambda: "tb"
    utils = types.ModuleType("frappe.utils")
    utils.now_datetime = utils.add_to_date = utils.get_datetime = lambda *a, **k: None
    mods = {"frappe": fk, "frappe.utils": utils}
    saved = {k: sys.modules.get(k) for k in mods}
    sys.modules.update(mods)
    try:
        nh = types.ModuleType("_nh_prd")
        exec(compile(_read("next_handler.py"), "next_handler.py", "exec"), nh.__dict__)
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
    nh.next_level_approvers = lambda ar, lv: list(approvers or [])
    nh.provider_ids_for = lambda users, env: (["P-" + u for u in users], [])
    nh._level_of = lambda dsr: 4
    ad = types.SimpleNamespace(eligible_recipients=lambda *a: eligible)
    return nh, ad


DSR_CEO = _D(name="DSR-9", approval_request="AR-1", action="Sign", actor_type="Approval Level",
             effective_scts_user_id="U-CEO")
ST6 = {"current_state_id": "6", "transitions": [
    {"transition_id": -5, "transition_name": "x", "requires_signature": True,
     "process_action": "WfFunctionRunSignedA", "sign_type": None, "to_state": "7",
     "terminal": False}]}


class TestBuocDoiTac(unittest.TestCase):
    def _plan(self, *a, **k):
        nh, ad = _nh(*a, **k)
        return nh.plan_portal_step(DSR_CEO, ST6, "P", "UAT", adapter=ad, instance_id="I")

    def test_ho_so_khong_bat_dung_nhu_cu(self):
        p = self._plan(0, {"DT-1"})
        self.assertEqual((p["mode"], p["reason"]),
                         ("stop", "no_next_level_approver:partner_step_not_supported"))

    def test_dung_mot_nguoi_nhan(self):
        p = self._plan(1, {"DT-1"})
        self.assertEqual(p["mode"], "transition")
        self.assertEqual((p["to_users"], p["erp_users"]), (["DT-1"], []))
        self.assertTrue(p["partner_handover"])
        self.assertEqual(p["config"]["transition_id"], -5)

    def test_chua_phai_cap_cuoi_thi_dung(self):
        p = self._plan(1, {"DT-1"}, final=5)
        self.assertEqual((p["mode"], p["reason"]), ("stop", "no_next_level_approver:not_final_level"))
        p = self._plan(1, {"DT-1"}, final=None)
        self.assertEqual(p["mode"], "stop")

    def test_nguoi_nhan_noi_bo_hoac_chinh_minh_thi_dung(self):
        p = self._plan(1, {"U-CEO"})
        self.assertEqual((p["mode"], p["reason"]), ("stop", "partner_recipient_internal:U-CEO"))
        p = self._plan(1, {"KT-7"}, internal=("KT-7",))
        self.assertEqual(p["reason"], "partner_recipient_internal:KT-7")

    def test_khong_hoi_duoc_rong_nhieu_thi_dung(self):
        for el, mode, why in ((None, "wait", "partner_recipient_unverified"),
                              (set(), "stop", "partner_recipient_ambiguous:0"),
                              ({"A", "B"}, "stop", "partner_recipient_ambiguous:2")):
            # Khong hoi duoc nguoi nhan (loi tam thoi) -> CHO thu lai, khong gui (PR-F QC vong 2).
            p = self._plan(1, el)
            self.assertEqual((p["mode"], p["reason"]), (mode, why))
        nh, ad = _nh(1, {"DT-1"})
        self.assertEqual(nh.plan_portal_step(DSR_CEO, ST6, "P", "UAT")["reason"],
                         "partner_recipient_unverified", "khong co adapter -> khong doan")

    def test_con_nguoi_erp_thi_khong_vao_nhanh_doi_tac(self):
        p = self._plan(1, None, approvers=["ktt@x"])
        self.assertEqual(p["to_users"], ["P-ktt@x"])
        self.assertFalse(p.get("partner_handover"))


# =============================================================================== 4. retrieval gate
def _gate(allow, signers, ext_rows=None, sign_pairs=(("U-A", {"a@ec"}),), approve_mails=(),
          sent=None, status="processing", destroyed=False):
    dsrs = [_D(name="D1", status="Approval Completed")]

    def gv(dt, n, f=None, **k):
        if f == "allow_external_signers":
            return allow
        return None

    def get_all(dt, filters=None, fields=None, **k):
        if dt == "EC Digital Signature Event":
            return ([_D(request_meta=json.dumps({"partner_emails": sent}))]
                    if sent is not None else [])
        return dsrs
    fk = _fk(db=types.SimpleNamespace(get_value=gv), get_all=get_all)
    tasks = types.ModuleType("tasks")

    def ext(pkg):
        if ext_rows is None:
            raise _PE("partner_info_missing")
        return ext_rows
    tasks._external_handlers_for = ext
    pkgmod = types.ModuleType("ecentric_workspace.platform.esign")
    pkgmod.tasks = tasks
    saved = {k: sys.modules.get(k) for k in ("ecentric_workspace.platform.esign",
                                             "ecentric_workspace.platform.esign.tasks")}
    g = {"frappe": fk, "json": json, "PKG": "EC Digital Signature Package", "DSR": "DSR",
         "EVT": "EC Digital Signature Event",
         "DSR_TERMINAL": ("Approval Completed", "Cancelled", "Permanent Failure"),
         "_TERMINAL_SIGNED": ("signed", "completed"),
         "_expected_signer_pairs": lambda n: [(i, frozenset(m)) for i, m in sign_pairs]}
    exec(compile(_fns(_read("signed_files.py"),
                      ["PROFILE", "_external_expectation", "_RETURNED", "_partner_state",
                       "_is_partner", "_terminal_signed_ok"]), "sf", "exec"), g)
    g["_approve_leg_emails"] = lambda n: set(approve_mails)
    adapter = types.SimpleNamespace(poll_status=lambda d: _D(
        status=status, signers=signers, identity={"destroyed": destroyed}))

    def run():
        sys.modules["ecentric_workspace.platform.esign"] = pkgmod
        sys.modules["ecentric_workspace.platform.esign.tasks"] = tasks
        try:
            return g["_terminal_signed_ok"](adapter, _D(name="PKG-1", profile="P",
                                                        scts_document_id="DOC",
                                                        business_doctype="X",
                                                        business_name="Y"))
        finally:
            for k, v in saved.items():
                if v is None:
                    sys.modules.pop(k, None)
                else:
                    sys.modules[k] = v
    return run


A = {"user_id": "U-A", "email": "a@ec", "status": "signed", "is_external": False}
P_ROW = [{"full_name": "KOL", "email": "kol@x.vn"}]


def _p(st, ext=True, email="KOL@x.vn", raw=None):
    return {"user_id": None, "email": email, "status": st, "is_external": ext,
            "provider_status": raw}


class TestCongTai(unittest.TestCase):
    def test_doi_tac_chua_ky(self):
        self.assertEqual(_gate(1, [A, _p("pending")], P_ROW)(), (False, "waiting_partner"))

    def test_doi_tac_tu_choi(self):
        self.assertEqual(_gate(1, [A, _p("rejected", raw="từ chối")], P_ROW)(),
                         (False, "partner_rejected"))

    def test_doi_tac_tra_lai_khac_tu_choi(self):
        self.assertEqual(_gate(1, [A, _p("rejected", raw="trả lại")], P_ROW)(),
                         (False, "partner_returned"))

    def test_tu_choi_khong_bi_cho_che(self):
        two = [{"full_name": "K1", "email": "k1@x"}, {"full_name": "K2", "email": "k2@x"}]
        r = _gate(1, [A, _p("pending", email="k1@x"), _p("rejected", email="k2@x")], two)()
        self.assertEqual(r, (False, "partner_rejected"))

    def test_tai_lieu_huy_khi_cho_doi_tac(self):
        self.assertEqual(_gate(1, [A, _p("pending")], P_ROW, status="cancelled")(),
                         (False, "document_dead:cancelled"))
        self.assertEqual(_gate(1, [A, _p("pending")], P_ROW, destroyed=True)()[1],
                         "document_dead:processing")

    def test_doi_tac_ky_xong(self):
        ok, why = _gate(1, [A, _p("signed")], P_ROW)()
        self.assertTrue(ok, why)

    def test_doi_tac_vang_mat(self):
        ok, why = _gate(1, [A], P_ROW)()
        self.assertEqual((ok, why), (False, "expected_signer_absent:kol@x.vn"))

    def test_dung_ban_da_gui_khong_doc_lai_hook(self):
        """Email doi tac sua sau khi tao / co ho so tat giua chung: van doi chieu ban DA GUI."""
        ok, why = _gate(0, [A, _p("signed")], ext_rows=[{"email": "moi@x"}],
                        sent=["kol@x.vn"])()
        self.assertTrue(ok, why)
        self.assertEqual(_gate(1, [A, _p("signed")], sent=[])(), (False, "partner_info_missing"))

    def test_khong_lay_duoc_doi_tac_thi_chan(self):
        self.assertEqual(_gate(1, [A, _p("signed")], None)(), (False, "partner_info_missing"))

    def test_nguoi_la_van_bi_chan(self):
        x = {"user_id": "U-X", "email": "x@la", "status": "signed", "is_external": False}
        self.assertEqual(_gate(1, [A, _p("signed"), x], P_ROW)(),
                         (False, "unexpected_signer_identity"))

    def test_nguoi_duyet_khong_ky_khong_phai_nguoi_la(self):
        ceo = {"user_id": "U-C", "email": "ceo@ec", "status": "signed", "is_external": False}
        ok, why = _gate(1, [A, _p("signed"), ceo], P_ROW, approve_mails={"ceo@ec"})()
        self.assertTrue(ok, why)

    def test_ho_so_khong_bat_giu_nguyen(self):
        """DNTT: doi tac pending -> non_signed nhu cu; doi tac signed -> nguoi la."""
        self.assertEqual(_gate(0, [A, _p("pending")])(),
                         (False, "non_signed_signer_present:pending"))
        self.assertEqual(_gate(0, [A, _p("signed")])(), (False, "unexpected_signer_identity"))
        ceo = {"user_id": "U-C", "email": "ceo@ec", "status": "signed", "is_external": False}
        self.assertEqual(_gate(0, [A, ceo], approve_mails={"ceo@ec"})(),
                         (False, "unexpected_signer_identity"))
        self.assertEqual(_gate(0, [A, _p("pending")], status="cancelled")(),
                         (False, "non_signed_signer_present:pending"))


# =============================================================================== 5. cron loop
class TestVongTai(unittest.TestCase):
    def _run(self, detail, closed=False, failures=0, handler=True, not_ready=(), overdue=False):
        w = {"reported": [], "stalled": []}
        pkg = _D(name="PKG-1", provider="SCTS", environment="UAT", approval_request="AR-1")

        def exists(dt, f):
            if dt == "EVT":
                if f.get("event_type") == "SignedRetrievalNotReady":
                    assert f["creation"][0] == "<"
                    return overdue
                return closed
            return True

        def get_all(dt, filters=None, **k):
            if dt == "EVT":
                return [_D(verification_result=v) for v in not_ready]
            return [pkg]
        fk = _fk(get_all=get_all,
                 db=types.SimpleNamespace(exists=exists, get_value=lambda *a, **k: "Approved",
                                          count=lambda dt, f: failures))
        sf = types.ModuleType("sf")
        sf.retrieve_and_store_for_package = lambda n: {"ok": False, "reason": "x",
                                                       "detail": detail}
        oc = types.ModuleType("oc")
        oc.sweep_unreported = lambda commit=None: 0
        oc.handler_path = lambda bd: "biz.f" if handler else None
        oc.MAX_ATTEMPTS = 5
        mods = {"ecentric_workspace.platform.esign.signed_files": sf,
                "ecentric_workspace.platform.esign.outcomes": oc}
        pkgmod = types.ModuleType("ecentric_workspace.platform.esign")
        pkgmod.signed_files, pkgmod.outcomes = sf, oc
        mods["ecentric_workspace.platform.esign"] = pkgmod
        g = {"frappe": fk, "DSR": "DSR", "EVT": "EVT", "_disabled": lambda: False,
             "now_datetime": lambda: "NOW", "add_to_date": lambda d, days=0: (d, days),
             "_integration_open": lambda *a: True, "_commit_step": lambda: None,
             "_report_outcome": lambda p, o, d=None: w["reported"].append((p, o, d)),
             "_flag_stalled_retrieval": lambda n, threshold=None, reason=None:
                 w["stalled"].append((n, threshold, reason))}
        exec(compile(_fns(_read("tasks.py"), [
            "_AR_CLOSED", "_PARTNER_REASONS", "PARTNER_ALERT_DAYS", "_MSG_PARTNER_REJECTED",
            "_MSG_PARTNER_RETURNED", "_MSG_DOC_DEAD", "_handle_partner_round",
            "_outcome_closed", "retrieve_signed_bundles"]), "t", "exec"), g)
        saved = {k: sys.modules.get(k) for k in mods}
        sys.modules.update(mods)
        try:
            g["retrieve_signed_bundles"]()
        finally:
            for k, v in saved.items():
                if v is None:
                    sys.modules.pop(k, None)
                else:
                    sys.modules[k] = v
        return w, g

    def test_cho_doi_tac_chi_bao_khi_qua_lau(self):
        w, g = self._run("waiting_partner")
        self.assertEqual((w["reported"], w["stalled"]), ([], []))
        w, g = self._run("waiting_partner", overdue=True)
        self.assertEqual(w["stalled"], [("PKG-1", 0, "partner_overdue")])

    def test_tu_choi_can_hai_vong_lien_tiep(self):
        w, g = self._run("partner_rejected", not_ready=("partner_rejected",))
        self.assertEqual(w["reported"], [], "mot vong -> chua bao")
        w, g = self._run("partner_rejected", not_ready=("partner_rejected", "waiting_partner"))
        self.assertEqual(w["reported"], [])
        w, g = self._run("partner_rejected", not_ready=("partner_rejected", "partner_rejected"))
        self.assertEqual(w["reported"], [("PKG-1", "rejected", g["_MSG_PARTNER_REJECTED"])])

    def test_tra_lai_bao_returned(self):
        w, g = self._run("partner_returned", not_ready=("partner_returned",))
        self.assertEqual(w["reported"], [])
        w, g = self._run("partner_returned", not_ready=("partner_returned",) * 2)
        self.assertEqual(w["reported"], [("PKG-1", "returned", g["_MSG_PARTNER_RETURNED"])])

    def test_tai_lieu_huy_can_hai_vong(self):
        w, g = self._run("document_dead:cancelled", not_ready=("document_dead:cancelled",))
        self.assertEqual(w["reported"], [])
        w, g = self._run("document_dead:cancelled",
                         not_ready=("document_dead:cancelled", "document_dead:processing"))
        self.assertEqual(w["reported"], [("PKG-1", "destroyed", g["_MSG_DOC_DEAD"])])

    def test_khong_bao_duoc_thi_bao_nguoi(self):
        for kw in ({"handler": False}, {"failures": 5}):
            w, g = self._run("document_dead:cancelled", not_ready=("document_dead:x",) * 2, **kw)
            self.assertEqual(w["reported"], [])
            self.assertEqual(w["stalled"], [("PKG-1", 0, "document_dead:cancelled")])

    def test_da_bao_ket_thuc_thi_bo_qua(self):
        w, g = self._run("partner_rejected", closed=True,
                         not_ready=("partner_rejected", "partner_rejected"))
        self.assertEqual((w["reported"], w["stalled"]), ([], []))

    def test_ly_do_khac_van_bao_treo(self):
        self.assertEqual(self._run("no_signers_on_document")[0]["stalled"],
                         [("PKG-1", None, None)])


# =============================================================================== 6. token
class TestToken(unittest.TestCase):
    def _f(self, allow):
        def gv(dt, n, f=None, **k):
            return "P" if f == "profile" else allow
        g = {"frappe": _fk(db=types.SimpleNamespace(get_value=gv)),
             "needs_own_token": lambda u, s: True}
        exec(compile(_fns(_read("user_link.py"), ["signer_token_needed",
                                                  "_profile_allows_external"]), "u", "exec"), g)
        return g["signer_token_needed"]

    def test_approve_chi_khi_co_doi_tac(self):
        d = _D(actor_type="Approval Level", action="Approve", approver="ceo@ec", package="PKG")
        self.assertIsNone(self._f(0)(d, None), "DNTT: buoc duyet van tai khoan tich hop")
        self.assertEqual(self._f(1)(d, None), "ceo@ec")

    def test_sign_khong_doi(self):
        d = _D(actor_type="Approval Level", action="Sign", approver="kt@ec", package="PKG")
        self.assertEqual(self._f(0)(d, None), "kt@ec")

    def test_service_chot_ket_noi_approve_theo_ho_so(self):
        src = _read("service.py")
        self.assertIn('elif action == "Approve" and int(profile.get("allow_external_signers")'
                      ' or 0):', src)


if __name__ == "__main__":
    unittest.main()
