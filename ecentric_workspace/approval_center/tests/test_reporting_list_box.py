# Copyright (c) 2026, eCentric and contributors
"""list_requests box filter (Teams-style Received/Sent) + sender/recipient enrichment.

Governance: box=received -> requests where I am an approver (EC Approval Request Approver);
box=sent -> requests I requested. Scope predicate still applies underneath (admin here to
isolate the box dimension). Enrichment adds requester_info + sent_to without per-row queries.
"""
import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import now_datetime

from ecentric_workspace.approval_center.reporting import scope as _scope
from ecentric_workspace.approval_center.reporting import service as _service

TYPE = "REP_BOX_TYPE"
PFX = "zzbox_"


def _user(email, roles=None):
    if not frappe.db.exists("User", email):
        u = frappe.get_doc({"doctype": "User", "email": email, "first_name": email.split("@")[0],
                            "user_type": "System User", "enabled": 1, "send_welcome_email": 0})
        u.flags.no_welcome_mail = True
        u.insert(ignore_permissions=True)
        u.add_roles("Employee")
    if roles:
        frappe.get_doc("User", email).add_roles(*roles)
    return email


def _ensure_type():
    if not frappe.db.exists("EC Approval Type", TYPE):
        frappe.get_doc({"doctype": "EC Approval Type", "approval_code": TYPE, "approval_title": "Box Test",
                        "category": "OTHERS", "card_status": "Coming Soon", "route": "approvals/box-test"}).insert(ignore_permissions=True)


def _req(requester, approver):
    doc = frappe.get_doc({"doctype": "EC Approval Request", "approval_type": TYPE,
                          "reference_doctype": "EC Approval Type", "reference_name": TYPE,
                          "requested_by": requester, "submitted_at": now_datetime(),
                          "approval_status": "Pending", "current_level": 1}).insert(ignore_permissions=True)
    frappe.get_doc({"doctype": "EC Approval Request Approver", "parent": doc.name,
                    "parenttype": "EC Approval Request", "parentfield": "approvers",
                    "approval_request": doc.name, "approver": approver,
                    "level_no": 1, "status": "Pending"}).insert(ignore_permissions=True)
    return doc.name


class TestReportingListBox(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        _ensure_type()
        cls.admin = _user(PFX + "admin@x.com", roles=["System Manager"])
        cls.reqr = _user(PFX + "requester@x.com")
        cls.appr = _user(PFX + "approver@x.com")
        cls.rid = _req(cls.reqr, cls.appr)
        frappe.db.commit()

    def _list(self, me, box):
        sc = _scope.resolve_scope(self.admin)  # admin scope isolates the box dimension
        filters = {"approval_type": TYPE, "box": box, "_me": me}
        return _service.list_requests(sc, filters, start=0, page_length=50)

    def test_sent_box_matches_requester(self):
        names = {r["name"] for r in self._list(self.reqr, "sent")["rows"]}
        self.assertIn(self.rid, names)
        self.assertFalse({r["name"] for r in self._list(self.appr, "sent")["rows"]} & {self.rid})

    def test_received_box_matches_approver(self):
        names = {r["name"] for r in self._list(self.appr, "received")["rows"]}
        self.assertIn(self.rid, names)
        self.assertNotIn(self.rid, {r["name"] for r in self._list(self.reqr, "received")["rows"]})

    def test_enrichment_sender_and_recipients(self):
        row = next(r for r in self._list(self.reqr, "sent")["rows"] if r["name"] == self.rid)
        self.assertEqual(row["requester_info"]["user"], self.reqr)
        self.assertIn("name", row["requester_info"])
        recips = {x["user"] for x in row["sent_to"]}
        self.assertIn(self.appr, recips)
