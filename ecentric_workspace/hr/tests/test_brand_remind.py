# Copyright (c) 2026, eCentric and contributors
"""Nut Nhac tab Phan bo cong viec (02/10/2026): ai nhan tin gi. frappe gia, KHONG can bench."""
import importlib
import sys
import types
import unittest


def _mod():
    fr = types.ModuleType("frappe")
    utils = types.ModuleType("frappe.utils")
    utils.now_datetime = lambda: None
    fr.utils = utils
    sys.modules["frappe"] = fr
    sys.modules["frappe.utils"] = utils
    ev = types.ModuleType("ecentric_workspace.notification_center.events")
    ev.publish_notification_event = lambda *a, **k: None
    sys.modules["ecentric_workspace.notification_center.events"] = ev
    sys.modules.pop("ecentric_workspace.hr.overview.brand_remind", None)
    return importlib.import_module("ecentric_workspace.hr.overview.brand_remind")


def m(emp, status, user=None, approvers=()):
    return {"employee": emp, "status": status, "user": user, "approvers": list(approvers)}


DATA = {"departments": [
    {"department": "S", "label": "Service", "state": "partial", "manager_user": "boss@x", "members": [
        m("E1", "none", "a@x"), m("E2", "returned", "b@x"), m("E3", "wait_lead", "c@x", ["lead@x"]),
        m("E4", "wait_head", "d@x", ["boss@x"]), m("E5", "final", "e@x")]},
    {"department": "O", "label": "Ops", "state": "done", "manager_user": "ops@x", "members": [
        m("E6", "final", "f@x")]},
]}


class Plan(unittest.TestCase):
    def setUp(self):
        self.B = _mod()

    def test_ai_nhan_gi(self):
        p = self.B.plan(DATA, {"S"})
        self.assertEqual(p["a@x"], {"submit": "none"})
        self.assertEqual(p["b@x"], {"submit": "returned"})
        self.assertEqual(p["lead@x"], {"approve": 1})
        # truong phong vua phai duyet vua nhan tinh hinh phong
        self.assertEqual(p["boss@x"]["approve"], 1)
        self.assertEqual(p["boss@x"]["dept"], [("Service", 4)])
        # nguoi da chot va nguoi dang cho duyet khong bi nhac nop
        self.assertNotIn("e@x", p)
        self.assertNotIn("c@x", p)

    def test_chi_phong_duoc_chon(self):
        self.assertNotIn("ops@x", self.B.plan(DATA, {"S", "O"}))
        self.assertEqual(self.B.plan(DATA, {"O"}), {})


if __name__ == "__main__":
    unittest.main()
