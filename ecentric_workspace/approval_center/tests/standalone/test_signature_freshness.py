# Copyright (c) 2026, eCentric and contributors
"""Chữ ký phải MỚI hơn thời điểm yêu cầu — tái hiện sự cố pilot UAT VOID 5 (27/08/2026).

Sự việc: EC-PAYR-2026-00026 có ĐÚNG hai chữ ký trên PDF — 00:47:43 (Hoàn, vai người
trình) và 00:48:42 (Vinh, ký từ portal). Chân NGƯỜI DUYỆT được tạo lúc 00:57:58 và
được báo `Verified` + `Approval Completed` lúc 00:58:00, dù không hề có chữ ký nào cho
cấp đó. Nguyên nhân: kiểm chứng chỉ hỏi "email này có trong danh sách đã ký không" —
Hoàn đã ký từ 00:47 nên câu trả lời là "có".

Bộ test này khoá lại bất biến: chữ ký thoả mãn một chân ký phải có thời điểm ký muộn
hơn lúc chân ký đó được xếp hàng (trừ dung sai lệch đồng hồ).

  python -m unittest ecentric_workspace.approval_center.tests.standalone.test_signature_freshness
"""
import os
import sys
import unittest
from datetime import datetime, timedelta

_APP = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
if _APP not in sys.path:
    sys.path.insert(0, _APP)

from ecentric_workspace.platform.esign.providers.base import (  # noqa: E402
    NormalizedDocState, SignatureProviderAdapter)

DOC = "8e912015-aaaa-bbbb-cccc-000000000001"
HOAN = "hoan.tran@ecentric.vn"
TOL = SignatureProviderAdapter.SIGN_TIME_TOLERANCE_SECONDS


def _state(signers):
    return NormalizedDocState(DOC, "processing", signers=signers,
                              files=[{"file_id": "f1", "name": "Invoice.pdf"}])


def _signer(email=HOAN, status="signed", signed_at="27/08/2026 00:47:43", user_id=None):
    return {"user_id": user_id, "signature_id": None, "email": email,
            "display_name": "Hoan", "status": status, "signed_at": signed_at,
            "is_external": False}


def _expected(signed_after=None, **kw):
    out = {"document_id": DOC, "user_id": "73f72e15", "email": HOAN, "file_count": 1}
    if signed_after is not None:
        out["signed_after"] = signed_after
    out.update(kw)
    return out


class TestTimeParser(unittest.TestCase):
    """Nhà cung cấp trả nhiều định dạng; đọc sai định dạng sẽ khoá nhầm cả hệ thống."""

    def test_vietnamese_day_first(self):
        self.assertEqual(SignatureProviderAdapter._parse_provider_time("27/08/2026 00:47:43"),
                         datetime(2026, 8, 27, 0, 47, 43))

    def test_vietnamese_without_seconds(self):
        self.assertEqual(SignatureProviderAdapter._parse_provider_time("27/08/2026 00:47"),
                         datetime(2026, 8, 27, 0, 47))

    def test_iso_with_t_and_z(self):
        self.assertEqual(SignatureProviderAdapter._parse_provider_time("2026-08-27T00:47:43Z"),
                         datetime(2026, 8, 27, 0, 47, 43))

    def test_iso_with_microseconds(self):
        self.assertEqual(SignatureProviderAdapter._parse_provider_time("2026-08-27 00:47:43.123456"),
                         datetime(2026, 8, 27, 0, 47, 43, 123456))

    def test_datetime_passthrough(self):
        d = datetime(2026, 8, 27, 0, 47, 43)
        self.assertEqual(SignatureProviderAdapter._parse_provider_time(d), d)

    def test_unreadable_returns_none(self):
        for bad in (None, "", "   ", "Chưa có", "chua co", "hôm qua", "null", 12345.6):
            self.assertIsNone(SignatureProviderAdapter._parse_provider_time(bad), bad)


class TestBareClockFromProvider(unittest.TestCase):
    """eContract trả giờ ký là MỘT CÁI ĐỒNG HỒ TRẦN: "04:12", không có ngày.

    Quan sát thật 27/08/2026 qua endpoint chẩn đoán: `signed_at: "04:12"`. Bộ đọc thời gian
    không có định dạng đó nên trả None, phép kiểm fail-closed, và chân ký kẹt ở Verifying
    dù chữ ký ĐÃ nằm trên PDF. Giờ trần được giải theo mốc tham chiếu (thời điểm ta yêu cầu
    ký), và phải vượt qua được ranh giới nửa đêm.
    """

    def test_the_actual_observed_value_now_parses(self):
        ref = datetime(2026, 8, 27, 4, 9, 46)
        got = SignatureProviderAdapter._parse_provider_time("04:12", reference=ref)
        self.assertEqual(got, datetime(2026, 8, 27, 4, 12, 0))

    def test_the_real_pilot_case_now_verifies(self):
        """DSR xếp hàng 04:11:46, chữ ký "04:12" -> phải xác minh được."""
        asked = datetime(2026, 8, 27, 4, 11, 46) - timedelta(seconds=TOL)
        res = SignatureProviderAdapter.verify_signed_result(
            _state([_signer(signed_at="04:12")]), _expected(signed_after=asked))
        self.assertTrue(res.ok, res.reason)

    def test_bare_clock_still_catches_a_signature_from_an_earlier_leg(self):
        """Sự cố Vinh: ký 00:48, chân ký tạo 00:57:58 -> vẫn phải bị từ chối."""
        asked = datetime(2026, 8, 27, 0, 57, 58) - timedelta(seconds=TOL)
        res = SignatureProviderAdapter.verify_signed_result(
            _state([_signer(signed_at="00:48")]), _expected(signed_after=asked))
        self.assertFalse(res.ok)
        self.assertIn("signature_predates_request", res.reason)

    def test_midnight_crossing_resolves_to_the_nearer_day(self):
        ref = datetime(2026, 8, 27, 0, 3, 0)
        got = SignatureProviderAdapter._parse_provider_time("23:58", reference=ref)
        self.assertEqual(got, datetime(2026, 8, 26, 23, 58, 0))

    def test_day_month_without_year_uses_the_reference_year(self):
        ref = datetime(2026, 8, 27, 4, 0, 0)
        got = SignatureProviderAdapter._parse_provider_time("27/08 04:12", reference=ref)
        self.assertEqual(got, datetime(2026, 8, 27, 4, 12, 0))

    def test_without_a_reference_a_bare_clock_is_still_unreadable(self):
        """Không có mốc tham chiếu thì đồng hồ trần vô nghĩa — thà nói không đọc được."""
        self.assertIsNone(SignatureProviderAdapter._parse_provider_time("04:12"))

    def test_full_timestamps_are_unaffected_by_the_reference(self):
        ref = datetime(2020, 1, 1, 0, 0, 0)
        self.assertEqual(
            SignatureProviderAdapter._parse_provider_time("27/08/2026 04:12:43", reference=ref),
            datetime(2026, 8, 27, 4, 12, 43))


class TestFreshness(unittest.TestCase):
    def test_the_actual_incident_is_now_refused(self):
        """Chữ ký 00:48:42 KHÔNG được xác nhận cho chân ký tạo lúc 00:57:58."""
        asked = datetime(2026, 8, 27, 0, 57, 58) - timedelta(seconds=TOL)
        res = SignatureProviderAdapter.verify_signed_result(
            _state([_signer(signed_at="27/08/2026 00:48:42")]), _expected(signed_after=asked))
        self.assertFalse(res.ok)
        self.assertIn("signature_predates_request", res.reason)

    def test_requester_leg_still_verifies(self):
        """Chân người trình thật (tạo 00:47:37, ký 00:47:43) vẫn phải xanh."""
        asked = datetime(2026, 8, 27, 0, 47, 37) - timedelta(seconds=TOL)
        res = SignatureProviderAdapter.verify_signed_result(
            _state([_signer(signed_at="27/08/2026 00:47:43")]), _expected(signed_after=asked))
        self.assertTrue(res.ok, res.reason)

    def test_signature_slightly_before_within_tolerance_passes(self):
        """Dung sai hấp thụ lệch đồng hồ và mốc thời gian chỉ tới phút."""
        asked_raw = datetime(2026, 8, 27, 10, 0, 0)
        asked = asked_raw - timedelta(seconds=TOL)
        res = SignatureProviderAdapter.verify_signed_result(
            _state([_signer(signed_at=(asked_raw - timedelta(seconds=TOL - 10)
                                       ).strftime("%d/%m/%Y %H:%M:%S"))]),
            _expected(signed_after=asked))
        self.assertTrue(res.ok, res.reason)

    def test_just_outside_tolerance_is_refused(self):
        asked_raw = datetime(2026, 8, 27, 10, 0, 0)
        asked = asked_raw - timedelta(seconds=TOL)
        res = SignatureProviderAdapter.verify_signed_result(
            _state([_signer(signed_at=(asked_raw - timedelta(seconds=TOL + 30)
                                       ).strftime("%d/%m/%Y %H:%M:%S"))]),
            _expected(signed_after=asked))
        self.assertFalse(res.ok)
        self.assertIn("signature_predates_request", res.reason)

    def test_unreadable_time_fails_closed_and_says_what_it_saw(self):
        """Không đọc được giờ = không chứng minh được -> từ chối, và nêu giá trị thô."""
        res = SignatureProviderAdapter.verify_signed_result(
            _state([_signer(signed_at="Chưa có")]),
            _expected(signed_after=datetime(2026, 8, 27, 0, 57, 58)))
        self.assertFalse(res.ok)
        self.assertIn("signed_at_unreadable", res.reason)

    def test_without_signed_after_behaviour_is_unchanged(self):
        """Không truyền mốc thì giữ nguyên hành vi cũ (tương thích ngược)."""
        res = SignatureProviderAdapter.verify_signed_result(
            _state([_signer(signed_at="Chưa có")]), _expected())
        self.assertTrue(res.ok, res.reason)


class TestSamePersonSignsSeveralAreas(unittest.TestCase):
    """Một người giữ NHIỀU vùng ký trên cùng chứng từ — chuyện bình thường ở eCentric.

    Hoàn vừa là người trình vừa là trưởng bộ phận, nên ký hai lần. Quan sát thật
    27/08/2026: eContract trả HAI dòng cho cùng email, `04:12` và `11:54`.

    Cách tra cứu cũ hỏng theo cả hai chiều: có hai dòng thì nó trả về KHÔNG CÓ AI
    (`expected_signer_absent`); có một dòng thì nó bám vào dòng đầu, nên chân người duyệt bị
    đánh giá bằng chính chữ ký cũ của chân người trình (`signature_predates_request:04:12`).
    """

    def test_approver_leg_accepts_the_newer_row(self):
        asked = datetime(2026, 8, 27, 11, 54, 16) - timedelta(seconds=TOL)
        st = _state([_signer(signed_at="04:12"), _signer(signed_at="11:54")])
        res = SignatureProviderAdapter.verify_signed_result(st, _expected(signed_after=asked))
        self.assertTrue(res.ok, res.reason)

    def test_requester_leg_still_accepts_the_older_row(self):
        """Chân người trình xét lúc chỉ có dòng cũ — vẫn phải xanh."""
        asked = datetime(2026, 8, 27, 4, 11, 46) - timedelta(seconds=TOL)
        st = _state([_signer(signed_at="04:12"), _signer(signed_at="11:54")])
        res = SignatureProviderAdapter.verify_signed_result(st, _expected(signed_after=asked))
        self.assertTrue(res.ok, res.reason)

    def test_two_rows_no_longer_mean_nobody_found(self):
        st = _state([_signer(signed_at="04:12"), _signer(signed_at="11:54")])
        self.assertEqual(len(st.signers_for("73f72e15", HOAN)), 2)
        res = SignatureProviderAdapter.verify_signed_result(st, _expected())
        self.assertNotEqual(res.reason, "expected_signer_absent")

    def test_all_rows_too_old_is_still_refused(self):
        """Không được nới lỏng: mọi dòng đều cũ hơn yêu cầu thì vẫn phải từ chối."""
        asked = datetime(2026, 8, 27, 20, 0, 0) - timedelta(seconds=TOL)
        st = _state([_signer(signed_at="04:12"), _signer(signed_at="11:54")])
        res = SignatureProviderAdapter.verify_signed_result(st, _expected(signed_after=asked))
        self.assertFalse(res.ok)
        self.assertIn("signature_predates_request", res.reason)

    def test_a_pending_row_does_not_block_a_signed_one(self):
        st = _state([_signer(status="pending", signed_at=None), _signer(signed_at="11:54")])
        asked = datetime(2026, 8, 27, 11, 54, 16) - timedelta(seconds=TOL)
        res = SignatureProviderAdapter.verify_signed_result(st, _expected(signed_after=asked))
        self.assertTrue(res.ok, res.reason)

    def test_other_people_rows_are_never_considered(self):
        st = _state([_signer(email="ai.do@ecentric.vn", signed_at="11:54"),
                     _signer(signed_at="04:12")])
        asked = datetime(2026, 8, 27, 11, 54, 16) - timedelta(seconds=TOL)
        res = SignatureProviderAdapter.verify_signed_result(st, _expected(signed_after=asked))
        self.assertFalse(res.ok, "khong duoc muon chu ky cua nguoi khac de xac nhan")

    def test_file_count_is_checked_before_any_signer(self):
        """Số tệp thuộc về TÀI LIỆU, không thuộc về từng người ký — phải kiểm một lần."""
        st = _state([_signer(signed_at="11:54")])
        res = SignatureProviderAdapter.verify_signed_result(st, _expected(file_count=9))
        self.assertEqual(res.reason, "file_count_mismatch")


class TestUnchangedChecks(unittest.TestCase):
    """Các phép kiểm sẵn có không được đổi hành vi."""

    def test_document_mismatch(self):
        res = SignatureProviderAdapter.verify_signed_result(_state([_signer()]),
                                                     _expected(document_id="khac"))
        self.assertFalse(res.ok)
        self.assertEqual(res.reason, "document_id_mismatch")

    def test_signer_absent(self):
        res = SignatureProviderAdapter.verify_signed_result(
            _state([_signer(email="ai.do@ecentric.vn")]), _expected())
        self.assertFalse(res.ok)
        self.assertEqual(res.reason, "expected_signer_absent")

    def test_signer_not_signed(self):
        res = SignatureProviderAdapter.verify_signed_result(
            _state([_signer(status="pending", signed_at=None)]), _expected())
        self.assertFalse(res.ok)
        self.assertIn("signer_not_signed", res.reason)

    def test_file_count_mismatch(self):
        res = SignatureProviderAdapter.verify_signed_result(_state([_signer()]),
                                                     _expected(file_count=3))
        self.assertFalse(res.ok)
        self.assertEqual(res.reason, "file_count_mismatch")

    def test_freshness_runs_before_signature_id_check(self):
        """Chữ ký cũ phải bị chặn kể cả khi signature_id khớp."""
        asked = datetime(2026, 8, 27, 0, 57, 58) - timedelta(seconds=TOL)
        st = _state([dict(_signer(signed_at="27/08/2026 00:48:42"), signature_id="638649a4")])
        res = SignatureProviderAdapter.verify_signed_result(
            st, _expected(signed_after=asked, signature_id="638649a4"))
        self.assertFalse(res.ok)
        self.assertIn("signature_predates_request", res.reason)


if __name__ == "__main__":
    unittest.main(verbosity=2)
