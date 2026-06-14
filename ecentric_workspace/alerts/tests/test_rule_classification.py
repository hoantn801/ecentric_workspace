"""Canonical rule classification + Pre-E2E scope-hardening guards (2026-06-14).

All layers run WITHOUT a bench/DB:

  1. TestRuleClassification - drives services.rule_classification directly
     (pure Python, no frappe): operational vs setup vs system buckets, the
     default operational exclusion, the setup-only view, and the precedence of
     rule_code_condition().

  2. TestRuleCodeInventory - the EC Alert.rule_code Select enum is the canonical
     inventory; every enum value MUST be classified, so a new code can never
     silently leak into the operational default.

  3. Source guards - the operational/setup split is wired through the ONE shared
     helper in api_alerts + api_dashboard, exports stay scoped, and policy_caps
     rejects an out-of-scope brand (no false/false probe).

    bench run-tests --module ecentric_workspace.alerts.tests.test_rule_classification
"""
import json
import os
import re
import unittest

from ecentric_workspace.alerts.services import rule_classification as rc


def _src(rel):
    path = os.path.join(os.path.dirname(__file__), "..", rel)
    with open(os.path.abspath(path), "r", encoding="utf-8") as fh:
        return fh.read()


class TestRuleClassification(unittest.TestCase):
    def test_operational_set_is_the_four_price_rules(self):
        self.assertEqual(
            rc.OPERATIONAL_RULES,
            frozenset({"below_min", "above_high", "severe_price_drop",
                       "possible_missing_zero"}))

    def test_setup_and_system_buckets(self):
        self.assertIn("missing_brand_mapping", rc.SETUP_RULES)
        self.assertIn("missing_policy", rc.SETUP_RULES)
        self.assertIn("missing_integration_credential", rc.SYSTEM_RULES)
        self.assertIn("ingestion_api_failed", rc.SYSTEM_RULES)
        self.assertIn("stock_lock_api_failed", rc.SYSTEM_RULES)

    def test_buckets_are_disjoint(self):
        self.assertEqual(rc.OPERATIONAL_RULES & rc.SETUP_RULES, frozenset())
        self.assertEqual(rc.OPERATIONAL_RULES & rc.SYSTEM_RULES, frozenset())
        self.assertEqual(rc.SETUP_RULES & rc.SYSTEM_RULES, frozenset())

    def test_non_operational_is_setup_plus_system(self):
        self.assertEqual(rc.NON_OPERATIONAL_RULES,
                         rc.SETUP_RULES | rc.SYSTEM_RULES)
        # missing_brand_mapping (the flood) IS excluded from the default.
        self.assertIn("missing_brand_mapping", rc.non_operational_rule_codes())
        # operational price rules are NEVER excluded.
        for code in rc.OPERATIONAL_RULES:
            self.assertNotIn(code, rc.non_operational_rule_codes())

    def test_classify(self):
        self.assertEqual(rc.classify("below_min"), "operational")
        self.assertEqual(rc.classify("missing_brand_mapping"), "setup")
        self.assertEqual(rc.classify("ingestion_api_failed"), "system")
        self.assertEqual(rc.classify("brand_new_code"), "unknown")

    def test_rule_code_condition_default_excludes_non_operational(self):
        cond = rc.rule_code_condition({})
        self.assertEqual(cond[0], "rule_code")
        self.assertEqual(cond[1], "not in")
        self.assertEqual(set(cond[2]), set(rc.NON_OPERATIONAL_RULES))

    def test_rule_code_condition_explicit_rule_wins(self):
        # history / drill-down: an explicit code is matched exactly (so the
        # retired missing_policy and the setup missing_brand_mapping stay
        # queryable).
        for code in ("missing_brand_mapping", "missing_policy", "below_min"):
            self.assertEqual(rc.rule_code_condition({"rule_code": code}),
                             ["rule_code", "=", code])

    def test_rule_code_condition_setup_only_view(self):
        cond = rc.rule_code_condition({"setup_only": 1})
        self.assertEqual(cond[1], "in")
        self.assertEqual(set(cond[2]), set(rc.SETUP_RULES))
        # truthy string forms work (frontend sends 1 / "1")
        self.assertEqual(rc.rule_code_condition({"setup_only": "1"})[1], "in")
        # explicit rule_code still beats setup_only
        self.assertEqual(
            rc.rule_code_condition({"setup_only": 1, "rule_code": "below_min"}),
            ["rule_code", "=", "below_min"])

    def test_setup_only_falsey_forms_stay_operational(self):
        for v in ("", "0", "false", "no", None):
            self.assertEqual(rc.rule_code_condition({"setup_only": v})[1],
                             "not in")


class TestRuleCodeInventory(unittest.TestCase):
    """Every EC Alert.rule_code enum value MUST be classified - a new code that
    is added to the DocType but not to rule_classification would otherwise leak
    into (or vanish from) the operational default unnoticed."""

    def test_enum_matches_all_rules(self):
        meta = json.loads(_src("doctype/ec_alert/ec_alert.json"))
        opts = None
        for fld in meta.get("fields", []):
            if fld.get("fieldname") == "rule_code":
                opts = fld.get("options", "")
                break
        self.assertIsNotNone(opts, "rule_code Select field not found")
        enum = {o.strip() for o in opts.split("\n") if o.strip()}
        self.assertEqual(
            enum, set(rc.ALL_RULES),
            "EC Alert.rule_code enum %s != classified ALL_RULES %s"
            % (sorted(enum), sorted(rc.ALL_RULES)))


class TestApisUseCanonicalClassifier(unittest.TestCase):
    def test_no_module_hardcodes_its_own_exclusion_list(self):
        # the per-file ["missing_policy"] / ["missing_brand_mapping"] literals
        # are gone - both APIs go through rule_classification.
        for mod in ("api_alerts.py", "api_dashboard.py"):
            s = _src(mod)
            self.assertIn("rule_classification as rclass", s)
            self.assertNotIn('"not in", ["missing_policy"]', s)


class TestScopeHardening(unittest.TestCase):
    def test_policy_caps_rejects_out_of_scope_brand(self):
        s = _src("api_policies.py")
        # the explicit-brand branch now calls require_brand_access BEFORE
        # answering, so brand=LOF-VN by a FES-only user raises (not false/false).
        m = re.search(r"if brand:(.*?)return \{", s, re.S)
        self.assertIsNotNone(m, "policy_caps explicit-brand branch not found")
        self.assertIn("require_brand_access", m.group(1))

    def test_list_alerts_supports_status_group_without_losing_single(self):
        s = _src("api_alerts.py")
        # KPI cards send a status LIST (Open+In Review); single value still works.
        self.assertIn('["status", "in", list(vals)]', s)
        self.assertIn('["status", "=", st]', s)


if __name__ == "__main__":
    unittest.main(verbosity=2)
