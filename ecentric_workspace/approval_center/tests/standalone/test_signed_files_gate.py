# Copyright (c) 2026, eCentric and contributors
"""Cổng lấy file đã ký phải chịu được NHIỀU chân ký.

Sự cố pilot UAT VOID 5 (27/08/2026): quy tắc cũ đòi ĐÚNG MỘT chân ký hoàn tất, nên ngay
khi chân người duyệt xong (chân thứ hai), `retrieve_signed_files` trả
`not_exactly_one_completed_dsr:2` và không bao giờ lấy được file. Luồng thật LUÔN có nhiều
chân: người trình + mỗi cấp duyệt có ký.

Bất biến đúng: ít nhất một chân hoàn tất, và KHÔNG chân nào còn đang chạy (còn chạy nghĩa
là còn chữ ký sắp tới, file tải về sẽ thiếu).

  python -m unittest ecentric_workspace.approval_center.tests.standalone.test_signed_files_gate
"""
import os
import sys
import types
import unittest

_APP = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
if _APP not in sys.path:
    sys.path.insert(0, _APP)

DSR_TERMINAL = ("Approval Completed", "Permanent Failure", "Cancelled", "Rejected", "Superseded")


def _gate(rows):
    """Bản sao thuần của quy tắc cổng, giữ đồng bộ với signed_files._is_terminal_signed.

    Tách ra để chạy được không cần bench; `test_matches_shipped_source` bên dưới khoá lại
    việc nó không được lệch khỏi mã thật.
    """
    if not rows:
        return False, "no_signature_request"
    completed = [r for r in rows if r["status"] == "Approval Completed"]
    if not completed:
        return False, "no_completed_dsr:%d" % len(rows)
    in_flight = [r for r in rows if r["status"] not in DSR_TERMINAL]
    if in_flight:
        return False, "signing_still_in_flight:%s" % ",".join(
            sorted({r["status"] for r in in_flight}))
    return True, "all_legs_terminal"


def _rows(*statuses):
    return [{"name": "DSR-%d" % i, "status": s} for i, s in enumerate(statuses, 1)]


class TestGate(unittest.TestCase):
    def test_the_actual_incident_two_completed_legs_now_passes(self):
        ok, reason = _gate(_rows("Approval Completed", "Approval Completed"))
        self.assertTrue(ok, reason)

    def test_single_leg_still_passes(self):
        ok, _ = _gate(_rows("Approval Completed"))
        self.assertTrue(ok)

    def test_five_legs_requester_plus_four_levels(self):
        ok, _ = _gate(_rows(*(["Approval Completed"] * 5)))
        self.assertTrue(ok)

    def test_leg_still_running_blocks(self):
        """Còn chân đang chạy = file sẽ thiếu chữ ký -> chặn."""
        for running in ("Queued", "Provider Accepted", "Verifying", "Signed", "Manual Review"):
            ok, reason = _gate(_rows("Approval Completed", running))
            self.assertFalse(ok, running)
            self.assertIn("signing_still_in_flight", reason)
            self.assertIn(running, reason)

    def test_no_completed_leg_blocks(self):
        ok, reason = _gate(_rows("Queued"))
        self.assertFalse(ok)
        self.assertIn("no_completed_dsr", reason)

    def test_no_legs_at_all_blocks(self):
        ok, reason = _gate([])
        self.assertFalse(ok)
        self.assertEqual(reason, "no_signature_request")

    def test_failed_leg_alongside_completed_does_not_block(self):
        """Chân hỏng vĩnh viễn / bị huỷ là trạng thái kết thúc, không phải đang chạy."""
        for dead in ("Permanent Failure", "Cancelled", "Rejected", "Superseded"):
            ok, reason = _gate(_rows("Approval Completed", dead))
            self.assertTrue(ok, "%s -> %s" % (dead, reason))


class TestStaysInSyncWithSource(unittest.TestCase):
    def test_matches_shipped_source(self):
        """Bộ test grep mã nguồn sẽ MÙ nếu mã đổi mà test không đổi — khoá lại các chuỗi
        quyết định để việc sửa mã buộc phải sửa cả test này."""
        src_path = os.path.join(_APP, "ecentric_workspace", "platform", "esign",
                                "signed_files.py")
        with open(src_path, encoding="utf-8") as fh:
            src = fh.read()
        self.assertNotIn('"not_exactly_one_completed_dsr:%d"', src,
                         "cau lenh tra ve cua quy tac cu van con trong ma nguon")
        self.assertNotIn("exactly one DSR", src,
                         "docstring van mo ta quy tac cu -> tai lieu sai con nguy hiem hon ma sai")
        for token in ("no_signature_request", "no_completed_dsr",
                      "signing_still_in_flight", "DSR_TERMINAL"):
            self.assertIn(token, src, token)


if __name__ == "__main__":
    unittest.main(verbosity=2)
