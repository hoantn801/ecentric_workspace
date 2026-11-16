# Copyright (c) 2026, eCentric and contributors
"""Khong tu tao tai lieu bang tai khoan tich hop khi nguoi de nghi DA ky (16/11/2026, 00675).

Su co: lan tao lai tai lieu 03:57 bi CMC chan (het han muc) -> goi trong ma tai lieu. 09:22 cap 1
bam duyet -> tasks._ensure_provider_document (nhanh "lazy") TAO tai lieu bang tai khoan tich hop.
eContract giao buoc nguoi de nghi cho TAI KHOAN TAO -> chu ky nguoi de nghi (da ky tren ERP 13/11)
khong vao duoc (400 "khong co quyen"), lenh cap 1 roi vao im lang (Manual Review).

  1. _ensure_provider_document: chan KHONG phai nguoi de nghi + chan nguoi de nghi cua goi DA ky
     -> ProviderError provider_document_missing_after_requester (khong tao). Chan nguoi de nghi,
     hoac goi chua co chan nguoi de nghi ky (ho so khong can nguoi de nghi ky) -> nhu cu.
  2. process_signing_request: loi do -> Manual Review (khong Permanent Failure: sau khi tao lai
     tai lieu dung cach, "Gui lai co kiem" chay duoc), co ToDo cho ops.
  3. scts adapter: identity co creator_email (de nhan ra tai lieu tao nham tai khoan).
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

CODE = "provider_document_missing_after_requester"


class _D(dict):
    __getattr__ = dict.get


def _mod(requester_done):
    m = _tasks()
    pkg = types.SimpleNamespace(name="PKG-1", scts_document_id=None, error_code=None,
                                status="Active")
    m._fk.get_doc = lambda dt, name: pkg
    m.exists_calls = []

    def exists(dt, filters=None, *a, **k):
        m.exists_calls.append((dt, filters))
        return requester_done
    m._fk.db.exists = exists
    return m


class TestGuard(unittest.TestCase):
    def _call(self, m, actor_type):
        dsr = _D(name="DSR-X", package="PKG-1", actor_type=actor_type)
        with self.assertRaises(_PErr) as cm:
            m._ensure_provider_document(dsr, {"allow_document_creation": 0}, object())
        return cm.exception

    def test_cap_duyet_khi_nguoi_de_nghi_da_ky_thi_khong_tao(self):
        m = _mod(True)
        e = self._call(m, "Approval Level")
        self.assertEqual(e.code, CODE)
        self.assertFalse(e.retryable)
        dt, f = m.exists_calls[0]
        self.assertEqual(dt, "EC Digital Signature Request")
        self.assertEqual((f["package"], f["actor_type"]), ("PKG-1", "Requester"))
        self.assertEqual(sorted(f["status"][1]), ["Approval Completed", "Signed"])
        self.assertEqual(m._fk.set_values, [], "khong ghi gi")
        self.assertEqual(m._ev.calls, [], "khong ProviderSubmitted")

    def test_chan_nguoi_de_nghi_thi_nhu_cu(self):
        e = self._call(_mod(True), "Requester")
        self.assertEqual(e.code, "document_creation_gated")

    def test_ho_so_khong_co_nguoi_de_nghi_ky_thi_nhu_cu(self):
        # Ho so khong bat nguoi de nghi ky: cap 1 tao tai lieu (lazy) la duong dung, giu nguyen.
        e = self._call(_mod(False), "Approval Level")
        self.assertEqual(e.code, "document_creation_gated")


class TestWorkerManualReview(unittest.TestCase):
    def _run(self, code, retryable=False):
        m = _tasks()
        dsr = _D(name="DSR-X", package="PKG-1", actor_type="Approval Level", status="Queued",
                 action="Sign", provider="SCTS", environment="Production")
        m._fk.db.get_value = lambda *a, **k: dsr
        m._settings_and_adapter = lambda d: ({}, object())
        m.binding = types.SimpleNamespace(assert_outbound_binding=lambda *a, **k: None,
                                          BindingError=type("BindingError", (Exception,), {}))
        stopped = []
        m._leg_stopped = lambda *a, **k: stopped.append(a[0])

        def boom(*a, **k):
            raise _PErr(code, "x", retryable=retryable)
        m._ensure_provider_document = boom
        ul = types.ModuleType("user_link")
        ul.needs_own_token = lambda *a, **k: False
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
        return m, sets, stopped

    def test_loi_nay_vao_manual_review_co_todo(self):
        m, sets, stopped = self._run(CODE)
        self.assertEqual(len(sets), 1)
        self.assertEqual(sets[0][2], "Manual Review")
        self.assertEqual(sets[0][3]["extra_fields"]["manual_review_reason"], CODE)
        self.assertEqual(m._fk.todos, ["DSR-X"])
        self.assertEqual(stopped, ["DSR-X"])

    def test_loi_khac_khong_doi(self):
        m, sets, stopped = self._run("scts_create_rejected_400")
        self.assertEqual(sets[0][2], "Permanent Failure")


class TestAdapterCreator(unittest.TestCase):
    def test_identity_co_creator_email(self):
        with io.open(os.path.join(_ESIGN, "providers", "scts.py"), encoding="utf-8") as fh:
            src = fh.read()
        self.assertIn('"creator_email": raw.get("creatorEmail")', src)


if __name__ == "__main__":
    unittest.main()
