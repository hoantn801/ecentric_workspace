# Copyright (c) 2026, eCentric and contributors
"""CMC het han muc tai lieu (16/11/2026).

CMC tra AddDocument HTTP 500 kem {"success": false, "message": "Loi he thong: Da vuot han muc
su dung 32 luot. Da su dung 1132/1100 luot. ..."}. Truoc ban nay moi 5xx = ket qua MO HO ->
goi bi gan moc create_outcome_unknown -> phai doi soat tay tung phieu. Han muc bi chan TRUOC
khi tao (thu tren cong: payload thieu tep van nhan dung cau nay), nen:

  1. scts_client: 500 + JSON success=false + message co dau hieu han muc -> ProviderError
     scts_create_quota_exceeded, retryable, KHONG ambiguous. Moi 5xx khac giu nguyen mo ho.
  2. ui_state: co cau bao tieng Viet cho ma loi nay.
  3. tasks.poll_pending: chan Retryable Failure vi han muc KHONG tinh vao tran
     max_poll_attempts, thu lai moi QUOTA_RETRY_MINUTES phut. Loi khac giu tran nhu cu.
"""
import datetime
import importlib.util
import io
import os
import sys
import types
import unicodedata
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_APP = os.path.abspath(os.path.join(_HERE, "..", "..", "..", ".."))
_ESIGN = os.path.join(_APP, "ecentric_workspace", "platform", "esign")
sys.path.insert(0, _HERE)
from test_provider_document_dead import _tasks            # noqa: E402  (loader code THAT)

QUOTA_MSG = (u"Lỗi hệ thống: Đã vượt hạn mức "
             u"sử dụng 32 lượt. Đã sử dụng 1132/1100 "
             u"lượt. Vui lòng liên hệ đơn vị cung cấp "
             u"dịch vụ để được gia hạn.")


def _client_mod():
    spec = importlib.util.spec_from_file_location(
        "_scts_client_han_muc", os.path.join(_ESIGN, "providers", "scts_client.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class _Resp(object):
    def __init__(self, status, body):
        self.status_code = status
        self._body = body
        self.text = body if isinstance(body, str) else ""

    def json(self):
        if isinstance(self._body, str):
            raise ValueError("not json")
        return self._body


class TestClientHanMuc(unittest.TestCase):
    def _add(self, status, body):
        m = _client_mod()
        calls = []

        def transport(method, url, headers=None, json_body=None, timeout=None, verify_tls=True):
            calls.append(url)
            return _Resp(status, body)
        c = m.SctsClient("https://x.example", transport=transport, sleeper=lambda s: None)
        try:
            c.add_document({"docCode": "X"}, "tok")
        except Exception as e:  # ProviderError (lop nap rieng - so bang thuoc tinh)
            self.assertEqual(len(calls), 1, "AddDocument khong bao gio thu lai trong client")
            return e
        self.fail("phai raise")

    def test_han_muc_la_tu_choi_chac_chan_thu_lai_duoc(self):
        e = self._add(500, {"success": False, "message": QUOTA_MSG, "data": None, "errors": None})
        self.assertEqual(e.code, "scts_create_quota_exceeded")
        self.assertTrue(e.retryable)
        self.assertFalse(e.ambiguous, "han muc KHONG duoc gan moc mo ho")
        self.assertIn("1132/1100", e.message)

    def test_dang_NFD_van_nhan_ra(self):
        e = self._add(500, {"success": False, "message": unicodedata.normalize("NFD", QUOTA_MSG)})
        self.assertEqual(e.code, "scts_create_quota_exceeded")

    def test_khong_dau_van_nhan_ra(self):
        e = self._add(500, {"success": False, "message": "Da vuot han muc su dung"})
        self.assertEqual(e.code, "scts_create_quota_exceeded")

    def test_500_khac_giu_mo_ho(self):
        e = self._add(500, {"success": False, "message": "Loi he thong: Object reference not set"})
        self.assertEqual(e.code, "scts_create_outcome_unknown")
        self.assertTrue(e.ambiguous)
        self.assertFalse(e.retryable)

    def test_500_khong_phai_json_giu_mo_ho(self):
        e = self._add(502, "<html>Bad gateway</html>")
        self.assertEqual(e.code, "scts_create_outcome_unknown")
        self.assertTrue(e.ambiguous)

    def test_success_khong_phai_false_giu_mo_ho(self):
        # Khong chac la cau tu choi cua ung dung -> khong doan, giu mo ho.
        e = self._add(500, {"message": QUOTA_MSG})
        self.assertTrue(e.ambiguous)
        e = self._add(500, {"success": True, "message": QUOTA_MSG})
        self.assertTrue(e.ambiguous)

    def test_4xx_khong_doi(self):
        e = self._add(400, {"success": False, "message": QUOTA_MSG})
        self.assertEqual(e.code, "scts_create_rejected_400")


class TestUiState(unittest.TestCase):
    def test_co_cau_bao(self):
        with io.open(os.path.join(_ESIGN, "ui_state.py"), encoding="utf-8") as fh:
            src = fh.read()
        self.assertIn('"scts_create_quota_exceeded":', src)
        self.assertIn(u"hết hạn mức", src)


class _Row(dict):
    __getattr__ = dict.get


NOW = datetime.datetime(2026, 11, 16, 9, 0, 0)


class TestPollPending(unittest.TestCase):
    def _mod(self, rows, polls=0, cap=30):
        m = _tasks()
        m._disabled = lambda: False
        m._integration_open = lambda *a, **k: True
        m.now_datetime = lambda: NOW
        m.add_to_date = lambda dt, minutes=0, **k: dt + datetime.timedelta(minutes=minutes)
        m.processed = []
        m.process_signing_request = lambda name: m.processed.append(name)
        m._leg_stopped = lambda *a, **k: None
        m._fk.get_all = lambda *a, **k: [_Row(r) for r in rows]
        m._fk.db.get_value = lambda *a, **k: cap
        m._fk.db.count = lambda *a, **k: polls
        m.commits = []
        m._fk.db.commit = lambda: m.commits.append(1)
        return m

    def _rf(self, code, minutes_ago):
        return {"name": "DSR-1", "status": "Retryable Failure", "provider": "SCTS",
                "environment": "Production", "request_attempt": 1, "error_code": code,
                "modified": NOW - datetime.timedelta(minutes=minutes_ago)}

    def _sets(self, m):
        return [c for c in m._ev.calls if c[0] == "set"]

    def test_han_muc_moi_hong_thi_cho(self):
        m = self._mod([self._rf("scts_create_quota_exceeded", 3)])
        m.poll_pending()
        self.assertEqual(m.processed, [])
        self.assertEqual(self._sets(m), [])

    def test_han_muc_du_10_phut_thi_thu_lai_khong_tinh_tran(self):
        m = self._mod([self._rf("scts_create_quota_exceeded", 11)], polls=999, cap=30)
        m.poll_pending()
        self.assertEqual(m.processed, ["DSR-1"])
        sets = self._sets(m)
        self.assertEqual([s[2] for s in sets], ["Queued"], "khong duoc sang Manual Review vi tran")
        self.assertEqual(m._fk.todos, [])
        self.assertEqual(m.commits, [1], "van chot (commit) sau chan nay nhu moi chan khac")

    def test_loi_khac_van_tinh_tran(self):
        m = self._mod([self._rf("scts_network_error", 11)], polls=30, cap=30)
        m.poll_pending()
        self.assertEqual(m.processed, [])
        sets = self._sets(m)
        self.assertEqual(sets[0][2], "Manual Review")
        self.assertEqual(sets[0][3]["extra_fields"]["manual_review_reason"],
                         "max_poll_attempts_exceeded")

    def test_loi_khac_duoi_tran_thu_lai_nhu_cu(self):
        m = self._mod([self._rf("scts_network_error", 0)], polls=2, cap=30)
        m.poll_pending()
        self.assertEqual(m.processed, ["DSR-1"])
        self.assertEqual(self._sets(m)[0][2], "Queued")


if __name__ == "__main__":
    unittest.main()
