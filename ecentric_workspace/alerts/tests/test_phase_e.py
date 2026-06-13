"""Alert Center Phase E tests - scoped UI endpoints + schedulers + D3 fields.
Needs a bench site:
    bench --site <dev-site> run-tests --module ecentric_workspace.alerts.tests.test_phase_e
ALERTE-* prefixed records, self-cleaning, safe to re-run.
"""
import unittest

import frappe
from frappe.utils import add_days, add_to_date, now_datetime

from ecentric_workspace.alerts import api_actions, api_alerts, api_pauses, tasks
from ecentric_workspace.alerts.services import ingestion

BRAND_A, BRAND_B = "ALERTE-A", "ALERTE-B"
KAM_A = "alerte.kam.a@example.com"
LEAD_A = "alerte.lead.a@example.com"
NOBODY = "alerte.nobody@example.com"
OMI_A, OMI_B = "omi-alerte-a", "omi-alerte-b"


def _user(email):
    if not frappe.db.exists("User", email):
        frappe.get_doc({"doctype": "User", "email": email, "first_name": email.split("@")[0],
                        "send_welcome_email": 0}).insert(ignore_permissions=True)


class TestPhaseE(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        cls._cleanup()
        for u in (KAM_A, LEAD_A, NOBODY):
            _user(u)
        frappe.get_doc({"doctype": "Brand Approver", "brand_code": BRAND_A,
                        "brand_name": "[ALERTE] A", "status": "Active",
                        "kam_owner": KAM_A, "leader_email": LEAD_A}).insert(ignore_permissions=True)
        frappe.get_doc({"doctype": "Brand Approver", "brand_code": BRAND_B,
                        "brand_name": "[ALERTE] B", "status": "Active"}).insert(ignore_permissions=True)
        for shop, omi, brand in ((BRAND_A + "-S", OMI_A, BRAND_A), (BRAND_B + "-S", OMI_B, BRAND_B)):
            frappe.get_doc({"doctype": "EC Marketplace Shop", "shop_code": shop,
                            "shop_name": shop, "platform": "Shopee", "brand": brand,
                            "omisell_shop_id": omi, "status": "Active"}).insert(ignore_permissions=True)
        for brand in (BRAND_A, BRAND_B):
            frappe.get_doc({"doctype": "EC Price Policy", "brand": brand, "platform": "Shopee",
                            "seller_sku": "ALERTE-SKU", "min_price": 50000,
                            "severe_drop_percent": 70, "enable_stock_safety_lock": 1,
                            "reference_price": 100000,
                            "status": "Active"}).insert(ignore_permissions=True)
        frappe.get_doc({"doctype": "EC Brand Integration Settings", "brand": BRAND_A,
                        "integration_type": "Omisell", "enabled": 1,
                        "credential_status": "Active", "api_key": "x",
                        "dry_run_stock_lock": 1}).insert(ignore_permissions=True)
        # seed alerts: A below_min, B below_min, A severe (lock-eligible, Medium conf)
        ingestion.ingest_orders([
            {"external_order_id": "ALERTE-A1", "platform": "Shopee", "omisell_shop_id": OMI_A,
             "items": [{"external_line_id": "L1", "seller_sku": "ALERTE-SKU",
                        "external_product_id": "EPID-1", "quantity": 1,
                        "customer_paid_price": 45000}]},
            {"external_order_id": "ALERTE-A2", "platform": "Shopee", "omisell_shop_id": OMI_A,
             "items": [{"external_line_id": "L1", "seller_sku": "ALERTE-SKU", "quantity": 1,
                        "customer_paid_price": 20000}]},
            {"external_order_id": "ALERTE-B1", "platform": "Shopee", "omisell_shop_id": OMI_B,
             "items": [{"external_line_id": "L1", "seller_sku": "ALERTE-SKU", "quantity": 1,
                        "customer_paid_price": 45000}]},
        ])

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        cls._cleanup()
        frappe.db.commit()

    @classmethod
    def _cleanup(cls):
        for dt in ("EC Alert Action", "EC Alert", "EC Automation Pause",
                   "EC Marketplace Order Log", "EC Price Policy",
                   "EC Brand Integration Settings", "EC Marketplace Shop"):
            for n in frappe.get_all(dt, filters={"brand": ("in", [BRAND_A, BRAND_B])}, pluck="name"):
                frappe.delete_doc(dt, n, force=True, ignore_permissions=True)
        for code in (BRAND_A, BRAND_B):
            if frappe.db.exists("Brand Approver", code):
                frappe.delete_doc("Brand Approver", code, force=True, ignore_permissions=True)

    def setUp(self):
        frappe.set_user("Administrator")

    # --- scope ---
    def test_01_unscoped_user_403(self):
        frappe.set_user(NOBODY)
        try:
            for fn, kw in ((api_alerts.list_alerts, {}), (api_alerts.get_cards, {}),
                           (api_alerts.my_scope, {}), (api_pauses.list_pauses, {}),
                           (api_actions.list_for_alert, {"alert": "x"})):
                with self.assertRaises(frappe.PermissionError):
                    fn(**kw)
        finally:
            frappe.set_user("Administrator")

    def test_02_kam_sees_only_own_brand(self):
        frappe.set_user(KAM_A)
        try:
            res = api_alerts.list_alerts()
            self.assertTrue(res["rows"])
            self.assertTrue(all(r.brand == BRAND_A for r in res["rows"]))
            # explicit filter for brand B yields nothing (scope intersection)
            res_b = api_alerts.list_alerts(filters={"brand": BRAND_B})
            self.assertEqual(res_b["total"], 0)
            scope = api_alerts.my_scope()
            self.assertEqual(list(scope["brands"]), [BRAND_A])
        finally:
            frappe.set_user("Administrator")

    def test_03_cards_match_sql(self):
        frappe.set_user(KAM_A)
        try:
            c = api_alerts.get_cards()
        finally:
            frappe.set_user("Administrator")
        raw = frappe.get_all("EC Alert", filters={"brand": BRAND_A,
                                                  "status": ("in", ["Open", "In Review"])})
        self.assertEqual(c["open"], len(raw))

    # --- status handling (canonical lifecycle: Closed is the completed
    # status; Resolved is NOT a writable target - Step 1, 2026-06-13) ---
    def test_04_set_status_rules(self):
        name = frappe.get_all("EC Alert", filters={"brand": BRAND_A},
                              pluck="name", limit_page_length=1)[0]
        frappe.set_user(KAM_A)
        try:
            # legacy Resolved must be REJECTED as a writable status (even with
            # a note) - it is no longer in HANDLE_STATUSES.
            with self.assertRaises(Exception):
                api_alerts.set_status(name, "Resolved", note="checked with shop")
            # Closed requires a note.
            with self.assertRaises(Exception):
                api_alerts.set_status(name, "Closed")
            api_alerts.set_status(name, "In Review")  # no note needed
            r = api_alerts.set_status(name, "Closed", note="checked with shop")
            self.assertEqual(r["status"], "Closed")
            self.assertEqual(r["resolved_by"], KAM_A)
            # terminal case must not reopen.
            with self.assertRaises(Exception):
                api_alerts.set_status(name, "In Review")
            b_alert = frappe.get_all("EC Alert", filters={"brand": BRAND_B},
                                     pluck="name", limit_page_length=1)[0]
            with self.assertRaises(frappe.PermissionError):
                api_alerts.set_status(b_alert, "In Review")
        finally:
            frappe.set_user("Administrator")

    # --- pauses ---
    def test_05_pause_permissions(self):
        args = dict(pause_from=str(now_datetime()),
                    pause_until=str(add_to_date(now_datetime(), hours=2)), reason="t")
        frappe.set_user(KAM_A)
        try:
            p = api_pauses.create_pause(brand=BRAND_A, **args)
            self.assertEqual(p["paused_by"], KAM_A)
            with self.assertRaises(frappe.PermissionError):
                api_pauses.create_pause(brand=BRAND_B, **args)
            with self.assertRaises(frappe.PermissionError):  # kam cannot cancel
                api_pauses.cancel_pause(p["name"])
        finally:
            frappe.set_user("Administrator")
        frappe.set_user(LEAD_A)
        try:
            with self.assertRaises(frappe.PermissionError):  # leader cannot create
                api_pauses.create_pause(brand=BRAND_A, **args)
            r = api_pauses.cancel_pause(p["name"])           # leader can cancel
            self.assertEqual(r["status"], "Cancelled")
        finally:
            frappe.set_user("Administrator")

    # --- schedulers ---
    def test_06_pause_expiry_job(self):
        doc = frappe.get_doc({"doctype": "EC Automation Pause",
                              "automation_type": "Stock Safety Lock", "brand": BRAND_A,
                              "platform": "All", "status": "Active",
                              "pause_from": add_days(now_datetime(), -2),
                              "pause_until": add_days(now_datetime(), -1),
                              "reason": "expired"})
        doc.insert(ignore_permissions=True)
        frappe.conf.ec_alerts_scheduler_disabled = 1
        try:
            tasks.expire_automation_pauses()
            self.assertEqual(frappe.db.get_value("EC Automation Pause", doc.name, "status"),
                             "Active")  # kill switch respected
        finally:
            frappe.conf.ec_alerts_scheduler_disabled = 0
        tasks.expire_automation_pauses()
        self.assertEqual(frappe.db.get_value("EC Automation Pause", doc.name, "status"), "Expired")
        tasks.expire_automation_pauses()  # idempotent
        self.assertEqual(frappe.db.get_value("EC Automation Pause", doc.name, "status"), "Expired")

    def test_07_queue_job_dry_run_only(self):
        tasks.process_action_queue_job()
        bad = frappe.get_all("EC Alert Action",
                             filters={"brand": ("in", [BRAND_A, BRAND_B]),
                                      "status": ("not in", ["Pending", "Dry Run", "Skipped", "Cancelled"])})
        self.assertEqual(bad, [])
        # the severe-drop A2 action must be Dry Run (BIS active + dry_run=1)
        acts = frappe.get_all("EC Alert Action",
                              filters={"brand": BRAND_A, "dedupe_key": ("like", "%ALERTE-A2%")},
                              fields=["status"])
        self.assertTrue(acts and acts[0].status == "Dry Run")

    # --- D3-E fields ---
    def test_08_d3_fields_persisted(self):
        self.assertIsNotNone(frappe.get_meta("EC Marketplace Order Item").get_field("external_product_id"))
        self.assertIsNotNone(frappe.get_meta("EC Marketplace Order Log").get_field("omisell_shop_id"))
        log = frappe.get_all("EC Marketplace Order Log",
                             filters={"external_order_id": "ALERTE-A1"}, pluck="name")[0]
        doc = frappe.get_doc("EC Marketplace Order Log", log)
        self.assertEqual(doc.omisell_shop_id, OMI_A)
        self.assertEqual(doc.items[0].external_product_id, "EPID-1")

    # --- actions read api ---
    def test_09_actions_scoped(self):
        a2 = frappe.get_all("EC Alert", filters={"brand": BRAND_A,
                                                 "rule_code": "severe_price_drop"},
                            pluck="name", limit_page_length=1)[0]
        frappe.set_user(KAM_A)
        try:
            rows = api_actions.list_for_alert(a2)
            self.assertTrue(rows)
            b1 = frappe.get_all("EC Alert", filters={"brand": BRAND_B},
                                pluck="name", limit_page_length=1)[0]
            with self.assertRaises(frappe.PermissionError):
                api_actions.list_for_alert(b1)
        finally:
            frappe.set_user("Administrator")
