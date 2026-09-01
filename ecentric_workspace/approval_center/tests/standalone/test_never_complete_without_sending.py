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


class TestFreshnessBeatsThePreviousLeg(unittest.TestCase):
    def _load(self, rows):
        body = re.search(r"(?m)^def _last_completed_leg_time\(.*?(?=\ndef )", _SVC, re.S)
        self.assertIsNotNone(body)

        class _Frappe(object):
            @staticmethod
            def get_all(dt, **kw):
                if isinstance(rows, Exception):
                    raise rows
                return rows

        class _Adapter(object):
            @staticmethod
            def _parse_provider_time(v, reference=None):
                if not v:
                    return None
                return v if isinstance(v, datetime) else datetime.fromisoformat(str(v))

        # `_last_completed_leg_time` import providers.base BEN TRONG ham, nen phai thay
        # tam module do. PHAI TRA LAI: ban dau minh cam module gia vao sys.modules va bo
        # luon - no lam 5 phep kiem cua bo test khac gay, vi ly do cua chinh stub chu khong
        # phai cua code. Dung stub lam nguon su that thu hai.
        import sys
        import types as _t
        key = "ecentric_workspace.platform.esign.providers.base"
        self._saved_mod = sys.modules.get(key)
        self._mod_key = key
        mod = _t.ModuleType(key)
        mod.SignatureProviderAdapter = _Adapter
        sys.modules[key] = mod
        self.addCleanup(self._restore_module)
        g = {"frappe": _Frappe()}
        exec(compile(body.group(0), "lc", "exec"), g)
        return g["_last_completed_leg_time"]

    def _restore_module(self):
        import sys
        if self._saved_mod is not None:
            sys.modules[self._mod_key] = self._saved_mod
        else:
            sys.modules.pop(self._mod_key, None)

    _DSR = {"package": "PKG-1", "effective_scts_user_id": "U1", "name": "DSR-2"}

    def test_it_finds_the_latest_prior_leg(self):
        fn = self._load([{"verified_at": "2026-08-28 23:53:30", "modified": None},
                         {"verified_at": "2026-08-28 23:40:00", "modified": None}])
        self.assertEqual(fn(_D(self._DSR)), datetime(2026, 8, 28, 23, 53, 30))

    def test_no_prior_leg_means_no_floor(self):
        self.assertIsNone(self._load([])(_D(self._DSR)))

    def test_a_read_failure_does_not_lower_the_bar(self):
        self.assertIsNone(self._load(RuntimeError("db"))(_D(self._DSR)))

    def test_it_never_looks_at_a_different_signer_or_package(self):
        body = re.search(r"(?m)^def _last_completed_leg_time\(.*?(?=\ndef )", _SVC, re.S).group(0)
        self.assertIn('"package": dsr.get("package")', body)
        self.assertIn('"effective_scts_user_id": dsr.get("effective_scts_user_id")', body)
        self.assertIn('"name": ["!=", dsr.get("name")]', body,
                      "phai loai chinh no ra, khong thi tu chan chinh minh")


class TestTheFloorIsAppliedToTheWindow(unittest.TestCase):
    def test_the_floor_raises_signed_after(self):
        body = re.search(r"(?m)^def _expected_for\(.*?(?=\ndef )", _SVC, re.S).group(0)
        self.assertIn("floor = _last_completed_leg_time(dsr)", body)
        m = re.search(r"if floor and \(signed_after is None or floor > signed_after\):\s*\n"
                      r"\s*signed_after = floor", body)
        self.assertIsNotNone(m, "san phai NANG moc len, va chi nang chu khong ha")

    def test_it_runs_after_the_tolerance_is_computed(self):
        body = re.search(r"(?m)^def _expected_for\(.*?(?=\ndef )", _SVC, re.S).group(0)
        self.assertLess(body.index("SIGN_TIME_TOLERANCE_SECONDS"), body.index("floor ="),
                        "san phai de len TREN dung sai, khong bi dung sai ghi de")


if __name__ == "__main__":
    unittest.main()
