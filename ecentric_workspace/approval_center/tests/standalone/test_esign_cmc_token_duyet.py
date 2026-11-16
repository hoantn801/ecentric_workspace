# Copyright (c) 2026, eCentric and contributors
"""Nguoi duyet ky bang TOKEN CUA CHINH HO (16/11/2026, chuyen SCTS -> CMC).

Do tren prod 16/11: CMC chi NHUNG chu ky so vao PDF khi nguoi gui lenh chinh la nguoi ky.
Tai khoan tich hop ky thay nguoi duyet (userId + chu ky cua ho) -> cong chuyen buoc, ghi
"Da ky", nhung PDF khong co chu ky (00672: 5 dong "Da ky", PDF 2 chu ky so; 00676: Hoan - chinh
la tai khoan tich hop - ky cap 1 thi PDF CO chu ky).

  1. user_link.signer_token_needed: chan KY cua nguoi de nghi / nguoi duyet -> chinh ho; tai
     khoan tich hop tu ky -> None; buoc duyet KHONG ky (Approve) -> None.
  2. tasks.process_signing_request: chan duyet dung token nguoi duyet; khong co token ->
     signer_not_linked (khong ky thay); chan dang doi soat thi doc bang tai khoan tich hop.
  3. service.approve_and_sign: chot assert_signer_linked truoc khi xep hang (chi action Sign).
  4. signed_files: PDF ky thieu chu ky so so voi so o ky -> VerificationMismatch + ToDo, van luu.
"""
import io
import os
import sys
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_APP = os.path.abspath(os.path.join(_HERE, "..", "..", "..", ".."))
_ESIGN = os.path.join(_APP, "ecentric_workspace", "platform", "esign")
sys.path.insert(0, _HERE)
from test_provider_document_dead import _tasks, _PErr     # noqa: E402  (loader code THAT)


def _read(*p):
    with io.open(os.path.join(_ESIGN, *p), encoding="utf-8") as fh:
        return fh.read()


class _D(dict):
    __getattr__ = dict.get


def _exec_with(src_name, mods):
    saved = {k: sys.modules.get(k) for k in mods}
    sys.modules.update(mods)
    try:
        m = types.ModuleType("_m_" + src_name.replace(".", "_"))
        exec(compile(_read(src_name), src_name, "exec"), m.__dict__)
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
    return m


def _user_link():
    fk = types.ModuleType("frappe")
    fk._ = lambda s: s
    fu = types.ModuleType("frappe.utils")
    fu.add_to_date = fu.get_datetime = fu.now_datetime = lambda *a, **k: None
    fp = types.ModuleType("frappe.utils.password")
    fp.get_decrypted_password = lambda *a, **k: None
    ev = types.ModuleType("ev")
    pm = types.ModuleType("pm")
    pm.verified_mapping = lambda *a, **k: None
    pv = types.ModuleType("pv")
    pv.get_adapter = lambda s: None
    pb = types.ModuleType("pb")
    pb.ProviderError = _PErr
    return _exec_with("user_link.py", {
        "frappe": fk, "frappe.utils": fu, "frappe.utils.password": fp,
        "ecentric_workspace.platform.esign.events": ev,
        "ecentric_workspace.platform.esign.permissions": pm,
        "ecentric_workspace.platform.esign.providers": pv,
        "ecentric_workspace.platform.esign.providers.base": pb})


S = {"username": "hoan@x"}


class TestSignerTokenNeeded(unittest.TestCase):
    def test_quy_tac(self):
        ul = _user_link()
        f = ul.signer_token_needed
        self.assertEqual(f(_D(actor_type="Requester", actor_user="huong@x", action="Sign"), S),
                         "huong@x")
        self.assertEqual(f(_D(actor_type="Approval Level", approver="lam@x", action="Sign"), S),
                         "lam@x", "nguoi duyet ky bang token rieng")
        self.assertIsNone(f(_D(actor_type="Approval Level", approver="Hoan@X ", action="Sign"),
                            S), "tai khoan tich hop tu ky")
        self.assertIsNone(f(_D(actor_type="Approval Level", approver="lam@x", action="Approve"),
                            S), "buoc duyet KHONG ky giu tai khoan tich hop")
        self.assertIsNone(f(_D(actor_type="Approval Level", approver=None, action="Sign"), S))


class _Adapter(object):
    def __init__(self):
        self.token = None

    def use_user_token(self, tok):
        self.token = tok
        return self


class TestWorker(unittest.TestCase):
    def _run(self, dsr, tokens):
        m = _tasks()
        m._fk.db.get_value = lambda *a, **k: dsr
        ad = _Adapter()
        m._settings_and_adapter = lambda d: (dict(S), ad)
        m.binding = types.SimpleNamespace(assert_outbound_binding=lambda *a, **k: None,
                                          BindingError=type("BE", (Exception,), {}))
        m._leg_stopped = lambda *a, **k: None
        seen = {}

        def stop(d, settings, adapter):
            seen["token"] = adapter.token
            raise _PErr("stop_here", "x", retryable=False)
        m._ensure_provider_document = stop
        ul = _user_link()
        ul.token_for = lambda user, env: tokens.get(user)
        pkgmod = types.ModuleType("ecentric_workspace.platform.esign")
        pkgmod.user_link = ul
        saved = sys.modules.get("ecentric_workspace.platform.esign")
        sys.modules["ecentric_workspace.platform.esign"] = pkgmod
        try:
            m.process_signing_request("DSR-X")
        finally:
            if saved is None:
                sys.modules.pop("ecentric_workspace.platform.esign", None)
            else:
                sys.modules["ecentric_workspace.platform.esign"] = saved
        sets = [c for c in m._ev.calls if c[0] == "set"]
        return seen, sets, m

    def _dsr(self, **k):
        d = _D(name="DSR-X", package="PKG-1", actor_type="Approval Level", approver="lam@x",
               action="Sign", status="Queued", environment="Production", provider="SCTS")
        d.update(k)
        return d

    def test_nguoi_duyet_dung_token_rieng(self):
        seen, sets, m = self._run(self._dsr(), {"lam@x": "T-LAM"})
        self.assertEqual(seen["token"], "T-LAM")

    def test_nguoi_duyet_khong_co_token_thi_khong_ky_thay(self):
        seen, sets, m = self._run(self._dsr(), {})
        self.assertNotIn("token", seen, "dung truoc moi lenh ghi")
        self.assertEqual(sets[0][2], "Permanent Failure")
        self.assertEqual(sets[0][3]["extra_fields"]["error_code"], "signer_not_linked")

    def test_tai_khoan_tich_hop_tu_ky(self):
        seen, sets, m = self._run(self._dsr(approver="hoan@x"), {})
        self.assertIsNone(seen["token"])

    def test_nguoi_de_nghi_nhu_cu(self):
        seen, sets, m = self._run(self._dsr(actor_type="Requester", actor_user="huong@x",
                                            approver="huong@x"), {})
        self.assertEqual(sets[0][3]["extra_fields"]["error_code"], "requester_not_linked")

    def test_dang_doi_soat_ma_mat_token_thi_doc_bang_tich_hop(self):
        # Provider Accepted: chi doc. Khong co token -> khong nem, doc bang tai khoan tich hop.
        seen, sets, m = self._run(self._dsr(status="Provider Accepted"), {})
        self.assertIsNone(seen["token"])

    def test_dang_doi_soat_co_token_van_doc_bang_tich_hop(self):
        # QC 16/11: token nguoi duyet bi CMC thu hoi giua chung -> scts_user_token_rejected (khong
        # retry) -> Permanent Failure tren chan co the da ky. Chan da gui: doc bang tich hop.
        for st in ("Provider Accepted", "Verifying"):
            seen, sets, m = self._run(self._dsr(status=st), {"lam@x": "T-LAM"})
            self.assertIsNone(seen["token"], st)

    def test_nguoi_de_nghi_dang_doi_soat_giu_nhu_cu(self):
        seen, sets, m = self._run(self._dsr(actor_type="Requester", actor_user="huong@x",
                                            approver="huong@x", status="Verifying"),
                                  {"huong@x": "T-H"})
        self.assertEqual(seen["token"], "T-H")

    def test_handover_ghi_auth_as(self):
        self.assertEqual(_read("tasks.py").count('"auth_as": own_user'), 3,
                         "HandoverTargeted + 2 HandoverPoolFallback")


class TestServicePrecheck(unittest.TestCase):
    def test_chot_truoc_khi_xep_hang(self):
        src = _read("service.py")
        i = src.index("def approve_and_sign(")
        body = src[i:src.index("\ndef ", i + 10)]
        a = body.index("user_link.assert_signer_linked(actor, settings, profile.environment)")
        self.assertIn('if action == "Sign":', body[a - 400:a])
        self.assertLess(a, body.index("frappe.enqueue("), "chot TRUOC khi xep hang")


class TestSignedPdfCount(unittest.TestCase):
    def _mod(self, placements, legs=None, source_sigs=0):
        fk = types.ModuleType("frappe")
        legs = legs if legs is not None else [{"actor_type": "Requester", "request_level": None},
                                              {"actor_type": "Approval Level",
                                               "request_level": "RL-1"}]

        def get_all(dt, filters=None, **k):
            if dt == "EC Digital Signature Request":
                return [_D(x) for x in legs]
            return [_D(x) for x in placements
                    if x["signature_file"] == filters.get("signature_file")]
        fk.get_all = get_all
        fk.db = types.SimpleNamespace(get_value=lambda dt, n, f=None, **k: {"RL-1": 1,
                                                                             "RL-2": 2}.get(n))

        class _F(object):
            def get_content(self):
                return b"%PDF " + b"/ByteRange " * source_sigs
        fk.get_doc = lambda dt, name: _F()
        fk.log_error = lambda *a, **k: None
        fk.get_traceback = lambda: ""
        fu = types.ModuleType("frappe.utils")
        fu.now_datetime = lambda: None
        st = types.ModuleType("st")
        st.DSR_TERMINAL = ()
        ev = types.ModuleType("ev")
        ev.calls = []
        ev.emit = lambda et, **k: ev.calls.append((et, k))
        pv = types.ModuleType("pv")
        pv.get_adapter = lambda s: None
        pb = types.ModuleType("pb")
        pb.ProviderError = _PErr
        sa = types.ModuleType("sa")
        sa.safe_error = str
        m = _exec_with("signed_files.py", {
            "frappe": fk, "frappe.utils": fu,
            "ecentric_workspace.platform.esign.state": st,
            "ecentric_workspace.platform.esign.events": ev,
            "ecentric_workspace.platform.esign.providers": pv,
            "ecentric_workspace.platform.esign.providers.base": pb,
            "ecentric_workspace.platform.esign.sanitize": sa})
        m.todos = []
        m._dead_letter_review = lambda pkg, reason: m.todos.append(reason)
        m._ev = ev
        return m

    PL = [{"signature_file": "F1", "status": "Placed", "level_no": 0},
          {"signature_file": "F1", "status": "Placed", "level_no": 1},
          {"signature_file": "F1", "status": "Placed", "level_no": 2},   # cap 2 bo qua
          {"signature_file": "F1", "status": "Invalid", "level_no": 1},
          {"signature_file": "F2", "status": "x", "level_no": 0}]

    def test_thieu_chu_ky_thi_bao(self):
        m = self._mod(self.PL)
        have, want = m._check_embedded_signatures(_D(name="PKG-1"),
                                                  _D(name="F1", file="S", file_name="a"),
                                                  b"%PDF /ByteRange")
        self.assertEqual((have, want), (1, 2), "chi dem cap DA KY (0, 1); cap 2 khong")
        self.assertEqual(m._ev.calls[0][0], "VerificationMismatch")
        self.assertEqual(m._ev.calls[0][1]["verification_result"],
                         "signed_pdf_signatures_missing:1/2")
        self.assertEqual(len(m.todos), 1)

    def test_du_thi_im(self):
        m = self._mod(self.PL)
        m._check_embedded_signatures(_D(name="PKG-1"), _D(name="F1", file="S", file_name="a"),
                                     b"/ByteRange" * 2)
        self.assertEqual((m._ev.calls, m.todos), ([], []))

    def test_tep_goc_co_san_chu_ky_thi_tru(self):
        m = self._mod(self.PL, source_sigs=1)
        have, want = m._check_embedded_signatures(_D(name="PKG-1"),
                                                  _D(name="F1", file="S", file_name="a"),
                                                  b"/ByteRange" * 2)
        self.assertEqual((have, want), (1, 2))
        self.assertEqual(len(m.todos), 1)

    def test_loi_khong_chan_luong_tai(self):
        m = self._mod(self.PL)

        def boom(*a, **k):
            raise RuntimeError("db")
        m.frappe.get_all = boom
        self.assertEqual(m._check_embedded_signatures(_D(name="P"), _D(name="F1"), b""),
                         (None, None))

    def _retrieve_mod(self, dsf_rows, doc_files):
        m = self._mod([])
        ad = types.SimpleNamespace(poll_status=lambda d: types.SimpleNamespace(files=doc_files))
        m._settings_and_adapter = lambda pkg: ({}, ad)
        m._terminal_signed_ok = lambda a, p: (True, "ok")
        rows = [_D(x) for x in dsf_rows]
        m.frappe.get_all = lambda dt, **k: rows
        m.frappe.db = types.SimpleNamespace(
            get_value=lambda *a, **k: _D(name="PKG-1", scts_document_id="DOC-NEW",
                                         business_doctype="X", business_name="Y"),
            set_value=lambda *a, **k: m.writes.append(a))
        m.writes, m.seen = [], []
        m._retrieve_one = lambda pkg, adapter, f, force=False: (
            m.seen.append((f.name, f.scts_document_file_id, f.get("stale_file_id"))) or
            {"stored": True})
        return m

    def test_ma_tep_cu_doi_theo_ten(self):
        m = self._retrieve_mod([{"name": "F1", "file_name": "a.pdf",
                                 "scts_document_file_id": "OLD"}],
                               [{"name": "a.pdf", "file_id": "NEW"}])
        m.retrieve_and_store_for_package("PKG-1")
        self.assertEqual(m.seen, [("F1", "NEW", None)])
        self.assertEqual(m._ev.calls[0][1]["request_meta"]["old_file_id"], "OLD")

    def test_ma_tep_cu_trung_ten_thi_khong_doan_khong_tai_bang_ma_cu(self):
        m = self._retrieve_mod([{"name": "F1", "file_name": "a.pdf",
                                 "scts_document_file_id": "OLD"}],
                               [{"name": "a.pdf", "file_id": "N1"},
                                {"name": "a.pdf", "file_id": "N2"}])
        m.retrieve_and_store_for_package("PKG-1")
        self.assertEqual(m.seen, [("F1", None, "OLD")])

    def test_ma_hop_le_giu_nguyen_ke_ca_khac_kieu(self):
        m = self._retrieve_mod([{"name": "F1", "file_name": "a.pdf",
                                 "scts_document_file_id": "7"}],
                               [{"name": "a.pdf", "file_id": 7}])
        m.retrieve_and_store_for_package("PKG-1")
        self.assertEqual(m.seen, [("F1", "7", None)])
        self.assertEqual(m.writes, [("EC Digital Signature Package", "PKG-1",
                                     "signed_bundle_complete", 1)])

    def test_duoc_goi_sau_khi_tai(self):
        src = _read("signed_files.py")
        i = src.index("def _retrieve_one(")
        body = src[i:src.index("\ndef ", i + 10)]
        self.assertIn('_check_embedded_signatures(pkg, f, res["content"])', body)


if __name__ == "__main__":
    unittest.main()
