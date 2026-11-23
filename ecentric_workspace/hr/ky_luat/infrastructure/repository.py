# Copyright (c) 2026, eCentric and contributors
"""Truy cap du lieu cua module Ky luat - NOI DUY NHAT goi frappe.db / frappe.get_doc / get_all.

Service nhan doi tuong nay (hoac FakeRepo trong test) qua tham so `repo`, nen logic nghiep vu
chay duoc ngoai bench. Moi ham tra dict thuong, khong tra Document.
"""
import json

import frappe
from frappe.utils import getdate, now_datetime, nowdate

from ecentric_workspace.hr.ky_luat import constants as C

_SETTINGS_DEFAULTS = {
    "union_rep_user": None,
    "signer_role": C.DEFAULT_SIGNER_ROLE,
    "notice_reply_days": C.DEFAULT_NOTICE_REPLY_DAYS,
    "hr_review_days": C.DEFAULT_HR_REVIEW_DAYS,
    "meeting_notice_days": C.DEFAULT_MEETING_NOTICE_DAYS,
    "ceo_sign_days": C.DEFAULT_CEO_SIGN_DAYS,
    "limitation_warn_days": C.DEFAULT_LIMITATION_WARN_DAYS,
    "legal_note": C.LEGAL_NOTE,
}
_EMP_FIELDS = ["name", "employee_name", "user_id", "company_email", "department", "designation",
               "status", "reports_to", "company"]


class Repository:
    # ------------------------------------------------------------------ thoi gian --
    def now(self):
        return now_datetime()

    def today(self):
        return getdate(nowdate())

    def holidays(self):
        from ecentric_workspace.approval_center.shared.workflow.ngay_lam_viec import ngay_le_cong_ty
        return ngay_le_cong_ty()

    # ------------------------------------------------------------------- cau hinh --
    def settings(self):
        out = dict(_SETTINGS_DEFAULTS)
        try:
            doc = frappe.get_cached_doc(C.SETTINGS)
            for k in out:
                v = doc.get(k)
                if v not in (None, "", 0):
                    out[k] = v
        except Exception:
            frappe.log_error(title="ky_luat: doc EC Discipline Settings")
        return out

    def rule(self, name):
        if not name:
            return None
        r = frappe.db.get_value(C.RULE, name, ["name", "title", "finance_related", "is_active",
                                               "is_sample", "suggested_card"], as_dict=True)
        return dict(r) if r else None

    def active_rules(self):
        return [dict(r) for r in frappe.get_all(
            C.RULE, filters={"is_active": 1},
            fields=["name", "title", "finance_related", "is_sample", "suggested_card", "description"],
            order_by="name asc", limit_page_length=0)]

    # ------------------------------------------------------------------- nhan su --
    def employee(self, name):
        if not name:
            return None
        e = frappe.db.get_value(C.EMPLOYEE, name, _EMP_FIELDS, as_dict=True)
        if not e:
            return None
        e = dict(e)
        e["user"] = e.get("user_id") or e.get("company_email")
        e["reports_to_user"] = (frappe.db.get_value(C.EMPLOYEE, e["reports_to"], "user_id")
                                if e.get("reports_to") else None)
        return e

    def employee_of_user(self, user):
        rows = frappe.get_all(C.EMPLOYEE, filters={"user_id": user}, fields=["name"],
                              order_by="status asc", limit_page_length=1)
        return rows[0].name if rows else None

    def team_of(self, employee, limit=2000):
        """Ma Employee cap duoi truc tiep + gian tiep (theo reports_to), chan vong lap."""
        if not employee:
            return set()
        seen, frontier = set(), [employee]
        while frontier and len(seen) < limit:
            rows = frappe.get_all(C.EMPLOYEE, filters={"reports_to": ["in", frontier]},
                                  pluck="name", limit_page_length=0)
            frontier = [r for r in rows if r not in seen and r != employee]
            seen.update(frontier)
        return seen

    def active_employees(self, names=None):
        filters = {"status": "Active"}
        if names is not None:
            if not names:
                return []
            filters["name"] = ["in", list(names)]
        return [dict(r) for r in frappe.get_all(C.EMPLOYEE, filters=filters,
                                                fields=["name", "employee_name", "department"],
                                                order_by="employee_name asc", limit_page_length=0)]

    def roles_of(self, user):
        return frappe.get_roles(user)

    def users_with_roles(self, roles):
        rows = frappe.get_all("Has Role", filters={"role": ["in", list(roles)], "parenttype": "User"},
                              pluck="parent", distinct=True, limit_page_length=0)
        if not rows:
            return []
        rows = [u for u in rows if u not in ("Administrator", "Guest")]
        if not rows:
            return []
        return frappe.get_all("User", filters={"name": ["in", rows], "enabled": 1},
                              pluck="name", limit_page_length=0)

    def set_relieving_date(self, employee, day):
        """Danh dau ngay nghi viec tren ho so (khoa tai khoan do job hr/offboarding lo)."""
        frappe.db.set_value(C.EMPLOYEE, employee, "relieving_date", day)

    def leave_periods(self, employee, start, end):
        """Khoang NV nghi DA DUOC DONG Y (D122.4) chong voi [start, end]: Leave Application da
        duyet + EC Leave Request co phieu engine Approved. Tra [(tu, den)]."""
        out = []
        for r in frappe.get_all(C.LEAVE_APPLICATION, filters={
                "employee": employee, "docstatus": 1, "status": "Approved",
                "from_date": ["<=", end], "to_date": [">=", start]},
                fields=["from_date", "to_date"], limit_page_length=0):
            out.append((getdate(r.from_date), getdate(r.to_date)))
        try:
            rows = frappe.db.sql(
                """select lr.start_date, lr.end_date from `tabEC Leave Request` lr
                   join `tabEC Approval Request` ar on ar.name = lr.approval_request
                   where lr.employee = %s and ar.approval_status = 'Approved'
                     and lr.start_date <= %s and lr.end_date >= %s""",
                (employee, end, start), as_dict=True)
            out += [(getdate(r.start_date), getdate(r.end_date)) for r in rows
                    if r.start_date and r.end_date]
        except Exception:
            frappe.log_error(title="ky_luat: doc EC Leave Request")
        return out

    def file_ok(self, url, user):
        """Tep do client gui len phai la tep RIENG TU, do chinh nguoi bam tai len, chua gan vao
        ban ghi khac (hoac da gan dung ban ghi nay) - chan gan nham / gan tep cua nguoi khac."""
        rows = frappe.get_all("File", filters={"file_url": url}, fields=["owner", "is_private",
                                                                         "attached_to_doctype"],
                              limit_page_length=5)
        return any(r.owner == user and int(r.is_private or 0) and
                   (not r.attached_to_doctype or r.attached_to_doctype in (C.NOTICE, C.CASE)) for r in rows)

    # ------------------------------------------------------------------- the vang --
    def get_notice(self, name):
        if not name or not frappe.db.exists(C.NOTICE, name):
            return None
        return self._as_dict(frappe.get_doc(C.NOTICE, name))

    def insert_notice(self, row, log):
        doc = frappe.get_doc(dict(row, doctype=C.NOTICE))
        doc.flags.ec_ky_luat_service = True
        doc.append("logs", log)
        doc.insert(ignore_permissions=True)
        return doc.name

    def update_notice(self, name, values, log):
        return self._update(C.NOTICE, name, values, log)

    def notices(self, employees=None, issued_by=None, limit=500):
        """employees=None + issued_by=None -> tat ca (chi goi khi nguoi xem duoc xem het)."""
        fields = ["name", "employee", "employee_name", "employee_user", "department", "issued_by",
                  "issuer_role", "behavior", "incident_date", "status", "sent_at", "reply_due",
                  "read_at", "responded_at", "line_manager_user", "creation"]
        if employees is None and issued_by is None:
            return [dict(r) for r in frappe.get_all(C.NOTICE, fields=fields, order_by="creation desc",
                                                    limit_page_length=limit)]
        or_filters = []
        if employees:
            or_filters.append(["employee", "in", list(employees)])
        if issued_by:
            or_filters.append(["issued_by", "=", issued_by])
        if not or_filters:
            return []
        return [dict(r) for r in frappe.get_all(C.NOTICE, fields=fields, or_filters=or_filters,
                                                order_by="creation desc", limit_page_length=limit)]

    def notice_dates(self, employee):
        return frappe.get_all(C.NOTICE, filters={"employee": employee,
                                                 "status": ["!=", C.NOTICE_CANCELLED]},
                              pluck="incident_date", limit_page_length=0)

    def overdue_notices(self, today):
        return [dict(r) for r in frappe.get_all(
            C.NOTICE, filters={"status": C.NOTICE_PENDING, "reply_due": ["<", today]},
            fields=["name", "employee", "employee_name", "issued_by", "reply_due"],
            limit_page_length=0)]

    # ------------------------------------------------------------------ ho so do/den --
    def get_case(self, name):
        if not name or not frappe.db.exists(C.CASE, name):
            return None
        return self._as_dict(frappe.get_doc(C.CASE, name))

    def insert_case(self, row, log):
        row = dict(row)
        if not isinstance(row.get("block_periods", ""), str):
            row["block_periods"] = json.dumps(row["block_periods"], default=str)
        doc = frappe.get_doc(dict(row, doctype=C.CASE))
        doc.flags.ec_ky_luat_service = True
        doc.append("logs", log)
        doc.insert(ignore_permissions=True)
        return doc.name

    def update_case(self, name, values, log):
        return self._update(C.CASE, name, values, log)

    def cases(self, employees=None, extra_or=None, limit=500, statuses=None):
        fields = ["name", "employee", "employee_name", "employee_user", "department", "status",
                  "card", "penalty", "violation_date", "limitation_effective_end", "meeting_date",
                  "decision_date", "expunge_due", "proposed_by", "union_rep_user",
                  "decision_request", "creation", "modified"]
        filters = {"status": ["in", list(statuses)]} if statuses else {}
        if employees is None and not extra_or:
            return [dict(r) for r in frappe.get_all(C.CASE, filters=filters, fields=fields,
                                                    order_by="modified desc", limit_page_length=limit)]
        or_filters = list(extra_or or [])
        if employees:
            or_filters.append(["employee", "in", list(employees)])
        if not or_filters:
            return []
        return [dict(r) for r in frappe.get_all(C.CASE, filters=filters, fields=fields,
                                                or_filters=or_filters, order_by="modified desc",
                                                limit_page_length=limit)]

    def cases_of_employee(self, employee, statuses=None):
        filters = {"employee": employee}
        if statuses:
            filters["status"] = ["in", list(statuses)]
        return [dict(r) for r in frappe.get_all(
            C.CASE, filters=filters,
            fields=["name", "status", "card", "penalty", "violation_date", "decision_date",
                    "expunge_due", "employee", "employee_user", "proposed_by", "union_rep_user"],
            order_by="creation desc", limit_page_length=0)]

    def open_cases(self):
        return [dict(r) for r in frappe.get_all(
            C.CASE, filters={"status": ["in", list(C.CASE_OPEN)]},
            fields=["name", "status", "employee", "employee_name", "limitation_effective_end",
                    "limitation_warned_at", "hr_owner", "decision_request", "block_to",
                    "hr_review_due", "ceo_due"], limit_page_length=0)]

    def issued_due_for_expunge(self, today):
        return [dict(r) for r in frappe.get_all(
            C.CASE, filters={"status": C.S_ISSUED, "expunge_due": ["<=", today]},
            fields=["name", "employee", "employee_name", "employee_user", "penalty",
                    "decision_date", "expunge_due", "expunge_hold_note", "hr_owner"],
            limit_page_length=0)]

    # ------------------------------------------------------- engine (qua cong nhan) --
    def decision_status(self, decision_request):
        if not decision_request:
            return None
        req = frappe.db.get_value(C.DECISION, decision_request, "approval_request")
        return frappe.db.get_value("EC Approval Request", req, "approval_status") if req else None

    # Cong sang module khac (gateways.py) - gan vao day de service chi phu thuoc MOT doi tuong.
    def create_decision(self, case, actor):
        from ecentric_workspace.hr.ky_luat.infrastructure import gateways
        return gateways.create_decision(case, actor)

    def resubmit_decision(self, case, actor):
        from ecentric_workspace.hr.ky_luat.infrastructure import gateways
        return gateways.resubmit_decision(case, actor)

    def create_clearance(self, employee, reason, last_day):
        from ecentric_workspace.hr.ky_luat.infrastructure import gateways
        return gateways.create_clearance(employee, reason, last_day)

    # ------------------------------------------------------------------ thong bao --
    def notify(self, users, subject, doctype, name, message="", url=None, email=False,
               severity=None):
        from ecentric_workspace.hr.ky_luat.infrastructure import notifier
        notifier.send(users, subject, doctype, name, message=message, url=url, email=email,
                      severity=severity)

    def log_error(self, title):
        frappe.log_error(title=title, message=frappe.get_traceback())

    # ------------------------------------------------------------------- noi bo --
    @staticmethod
    def _as_dict(doc):
        d = doc.as_dict(no_default_fields=False)
        d["logs"] = [{"at": r.get("at"), "actor": r.get("actor"), "action": r.get("action"),
                      "note": r.get("note")} for r in (doc.get("logs") or [])]
        if "block_periods" in d:
            try:
                d["block_periods"] = json.loads(d.get("block_periods") or "[]")
            except ValueError:
                d["block_periods"] = []
        return d

    @staticmethod
    def _update(doctype, name, values, log):
        doc = frappe.get_doc(doctype, name)
        vals = dict(values or {})
        if "block_periods" in vals and not isinstance(vals["block_periods"], str):
            vals["block_periods"] = json.dumps(vals["block_periods"], default=str)
        doc.update(vals)
        if log:
            doc.append("logs", log)
        doc.flags.ec_ky_luat_service = True
        doc.save(ignore_permissions=True)
        return name

