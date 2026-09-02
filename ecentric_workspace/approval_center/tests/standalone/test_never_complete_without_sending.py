# Copyright (c) 2026, eCentric and contributors
"""A level must never close on a signature that belongs to a different leg.

2026-08-28 23:54, EC-DSR-2026-00023. The Direct Manager leg went

    Queued -> BindingValidated -> Verified -> ApprovalCompleted

in 1.4 seconds, with no ProviderAccepted anywhere: not one command reached the provider. The
level closed, the request moved on to Finance, and the document carried no manager signature
at all. Same family as UAT VOID 5.

Two independent holes lined up, and either one alone would have prevented it.

1. POLL-FIRST ran before sending. It answers "did a previous attempt already succeed?", which
   is only a meaningful question once something has been sent. On a brand-new leg it looked
   at the document, saw a signature by the right person, and finished.

2. The freshness window was wider than the gap between two legs. `signed_after` was
   `queued_at - 120s` (clock-skew tolerance). The requester signed at 23:53; this leg queued
   at 23:54:01, so the bar sat at 23:52:01 - and the requester's own signature, 40 seconds
   old, cleared it.

The signature that satisfies a leg must be NEWER than the last completed leg by the same
signer on the same package. The tolerance now only helps the first signature.
"""
import io
import os
import re
import unittest
from datetime import datetime, timedelta

_HERE = os.path.dirname(os.path.abspath(__file__))


def _src(*parts):
    root, tried = _HERE, []
    for _i in range(8):
        path = os.path.join(root, *parts)
        tried.append(path)
        if os.path.exists(path):
            return io.open(path, encoding="utf-8").read()
        parent = os.path.dirname(root)
        if parent == root:
            break
        root = parent
    raise AssertionError("khong tim thay %s" % parts[-1])


_TASKS = _src("platform", "esign", "tasks.py")
_SVC = _src("platform", "esign", "service.py")
_STATE_SRC = _src("platform", "esign", "state.py")


def _state():
    """Nap `state.py` that su.

    `exec(compile(...))` chu khong phai loader theo duong dan: loader dung lai
    `__pycache__`, va bo nho dem do chi bi coi la cu khi mtime HOAC kich thuoc doi - nen mot
    phep dot bien di chuyen khoi lenh se duoc cham tren ban .pyc cu va bao xanh gia.
    `state.py` khong import frappe nen nap truc tiep duoc.
    """
    import types
    mod = types.ModuleType("esign_state_under_test")
    exec(compile(_STATE_SRC, "state.py", "exec"), mod.__dict__)   # noqa: S102
    return mod


class _D(dict):
    """Frappe tra ve _dict: truy cap duoc CA bang thuoc tinh lan bang khoa.

    Code that doc `dsr.status` (thuoc tinh) VA `dsr.get("accepted_at")` (khoa) trong cung
    mot bieu thuc. Stub chi ho tro mot kieu se lam phep kiem no vi ly do cua chinh stub,
    khong phai vi code.
    """

    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError:
            raise AttributeError(k)


class TestPollFirstOnlyAfterSending(unittest.TestCase):
    def setUp(self):
        self.body = re.search(r"(?m)^def process_signing_request\(.*?(?=\n@|\ndef )",
                              _TASKS, re.S).group(0)

    def _load_gate(self, dsr):
        """Chay CHINH phep chan that, khong doc chuoi trong tasks.py.

        Truoc 02/09 ham nay cat bieu thuc `may_have_sent = (...)` ra khoi `tasks.py` bang
        regex roi `eval`. Khi phep chan duoc dua ve `state.may_have_sent` - de trang ops
        dung chung MOT dinh nghia voi worker - thi regex khong khop nua va ca sau phep kiem
        do vi "khong tim thay", chu khong phai vi hanh vi doi. Do la lop test-grep-nguon bi
        mu sau refactor.

        Doi lai: goi thang ham. Kem mot phep kiem rieng ben duoi rang worker THAT SU dung
        ham nay, de "goi thang ham" khong tro thanh kiem mot thu khong ai xai.
        """
        return _state().may_have_sent(dsr)

    def test_a_brand_new_leg_is_not_allowed_to_finish_by_looking(self):
        dsr = {"status": "Queued", "request_attempt": 1}
        self.assertFalse(self._load_gate(_D(dsr)),
                         "chan ky chua gui gi ma van hoan tat duoc bang cach nhin")

    def test_a_leg_the_provider_accepted_may_poll(self):
        self.assertTrue(self._load_gate(_D({"status": "Provider Accepted"})))

    def test_a_verifying_leg_may_poll(self):
        self.assertTrue(self._load_gate(_D({"status": "Verifying"})))

    def test_a_queued_retry_may_poll(self):
        # gui lan 1 that bai, xep hang lai -> co the lan 1 da toi noi
        self.assertTrue(self._load_gate(_D({"status": "Queued", "request_attempt": 2})))

    def test_an_accepted_at_stamp_alone_is_enough(self):
        self.assertTrue(self._load_gate(
            _D({"status": "Queued", "accepted_at": "2026-08-28 23:54:00"})))

    def test_a_transaction_id_alone_is_enough(self):
        self.assertTrue(self._load_gate(
            _D({"status": "Queued", "bulk_job_transaction_id": "abc"})))

    def test_the_refusal_is_recorded_not_silent(self):
        self.assertIn('"not_sent_yet"', self.body,
                      "khong duoc im lang bo qua - phai noi ro vi sao chua verify")

    def test_the_gate_is_evaluated_before_the_verify(self):
        self.assertLess(self.body.index("may_have_sent = "),
                        self.body.index("verify_signed_result(doc_state, expected)"))

    def test_the_worker_uses_THIS_function(self):
        """Chan cach cho phep kiem o tren.

        Cac phep kiem kia goi thang `state.may_have_sent`. Neu worker mot ngay nao do tu
        tinh lai phep chan bang tay thi ca sau van xanh trong khi worker chay theo mot luat
        khac - dung kieu lech ma ban sua nay sinh ra de cham dut.
        """
        self.assertIn("sm.may_have_sent(dsr)", self.body,
                      "worker phai dung CHUNG dinh nghia voi trang ops, khong tu tinh lai")


class TestManualReviewNoiRoViSao(unittest.TestCase):
    """Roi Manual Review sau POLL-FIRST ma khong ghi ly do verify = nguoi truc phai doan.

    02/09 23:40 su kien ManualReview trong ron, phai suy luan ra cua so thoi gian bi Thu lai
    day len sau chu ky. `vr.reason` co san ngay do, chi la khong ai ghi no lai.
    """

    def test_nhanh_may_have_sent_ghi_verification_result(self):
        src = _src("platform", "esign", "tasks.py")
        i = src.find('"prior_bulk_submit_uncertain"')
        self.assertNotEqual(i, -1, "nhanh Manual Review sau poll-first khong con")
        doan = src[max(0, i - 400):i]
        self.assertIn("verification_result=vr.reason", doan,
                      "ly do verify tu choi bi vut - su kien ManualReview se trong ron")


class TestOrdinalBeatsThePreviousLeg(unittest.TestCase):
    """Chan thu N cua mot nguoi doi chu ky thu N+1 cua nguoi do - dem, khong so gio.

    Truoc 02/09 cho nay la mot SAN THOI GIAN (`_last_completed_leg_time`): chu ky phai moi
    hon luc chan truoc cua cung nguoi hoan tat. Dung y, hong voi du lieu that: eContract tra
    `signed_at` chi toi PHUT. 02/09 23:06 mot nguoi trinh ky roi duyet cap 1 trong cung mot
    phut, ca hai chu ky doc thanh 23:06:00, deu "cu hon" san 23:06:2x, chan duyet quay
    `signature_predates_request` toi Manual Review. Dem thi khong can phan biet hai chu ky
    cung phut, ma loi 28/08 (cap duyet dong bang chu ky trinh ky) van bi chan: khi do chi co
    MOT chu ky, chan doi cai thu HAI.
    """

    def _load(self, count):
        body = re.search(r"(?m)^def _completed_legs_of_same_signer\(.*?(?=\ndef )", _SVC, re.S)
        self.assertIsNotNone(body, "ham dem chan da hoan tat cua cung nguoi khong con")

        class _DB(object):
            @staticmethod
            def count(dt, filters):
                if isinstance(count, Exception):
                    raise count
                _DB.last_filters = filters
                return count

        class _Frappe(object):
            db = _DB()

        g = {"frappe": _Frappe()}
        exec(compile(body.group(0), "lc", "exec"), g)
        self._db = _DB
        return g["_completed_legs_of_same_signer"]

    _DSR = {"package": "PKG-1", "effective_scts_user_id": "U1", "name": "DSR-2"}

    def test_it_counts_prior_legs(self):
        self.assertEqual(self._load(2)(_D(self._DSR)), 2)

    def test_no_prior_leg_is_ZERO_not_None(self):
        """0 va None khac han nhau: 0 = 'chu ky dau tien cua nguoi nay la du'."""
        self.assertEqual(self._load(0)(_D(self._DSR)), 0)

    def test_a_read_failure_is_None_not_zero(self):
        """None = 'khong biet' -> giu duong cu. Tra 0 thi chan thu hai chap nhan chu ky
        cua chan thu nhat - dung lop loi UAT VOID 5."""
        self.assertIsNone(self._load(RuntimeError("db"))(_D(self._DSR)))

    def test_it_never_looks_at_a_different_signer_or_package(self):
        self._load(0)(_D(self._DSR))
        f = self._db.last_filters
        self.assertEqual(f.get("package"), "PKG-1")
        self.assertEqual(f.get("effective_scts_user_id"), "U1")
        self.assertEqual(f.get("name"), ["!=", "DSR-2"], "phai loai chinh no ra")
        self.assertIn("Approval Completed", tuple(f.get("status")[1]))


class TestOrdinalIsPassedToTheVerifier(unittest.TestCase):
    def test_expected_carries_prior_signatures(self):
        body = re.search(r"(?m)^def _expected_for\(.*?(?=\ndef )", _SVC, re.S).group(0)
        self.assertIn('"prior_signatures": _completed_legs_of_same_signer(dsr)', body,
                      "khong truyen thu tu xuong thi verifier quay ve 'bat ky dong nao', "
                      "tuc lai cho chu ky cua chan truoc dong chan nay")

    def test_the_time_floor_is_gone(self):
        body = re.search(r"(?m)^def _expected_for\(.*?(?=\ndef )", _SVC, re.S).group(0)
        self.assertNotIn("_last_completed_leg_time", body,
                         "san thoi gian quay lai = chan cung phut lai ket mai mai")

    def test_moc_thoi_gian_la_accepted_at_khong_phai_queued_at(self):
        """Thu lai dat lai queued_at = bay gio; lay no lam moc thi chu ky that (da co tu
        truoc) luon bi coi la "truoc khi hoi". 02/09 23:40: chan ky luc 23:06, thu lai luc
        23:40, cua so 23:38:40 -> tu choi mai. `accepted_at` khong doi qua cac lan thu lai."""
        body = re.search(r"(?m)^def _expected_for\(.*?(?=\ndef )", _SVC, re.S).group(0)
        m = re.search(r'asked_at = (.+)', body)
        self.assertIsNotNone(m)
        thu_tu = m.group(1)
        self.assertLess(thu_tu.find('"accepted_at"'), thu_tu.find('"queued_at"'),
                        "accepted_at phai duoc uu tien TRUOC queued_at")
        self.assertNotEqual(thu_tu.find('"accepted_at"'), -1)

    def test_tolerance_window_still_exists(self):
        """Thu tu thay SAN, khong thay CUA SO. Cua so 120s van chan chu ky lam TRUOC khi
        minh hoi - do la lop bao ve khac, cho truong hop khac."""
        body = re.search(r"(?m)^def _expected_for\(.*?(?=\ndef )", _SVC, re.S).group(0)
        self.assertIn("SIGN_TIME_TOLERANCE_SECONDS", body)


if __name__ == "__main__":
    unittest.main()
