"""Phase G1 tests - brand readiness derivation + secret redaction.

The readiness precedence tests are PURE (brand_readiness imports nothing) and
run anywhere. The secret-redaction + ordering tests import api_brands behind a
minimal frappe stub so they also run without a bench site:
    bench --site <dev-site> run-tests --module ecentric_workspace.alerts.tests.test_phase_g1
"""
import sys
import types
import unittest

from ecentric_workspace.alerts.services import brand_readiness as br


def _facts(**kw):
    base = dict(
        ba_exists=True, ba_status="Active", kam_owner="kam@x.com",
        manager_email="m@x.com", leader_email="l@x.com",
        bis_exists=True, enabled=1, credential_status="Active",
        dry_run_stock_lock=1, consecutive_failures=0,
        last_sync_at="2026-06-08 10:00:00", sync_age_minutes=5.0,
        running=False, in_allowlist=True, last_run_state="done",
        coverage_pct=80.0,
    )
    base.update(kw)
    return base


class TestReadinessPrecedence(unittest.TestCase):
    def _status(self, **kw):
        return br.derive(_facts(**kw))["status"]

    def test_healthy_scheduled_brand_is_scheduler_enabled(self):
        # FES-VN profile
        self.assertEqual(self._status(), br.SCHEDULER_ENABLED)

    def test_missing_brand_approver(self):
        self.assertEqual(self._status(ba_exists=False), br.BLOCKED)
        self.assertEqual(self._status(ba_status="Inactive"), br.BLOCKED)

    def test_missing_bis_is_blocked(self):
        # LOF-VN profile: BA exists, BIS missing
        v = br.derive(_facts(bis_exists=False, credential_status=None,
                             enabled=None, dry_run_stock_lock=None,
                             last_sync_at=None, sync_age_minutes=None,
                             in_allowlist=False, last_run_state=None,
                             coverage_pct=None))
        self.assertEqual(v["status"], br.BLOCKED)
        self.assertEqual(v["blockers"][0]["code"], "missing_bis")
        self.assertEqual(v["action"]["code"], "create_bis")

    def test_bis_disabled(self):
        self.assertEqual(self._status(enabled=0), br.BLOCKED)
        self.assertEqual(self._status(enabled="0"), br.BLOCKED)  # bool("0") trap

    def test_ds1_unsafe_blocks(self):
        v = br.derive(_facts(dry_run_stock_lock=0))
        self.assertEqual(v["status"], br.BLOCKED)
        self.assertEqual(v["blockers"][0]["code"], "ds1_unsafe")

    def test_credential_not_active(self):
        v = br.derive(_facts(credential_status="Expired"))
        self.assertEqual(v["status"], br.BLOCKED)
        self.assertEqual(v["action"]["code"], "run_probe")

    def test_breaker_open(self):
        self.assertEqual(self._status(consecutive_failures=3), br.BLOCKED)
        self.assertEqual(self._status(consecutive_failures=2), br.SCHEDULER_ENABLED)

    def test_hard_blocker_precedence_order(self):
        # missing_bis must win over a (would-be) credential issue
        v = br.derive(_facts(bis_exists=False, credential_status="Expired"))
        self.assertEqual(v["blockers"][0]["code"], "missing_bis")

    def test_running_when_not_blocked(self):
        self.assertEqual(self._status(running=True), br.RUNNING)
        # but a hard blocker still wins over running
        self.assertEqual(self._status(running=True, enabled=0), br.BLOCKED)

    def test_never_synced_is_manual_pull(self):
        v = br.derive(_facts(last_sync_at=None, sync_age_minutes=None,
                             in_allowlist=False, last_run_state=None,
                             coverage_pct=None))
        self.assertEqual(v["status"], br.MANUAL_PULL)
        self.assertEqual(v["action"]["code"], "run_preview_then_pull")

    def test_stale_not_allowlisted_is_manual_pull(self):
        self.assertEqual(self._status(sync_age_minutes=120.0, in_allowlist=False),
                         br.MANUAL_PULL)

    def test_stale_while_allowlisted_is_warning(self):
        v = br.derive(_facts(sync_age_minutes=120.0, in_allowlist=True))
        self.assertEqual(v["status"], br.WARNING)
        self.assertTrue(any(b["code"] == "stale_sync_scheduled" for b in v["blockers"]))

    def test_no_kam_owner_warning(self):
        v = br.derive(_facts(kam_owner=None))
        self.assertEqual(v["status"], br.WARNING)
        self.assertTrue(any(b["code"] == "no_kam_owner" for b in v["blockers"]))

    def test_low_coverage_warning(self):
        v = br.derive(_facts(coverage_pct=20.0))
        self.assertEqual(v["status"], br.WARNING)
        self.assertTrue(any(b["code"] == "low_policy_coverage" for b in v["blockers"]))

    def test_coverage_none_does_not_warn(self):
        self.assertEqual(self._status(coverage_pct=None), br.SCHEDULER_ENABLED)

    def test_ready_when_fresh_but_not_allowlisted(self):
        v = br.derive(_facts(in_allowlist=False))
        self.assertEqual(v["status"], br.READY)
        self.assertEqual(v["action"]["code"], "add_to_scheduler")

    def test_status_enum_is_closed_set(self):
        valid = {br.BLOCKED, br.RUNNING, br.MANUAL_PULL, br.WARNING,
                 br.SCHEDULER_ENABLED, br.READY}
        # exercise a spread of profiles
        for kw in ({}, {"ba_exists": False}, {"bis_exists": False},
                   {"enabled": 0}, {"dry_run_stock_lock": 0},
                   {"credential_status": "Expired"}, {"consecutive_failures": 5},
                   {"running": True}, {"last_sync_at": None, "sync_age_minutes": None,
                    "in_allowlist": False, "last_run_state": None},
                   {"kam_owner": None}, {"coverage_pct": 10.0},
                   {"in_allowlist": False}):
            self.assertIn(br.derive(_facts(**kw))["status"], valid)


# --- secret redaction (frappe-stubbed so it runs in the sandbox too) ---------

def _install_frappe_stub():
    if "frappe" in sys.modules and getattr(sys.modules["frappe"], "_g1_real", False):
        return
    try:
        import frappe  # noqa: F401  (real frappe present -> use it)
        return
    except Exception:
        pass
    f = types.ModuleType("frappe")
    f.whitelist = lambda *a, **k: (lambda fn: fn)
    f._ = lambda s: s
    f.throw = lambda *a, **k: (_ for _ in ()).throw(Exception("throw"))
    f.PermissionError = type("PermissionError", (Exception,), {})
    f.ValidationError = type("ValidationError", (Exception,), {})
    f.session = types.SimpleNamespace(user="Administrator")
    f.conf = {}
    f.get_roles = lambda *a, **k: []
    sys.modules["frappe"] = f
    futils = types.ModuleType("frappe.utils")
    for n in ("add_days", "get_datetime", "now_datetime", "nowdate"):
        setattr(futils, n, lambda *a, **k: None)
    sys.modules["frappe.utils"] = futils


class TestSecretRedaction(unittest.TestCase):
    def test_bis_field_allowlist_excludes_secrets(self):
        _install_frappe_stub()
        from ecentric_workspace.alerts import api_brands
        for secret in ("api_key", "api_secret", "token"):
            self.assertNotIn(secret, api_brands._BIS_FIELDS,
                             "%s must never be in the BIS projection" % secret)

    def test_status_order_covers_all_statuses(self):
        _install_frappe_stub()
        from ecentric_workspace.alerts import api_brands
        for st in (br.BLOCKED, br.WARNING, br.MANUAL_PULL, br.RUNNING,
                   br.READY, br.SCHEDULER_ENABLED):
            self.assertIn(st, api_brands._STATUS_ORDER)


if __name__ == "__main__":
    unittest.main()
