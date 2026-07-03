# Copyright (c) 2026, eCentric and contributors
"""Guard test: every Approval Center DocType must have an importable controller
module + correctly-named class. Reproduces the migrate failure mode
(get_controller import) so a missing/misnamed module is caught before deploy.

  bench --site <site> run-tests --module \
    ecentric_workspace.approval_center.tests.test_controllers_importable
"""
import frappe
from frappe.tests.utils import FrappeTestCase

DOCTYPES = [
    "EC Approval Process", "EC Approval Level", "EC Approval Participant",
    "EC Approval Request", "EC Approval Request Level", "EC Approval Request Approver",
    "EC Approval Action", "EC AI Tool", "EC AI Topup Request",
    # catalog (B1) also guarded:
    "EC Approval Category", "EC Approval Type", "EC Approval Type Role",
    "EC Approval Type Department",
]


class TestControllersImportable(FrappeTestCase):
    def test_all_controllers_import(self):
        for dt in DOCTYPES:
            cls = frappe.get_controller(dt)  # raises if the controller module is missing
            self.assertEqual(cls.__name__, "".join(dt.split()),
                             "controller class name mismatch for %s" % dt)
