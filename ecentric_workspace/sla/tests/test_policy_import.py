# Copyright (c) 2026, eCentric and contributors
"""Kiem tra tep cau hinh SLA va cach sinh ma chinh sach - khong can bench.

    python3 -m unittest ecentric_workspace.sla.tests.test_policy_import -v

Phan lon test o day kiem chinh TEP DU LIEU chu khong phai code. Co y: tep do la
thu con nguoi go tay vao Excel, va mot so go nham o do se am tham tro thanh mot
cai han sai tren dau mot dong nghiep. Code thi co review; con so thi khong -
tru khi co test.
"""
import io
import json
import os
import unittest

_FIXTURE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "fixtures", "approval_sla.json")

with io.open(_FIXTURE, encoding="utf-8") as _f:
    DOC = json.load(_f)
ROWS = DOC["rows"]

UNIT_BUSINESS = "giờ làm việc"
UNIT_CALENDAR = "giờ đồng hồ"


def policy_code_for(hours, reminder_hours, unit):
    """Ban sao thuan cua policy_import.policy_code_for, de test khong phai nap frappe."""
    prefix = "WH" if unit == UNIT_BUSINESS else "CH"
    h = int(hours) if float(hours) == int(hours) else hours
    return "%s-%sH-R%s" % (prefix, h, int(reminder_hours or 0))


class TestFixtureShape(unittest.TestCase):
    def test_row_count(self):
        self.assertEqual(len(ROWS), 65)
        self.assertEqual(sum(1 for r in ROWS if not r["fulfillment"]), 60)
        self.assertEqual(sum(1 for r in ROWS if r["fulfillment"]), 5)

    def test_keys_unique(self):
        keys = [r["key"] for r in ROWS]
        self.assertEqual(len(keys), len(set(keys)))

    def test_key_matches_process_and_level(self):
        for r in ROWS:
            tail = "FUL" if r["fulfillment"] else str(r["level_no"])
            self.assertEqual(r["key"], "%s#%s" % (r["process_code"], tail))

    def test_every_row_has_a_positive_duration(self):
        for r in ROWS:
            self.assertGreater(r["hours"], 0, r["key"])

    def test_unit_is_one_of_two(self):
        for r in ROWS:
            self.assertIn(r["unit"], (UNIT_BUSINESS, UNIT_CALENDAR), r["key"])

    def test_reminder_is_shorter_than_the_deadline(self):
        # Nhac truoc >= han nghia la nhac ngay luc mo - vo nghia, va nguoi nhan
        # se hoc cach bo qua moi loi nhac.
        for r in ROWS:
            self.assertLess(r["reminder_hours"], r["hours"], r["key"])

    def test_level_no_present_exactly_when_not_fulfillment(self):
        for r in ROWS:
            if r["fulfillment"]:
                self.assertIsNone(r["level_no"], r["key"])
            else:
                self.assertIsInstance(r["level_no"], int, r["key"])
                self.assertGreaterEqual(r["level_no"], 1, r["key"])


class TestPolicyCode(unittest.TestCase):
    def test_same_numbers_share_one_code(self):
        self.assertEqual(policy_code_for(4, 2, UNIT_BUSINESS),
                         policy_code_for(4.0, 2, UNIT_BUSINESS))

    def test_different_reminder_is_a_different_code(self):
        # 8 gio nhac truoc 2 va 8 gio nhac truoc 4 la HAI chinh sach. Gop lai se
        # lam mot trong hai buoc nhan loi nhac sai gio.
        self.assertNotEqual(policy_code_for(8, 2, UNIT_BUSINESS),
                            policy_code_for(8, 4, UNIT_BUSINESS))

    def test_unit_changes_the_prefix(self):
        self.assertTrue(policy_code_for(4, 2, UNIT_BUSINESS).startswith("WH-"))
        self.assertTrue(policy_code_for(4, 2, UNIT_CALENDAR).startswith("CH-"))

    def test_fixture_derives_six_distinct_codes(self):
        """Sau ma - do la so chinh sach mot ban CAI MOI can.

        Tren ban dang chay thi it hon: bon dong AI_TOPUP giu ma rieng cua tinh
        nang do (`AI_TOPUP_MANAGER_3H`...) nen `WH-3H-R1` duoc suy ra nhung
        khong duoc ghi. Test nay doi chieu TEP CAU HINH, khong doi chieu he
        thong - doi chieu he thong la viec cua `policy_import.verify()`.
        """
        codes = {policy_code_for(r["hours"], r["reminder_hours"], r["unit"]) for r in ROWS}
        self.assertEqual(codes, {"WH-3H-R1", "WH-4H-R2", "WH-8H-R2",
                                 "WH-8H-R4", "WH-16H-R8", "WH-24H-R12"})

    def test_only_ai_topup_uses_the_three_hour_code(self):
        # Neu mot buoc khac cung roi vao 3h/R1, no se dung chung mot ban ghi voi
        # AI Topup - nhung AI Topup lai giu ma rieng, nen hai buoc "giong nhau"
        # se nam o hai ban ghi va troi ra khoi nhau tu lan sua dau tien.
        three = {r["key"] for r in ROWS
                 if policy_code_for(r["hours"], r["reminder_hours"], r["unit"]) == "WH-3H-R1"}
        self.assertEqual(three, {"AI_TOPUP#1", "AI_TOPUP#2", "AI_TOPUP#3", "AI_TOPUP#FUL"})


class TestBusinessSense(unittest.TestCase):
    """Nhung dieu dung ve ky thuat nhung dang de y ve van hanh."""

    def test_no_step_is_absurdly_short(self):
        # Duoi 1 gio lam viec thi khong ai phan hoi kip, va ca nhom se hong SLA
        # vi mot con so chu khong vi hanh vi.
        for r in ROWS:
            self.assertGreaterEqual(r["hours"], 1, r["key"])

    def test_no_step_runs_longer_than_a_working_week(self):
        # 45 gio lam viec ~ mot tuan. Dai hon the thi "han" khong con dieu khien
        # duoc hanh vi nao ca.
        for r in ROWS:
            self.assertLessEqual(r["hours"], 45, r["key"])


if __name__ == "__main__":
    unittest.main()
