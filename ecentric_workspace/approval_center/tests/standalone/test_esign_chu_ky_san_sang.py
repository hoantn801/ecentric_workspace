# Copyright (c) 2026, eCentric and contributors
"""Chu ky CMC phai KY DUOC tu ERP truoc khi tao chan ky (19/11/2026, vu thu.nguyen2).

Anh xa tro vao chu ky khong con tren cong + chu ky moi chua co HSM -> cong nhan lenh roi im, phieu
treo "Dang doi soat". user_link.assert_signature_ready chan som voi cau bao ro:
  * ma chu ky khong con tren cong -> chan;  * chu ky tat -> chan;
  * khong HSM / sign_token=1 (ky tay OfficeSignTool) -> chan;
  * cong loi -> KHONG chan (ghi log);  thieu anh xa -> de chot khac bao;
  * adapter khong khai has_hsm (mock) -> khong chan vi ly do HSM.
Goi o requester (Gui & Ky) va service.approve_and_sign (chan Sign), SAU chot ket noi.
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


class PE(Exception):
    def __init__(self, code, message="", retryable=False, ambiguous=False):
        super().__init__(message)
        self.code = code


class _Throw(Exception):
    pass


def _load(mapping, sigs=None, fail=False):
    logs = []
    fk = types.ModuleType("frappe")
    fk._ = lambda s: s
    fk.throw = lambda m, *a, **k: (_ for _ in ()).throw(_Throw(m))
    fk.log_error = lambda *a, **k: logs.append(a)
    fk.get_traceback = lambda: ""
    fu = types.ModuleType("frappe.utils")
    fu.add_to_date = fu.get_datetime = fu.now_datetime = lambda *a, **k: None
    fp = types.ModuleType("frappe.utils.password")
    fp.get_decrypted_password = lambda *a, **k: None
    ev = types.ModuleType("ev")
    pm = types.ModuleType("pm")
    pm.verified_mapping = lambda user, env: mapping
    pv = types.ModuleType("pv")

    class A(object):
        def list_user_signatures(self, uid):
            if fail:
                raise PE("scts_network_error")
            return sigs
    pv.get_adapter = lambda s: A()
    pb = types.ModuleType("pb")
    pb.ProviderError = PE
    mods = {"frappe": fk, "frappe.utils": fu, "frappe.utils.password": fp,
            "ecentric_workspace.platform.esign.events": ev,
            "ecentric_workspace.platform.esign.permissions": pm,
            "ecentric_workspace.platform.esign.providers": pv,
            "ecentric_workspace.platform.esign.providers.base": pb}
    saved = {k: sys.modules.get(k) for k in mods}
    sys.modules.update(mods)
    try:
        m = types.ModuleType("_user_link_ready")
        exec(compile(_read("user_link.py"), "user_link.py", "exec"), m.__dict__)
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
    m._logs = logs
    return m


MAP = {"scts_user_id": "U-1", "signature_id": "S-NEW"}


def _sig(**k):
    d = {"id": "S-NEW", "signerId": "U-1", "active": True, "has_hsm": True, "sign_token": None}
    d.update(k)
    return d


class TestReady(unittest.TestCase):
    def call(self, mapping=MAP, sigs=None, fail=False):
        m = _load(mapping, sigs if sigs is not None else [_sig()], fail)
        return m, m.assert_signature_ready("thu@x", {}, "UAT")

    def test_san_sang(self):
        m, r = self.call()
        self.assertEqual(r["id"], "S-NEW")

    def test_ma_chu_ky_cu_thi_chan(self):
        with self.assertRaises(_Throw) as cm:
            self.call(sigs=[_sig(id="S-OTHER")])
        self.assertIn("đã thay đổi", str(cm.exception))

    def test_chu_ky_tat_thi_chan(self):
        with self.assertRaises(_Throw):
            self.call(sigs=[_sig(active=False)])

    def test_khong_hsm_hoac_ky_tay_thi_chan(self):
        for k in ({"has_hsm": False}, {"sign_token": 1}):
            with self.assertRaises(_Throw) as cm:
                self.call(sigs=[_sig(**k)])
            self.assertIn("HSM", str(cm.exception), k)

    def test_mock_khong_khai_hsm_thi_khong_chan(self):
        s = _sig()
        del s["has_hsm"]
        m, r = self.call(sigs=[s])
        self.assertEqual(r["id"], "S-NEW")

    def test_cong_loi_thi_khong_chan_co_log(self):
        m, r = self.call(fail=True)
        self.assertIsNone(r)
        self.assertEqual(len(m._logs), 1)

    def test_thieu_anh_xa_de_chot_khac(self):
        m, r = self.call(mapping=None)
        self.assertIsNone(r)


class TestWiring(unittest.TestCase):
    def test_requester_goi_sau_chot_ket_noi(self):
        src = _read("requester.py")
        a = src.index("user_link.assert_requester_linked(requester, st, prof.environment)")
        b = src.index("user_link.assert_signature_ready(requester, st, prof.environment)")
        self.assertLess(a, b)
        self.assertLess(b, src.index("pkgsvc.signable_package_for_request(ar)", a))

    def test_service_goi_cho_chan_ky_truoc_khi_xep_hang(self):
        src = _read("service.py")
        i = src.index("def approve_and_sign(")
        body = src[i:src.index("\ndef ", i + 10)]
        b = body.index("user_link.assert_signature_ready(actor, settings, profile.environment)")
        self.assertIn('if action == "Sign":', body[b - 600:b])
        self.assertLess(b, body.index("frappe.enqueue("))


if __name__ == "__main__":
    unittest.main()
