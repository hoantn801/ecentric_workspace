# Copyright (c) 2026, eCentric and contributors
"""Bang huong dan nap san (12 ma + muc chung, khong ghi de) + envelope API (ma HTTP cho app thu lai)."""
import sys
import types
import unittest

from ecentric_workspace.host_qc.exceptions import AuthError, InvalidInput, TooManyAttempts
from ecentric_workspace.host_qc.patches import p001_setup as P
from ecentric_workspace.host_qc.services.build_rules_config_service import BuildRulesConfigService
from ecentric_workspace.host_qc.services.get_guide_service import GetGuideService
from ecentric_workspace.host_qc.exceptions import ForbiddenError
from ecentric_workspace.host_qc.tests import fakes as F


class TestSeed(unittest.TestCase):
    def test_12_ma_va_muc_chung(self):
        rows = P._load()
        codes = [r["code"] for r in rows if r["group"] != "–"]
        self.assertEqual(len(codes), 12)
        self.assertTrue(all(r["code"].startswith("GENERAL-") for r in rows if r["group"] == "–"))
        by = {r["code"]: r for r in rows}
        self.assertEqual((by["VOI-02"]["default_review"], by["VOI-02"]["deduct_only_valid"]), ("Need Review", 1))
        self.assertEqual((by["CMP-01"]["severity"], by["CMP-02"]["severity"]), ("Critical", "Critical"))
        self.assertTrue(all(p["unit"] and p["description"] for r in rows for p in r["params"]))

    def test_khong_ghi_de_ma_da_sua(self):
        repo = F.FakeRules([F.rule("VOI-01", "A", "Major")])
        added = P.seed_rules(repo, P._load())
        self.assertEqual(added, len(P._load()) - 1)
        self.assertEqual([r for r in repo.rows if r["code"] == "VOI-01"][0]["severity"], "Major")

    def test_seed_ra_rules_config_giong_app(self):
        repo = F.FakeRules([])
        P.seed_rules(repo, P._load())
        cfg = BuildRulesConfigService(F.FakeSettings(), repo).execute()
        self.assertEqual(cfg["codes"]["VOI-01"], {"group": "A", "enabled": True, "severity": "Minor", "window_min": 5,
                                                  "clear_ratio": 0.95, "min_db": -38, "hits_per_violation": 3,
                                                  "min_speech_s": 20})
        self.assertEqual(cfg["codes"]["CMP-01"]["llm_confirm"], 1)
        self.assertEqual(cfg["formats"]["branding"], {"SAL-02": {"enabled": False}, "SAL-01": {"gap_min": 10}})
        self.assertEqual(cfg["formats"]["education"], {"SAL-02": {"gap_min": 10}})

    def test_guide_theo_role(self):
        g = GetGuideService(F.FakeSettings(), F.FakeRules()).execute(["Host QC Viewer"])
        self.assertFalse(g["can_edit"])
        self.assertTrue(GetGuideService(F.FakeSettings(), F.FakeRules()).execute(["Host QC Manager"])["can_edit"])
        with self.assertRaises(ForbiddenError):
            GetGuideService(F.FakeSettings(), F.FakeRules()).execute(["Employee"])


@unittest.skipIf(hasattr(sys.modules["frappe"], "__file__"), "frappe that: test envelope chay qua bench")
class TestEnvelope(unittest.TestCase):
    def setUp(self):
        fr = sys.modules["frappe"]
        self.rolled = []

        class VE(Exception):
            pass
        fr.ValidationError = VE
        fr.db = types.SimpleNamespace(rollback=lambda: self.rolled.append(1))
        fr.local = types.SimpleNamespace(response={})
        fr.log_error = lambda **k: None
        fr.utils = types.SimpleNamespace(strip_html=lambda s: s)
        from ecentric_workspace.host_qc.api import _envelope
        self.E, self.fr = _envelope, fr

    def call(self, exc):
        def boom():
            raise exc
        self.fr.local.response = {}
        out = self.E.run(boom)
        return self.fr.local.response.get("http_status_code"), out["success"], out["message"]

    def test_ma_http(self):
        self.assertEqual(self.E.run(lambda: {"a": 1}), {"success": True, "message": "", "data": {"a": 1}})
        self.assertEqual(self.call(AuthError("x"))[:2], (401, False))
        self.assertEqual(self.call(TooManyAttempts("x"))[0], 429)
        self.assertEqual(self.call(InvalidInput("sai"))[:3], (400, False, "sai"))
        self.assertEqual(self.call(self.fr.ValidationError("v"))[0], 400)
        code, ok, msg = self.call(RuntimeError("db khoa"))
        self.assertEqual((code, ok), (503, False))
        self.assertNotIn("db khoa", msg)
        self.assertEqual(len(self.rolled), 5)


if __name__ == "__main__":
    unittest.main()
