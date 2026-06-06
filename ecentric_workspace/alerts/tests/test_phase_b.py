"""Alert Center Phase B tests - schema + service-layer permission.

Run on a local bench dev site (NOT production):
    bench --site <dev-site> run-tests --module ecentric_workspace.alerts.tests.test_phase_b

Covers plan 01_PHASE_B_PLAN.md s7 cases 1-10. Creates [ALERT TEST] prefixed
records and cleans them up; safe to re-run.
"""

import frappe
import unittest

from ecentric_workspace.alerts import permissions as perms

ALERT_DOCTYPES = [
    "EC Marketplace Shop",
    "EC Brand Integration Settings",
    "EC Price Policy",
    "EC Marketplace Order Log",
    "EC Marketplace Order Item",
    "EC Alert",
    "EC Alert Action",
    "EC Automation Pause",
]

TEST_BRAND_A = "ALERTTEST-A"
TEST_BRAND_B = "ALERTTEST-B"
TEST_USERS = {
    "kam_a": "alerttest.kam.a@example.com",
    "mgr_a": "alerttest.mgr.a@example.com",
    "lead_a": "alerttest.lead.a@example.com",
    "kam_b": "alerttest.kam.b@example.com",
    "nobody": "alerttest.nobody@example.com",
}


def _ensure_user(email):
    if not frappe.db.exists("User", email):
        frappe.get_doc({
            "doctype": "User",
            "email": email,
            "first_name": email.split("@")[0],
            "send_welcome_email": 0,
        }).insert(ignore_permissions=True)


def _ensure_brand(code, kam=None, manager=None, leader=None):
    if frappe.db.exists("Brand Approver", code):
        frappe.delete_doc("Brand Approver", code, force=True, ignore_permissions=True)
    doc = frappe.get_doc({
        "doctype": "Brand Approver",
        "brand_code": code,
        "brand_name": "[ALERT TEST] " + code,
        "status": "Active",
        "kam_owner": kam,
        "manager_email": manager,
        "leader_email": leader,
    })
    doc.insert(ignore_permissions=True)
    return doc


class TestAlertCenterPhaseB(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        for email in TEST_USERS.values():
            _ensure_user(email)
        _ensure_brand(TEST_BRAND_A, kam=TEST_USERS["kam_a"],
                      manager=TEST_USERS["mgr_a"], leader=TEST_USERS["lead_a"])
        _ensure_brand(TEST_BRAND_B, kam=TEST_USERS["kam_b"])

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        for dt in ["EC Automation Pause", "EC Alert Action", "EC Alert",
                   "EC Marketplace Order Log", "EC Price Policy",
                   "EC Brand Integration Settings", "EC Marketplace Shop"]:
            for name in frappe.get_all(dt, filters={"brand": ("in", [TEST_BRAND_A, TEST_BRAND_B])},
                                       pluck="name", ignore_permissions=True):
                frappe.delete_doc(dt, name, force=True, ignore_permissions=True)
        for code in (TEST_BRAND_A, TEST_BRAND_B):
            if frappe.db.exists("Brand Approver", code):
                frappe.delete_doc("Brand Approver", code, force=True, ignore_permissions=True)
        frappe.db.commit()

    def setUp(self):
        frappe.set_user("Administrator")

    # 1-2. DocTypes exist, module Alerts, track_changes
    def test_01_schema_exists_and_tracked(self):
        for dt in ALERT_DOCTYPES:
            self.assertTrue(frappe.db.exists("DocType", dt), dt + " missing")
            meta = frappe.get_meta(dt)
            self.assertEqual(meta.module, "Alerts", dt)
            self.assertEqual(int(meta.track_changes or 0), 1, dt + " track_changes")

    # 3. Unique constraints
    def test_03_unique_dedupe(self):
        def mk_alert(key):
            return frappe.get_doc({
                "doctype": "EC Alert", "alert_type": "Price Compliance",
                "severity": "Warning", "status": "Open",
                "brand": TEST_BRAND_A, "title": "[ALERT TEST] dup",
                "dedupe_key": key,
            }).insert(ignore_permissions=True)

        key = "omisell|TESTORD1|L1|price|below_min"
        mk_alert(key)
        with self.assertRaises(Exception):
            mk_alert(key)
        frappe.db.rollback()

    # 4. kam_owner custom field on Brand Approver
    def test_04_kam_owner_field(self):
        df = frappe.get_meta("Brand Approver").get_field("kam_owner")
        self.assertIsNotNone(df, "Brand Approver.kam_owner missing (fixture not synced?)")
        self.assertEqual(df.fieldtype, "Link")
        self.assertEqual(df.options, "User")

    # 5. Link integrity
    def test_05_link_targets(self):
        m = frappe.get_meta("EC Alert")
        self.assertEqual(m.get_field("brand").options, "Brand Approver")
        self.assertEqual(m.get_field("shop").options, "EC Marketplace Shop")
        self.assertEqual(m.get_field("item").options, "Item")
        self.assertEqual(m.get_field("reference_name").fieldtype, "Dynamic Link")
        with self.assertRaises(Exception):
            frappe.get_doc({
                "doctype": "EC Alert", "alert_type": "Price Compliance",
                "severity": "Info", "status": "Open",
                "brand": "NO-SUCH-BRAND-XYZ",
            }).insert(ignore_permissions=True)
        frappe.db.rollback()

    # 6. BIS uniqueness + dry-run default + perm lockdown
    def test_06_integration_settings(self):
        bis = frappe.get_doc({
            "doctype": "EC Brand Integration Settings",
            "brand": TEST_BRAND_A, "integration_type": "Omisell",
        }).insert(ignore_permissions=True)
        self.assertEqual(int(bis.dry_run_stock_lock), 1, "dry_run default must be 1")
        self.assertEqual(bis.credential_status, "Inactive")
        with self.assertRaises(Exception):
            frappe.get_doc({
                "doctype": "EC Brand Integration Settings",
                "brand": TEST_BRAND_A, "integration_type": "Omisell",
            }).insert(ignore_permissions=True)
        frappe.db.rollback()

    # 7. Policy validation
    def test_07_policy_validation(self):
        with self.assertRaises(Exception):  # dates inverted
            frappe.get_doc({
                "doctype": "EC Price Policy", "brand": TEST_BRAND_A,
                "platform": "All", "seller_sku": "TESTSKU",
                "effective_from": "2026-06-10", "effective_to": "2026-06-01",
            }).insert(ignore_permissions=True)
        with self.assertRaises(Exception):  # no target, no fallback flag
            frappe.get_doc({
                "doctype": "EC Price Policy", "brand": TEST_BRAND_A,
                "platform": "All",
            }).insert(ignore_permissions=True)
        ok = frappe.get_doc({  # explicit brand fallback allowed
            "doctype": "EC Price Policy", "brand": TEST_BRAND_A,
            "platform": "All", "is_brand_fallback": 1, "min_price": 10000,
        }).insert(ignore_permissions=True)
        self.assertEqual(float(ok.severe_drop_percent), 70.0)
        frappe.db.rollback()

    # 8. Permission matrix (service layer)
    def test_08_permission_matrix(self):
        u = TEST_USERS
        self.assertEqual(perms.get_allowed_brands(u["kam_a"]).get(TEST_BRAND_A), "kam")
        self.assertEqual(perms.get_allowed_brands(u["mgr_a"]).get(TEST_BRAND_A), "manager")
        self.assertEqual(perms.get_allowed_brands(u["lead_a"]).get(TEST_BRAND_A), "leader")
        self.assertNotIn(TEST_BRAND_B, perms.get_allowed_brands(u["kam_a"]))
        self.assertEqual(perms.get_allowed_brands(u["nobody"]), {})
        self.assertEqual(perms.get_allowed_brands("Administrator"), perms.ALL_BRANDS)

        self.assertTrue(perms.can_handle_alert(u["kam_a"], TEST_BRAND_A))
        self.assertTrue(perms.can_handle_alert(u["lead_a"], TEST_BRAND_A))
        self.assertFalse(perms.can_handle_alert(u["kam_a"], TEST_BRAND_B))

        self.assertTrue(perms.can_create_pause(u["kam_a"], TEST_BRAND_A))
        self.assertTrue(perms.can_create_pause(u["mgr_a"], TEST_BRAND_A))
        self.assertFalse(perms.can_create_pause(u["lead_a"], TEST_BRAND_A))
        self.assertFalse(perms.can_create_pause(u["kam_a"], TEST_BRAND_B))

        self.assertTrue(perms.can_cancel_pause(u["mgr_a"], TEST_BRAND_A))
        self.assertTrue(perms.can_cancel_pause(u["lead_a"], TEST_BRAND_A))
        self.assertFalse(perms.can_cancel_pause(u["kam_a"], TEST_BRAND_A))

        for email in u.values():
            self.assertFalse(perms.can_manage_credentials(email))
            self.assertFalse(perms.can_execute_action(email))

        with self.assertRaises(frappe.PermissionError):
            frappe.set_user(u["nobody"])
            try:
                perms.require_alert_center_access()
            finally:
                frappe.set_user("Administrator")

    # 9. Desk lockdown: non-SM cannot read Alert Center doctypes
    def test_09_desk_lockdown(self):
        frappe.set_user(TEST_USERS["kam_a"])
        try:
            self.assertFalse(frappe.has_permission("EC Alert", "read"))
            self.assertFalse(frappe.has_permission("EC Brand Integration Settings", "read"))
            self.assertFalse(frappe.has_permission("EC Alert", "delete"))
        finally:
            frappe.set_user("Administrator")

    # 10. Order log dedupe key
    def test_10_order_key(self):
        log = frappe.get_doc({
            "doctype": "EC Marketplace Order Log",
            "source_system": "Omisell", "external_order_id": " ORD-001 ",
            "brand": TEST_BRAND_A,
        }).insert(ignore_permissions=True)
        self.assertEqual(log.order_key, "Omisell|ORD-001")
        with self.assertRaises(Exception):
            frappe.get_doc({
                "doctype": "EC Marketplace Order Log",
                "source_system": "Omisell", "external_order_id": "ORD-001",
                "brand": TEST_BRAND_A,
            }).insert(ignore_permissions=True)
        frappe.db.rollback()
