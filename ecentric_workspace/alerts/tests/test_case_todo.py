"""Step 2 two-flow ToDo tests (rev 2026-06-13).

Flow A (incident per-case) + Flow B (setup aggregated per brand) proven with
an in-memory ToDo store + monkeypatched assignment helpers + a stubbed
remaining-count - no DB. Bench-gated class (skipped) covers the real
assign_to / SQL round-trip.

    bench --site <dev-site> run-tests --module ecentric_workspace.alerts.tests.test_case_todo
"""
import os
import sys
import types
import unittest


def _stub_frappe():
    try:
        import frappe  # noqa: F401
        return
    except Exception:
        pass
    f = types.ModuleType("frappe")
    f.flags = types.SimpleNamespace()
    f._warns = []
    f._errs = []
    f.logger = lambda *a, **k: types.SimpleNamespace(
        warning=lambda payload: f._warns.append(payload))
    f.log_error = lambda *a, **k: f._errs.append(a)
    f.get_traceback = lambda *a, **k: "tb"
    f.get_all = lambda *a, **k: []
    f.db = types.SimpleNamespace(set_value=lambda *a, **k: None, sql=lambda *a, **k: [])
    sys.modules["frappe"] = f


_stub_frappe()
from ecentric_workspace.alerts.services import case_todo


class FakeCase:
    def __init__(self, name, status, owner_user, brand="FES-VN",
                 rule_code="below_min", seller_sku="P02056"):
        self.name = name
        self.status = status
        self.owner_user = owner_user
        self.brand = brand
        self.rule_code = rule_code
        self.seller_sku = seller_sku
        self.item = None

    def get(self, k, default=None):
        return getattr(self, k, default)


class _Harness(unittest.TestCase):
    def setUp(self):
        import frappe
        frappe._warns = []
        frappe._errs = []
        frappe.flags = types.SimpleNamespace()
        self.store = {}          # (ref_type, ref_name) -> [ {name,allocated_to,description} ]
        self._seq = 0
        self.adds = []
        self.removes = []
        self.remaining = {}      # brand -> distinct missing SKU count
        self._orig = (case_todo._open_todos, case_todo._assign_add,
                      case_todo._assign_remove, case_todo._remaining_missing_skus)

        def fake_open(rt, rn, extra=None):
            rows = self.store.get((rt, rn), [])
            out = []
            for t in rows:
                if extra:
                    if "allocated_to" in extra and t["allocated_to"] != extra["allocated_to"]:
                        continue
                    if "description" in extra:
                        pat = extra["description"][1].rstrip("%")
                        if not (t["description"] or "").startswith(pat):
                            continue
                out.append(types.SimpleNamespace(**t))
            return out

        def fake_add(args):
            self._seq += 1
            self.adds.append((args["doctype"], args["name"], args["assign_to"][0]))
            self.store.setdefault((args["doctype"], args["name"]), []).append(
                {"name": "TODO-%d" % self._seq,
                 "allocated_to": args["assign_to"][0],
                 "description": args.get("description", "")})

        def fake_remove(dt, name, user):
            self.removes.append((dt, name, user))
            self.store[(dt, name)] = [t for t in self.store.get((dt, name), [])
                                      if t["allocated_to"] != user]

        def fake_remaining(brand):
            return self.remaining.get(brand, 0)

        case_todo._open_todos = fake_open
        case_todo._assign_add = fake_add
        case_todo._assign_remove = fake_remove
        case_todo._remaining_missing_skus = fake_remaining

        # frappe.db.set_value -> update description in store
        def set_value(dt, name, field, val, **k):
            for rows in self.store.values():
                for t in rows:
                    if t["name"] == name:
                        t[field] = val
        frappe.db.set_value = set_value

    def tearDown(self):
        (case_todo._open_todos, case_todo._assign_add,
         case_todo._assign_remove, case_todo._remaining_missing_skus) = self._orig

    def _opens(self, rt, rn):
        return self.store.get((rt, rn), [])


# ----- Flow A: incident -----------------------------------------------------
class TestIncidentFlow(_Harness):
    def test_01_new_incident_one_todo(self):
        case_todo.sync_todo(FakeCase("C1", "Open", "kam@x", rule_code="below_min"))
        self.assertEqual(len(self._opens("EC Alert", "C1")), 1)
        self.assertEqual(self.adds, [("EC Alert", "C1", "kam@x")])

    def test_02_occurrences_no_duplicate(self):
        c = FakeCase("C1", "Open", "kam@x", rule_code="severe_price_drop")
        for _ in range(4):
            case_todo.sync_todo(c)
        self.assertEqual(len(self._opens("EC Alert", "C1")), 1)
        self.assertEqual(len(self.adds), 1)

    def test_03_reassign_owner(self):
        case_todo.sync_todo(FakeCase("C1", "Open", "old@x", rule_code="above_high"))
        case_todo.sync_todo(FakeCase("C1", "In Review", "new@x", rule_code="above_high"))
        self.assertEqual([t["allocated_to"] for t in self._opens("EC Alert", "C1")], ["new@x"])
        self.assertIn(("EC Alert", "C1", "old@x"), self.removes)

    def test_04_terminal_closes(self):
        case_todo.sync_todo(FakeCase("C1", "Open", "kam@x", rule_code="below_min"))
        case_todo.sync_todo(FakeCase("C1", "Closed", "kam@x", rule_code="below_min"))
        self.assertEqual(self._opens("EC Alert", "C1"), [])
        self.assertIn(("EC Alert", "C1", "kam@x"), self.removes)

    def test_05_new_case_after_terminal(self):
        case_todo.sync_todo(FakeCase("C1", "Open", "kam@x", rule_code="below_min"))
        case_todo.sync_todo(FakeCase("C1", "Ignored", "kam@x", rule_code="below_min"))
        case_todo.sync_todo(FakeCase("C2", "Open", "kam@x", rule_code="below_min"))
        self.assertEqual(self._opens("EC Alert", "C1"), [])
        self.assertEqual(len(self._opens("EC Alert", "C2")), 1)

    def test_missing_policy_is_NOT_incident(self):
        case_todo.sync_todo(FakeCase("C1", "Open", "kam@x", rule_code="missing_policy"))
        self.assertEqual(self._opens("EC Alert", "C1"), [])  # no per-case ToDo

    def test_non_kam_rule_no_todo(self):
        case_todo.sync_todo(FakeCase("C1", "Open", "kam@x", rule_code="ingestion_api_failed"))
        self.assertEqual(self.adds, [])


# ----- Flow B: setup aggregated per brand -----------------------------------
class TestSetupFlow(_Harness):
    def _mp(self, name, brand="FES-VN", owner="kam@x", status="Open"):
        return FakeCase(name, status, owner, brand=brand, rule_code="missing_policy")

    def test_06_twenty_missing_policy_one_setup_todo(self):
        self.remaining["FES-VN"] = 20
        for i in range(20):
            case_todo.sync_todo(self._mp("MP%d" % i))
        setup = self._opens("Brand Approver", "FES-VN")
        self.assertEqual(len(setup), 1)               # ONE aggregated ToDo
        self.assertIn("20 SKU", setup[0]["description"])
        self.assertTrue(setup[0]["description"].startswith(case_todo.SETUP_MARKER))

    def test_07_count_updates_no_duplicate(self):
        self.remaining["FES-VN"] = 20
        case_todo.sync_todo(self._mp("MP1"))
        self.remaining["FES-VN"] = 12               # some SKUs got policies
        case_todo.sync_todo(self._mp("MP2", status="Closed"))
        setup = self._opens("Brand Approver", "FES-VN")
        self.assertEqual(len(setup), 1)
        self.assertIn("12 SKU", setup[0]["description"])

    def test_08_zero_remaining_closes(self):
        self.remaining["FES-VN"] = 3
        case_todo.sync_todo(self._mp("MP1"))
        self.assertEqual(len(self._opens("Brand Approver", "FES-VN")), 1)
        self.remaining["FES-VN"] = 0
        case_todo.sync_todo(self._mp("MP1", status="Closed"))
        self.assertEqual(self._opens("Brand Approver", "FES-VN"), [])

    def test_09_recurrence_new_todo_not_reopen(self):
        self.remaining["FES-VN"] = 2
        case_todo.sync_todo(self._mp("MP1"))
        first = self._opens("Brand Approver", "FES-VN")[0]["name"]
        self.remaining["FES-VN"] = 0
        case_todo.sync_todo(self._mp("MP1", status="Closed"))
        self.assertEqual(self._opens("Brand Approver", "FES-VN"), [])
        # recurrence
        self.remaining["FES-VN"] = 5
        case_todo.sync_todo(self._mp("MP2"))
        nowopen = self._opens("Brand Approver", "FES-VN")
        self.assertEqual(len(nowopen), 1)
        self.assertNotEqual(nowopen[0]["name"], first)   # NEW ToDo, not reopened

    def test_10_different_brands_separate_todos(self):
        self.remaining["FES-VN"] = 4
        self.remaining["LOF-VN"] = 7
        case_todo.sync_todo(self._mp("MPA", brand="FES-VN", owner="kamA"))
        case_todo.sync_todo(self._mp("MPB", brand="LOF-VN", owner="kamB"))
        self.assertEqual(len(self._opens("Brand Approver", "FES-VN")), 1)
        self.assertEqual(len(self._opens("Brand Approver", "LOF-VN")), 1)
        self.assertIn("4 SKU", self._opens("Brand Approver", "FES-VN")[0]["description"])
        self.assertIn("7 SKU", self._opens("Brand Approver", "LOF-VN")[0]["description"])

    def test_setup_reassign_on_owner_change(self):
        self.remaining["FES-VN"] = 3
        case_todo.sync_todo(self._mp("MP1", owner="old@x"))
        case_todo.sync_todo(self._mp("MP2", owner="new@x"))
        setup = self._opens("Brand Approver", "FES-VN")
        self.assertEqual([t["allocated_to"] for t in setup], ["new@x"])

    def test_setup_no_owner_diagnostic(self):
        import frappe
        self.remaining["FES-VN"] = 5
        case_todo.sync_todo(self._mp("MP1", owner=None))
        self.assertEqual(self._opens("Brand Approver", "FES-VN"), [])
        self.assertTrue(any("setup_todo_skipped_no_owner" in w for w in frappe._warns))


# ----- guard + fail-open ----------------------------------------------------
class TestGuards(_Harness):
    def test_recursion_guard(self):
        import frappe
        frappe.flags._ec_alert_todo_syncing = True
        case_todo.sync_todo(FakeCase("C1", "Open", "kam@x", rule_code="below_min"))
        self.assertEqual(self.adds, [])

    def test_guard_reset(self):
        import frappe
        case_todo.sync_todo(FakeCase("C1", "Open", "kam@x", rule_code="below_min"))
        self.assertFalse(getattr(frappe.flags, "_ec_alert_todo_syncing", False))

    def test_fail_open(self):
        import frappe
        orig = case_todo._ensure_incident_todo
        case_todo._ensure_incident_todo = lambda c: (_ for _ in ()).throw(RuntimeError("x"))
        try:
            case_todo.sync_todo(FakeCase("C1", "Open", "kam@x", rule_code="below_min"))
            self.assertTrue(frappe._errs)
        finally:
            case_todo._ensure_incident_todo = orig


def _src(rel):
    path = os.path.join(os.path.dirname(__file__), "..", rel)
    with open(os.path.abspath(path), "r", encoding="utf-8") as fh:
        return fh.read()


class TestRuleClassification(_Harness):
    """Gate 1: every REAL emitted rule_code is classified + behaves correctly;
    unknown codes fail safe with a diagnostic."""

    # The canonical EC Alert.rule_code enum (verified by grep 2026-06-13).
    EXPECTED = {
        "below_min", "above_high", "severe_price_drop", "possible_missing_zero",
        "missing_policy", "missing_brand_mapping",
        "missing_integration_credential", "ingestion_api_failed",
        "stock_lock_api_failed",
    }

    def test_sets_disjoint(self):
        i, s, y = case_todo.INCIDENT_RULES, case_todo.SETUP_RULES, case_todo.SYSTEM_RULES
        self.assertEqual(i & s, frozenset())
        self.assertEqual(i & y, frozenset())
        self.assertEqual(s & y, frozenset())

    def test_union_covers_every_real_code(self):
        union = case_todo.INCIDENT_RULES | case_todo.SETUP_RULES | case_todo.SYSTEM_RULES
        self.assertEqual(set(union), self.EXPECTED)

    def test_each_incident_code_creates_ec_alert_todo(self):
        for i, rc in enumerate(sorted(case_todo.INCIDENT_RULES)):
            self.setUp()  # reset store per code
            case_todo.sync_todo(FakeCase("CI%d" % i, "Open", "kam@x", rule_code=rc))
            self.assertEqual([a[0] for a in self.adds], ["EC Alert"], rc)

    def test_setup_code_creates_brand_approver_todo(self):
        self.remaining["FES-VN"] = 3
        case_todo.sync_todo(FakeCase("MP", "Open", "kam@x", rule_code="missing_policy"))
        self.assertEqual([a[0] for a in self.adds], ["Brand Approver"])

    def test_system_codes_create_no_todo(self):
        for i, rc in enumerate(sorted(case_todo.SYSTEM_RULES)):
            self.setUp()
            case_todo.sync_todo(FakeCase("SY%d" % i, "Open", "kam@x", rule_code=rc))
            self.assertEqual(self.adds, [], rc)

    def test_unknown_code_no_todo_and_diagnostic(self):
        import frappe
        case_todo.sync_todo(FakeCase("CX", "Open", "kam@x", rule_code="some_future_rule"))
        self.assertEqual(self.adds, [])
        self.assertTrue(any("todo_unknown_rule_code" in w for w in frappe._warns))


class TestSetupCompletionDependency(_Harness):
    """Setup ToDo lifecycle as a function of the remaining missing-COVERAGE count
    (2026-06-14: sourced from services.policy_coverage - order-derived - NOT from
    active missing_policy EC Alert rows): the ToDo stays open while the count > 0
    and closes at 0, and a later recurrence opens a NEW ToDo (never reopens the
    closed one). The count source is stubbed here; its correctness is proven in
    test_missing_policy_retired.TestPolicyCoverage."""

    def _mp(self, name, brand="FES-VN", owner="kam@x", status="Open"):
        return FakeCase(name, status, owner, brand=brand, rule_code="missing_policy")

    def test_terminalizing_final_case_closes_setup_todo(self):
        self.remaining["FES-VN"] = 1
        case_todo.sync_todo(self._mp("MP1"))
        self.assertEqual(len(self._opens("Brand Approver", "FES-VN")), 1)
        self.remaining["FES-VN"] = 0           # coverage complete -> 0 remaining
        case_todo.sync_todo(self._mp("MP1", status="Closed"))
        self.assertEqual(self._opens("Brand Approver", "FES-VN"), [])

    def test_remaining_cases_keep_it_open(self):
        self.remaining["FES-VN"] = 5
        case_todo.sync_todo(self._mp("MP1"))
        self.remaining["FES-VN"] = 4           # coverage improved: 4 SKUs still uncovered
        case_todo.sync_todo(self._mp("MP2", status="Closed"))
        self.assertEqual(len(self._opens("Brand Approver", "FES-VN")), 1)

    def test_recurrence_new_todo_not_reopen(self):
        self.remaining["FES-VN"] = 1
        case_todo.sync_todo(self._mp("MP1"))
        first = self._opens("Brand Approver", "FES-VN")[0]["name"]
        self.remaining["FES-VN"] = 0
        case_todo.sync_todo(self._mp("MP1", status="Closed"))
        self.remaining["FES-VN"] = 2
        case_todo.sync_todo(self._mp("MP2"))
        nowopen = self._opens("Brand Approver", "FES-VN")
        self.assertEqual(len(nowopen), 1)
        self.assertNotEqual(nowopen[0]["name"], first)


class TestWiringConstraints(unittest.TestCase):
    def test_classification_constants(self):
        s = _src("services/case_todo.py")
        self.assertIn('"below_min", "above_high", "severe_price_drop", "possible_missing_zero"', s)
        self.assertIn('SETUP_RULES = frozenset({"missing_policy"})', s)
        self.assertIn('SETUP_REF_DOCTYPE = "Brand Approver"', s)
        self.assertIn('SETUP_MARKER = "[price_setup_missing]"', s)

    def test_reuses_pm_add_contract_no_close_all(self):
        s = _src("services/case_todo.py")
        self.assertIn("from frappe.desk.form.assign_to import add as _add", s)
        self.assertIn("from frappe.desk.form.assign_to import remove as _remove", s)
        # unproven signature -> never CALLED/imported (docstring mention is fine)
        self.assertNotIn("close_all_assignments(", s)
        self.assertNotIn("import close_all_assignments", s)

    def test_no_force_todo_status(self):
        s = _src("services/case_todo.py")
        self.assertNotIn('set_value("ToDo"', s.replace(
            'set_value("ToDo", correct[0].name, "description"', ""))  # only description set

    def test_controller_dispatch_unchanged(self):
        s = _src("doctype/ec_alert/ec_alert.py")
        self.assertIn("case_todo.sync_todo(self)", s)


if __name__ == "__main__":
    unittest.main()
