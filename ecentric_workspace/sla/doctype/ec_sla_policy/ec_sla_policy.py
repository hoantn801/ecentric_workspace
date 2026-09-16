# Copyright (c) 2026, eCentric and contributors
"""EC SLA Policy - cau hinh cach tinh HAN. Controller mong, chi validate.

Validate o day chan mot loai loi rat dat: mot chinh sach thieu tham so khong
gay loi luc luu, no gay loi luc MO nghia vu - tuc la giua luong duyet don cua
mot nguoi khac, hang tuan sau, va khong ai noi duoc tai sao. Chan tai cho nhap.
"""
import frappe
from frappe import _
from frappe.model.document import Document

from ecentric_workspace.sla.constants import (
    ALL_DUE_RULES, DUE_BUSINESS_HOURS, DUE_CALENDAR_HOURS, DUE_FIXED_TIME,
)


class ECSLAPolicy(Document):
    def validate(self):
        if self.due_rule not in ALL_DUE_RULES:
            frappe.throw(_("due_rule '{0}' khong hop le.").format(self.due_rule))
        if not self.is_new():
            before = self.get_doc_before_save()
            if before and before.policy_code and before.policy_code != self.policy_code:
                frappe.throw(_("policy_code la bat bien."))

        if self.due_rule in (DUE_BUSINESS_HOURS, DUE_CALENDAR_HOURS):
            if not self.duration_hours or float(self.duration_hours) <= 0:
                frappe.throw(_("Luat {0} can so gio > 0.").format(self.due_rule))
        if self.due_rule == DUE_FIXED_TIME and not self.fixed_time:
            frappe.throw(_("Luat {0} can gio co dinh.").format(DUE_FIXED_TIME))

        if self.due_rule == DUE_BUSINESS_HOURS:
            if not self.business_calendar:
                frappe.throw(_("Luat {0} can mot lich lam viec.").format(DUE_BUSINESS_HOURS))
            if not frappe.db.get_value("EC Approval Business Calendar",
                                       self.business_calendar, "active"):
                frappe.throw(_("Lich lam viec '{0}' phai ton tai va dang bat.")
                             .format(self.business_calendar))
        if self.holiday_list and not frappe.db.exists("Holiday List", self.holiday_list):
            frappe.throw(_("Danh sach nghi le '{0}' khong ton tai.").format(self.holiday_list))
        if self.grace_minutes and int(self.grace_minutes) < 0:
            frappe.throw(_("An han khong duoc am."))
