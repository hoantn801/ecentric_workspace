# Copyright (c) 2026, eCentric and contributors
"""list_requests: governed paginated cross-form list (scope isolation, paging, search)."""
import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import now_datetime

from ecentric_workspace.approval_center.reporting import scope as _scope
from ecentric_workspace.approval_center.reporting import service as _service

TYPE = "REP_LIST_TYPE"
PFX = "zzlist_"


def _user(email):
    if not frappe.db.exists("User", email):
        u = frappe.get_doc({"doctype": "User", "email": email, "first_name": email.split("@")[0],
                            "user_type": "System User", "enabled": 1, "send_welcome_email": 0})
        u.flags.no_welcome_mail = True
        u.insert(ignore_permissions=True)
        u.add_roles("Employee")
    return email


def _ensure_type():
    if not frappe.db.exists("EC Approval Type", TYPE):
        frappe.get_doc({"doctype": "EC Approval Type", "approval_code": TYPE, "approval_title": "List Test",
                        "category": "OTHERS", "card_status": "Coming Soon", "route": "approvals/list-test"}).insert(ignore_permissions=True)


def _req(requester, status="Pending"):
    return frappe.get_doc({"doctype": "EC Approval Request", "approval_type": TYPE,
                           "reference_doctype": "EC Approval Type", "reference_name": TYPE,
                           "requested_by": requester, "submitted_at": now_datetime(),
                           "approval_status": status, "current_level": 1}).insert(ignore_permissions=True).name


class TestReportingList(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        _ensure_type()
        cls.admin = _user(PFX + "admin@x.com"); frappe.get_doc("User", cls.admin).add_roles("System Manager")
        cls.reqA = _user(PFX + "a@x.com"); cls.reqB = _user(PFX + "b@x.com")
        cls.mine = [_req(cls.reqA) for _ in range(3)]
        cls.other = _req(cls.reqB)
        frappe.db.commit()

    def _list(self, user, **kw):
        sc = _scope.resolve_scope(user)
        return _service.list_requests(sc, {"approval_type": TYPE}, **kw)

    def test_admin_sees_all_with_total(self):
        out = self._list(self.admin, start=0, page_length=50)
        names = {r["name"] for r in out["rows"]}
        self.assertTrue(set(self.mine).issubset(names))
        self.assertIn(self.other, names)
        self.assertGreaterEqual(out["total"], 4)

    def test_pagination(self):
        p1 = self._list(self.admin, start=0, page_length=2)
        p2 = self._list(self.admin, start=2, page_length=2)
        self.assertEqual(len(p1["rows"]), 2)
        self.assertEqual(p1["total"], p2["total"])
        self.assertFalse({r["name"] for r in p1["rows"]} & {r["name"] for r in p2["rows"]})

    def test_requester_scope_isolation(self):
        frappe.set_user(self.reqB)
        try:
            out = self._list(self.reqB, start=0, page_length=50)
        finally:
            frappe.set_user("Administrator")
        names = {r["name"] for r in out["rows"]}
        self.assertIn(self.other, names)
        self.assertFalse(set(self.mine) & names)

    def test_search(self):
        out = _service.list_requests(_scope.resolve_scope(self.admin),
                                     {"approval_type": TYPE}, start=0, page_length=50, search=self.other)
        self.assertTrue(any(r["name"] == self.other for r in out["rows"]))
