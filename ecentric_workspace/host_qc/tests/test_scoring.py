# Copyright (c) 2026, eCentric and contributors
"""Cham diem: khop src/rules/scoring.js cua app + ERP chi tru VOI-02 khi duyet Valid."""
import unittest

from ecentric_workspace.host_qc.tests import fakes as F
from ecentric_workspace.host_qc.services.build_rules_config_service import BuildRulesConfigService
from ecentric_workspace.host_qc.services.compute_score_service import ComputeScoreService


def V(code, group, sev, review="Pending", minute=1):
    return {"code": code, "group": group, "severity": sev, "review": review,
            "start_time": F.NOW.replace(minute=minute), "end_time": F.NOW.replace(minute=minute)}


class TestScoring(unittest.TestCase):
    def setUp(self):
        self.rules = BuildRulesConfigService(F.FakeSettings(), F.FakeRules()).execute()
        self.c = ComputeScoreService()

    def test_slide8_2_major_1_critical_62_red_roi_duyet_len_90_yellow(self):
        vs = [V("SAL-01", "D", "Major", minute=1), V("SAL-02", "D", "Major", minute=2),
              V("CMP-01", "B", "Critical", "Need Review", minute=3)]
        sc = self.c.execute(vs, self.rules, t0=F.NOW)
        self.assertEqual((sc["total"], sc["status"]), (62, "RED"))
        self.assertTrue(sc["needs_verification"])
        vs[2]["review"] = "False Positive"
        sc = self.c.execute(vs, self.rules, t0=F.NOW)
        self.assertEqual((sc["total"], sc["status"]), (80, "RED"))      # 2 Major van RED
        self.assertFalse(sc["needs_verification"])
        vs[1]["review"] = "False Positive"
        sc = self.c.execute(vs, self.rules, t0=F.NOW)
        self.assertEqual((sc["total"], sc["status"]), (90, "YELLOW"))   # 1 Major -> YELLOW

    def test_nhom_khong_am(self):
        vs = [V("SAL-01", "D", "Major", minute=i) for i in range(1, 5)]
        sc = self.c.execute(vs, self.rules)
        self.assertEqual(sc["groups"]["D"]["score"], 0)
        self.assertEqual(sc["total"], 75)

    def test_voi02_chi_tru_khi_valid(self):
        v = V("VOI-02", "A", "Major", "Need Review")
        self.assertEqual(self.c.execute([v], self.rules)["total"], 100)
        v["review"] = "Valid Violation"
        sc = self.c.execute([v], self.rules)
        self.assertEqual((sc["total"], sc["status"]), (90, "YELLOW"))

    def test_5_minor_yellow(self):
        vs = [V("VOI-01", "A", "Minor", minute=i) for i in range(1, 6)]
        sc = self.c.execute(vs, self.rules)
        self.assertEqual((sc["total"], sc["status"], sc["counts"]["Minor"]), (85, "YELLOW", 5))


class TestRulesConfig(unittest.TestCase):
    def test_dang_rules_config(self):
        cfg = BuildRulesConfigService(F.FakeSettings(), F.FakeRules()).execute()
        self.assertEqual(cfg["version"], "v1")
        self.assertEqual(cfg["deduction"], {"Minor": 3, "Major": 10, "Critical": 18})
        self.assertEqual(cfg["groups"]["A"], {"name": "Voice", "max": 30})
        self.assertNotIn("GENERAL-01", cfg["codes"])
        self.assertEqual(len(cfg["guide"]), len(F.RULES))
        self.assertEqual(cfg["codes"]["VOI-01"]["min_db"], -38)
        self.assertEqual(cfg["codes"]["VOI-01"]["clear_ratio"], 0.95)
        self.assertTrue(cfg["codes"]["VOI-02"]["deduct_only_valid"])
        self.assertEqual(cfg["codes"]["VOI-02"]["default_review"], "Need Review")
        self.assertNotIn("severity", cfg["codes"]["ENG-01"])
        self.assertEqual(cfg["formats"]["branding"], {"SAL-01": {"gap_min": 10}, "SAL-02": {"enabled": False}})
        self.assertEqual(cfg["llm"]["models"], ["m1", "m2"])
        self.assertNotIn("kie_api_key", str(cfg))


if __name__ == "__main__":
    unittest.main()
