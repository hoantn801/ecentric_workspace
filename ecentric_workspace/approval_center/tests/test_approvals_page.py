# Copyright (c) 2026, eCentric and contributors
"""B2b: the /approvals Web Page is created and is data-driven (no hardcoded
approval list in the frontend).

  bench --site <site> run-tests --module \
    ecentric_workspace.approval_center.tests.test_approvals_page
"""
import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.approval_center.patches import p003_create_approvals_page as p003

# Seeded approval_codes that MUST NOT appear literally in the page source
# (they must come from the API, not be hardcoded in HTML/JS).
SEED_CODES = ["AI_TOPUP", "RESIGNATION", "PAYMENT_REQUEST", "PURCHASE_REQUEST",
              "OUTSIDE_WORK", "DATA_REQUEST", "DOCUMENT_REQUEST"]


class TestApprovalsPage(FrappeTestCase):
    def test_page_created_and_data_driven(self):
        p003.execute()
        name = "approval-center"
        if not frappe.db.exists("Web Page", name):
            rows = frappe.get_all("Web Page", filters={"route": "approvals"}, pluck="name")
            self.assertTrue(rows, "Web Page /approvals not found")
            name = rows[0]
        wp = frappe.get_doc("Web Page", name)
        self.assertEqual(wp.route, "approvals")
        self.assertTrue(wp.published)
        html = (wp.main_section_html or wp.main_section or "")
        # data-driven wiring present
        self.assertIn("ec-approval-center", html)
        self.assertIn("approval_center.api.catalog.list_catalog", html)
        # /approval shortcut present, /approval route not repurposed as a type
        self.assertIn('href="/approval"', html)
        # NO hardcoded approval list
        for code in SEED_CODES:
            self.assertNotIn(code, html, f"hardcoded approval code {code} found in page")

    def test_idempotent(self):
        p003.execute()
        p003.execute()
        rows = frappe.get_all("Web Page", filters={"route": "approvals"}, pluck="name")
        self.assertEqual(len(rows), 1)
