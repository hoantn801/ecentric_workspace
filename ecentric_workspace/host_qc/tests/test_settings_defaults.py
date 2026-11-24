# Copyright (c) 2026, eCentric and contributors
"""set_defaults so voi gia tri DA LUU (tabSingles), khong voi get_single (loi p001 24/11: Settings toan 0)."""
import sys
import types
import unittest

from ecentric_workspace.host_qc.repositories.settings_repository import SettingsRepository


@unittest.skipIf(hasattr(sys.modules["frappe"], "__file__"), "frappe that: chay qua bench")
class TestSetDefaults(unittest.TestCase):
    def setUp(self):
        self.stored, self.cleared = {}, []
        fr = sys.modules["frappe"]
        fr.db = types.SimpleNamespace(get_singles_dict=lambda dt: dict(self.stored),
                                      set_single_value=lambda dt, vals: self.stored.update(vals))
        fr.clear_document_cache = lambda *a: self.cleared.append(a)
        fr.get_single = lambda dt: self.fail("khong duoc dua vao get_single (tra mac dinh trong bo nho)")

    def test_single_chua_luu_gi_thi_dien_het(self):
        filled = SettingsRepository().set_defaults({"green_min": 85, "deduction_major": 10})
        self.assertEqual(filled, ["deduction_major", "green_min"])
        self.assertEqual(self.stored, {"green_min": 85, "deduction_major": 10})
        self.assertTrue(self.cleared)

    def test_chi_dien_o_trong_hoac_0_khong_ghi_de(self):
        self.stored.update(rules_version="v1", green_min="0", deduction_major=12)
        filled = SettingsRepository().set_defaults({"green_min": 85, "deduction_major": 10})
        self.assertEqual(filled, ["green_min"])
        self.assertEqual(self.stored["deduction_major"], 12)

    def test_du_roi_thi_khong_ghi(self):
        self.stored.update(green_min=80)
        self.assertEqual(SettingsRepository().set_defaults({"green_min": 85}), [])
        self.assertFalse(self.cleared)


if __name__ == "__main__":
    unittest.main()
