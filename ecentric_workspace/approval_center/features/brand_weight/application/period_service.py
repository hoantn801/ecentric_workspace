# Copyright (c) 2026, eCentric and contributors
"""Phieu cua chinh nguoi dang dang nhap: doc ky, nop / nop lai.

Chi mo ky DA QUA (thang truoc tro ve): ngay 1 moi thang nguoi dung nhap cho thang vua
xong. Mo ky hien tai cho nhap la moi nguoi doan truoc cong suc cua ca thang chua het."""
import frappe
from frappe import _
from frappe.utils import nowdate

from ecentric_workspace.approval_center.features.brand_weight.application import service
from ecentric_workspace.approval_center.features.brand_weight.application.routing import is_self_final
from ecentric_workspace.approval_center.features.brand_weight.application.validation import PERIOD_RE
from ecentric_workspace.approval_center.features.brand_weight.application.weights import (
    parse_weights, prev_period,
)
from ecentric_workspace.approval_center.features.brand_weight.domain.status import status_of
from ecentric_workspace.approval_center.features.brand_weight.infrastructure import (
    brand_weight_repository as repo,
)

LOCKED = ("wait_lead", "wait_head", "final")


def default_period():
    return prev_period(nowdate()[:7])


def check_period(period):
    if not PERIOD_RE.match(period or ""):
        frappe.throw(_("Kỳ phải đúng định dạng YYYY-MM, ví dụ 2026-09."))
    if period > default_period():
        frappe.throw(_("Chỉ nhập được cho tháng đã qua. Kỳ gần nhất đang mở là {0}.")
                     .format(default_period()))


def _payload(r, employee, period):
    name = r.find_doc(employee, period)
    return r.payload(name) if name else None


class GetMyPeriodService:
    def __init__(self, r=repo):
        self.r = r

    def execute(self, user, period):
        check_period(period)
        emp = self.r.employee_of(user)
        if not emp:
            frappe.throw(_(service.MSG_NO_EMPLOYEE))
        cur = _payload(self.r, emp.name, period)
        last = _payload(self.r, emp.name, prev_period(period))
        closed = None if cur else self.r.latest_closed(emp.name, period)
        caps = self.r.capabilities_for(user, cur["name"]) if cur else {"can_edit": True, "can_cancel": False}
        return {
            "period": period, "employee": emp.name, "employee_name": emp.employee_name,
            "department": emp.department, "name": cur and cur["name"], "status": status_of(cur),
            "note": cur["note"] if cur else "", "weights": cur["weights"] if cur else {},
            "last": last["weights"] if last else {}, "last_status": status_of(last),
            "lead_name": self.r.full_name(self.r.user_of_employee(emp.reports_to)) or "",
            "brands": self.r.active_brands(), "capabilities": caps,
            "self_final": is_self_final(emp.department),
            "closed_status": status_of(closed) if closed else None,
            "closed_weights": closed["weights"] if closed else {},
        }


class SubmitWeightsService:
    def __init__(self, r=repo):
        self.r = r

    def execute(self, user, period, raw_weights):
        check_period(period)
        weights = parse_weights(raw_weights)
        inactive = sorted(set(weights) - self.r.active_brand_ids())
        if inactive:
            frappe.throw(_("Brand không còn hoạt động: {0}. Bỏ ra rồi nộp lại.").format(", ".join(inactive)))
        emp = self.r.employee_of(user)
        if not emp:
            frappe.throw(_(service.MSG_NO_EMPLOYEE))
        name = self.r.find_doc(emp.name, period)
        st = status_of(self.r.payload(name)) if name else "none"
        if st in LOCKED:
            frappe.throw(_("Phiếu kỳ {0} đã nộp nên không sửa được. Cần sửa thì nhờ lead trả lại.")
                         .format(period))
        target = name or self.r.create_doc(emp, period, user)
        name = self.r.write_weights(target, weights, "submit")
        if st == "returned":
            service.resubmit(name, actor=user)
            return {"name": name, "resubmitted": True}
        service.submit(name)
        return {"name": name, "resubmitted": False}
