# Copyright (c) 2026, eCentric and contributors
"""Lop Report cua site: chi khac Frappe goc o MOT cho - bao cao Monthly Attendance Sheet
co them 2 cot chot cong (report_columns.py). Moi bao cao khac di thang ban goc.

Bat o `execute_module` vi ca xem tren man hinh, xuat Excel lan prepared report deu di qua
day (query_report.get_report_result -> execute_script_report -> execute_module).
Moi loi trong phan them cot bi nuot + ghi Error Log: tra ve nguyen ket qua cua HRMS.
"""
import frappe
from frappe.core.doctype.report.report import Report

from ecentric_workspace.hr.timesheet_close import report_columns as RC

_FIELDS = ["employee", "status", "close_mode", "lead_user", "member_closed_at",
           "member_deadline", "team_closed_at", "lead_deadline"]


class EcReport(Report):
    def execute_module(self, filters):
        res = super().execute_module(filters)
        if self.name != RC.REPORT_NAME:
            return res
        try:
            period = RC.period_from_filters(filters)
            if not period:
                return res
            rows = frappe.get_all("EC Timesheet Close", filters={"period_month": period},
                                  fields=_FIELDS, limit_page_length=0)
            return RC.add_columns(res, {r.employee: r for r in rows})
        except Exception:
            frappe.log_error(title="Bang cong: khong them duoc cot chot cong",
                             message=frappe.get_traceback())
            return res
