"""Canonical brand-scope permission model (owner decision 2026-06-15).

Runs WITHOUT a bench/DB: a minimal frappe stub feeds controllable roles /
Employee rows / Brand Approver rows into ecentric_workspace.alerts.permissions,
so the FULL resolution logic (global scope, Management-Department global
access, brand-scoped union, deny-by-default, capability separation) is executed
for real.

Owner model:
  * Administrator / System Manager                 -> ALL_BRANDS
  * active Employee in Department "Management - EC" -> ALL_BRANDS (scope only)
  * else: UNION of brands from active Brand Approver rows
        (kam_owner / manager_email / leader_email)
  * no rows -> empty scope (NEVER all brands)

    bench run-tests --module ecentric_workspace.alerts.tests.test_permissions_scope
"""
import sys
import types
import unittest


class _AttrDict(dict):
    __getattr__ = dict.get


# --------------------------------------------------------------------------- #
# mutable stub state + a minimal `frappe` installed before importing perms     #
# --------------------------------------------------------------------------- #
class _State:
    roles = {}        # user -> [role, ...]
    employees = []    # [{user_id,status,department,name}, ...]
    brand_rows = []   # active Brand Approver rows (dicts)
    conf = {}


ST = _State()


def _install_stub_frappe():
    if "frappe" in sys.modules and not getattr(sys.modules["frappe"], "_ec_stub", False):
        return sys.modules["frappe"], False
    f = types.ModuleType("frappe")
    f._ec_stub = True

    class PermissionError(Exception):
        pass

    class ValidationError(Exception):
        pass

    f.PermissionError = PermissionError
    f.ValidationError = ValidationError
    f._ = lambda s, *a, **k: s
    f.conf = ST.conf
    f.session = types.SimpleNamespace(user="Guest")
    f.get_roles = lambda user=None: list(ST.roles.get(user, []))
    f.log_error = lambda *a, **k: None
    f.get_traceback = lambda: ""

    def throw(msg, exc=None):
        raise (exc or Exception)(msg)
    f.throw = throw

    def get_all(doctype, filters=None, fields=None, pluck=None, limit=None, **k):
        filters = filters or {}
        if doctype == "Employee":
            out = [e for e in ST.employees
                   if all(e.get(kk) == vv for kk, vv in filters.items())]
            if limit:
                out = out[:limit]
            return [e[pluck] for e in out] if pluck else [_AttrDict(**e) for e in out]
        if doctype == "Brand Approver":
            # the service asks for status=Active; ST.brand_rows are the active set
            return [_AttrDict(**r) for r in ST.brand_rows]
        return []
    f.get_all = get_all
    sys.modules["frappe"] = f
    return f, True


_FK, _IS_STUB = _install_stub_frappe()
from ecentric_workspace.alerts import permissions as perms  # noqa: E402


def _reset():
    ST.roles = {}
    ST.employees = []
    ST.brand_rows = []
    ST.conf.clear()


def _emp(user, dept="Management - EC", status="Active", name="E1"):
    return {"user_id": user, "status": status, "department": dept, "name": name}


def _ba(name, kam=None, manager=None, leader=None):
    return {"name": name, "kam_owner": kam, "manager_email": manager,
            "leader_email": leader}


@unittest.skipUnless(_IS_STUB, "runs on the stubbed-frappe harness")
class TestGlobalScope(unittest.TestCase):
    def setUp(self):
        _reset()

    def test_01_administrator_sees_all(self):
        self.assertEqual(perms.get_allowed_brands("Administrator"), perms.ALL_BRANDS)

    def test_02_system_manager_sees_all(self):
        ST.roles = {"sm@x": ["System Manager", "Employee"]}
        self.assertEqual(perms.get_allowed_brands("sm@x"), perms.ALL_BRANDS)

    def test_03_active_management_ec_employee_sees_all(self):
        ST.employees = [_emp("boss@x")]
        self.assertEqual(perms.get_allowed_brands("boss@x"), perms.ALL_BRANDS)

    def test_04a_inactive_management_employee_denied(self):
        ST.employees = [_emp("boss@x", status="Inactive")]
        self.assertEqual(perms.get_allowed_brands("boss@x"), {})   # deny, not all

    def test_04b_inactive_management_but_brand_scoped_gets_only_that_brand(self):
        ST.employees = [_emp("u@x", status="Left")]
        ST.brand_rows = [_ba("FES-VN", kam="u@x")]
        self.assertEqual(perms.get_allowed_brands("u@x"), {"FES-VN": "kam"})

    def test_05_employee_other_department_not_all(self):
        ST.employees = [_emp("u@x", dept="Sales - EC")]
        self.assertEqual(perms.get_allowed_brands("u@x"), {})       # not ALL_BRANDS

    def test_06_no_employee_mapping_not_all(self):
        ST.employees = []
        self.assertEqual(perms.get_allowed_brands("nobody@x"), {})  # deny-by-default

    def test_management_department_is_configurable(self):
        ST.conf["ec_alerts_management_department"] = "Management - XY"
        ST.employees = [_emp("u@x", dept="Management - XY")]
        self.assertEqual(perms.get_allowed_brands("u@x"), perms.ALL_BRANDS)


@unittest.skipUnless(_IS_STUB, "runs on the stubbed-frappe harness")
class TestBrandScopedUnion(unittest.TestCase):
    def setUp(self):
        _reset()

    def test_07_kam_single_brand(self):
        ST.brand_rows = [_ba("FES-VN", kam="kam@x")]
        self.assertEqual(perms.get_allowed_brands("kam@x"), {"FES-VN": "kam"})

    def test_08_kam_multiple_brands_union(self):
        ST.brand_rows = [_ba("FES-VN", kam="kam@x"), _ba("LOF-VN", kam="kam@x"),
                         _ba("OTH-VN", kam="someone@else")]
        self.assertEqual(perms.get_allowed_brands("kam@x"),
                         {"FES-VN": "kam", "LOF-VN": "kam"})

    def test_09_manager_single_and_multiple(self):
        ST.brand_rows = [_ba("FES-VN", manager="mgr@x")]
        self.assertEqual(perms.get_allowed_brands("mgr@x"), {"FES-VN": "manager"})
        ST.brand_rows = [_ba("FES-VN", manager="mgr@x"), _ba("LOF-VN", manager="mgr@x")]
        self.assertEqual(perms.get_allowed_brands("mgr@x"),
                         {"FES-VN": "manager", "LOF-VN": "manager"})

    def test_10_leader_single_and_multiple(self):
        ST.brand_rows = [_ba("FES-VN", leader="lead@x")]
        self.assertEqual(perms.get_allowed_brands("lead@x"), {"FES-VN": "leader"})
        ST.brand_rows = [_ba("FES-VN", leader="lead@x"), _ba("LOF-VN", leader="lead@x")]
        self.assertEqual(perms.get_allowed_brands("lead@x"),
                         {"FES-VN": "leader", "LOF-VN": "leader"})

    def test_strongest_role_wins_same_brand(self):
        # kam_owner AND manager_email both = user on the same row -> kam (rank 3).
        ST.brand_rows = [_ba("FES-VN", kam="u@x", manager="u@x")]
        self.assertEqual(perms.get_allowed_brands("u@x"), {"FES-VN": "kam"})

    def test_manager_email_is_brand_scoped_not_management_department(self):
        # manager_email grants ONLY that brand - it must NOT be confused with the
        # Management Department global grant.
        ST.brand_rows = [_ba("FES-VN", manager="mgr@x")]
        self.assertNotEqual(perms.get_allowed_brands("mgr@x"), perms.ALL_BRANDS)
        self.assertEqual(perms.get_brand_role("mgr@x", "FES-VN"), "manager")
        self.assertIsNone(perms.get_brand_role("mgr@x", "LOF-VN"))


@unittest.skipUnless(_IS_STUB, "runs on the stubbed-frappe harness")
class TestEnforcementPrimitives(unittest.TestCase):
    def setUp(self):
        _reset()
        ST.brand_rows = [_ba("FES-VN", kam="kam@x")]   # FES-only KAM

    def test_11_explicit_out_of_scope_brand_rejected(self):
        # require_brand_access raises; get_brand_role is None.
        self.assertIsNone(perms.get_brand_role("kam@x", "LOF-VN"))
        with self.assertRaises(_FK.PermissionError):
            perms.require_brand_access("kam@x", "LOF-VN")
        # own brand allowed
        perms.require_brand_access("kam@x", "FES-VN")

    def test_12_filter_brands_drops_unauthorized(self):
        # the primitive every list/aggregate/export endpoint uses to scope rows.
        self.assertEqual(
            perms.filter_brands("kam@x", ["FES-VN", "LOF-VN", "ZZZ"]), ["FES-VN"])
        # global user keeps everything
        self.assertEqual(
            perms.filter_brands("Administrator", ["FES-VN", "LOF-VN"]),
            ["FES-VN", "LOF-VN"])

    def test_13_dropdown_source_is_allowed_scope(self):
        # my_scope returns `allowed` for scoped users -> the brand <select> only
        # ever lists backend-allowed brands.
        allowed = perms.get_allowed_brands("kam@x")
        self.assertEqual(set(allowed), {"FES-VN"})
        self.assertNotIn("LOF-VN", allowed)

    def test_require_access_denies_unscoped_user(self):
        with self.assertRaises(_FK.PermissionError):
            perms.require_alert_center_access("nobody@x")
        # scoped user passes
        self.assertEqual(perms.require_alert_center_access("kam@x"),
                         {"FES-VN": "kam"})


@unittest.skipUnless(_IS_STUB, "runs on the stubbed-frappe harness")
class TestManagementDeptNoCapabilityEscalation(unittest.TestCase):
    """Management-Department employees get all-brand SCOPE but must NOT gain
    System-Manager-only capabilities (credential mgmt / action execution / case
    cancellation / forced cooldown bypass)."""

    def setUp(self):
        _reset()
        ST.employees = [_emp("boss@x")]   # active Management - EC

    def test_has_global_scope(self):
        self.assertEqual(perms.get_allowed_brands("boss@x"), perms.ALL_BRANDS)
        self.assertEqual(perms.get_brand_role("boss@x", "ANY-VN"), "supervisor")

    def test_not_a_system_manager(self):
        self.assertFalse(perms.is_global_supervisor("boss@x"))

    def test_no_sm_only_capabilities(self):
        self.assertFalse(perms.can_manage_credentials("boss@x"))
        self.assertFalse(perms.can_execute_action("boss@x"))
        self.assertFalse(perms.can_cancel_case("boss@x"))
        self.assertFalse(perms.can_mark_order_retry_dead("boss@x"))

    def test_can_handle_alerts_for_any_brand(self):
        # operational handling IS allowed (supervisor brand role).
        self.assertTrue(perms.can_handle_alert("boss@x", "FES-VN"))
        self.assertTrue(perms.can_manage_policy("boss@x", "LOF-VN"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
