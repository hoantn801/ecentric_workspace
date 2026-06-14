"""Alert Center Phase C integration tests - the 13 approved cases.
Needs a bench site (NOT runnable in the doc workspace):
    bench --site <dev-site> run-tests --module ecentric_workspace.alerts.tests.test_phase_c
Creates ALERTC-* prefixed records and cleans up; safe to re-run.
"""
import unittest

import frappe
from frappe.utils import add_days, now_datetime, nowdate

from ecentric_workspace.alerts.services import action_queue, ingestion

BRAND_A, BRAND_B = "ALERTC-A", "ALERTC-B"
SHOP_A, SHOP_B = "ALERTC-SHOP-A", "ALERTC-SHOP-B"
OMI_A, OMI_B = "omi-alertc-a", "omi-alertc-b"
KAM_A = "alertc.kam.a@example.com"
SKU = "ALERTC-SKU-1"
_seq = [0]


def order(eid, shop_id, lines, **kw):
    o = {"external_order_id": eid, "platform": "Shopee", "omisell_shop_id": shop_id,
         "order_datetime": str(now_datetime()), "order_status": "PAID", "items": lines}
    o.update(kw)
    return o


def line(lid, sku=SKU, paid=None, qty=1, **kw):
    ln = {"external_line_id": lid, "seller_sku": sku, "quantity": qty,
          "customer_paid_price": paid, "product_name": "test"}
    ln.update(kw)
    return ln


def ingest(*orders_):
    res = ingestion.ingest_orders(list(orders_))
    action_queue.process_pending_actions()
    return res


def alerts(**filters):
    return frappe.get_all("EC Alert", filters=filters,
                          fields=["name", "rule_code", "severity", "status", "brand",
                                  "recommended_action", "dedupe_key", "owner_user"])


def actions(**filters):
    return frappe.get_all("EC Alert Action", filters=filters,
                          fields=["name", "status", "brand", "dedupe_key", "error_message"])


def seed_history(brand, shop, sku, price, n, eid_prefix):
    """n historical order lines (last 30d) at unit price -> median baseline."""
    for i in range(n):
        _seq[0] += 1
        ingestion.ingest_orders([order("%s-%d-%d" % (eid_prefix, _seq[0], i),
                                       OMI_A if brand == BRAND_A else OMI_B,
                                       [line("L1", sku=sku, paid=price, qty=1)])])


class TestPhaseC(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        cls._cleanup()
        if not frappe.db.exists("User", KAM_A):
            frappe.get_doc({"doctype": "User", "email": KAM_A, "first_name": "kamA",
                            "send_welcome_email": 0}).insert(ignore_permissions=True)
        for code, kam in ((BRAND_A, KAM_A), (BRAND_B, None)):
            frappe.get_doc({"doctype": "Brand Approver", "brand_code": code,
                            "brand_name": "[ALERTC] " + code, "status": "Active",
                            "kam_owner": kam}).insert(ignore_permissions=True)
        for shop, omi, brand in ((SHOP_A, OMI_A, BRAND_A), (SHOP_B, OMI_B, BRAND_B)):
            frappe.get_doc({"doctype": "EC Marketplace Shop", "shop_code": shop,
                            "shop_name": shop, "platform": "Shopee", "brand": brand,
                            "omisell_shop_id": omi, "status": "Active"}).insert(ignore_permissions=True)
        # policies: brand A locks enabled; brand B different min price (case 11)
        frappe.get_doc({"doctype": "EC Price Policy", "brand": BRAND_A, "platform": "Shopee",
                        "seller_sku": SKU, "min_price": 50000, "high_alert_percent": 30,
                        "severe_drop_percent": 70, "enable_stock_safety_lock": 1,
                        "status": "Active"}).insert(ignore_permissions=True)
        frappe.get_doc({"doctype": "EC Price Policy", "brand": BRAND_B, "platform": "Shopee",
                        "seller_sku": SKU, "min_price": 80000, "severe_drop_percent": 70,
                        "enable_stock_safety_lock": 1,
                        "status": "Active"}).insert(ignore_permissions=True)
        # credentials: brand A active+dry-run; brand B none (case in spec)
        frappe.get_doc({"doctype": "EC Brand Integration Settings", "brand": BRAND_A,
                        "integration_type": "Omisell", "enabled": 1,
                        "credential_status": "Active", "api_key": "fake-key-for-test",
                        "dry_run_stock_lock": 1}).insert(ignore_permissions=True)
        # history: 6 orders at 99k -> High-confidence median 99,000 for brand A
        seed_history(BRAND_A, SHOP_A, SKU, 99000, 6, "HIST-A")

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        cls._cleanup()
        frappe.db.commit()

    @classmethod
    def _cleanup(cls):
        for dt, field in (("EC Alert Action", "brand"), ("EC Alert", "brand"),
                          ("EC Automation Pause", "brand"),
                          ("EC Marketplace Order Log", "brand"),
                          ("EC Price Policy", "brand"),
                          ("EC Brand Integration Settings", "brand"),
                          ("EC Marketplace Shop", "brand")):
            for n in frappe.get_all(dt, filters={field: ("in", [BRAND_A, BRAND_B])}, pluck="name"):
                frappe.delete_doc(dt, n, force=True, ignore_permissions=True)
        # missing-brand alerts have brand=None but ALERTC dedupe keys
        for n in frappe.get_all("EC Alert", filters={"dedupe_key": ("like", "%ALERTC%")}, pluck="name"):
            frappe.delete_doc("EC Alert", n, force=True, ignore_permissions=True)
        for n in frappe.get_all("EC Marketplace Order Log",
                                filters={"external_order_id": ("like", "%ALERTC%")}, pluck="name"):
            frappe.delete_doc("EC Marketplace Order Log", n, force=True, ignore_permissions=True)
        for code in (BRAND_A, BRAND_B):
            if frappe.db.exists("Brand Approver", code):
                frappe.delete_doc("Brand Approver", code, force=True, ignore_permissions=True)

    def setUp(self):
        frappe.set_user("Administrator")

    # 1. missing brand mapping
    def test_01_missing_brand_mapping(self):
        ingest(order("ALERTC-NOMAP-1", "no-such-shop", [line("L1", paid=10000)]))
        a = alerts(rule_code="missing_brand_mapping", dedupe_key=("like", "%no-such-shop%ALERTC%"))
        a = a or alerts(rule_code="missing_brand_mapping")
        self.assertTrue(a)
        self.assertEqual(a[0].severity, "Warning")
        self.assertFalse(actions(dedupe_key=("like", "%ALERTC-NOMAP-1%")))

    # 2+3. missing_policy is RETIRED (2026-06-14): the engine no longer creates a
    # missing_policy EC Alert. A line with no active policy is marked "Missing
    # Rule" and skipped (coverage gap tracked by Price Setup), so NO operational
    # alert is raised - even for many lines/day.
    def test_02_03_missing_policy_not_created(self):
        lines = [line("L%d" % i, sku="ALERTC-NOPOLICY", paid=10000) for i in range(10)]
        ingest(order("ALERTC-NOPOL-1", OMI_A, lines))
        got = alerts(rule_code="missing_policy", brand=BRAND_A)
        self.assertEqual(len(got), 0)

    # 4. below min, not severe
    def test_04_below_min(self):
        ingest(order("ALERTC-BMIN-1", OMI_A, [line("L1", paid=45000)]))
        a = alerts(dedupe_key="omisell|ALERTC-BMIN-1|L1|price|below_min")
        self.assertEqual(len(a), 1)
        self.assertEqual((a[0].severity, a[0].recommended_action), ("Critical", "Notify Only"))
        self.assertFalse(actions(dedupe_key=("like", "%ALERTC-BMIN-1%")))

    # 5. above high
    def test_05_above_high(self):
        ingest(order("ALERTC-HIGH-1", OMI_A, [line("L1", paid=140000)]))
        a = alerts(dedupe_key="omisell|ALERTC-HIGH-1|L1|price|above_high")
        self.assertEqual(len(a), 1)
        self.assertEqual(a[0].severity, "Warning")
        self.assertFalse(actions(dedupe_key=("like", "%ALERTC-HIGH-1%")))

    # 6. 9,900 vs median 99,000 -> missing zero + dry-run lock
    def test_06_missing_zero_dry_run_lock(self):
        ingest(order("ALERTC-MZ-1", OMI_A, [line("L1", paid=9900)]))
        a = alerts(dedupe_key="omisell|ALERTC-MZ-1|L1|price|possible_missing_zero")
        self.assertEqual(len(a), 1)
        self.assertEqual(a[0].severity, "Critical")
        self.assertEqual(a[0].owner_user, KAM_A)
        act = actions(dedupe_key="omisell|ALERTC-MZ-1|L1|stock_safety_lock|possible_missing_zero")
        self.assertEqual(len(act), 1)
        self.assertEqual(act[0].status, "Dry Run")

    # 7. 25,000 vs median 99,000 @70 -> severe + dry-run lock
    def test_07_severe_dry_run_lock(self):
        ingest(order("ALERTC-SV-1", OMI_A, [line("L1", paid=25000)]))
        self.assertEqual(len(alerts(dedupe_key="omisell|ALERTC-SV-1|L1|price|severe_price_drop")), 1)
        act = actions(dedupe_key="omisell|ALERTC-SV-1|L1|stock_safety_lock|severe_price_drop")
        self.assertEqual(act[0].status, "Dry Run")

    # 8. triple match -> exactly one alert, missing_zero wins
    def test_08_priority_single_alert(self):
        ingest(order("ALERTC-PRI-1", OMI_A, [line("L1", paid=9900)]))
        all_for_line = alerts(dedupe_key=("like", "omisell|ALERTC-PRI-1|L1|price|%"))
        self.assertEqual(len(all_for_line), 1)
        self.assertEqual(all_for_line[0].rule_code, "possible_missing_zero")

    # 9. active pause -> alert yes, lock skipped
    def test_09_pause_skips_lock(self):
        frappe.get_doc({"doctype": "EC Automation Pause", "automation_type": "Stock Safety Lock",
                        "brand": BRAND_A, "platform": "All", "status": "Active",
                        "pause_from": add_days(now_datetime(), -1),
                        "pause_until": add_days(now_datetime(), 1),
                        "reason": "test"}).insert(ignore_permissions=True)
        try:
            ingest(order("ALERTC-PAUSE-1", OMI_A, [line("L1", paid=9900)]))
            self.assertTrue(alerts(dedupe_key=("like", "%ALERTC-PAUSE-1%")))
            act = actions(dedupe_key=("like", "%ALERTC-PAUSE-1%"))
            self.assertEqual(len(act), 1)
            self.assertEqual(act[0].status, "Skipped")
        finally:
            for n in frappe.get_all("EC Automation Pause", filters={"brand": BRAND_A}, pluck="name"):
                frappe.delete_doc("EC Automation Pause", n, force=True, ignore_permissions=True)

    # 10. idempotent re-ingest
    def test_10_no_duplicates_on_resync(self):
        o = order("ALERTC-DUP-1", OMI_A, [line("L1", paid=9900)])
        ingest(o)
        before_a = len(alerts(dedupe_key=("like", "%ALERTC-DUP-1%")))
        before_x = len(actions(dedupe_key=("like", "%ALERTC-DUP-1%")))
        ingest(o)  # same payload again
        self.assertEqual(len(alerts(dedupe_key=("like", "%ALERTC-DUP-1%"))), before_a)
        self.assertEqual(len(actions(dedupe_key=("like", "%ALERTC-DUP-1%"))), before_x)
        logs = frappe.get_all("EC Marketplace Order Log",
                              filters={"external_order_id": "ALERTC-DUP-1"})
        self.assertEqual(len(logs), 1)

    # 11. same seller_sku, two brands -> own policies only
    def test_11_brand_isolation(self):
        # 70k: above Brand B min (80k -> below_min) but fine for Brand A (min 50k, no severe vs 99k median... 70k>29.7k)
        ingest(order("ALERTC-ISO-A", OMI_A, [line("L1", paid=70000)]),
               order("ALERTC-ISO-B", OMI_B, [line("L1", paid=70000)]))
        self.assertFalse(alerts(dedupe_key=("like", "omisell|ALERTC-ISO-A|%")))
        b = alerts(dedupe_key="omisell|ALERTC-ISO-B|L1|price|below_min")
        self.assertEqual(len(b), 1)
        self.assertEqual(b[0].brand, BRAND_B)

    # 12. low confidence (no history, no reference_price) -> alert only, no lock
    def test_12_low_confidence_no_lock(self):
        # Brand B has no history & policy without reference_price -> baseline = min_price (Low)
        ingest(order("ALERTC-LOW-1", OMI_B, [line("L1", paid=8000)]))
        line_alerts = alerts(dedupe_key=("like", "omisell|ALERTC-LOW-1|L1|price|%"))
        self.assertEqual(len(line_alerts), 1)
        self.assertFalse(actions(dedupe_key=("like", "%ALERTC-LOW-1%")))

    # 13. permission: non-SM cannot ingest; brand scope enforced
    def test_13_permissions(self):
        from ecentric_workspace.alerts import api, permissions
        frappe.set_user(KAM_A)
        try:
            with self.assertRaises(frappe.PermissionError):
                api.ingest_mock_orders('[{"external_order_id": "X"}]')
            self.assertIn(BRAND_A, permissions.get_allowed_brands(KAM_A))
            self.assertNotIn(BRAND_B, permissions.get_allowed_brands(KAM_A))
            with self.assertRaises(frappe.PermissionError):
                permissions.require_brand_access(KAM_A, BRAND_B)
        finally:
            frappe.set_user("Administrator")
