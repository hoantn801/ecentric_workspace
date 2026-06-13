"""Step 1 lifecycle tests (2026-06-13) - status model + terminal guards.

Layers:
  * PURE (case_lifecycle): active/terminal sets, transition matrix, receive-
    occurrence rule, legacy-Resolved-as-terminal.
  * SOURCE-TEXT wiring: every guarded path actually references the shared
    helper (engine lookup, _bump_case, _recalc, api set_status/bulk/cancel,
    controller freeze) - no ad-hoc status list survives.
  * PATCH static: p002 is idempotent + raw-SQL + reports count.
  * BENCH (auto-skipped without a site): real occurrence-append rejection +
    migration behavior.

    bench --site <dev-site> run-tests --module ecentric_workspace.alerts.tests.test_case_lifecycle
"""
import os
import sys
import types
import unittest

from ecentric_workspace.alerts.services import case_lifecycle as cl


class TestStatusSets(unittest.TestCase):
    def test_canonical_sets(self):
        self.assertEqual(cl.ACTIVE_STATUSES, ("Open", "In Review"))
        self.assertEqual(cl.TERMINAL_STATUSES, ("Closed", "Ignored", "Cancelled"))
        self.assertEqual(cl.LEGACY_TERMINAL, ("Resolved",))

    def test_is_active_terminal(self):
        for s in ("Open", "In Review"):
            self.assertTrue(cl.is_active(s))
            self.assertFalse(cl.is_terminal(s))
        for s in ("Closed", "Ignored", "Cancelled", "Resolved"):
            self.assertTrue(cl.is_terminal(s), s)
            self.assertFalse(cl.is_active(s), s)

    def test_legacy_resolved_is_terminal(self):
        """Transitional read-compat: a half-migrated DB never lets Resolved
        re-accept evidence."""
        self.assertTrue(cl.is_terminal("Resolved"))
        self.assertFalse(cl.can_receive_occurrence("Resolved"))

    def test_can_receive_occurrence_only_active(self):
        self.assertTrue(cl.can_receive_occurrence("Open"))
        self.assertTrue(cl.can_receive_occurrence("In Review"))
        for s in ("Closed", "Ignored", "Cancelled", "Resolved"):
            self.assertFalse(cl.can_receive_occurrence(s), s)


class TestTransitionMatrix(unittest.TestCase):
    def test_allowed_normal(self):
        for frm, to in (("Open", "In Review"), ("Open", "Closed"),
                        ("Open", "Ignored"), ("In Review", "Closed"),
                        ("In Review", "Ignored")):
            self.assertTrue(cl.can_transition(frm, to), (frm, to))

    def test_same_state_noop_allowed(self):
        self.assertTrue(cl.can_transition("In Review", "In Review"))

    def test_no_reopen(self):
        for frm in ("Closed", "Ignored", "Cancelled", "Resolved"):
            for to in ("Open", "In Review"):
                self.assertFalse(cl.can_transition(frm, to), (frm, to))

    def test_in_review_cannot_go_back_to_open(self):
        self.assertFalse(cl.can_transition("In Review", "Open"))

    def test_cancel_only_from_active(self):
        self.assertTrue(cl.can_cancel("Open"))
        self.assertTrue(cl.can_cancel("In Review"))
        for s in ("Closed", "Ignored", "Cancelled", "Resolved"):
            self.assertFalse(cl.can_cancel(s), s)


def _src(rel):
    path = os.path.join(os.path.dirname(__file__), "..", rel)
    with open(os.path.abspath(path), "r", encoding="utf-8") as fh:
        return fh.read()


class TestGuardedPathsWired(unittest.TestCase):
    def test_engine_lookup_uses_shared_active(self):
        s = _src("services/alert_engine.py")
        self.assertIn("list(case_lifecycle.ACTIVE_STATUSES)", s)
        self.assertNotIn('["Open", "In Review"]', s)  # no ad-hoc list left

    def test_bump_case_rejects_terminal(self):
        body = _src("services/alert_engine.py").split("def _bump_case")[1]
        self.assertIn("case_lifecycle.is_terminal(case.status)", body)
        # guard precedes the count increment
        self.assertLess(body.find("is_terminal"),
                        body.find("occurrence_count = int"))

    def test_repair_recalc_guards_terminal(self):
        s = _src("api_repair.py")
        self.assertIn("ACTIVE = cl.ACTIVE_STATUSES", s)
        body = s.split("def _recalc")[1]
        self.assertIn("cl.is_terminal(case.status)", body)
        self.assertLess(body.find("is_terminal"), body.find("len(occ)"))

    def test_controller_guards(self):
        s = _src("doctype/ec_alert/ec_alert.py")
        self.assertIn("def _guard_no_reopen", s)
        self.assertIn("def _guard_terminal_evidence_frozen", s)
        self.assertIn("cl.is_terminal(before.status)", s)
        for f in ("occurrence_count", "first_seen_at", "last_seen_at"):
            self.assertIn(f, s)

    def test_api_status_consts_and_transition_guard(self):
        s = _src("api_alerts.py")
        self.assertIn('HANDLE_STATUSES = ("In Review", "Closed", "Ignored")', s)
        self.assertIn('NOTE_REQUIRED = ("Closed", "Ignored")', s)
        self.assertIn("cl.can_transition(doc.status, new_status)", s)
        # Resolved must not appear as a WRITABLE status literal (HANDLE list /
        # set_status / cancel). It may appear only via cl.LEGACY_TERMINAL.
        self.assertNotIn('new_status = "Resolved"', s)
        self.assertNotIn('"Resolved",', s)  # no Resolved in any literal tuple here

    def test_cancel_case_supervisor_only_reason_required(self):
        s = _src("api_alerts.py")
        body = s.split("def cancel_case")[1]
        self.assertIn("perms.can_cancel_case(frappe.session.user)", body)
        self.assertIn("reason is required", body)
        self.assertIn('doc.status = "Cancelled"', body)
        self.assertIn("cl.can_cancel(doc.status)", body)

    def test_permission_cancel_is_global_only(self):
        s = _src("permissions.py")
        body = s.split("def can_cancel_case")[1]
        self.assertIn("is_global_supervisor(user)", body)
        self.assertNotIn("kam", body.split("return")[1])

    def test_no_new_resolved_written_in_engine(self):
        eng = _src("services/alert_engine.py")
        self.assertNotIn('"Resolved"', eng)


class TestCompletedKpiClassification(unittest.TestCase):
    """Blocker 1 (release gate 2026-06-13): dashboard completed-KPI must count
    Closed AND legacy Resolved, keep Ignored separate, exclude Cancelled.
    Proven on the canonical status set (deterministic, no DB needed)."""

    def test_closed_counts_as_completed(self):
        self.assertIn("Closed", cl.COMPLETED_STATUSES)

    def test_legacy_resolved_counts_during_transition(self):
        self.assertIn("Resolved", cl.COMPLETED_STATUSES)

    def test_ignored_separate_from_completed(self):
        self.assertNotIn("Ignored", cl.COMPLETED_STATUSES)

    def test_cancelled_excluded_from_completed_kpi(self):
        self.assertNotIn("Cancelled", cl.COMPLETED_STATUSES)

    def test_active_not_completed(self):
        for s in cl.ACTIVE_STATUSES:
            self.assertNotIn(s, cl.COMPLETED_STATUSES)

    def test_completed_set_exact(self):
        self.assertEqual(set(cl.COMPLETED_STATUSES), {"Closed", "Resolved"})


class TestDashboardWired(unittest.TestCase):
    @property
    def src(self):
        return _src("api_dashboard.py")

    def test_kpis_use_completed_set_not_resolved_literal(self):
        s = self.src
        self.assertIn("COMPLETED_STATUSES = list(cl.COMPLETED_STATUSES)", s)
        kpis = s.split("def kpis")[1].split("def by_dimension")[0]
        self.assertIn('["status", "in", COMPLETED_STATUSES]', kpis)
        self.assertNotIn('"status", "=", "Resolved"', kpis)
        # Cancelled never counted in the handled KPI (ignore comment lines)
        code = "\n".join(ln.split("#", 1)[0] for ln in kpis.splitlines())
        self.assertNotIn("Cancelled", code)

    def test_trend_uses_completed_set(self):
        body = self.src.split("def trend")[1].split("def hourly_trend")[0]
        self.assertIn('["status", "in", COMPLETED_STATUSES]', body)
        self.assertNotIn('"status", "=", "Resolved"', body)

    def test_active_status_shared(self):
        s = self.src
        self.assertIn("ACTIVE_STATUSES = list(cl.ACTIVE_STATUSES)", s)
        self.assertNotIn('["status", "in", ["Open", "In Review"]]', s)


class TestStatusOptions(unittest.TestCase):
    """Blocker 2: Resolved removed from the selectable Select options."""

    def test_options_exact(self):
        import json
        path = os.path.join(os.path.dirname(__file__), "..",
                            "doctype", "ec_alert", "ec_alert.json")
        d = json.load(open(os.path.abspath(path), encoding="utf-8"))
        opts = [f for f in d["fields"] if f["fieldname"] == "status"][0]["options"]
        self.assertEqual(opts.split("\n"),
                         ["Open", "In Review", "Closed", "Ignored", "Cancelled"])
        self.assertNotIn("Resolved", opts)


class TestPatchStatic(unittest.TestCase):
    def test_patch_idempotent_sql_and_count(self):
        s = _src("patches/p002_migrate_resolved_to_closed.py")
        self.assertIn("def execute():", s)
        self.assertIn("SET status = 'Closed' WHERE status = 'Resolved'", s)
        self.assertIn("COUNT(*)", s)          # reports affected count
        self.assertIn('if affected == 0:', s)  # idempotent no-op
        self.assertNotIn(".save(", s)          # raw SQL, bypasses controller

    def test_patch_registered(self):
        reg = _src("../patches.txt")
        self.assertIn("alerts.patches.p002_migrate_resolved_to_closed", reg)


# --------------------------- permission unit (stubbed) ----------------------

def _stub_frappe_for_perms():
    if "frappe" in sys.modules and hasattr(sys.modules["frappe"], "get_roles"):
        return
    f = types.ModuleType("frappe")
    f._ = lambda s: s
    f.session = types.SimpleNamespace(user="Administrator")
    f._roles = {}
    f.get_roles = lambda user=None: f._roles.get(user or f.session.user, [])
    sys.modules["frappe"] = f


class TestCancelPermissionUnit(unittest.TestCase):
    def setUp(self):
        _stub_frappe_for_perms()
        from ecentric_workspace.alerts import permissions as perms
        self.perms = perms
        self._orig = perms.is_global_supervisor

    def tearDown(self):
        self.perms.is_global_supervisor = self._orig

    def test_sm_allowed_kam_manager_denied(self):
        self.perms.is_global_supervisor = lambda u=None: u == "admin@x"
        self.assertTrue(self.perms.can_cancel_case("admin@x"))
        self.assertFalse(self.perms.can_cancel_case("kam@x"))
        self.assertFalse(self.perms.can_cancel_case("manager@x"))


if __name__ == "__main__":
    unittest.main()
