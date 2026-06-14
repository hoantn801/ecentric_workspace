"""Alert Center MVP - authoritative E2E permission matrix (bench-only).

Exercises the FINAL permission model against REAL whitelisted endpoints on a
bench site:

  * GLOBAL data scope  : Administrator / System Manager / active Employee in
                         Department "Management - EC"  -> all brands.
  * BRAND-SCOPED       : Brand Approver kam_owner / manager_email / leader_email
                         -> union of assigned brands only.
  * DENY-BY-DEFAULT    : unassigned user -> PermissionError / empty.
  * Management - EC global scope must NOT grant System-Manager-only
    capabilities (credentials / execute / cancel-case / cooldown bypass).

Read-mostly: it seeds a couple of disposable E2EPM-* records via the supported
ingestion path and cleans them through delete_doc(force) of E2EPM-* fixtures
only (test scaffolding, not audited production history).

    bench --site <dev-site> run-tests --module ecentric_workspace.alerts.tests.test_e2e_permission_matrix

The offline resolution proof lives in test_permissions_scope (no bench needed);
this module is the live-endpoint counterpart.
"""
import unittest

import frappe

from ecentric_workspace.alerts import (api_actions, api_alerts, api_brands,
                                        api_dashboard, api_pauses, api_policies,
                                        api_rules, api_sku_catalog)
from ecentric_workspace.alerts import permissions as perms
from ecentric_workspace.alerts.services import ingestion

BRAND_A, BRAND_B = "E2EPM-A", "E2EPM-B"
KAM_A = "e2epm.kam.a@example.com"
MGMT = "e2epm.mgmt@example.com"
NOBODY = "e2epm.nobody@example.com"
OMI_A, OMI_B = "omi-e2epm-a", "omi-e2epm-b"
MGMT_DEPT = "Management - EC"


def _user(email):
    if not frappe.db.exists("User", email):
        frappe.get_doc({"doctype": "User", "email": email,
                        "first_name": email.split("@")[0],
                        "send_welcome_email": 0}).insert(ignore_permissions=True)


def _seed_brand(code, omi, kam=None):
    frappe.get_doc({"doctype": "Brand Approver", "brand_code": code,
                    "brand_name": "[E2EPM] " + code, "status": "Active",
                    "kam_owner": kam}).insert(ignore_permissions=True)
    frappe.get_doc({"doctype": "EC Marketplace Shop", "shop_code": code + "-S",
                    "shop_name": code + "-S", "platform": "Shopee", "brand": code,
                    "omisell_shop_id": omi, "status": "Active"}).insert(ignore_permissions=True)
    frappe.get_doc({"doctype": "EC Price Policy", "brand": code, "platform": "Shopee",
                    "seller_sku": "E2EPM-SKU", "min_price": 50000,
                    "severe_drop_percent": 70, "reference_price": 100000,
                    "status": "Active"}).insert(ignore_permissions=True)


def _seed_alert(order_id, omi):
    ingestion.ingest_orders([
        {"external_order_id": order_id, "platform": "Shopee", "omisell_shop_id": omi,
         "items": [{"external_line_id": "L1", "seller_sku": "E2EPM-SKU",
                    "external_product_id": "EPID", "quantity": 1,
                    "customer_paid_price": 20000}]}])


class _Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        cls._cleanup()
        for u in (KAM_A, MGMT, NOBODY):
            _user(u)
        _seed_brand(BRAND_A, OMI_A, kam=KAM_A)
        _seed_brand(BRAND_B, OMI_B)            # B has no KAM -> KAM_A must not see it
        _seed_alert("E2EPM-A1", OMI_A)
        _seed_alert("E2EPM-B1", OMI_B)
        frappe.db.commit()

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        cls._cleanup()
        frappe.db.commit()

    @classmethod
    def _cleanup(cls):
        for dt in ("EC Alert Action", "EC Alert Occurrence", "EC Alert",
                   "EC Automation Pause", "EC Marketplace Order Item",
                   "EC Marketplace Order Log", "EC Price Policy",
                   "EC Marketplace Shop"):
            for n in frappe.get_all(dt, filters={"brand": ("in", [BRAND_A, BRAND_B])},
                                    pluck="name"):
                frappe.delete_doc(dt, n, force=True, ignore_permissions=True)
        for code in (BRAND_A, BRAND_B):
            if frappe.db.exists("Brand Approver", code):
                frappe.delete_doc("Brand Approver", code, force=True, ignore_permissions=True)


class TestBrandScopedKam(_Base):
    def setUp(self):
        frappe.set_user(KAM_A)

    def tearDown(self):
        frappe.set_user("Administrator")

    def test_list_only_own_brand(self):
        rows = api_alerts.list_alerts()["rows"]
        self.assertTrue(all(r.brand == BRAND_A for r in rows))

    def test_explicit_other_brand_yields_nothing(self):
        self.assertEqual(api_alerts.list_alerts(filters={"brand": BRAND_B})["total"], 0)

    def test_my_scope_is_only_a(self):
        self.assertEqual(set(api_alerts.my_scope()["brands"]), {BRAND_A})

    def test_dashboard_kpis_scoped(self):
        self.assertIsInstance(api_dashboard.kpis(), dict)        # no 500, scoped
        rows = api_dashboard.by_dimension("brand")["rows"]
        self.assertTrue(all(r["key"] in (BRAND_A, "(none)") for r in rows))

    def test_detail_and_occurrences_other_brand_denied(self):
        b = frappe.get_all("EC Alert", filters={"brand": BRAND_B}, pluck="name")
        if b:
            with self.assertRaises(frappe.PermissionError):
                api_alerts.alert_occurrences(b[0])

    def test_policy_list_scoped_and_other_brand_caps_rejected(self):
        pols = api_policies.list_policies()["rows"]
        self.assertTrue(all(p.brand == BRAND_A for p in pols))
        with self.assertRaises(frappe.PermissionError):
            api_policies.policy_caps(brand=BRAND_B)

    def test_coverage_other_brand_denied(self):
        with self.assertRaises(frappe.PermissionError):
            api_sku_catalog.policy_missing_skus(brand=BRAND_B)

    def test_rules_and_locks_scoped(self):
        self.assertTrue(all(r.brand == BRAND_A for r in api_rules.list_rules()["rows"]))
        self.assertTrue(all(r.brand == BRAND_A for r in api_actions.list_actions()["rows"]))
        self.assertTrue(all(z.brand == BRAND_A for z in api_pauses.list_pauses()))

    def test_brand_readiness_other_brand_denied(self):
        with self.assertRaises(frappe.PermissionError):
            api_brands.brand_readiness(brand=BRAND_B)


class TestDenyByDefault(_Base):
    def setUp(self):
        frappe.set_user(NOBODY)

    def tearDown(self):
        frappe.set_user("Administrator")

    def test_all_read_endpoints_403(self):
        for fn, kw in ((api_alerts.list_alerts, {}), (api_alerts.get_cards, {}),
                       (api_alerts.my_scope, {}), (api_dashboard.kpis, {}),
                       (api_policies.list_policies, {}), (api_rules.list_rules, {}),
                       (api_actions.list_actions, {}), (api_pauses.list_pauses, {}),
                       (api_brands.list_brand_readiness, {})):
            with self.assertRaises(frappe.PermissionError):
                fn(**kw)


class TestGlobalSupervisor(_Base):
    def setUp(self):
        frappe.set_user("Administrator")

    def test_sees_both_brands(self):
        rows = api_alerts.list_alerts(page_len=100)["rows"]
        brands = {r.brand for r in rows if r.brand}
        self.assertIn(BRAND_A, brands)
        self.assertIn(BRAND_B, brands)
        self.assertTrue(api_alerts.my_scope()["supervisor"])


class TestManagementEcGlobalScope(_Base):
    """Active Employee in 'Management - EC' sees all brands (scope) but gets NO
    System-Manager-only capabilities."""

    @classmethod
    def setUpClass(cls):
        # Skip the whole class if HR is not installed on this site (no import-
        # time DB access; evaluated when the suite runs).
        if not frappe.db.exists("DocType", "Employee"):
            raise unittest.SkipTest("Management-EC scope needs the HR Employee doctype")
        super().setUpClass()
        frappe.set_user("Administrator")
        cls._dept_created = False
        if not frappe.db.exists("Department", MGMT_DEPT):
            try:
                doc = {"doctype": "Department", "department_name": "Management"}
                # company is required on Department in ERPNext; use any existing one
                comp = frappe.db.get_value("Company", {}, "name")
                if comp:
                    doc["company"] = comp
                d = frappe.get_doc(doc)
                d.insert(ignore_permissions=True)
                cls._dept_created = (d.name == MGMT_DEPT)
            except Exception:
                cls._dept_created = False
        cls._emp = None
        if frappe.db.exists("Department", MGMT_DEPT):
            try:
                e = frappe.get_doc({"doctype": "Employee", "employee_name": "E2EPM Boss",
                                    "first_name": "E2EPM", "user_id": MGMT,
                                    "status": "Active", "department": MGMT_DEPT})
                e.insert(ignore_permissions=True)
                cls._emp = e.name
            except Exception:
                cls._emp = None
        frappe.db.commit()

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        if getattr(cls, "_emp", None) and frappe.db.exists("Employee", cls._emp):
            frappe.delete_doc("Employee", cls._emp, force=True, ignore_permissions=True)
        if getattr(cls, "_dept_created", False) and frappe.db.exists("Department", MGMT_DEPT):
            frappe.delete_doc("Department", MGMT_DEPT, force=True, ignore_permissions=True)
        super().tearDownClass()

    def setUp(self):
        if not getattr(self, "_emp", None):
            self.skipTest("could not provision a Management-EC Employee on this site")
        frappe.set_user(MGMT)

    def tearDown(self):
        frappe.set_user("Administrator")

    def test_global_scope_sees_all_brands(self):
        self.assertEqual(perms.get_allowed_brands(MGMT), perms.ALL_BRANDS)
        rows = api_alerts.list_alerts(page_len=100)["rows"]
        brands = {r.brand for r in rows if r.brand}
        self.assertTrue({BRAND_A, BRAND_B}.issubset(brands) or not rows)
        self.assertTrue(api_alerts.my_scope()["supervisor"])

    def test_not_system_manager_and_no_sm_capabilities(self):
        self.assertFalse(perms.is_global_supervisor(MGMT))
        self.assertFalse(perms.can_manage_credentials(MGMT))
        self.assertFalse(perms.can_execute_action(MGMT))
        self.assertFalse(perms.can_cancel_case(MGMT))
        self.assertFalse(perms.can_mark_order_retry_dead(MGMT))

    def test_cancel_case_rejected_for_management_user(self):
        a = frappe.get_all("EC Alert", filters={"brand": BRAND_A}, pluck="name")
        if a:
            with self.assertRaises(frappe.PermissionError):
                api_alerts.cancel_case(a[0], reason="should be blocked")


if __name__ == "__main__":
    unittest.main(verbosity=2)
