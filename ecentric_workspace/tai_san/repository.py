# Copyright (c) 2026, eCentric and contributors
"""Truy cap du lieu cua module tai san - NOI DUY NHAT goi frappe.db / frappe.get_all.

Ghi Asset bang frappe.db.set_value (KHONG doc.save()): 54 Asset dang Draft cua ERPNext, save goc
chay validate khau hao / tai khoan ke toan ma module khong dung (khau hao quan tri, xem README).
Moi lan ghi trang thai deu kem mot dong EC Asset Event do service tao.
"""
import json

import frappe
from frappe.utils import now_datetime

from ecentric_workspace.tai_san import constants as C

ASSET_FIELDS = ["name", "asset_name", "item_code", "asset_category", "company", "location",
                "purchase_date", "available_for_use_date", "net_purchase_amount", "custodian",
                "department", "docstatus", "creation",
                C.OPS_STATUS_FIELD, C.TAG_FIELD, C.SERIAL_FIELD, C.INSTALLED_ON_FIELD,
                C.INSTALLED_DATE_FIELD, "ec_condition", "ec_ownership", "ec_monthly_rent",
                "ec_warranty_until", "ec_supplier", "ec_invoice", "ec_useful_life_months",
                "ec_depreciation_start", "ec_salvage_value", C.RESERVED_FOR_FIELD,
                C.END_DATE_FIELD]


# ------------------------------------------------------------------ nguoi ----
def employee_of_user(user):
    return frappe.db.get_value(C.EMPLOYEE, {"user_id": user},
                               ["name", "employee_name", "department", "user_id", "status"],
                               as_dict=True)


def employees(ids):
    ids = [i for i in set(ids or []) if i]
    if not ids:
        return {}
    rows = frappe.get_all(C.EMPLOYEE, filters={"name": ["in", ids]},
                          fields=["name", "employee_name", "department", "user_id", "status",
                                  "relieving_date"])
    return {r.name: r for r in rows}


def active_employees():
    return frappe.get_all(C.EMPLOYEE, filters={"status": "Active"},
                          fields=["name", "employee_name", "department"], order_by="employee_name")


def departments_managed_by(user):
    return frappe.get_all(C.DEPARTMENT, filters={"manager_email": user}, pluck="name")


def employee_user(employee):
    return frappe.db.get_value(C.EMPLOYEE, employee, "user_id") if employee else None


# -------------------------------------------------------------- tai san -----
def categories():
    rows = frappe.get_all(C.CATEGORY, fields=["name", "ec_default_life_months", "ec_is_component",
                                              "ec_spec_template"])
    return {r.name: r for r in rows}


def assets(filters=None):
    return frappe.get_all(C.ASSET, filters=filters or {}, fields=ASSET_FIELDS,
                          order_by="name asc", limit_page_length=0)


def asset(name):
    rows = frappe.get_all(C.ASSET, filters={"name": name}, fields=ASSET_FIELDS)
    if not rows:
        frappe.throw("Không tìm thấy thiết bị %s." % name, frappe.DoesNotExistError)
    return rows[0]


def lock_asset(name):
    """Khoa dong Asset trong giao dich - hai nguoi cung bam cap phat mot may thi nguoi sau doc
    trang thai MOI (FOR UPDATE), khong ghi de nhau."""
    frappe.db.sql("select name from `tabAsset` where name=%s for update", (name,))


def set_asset(name, values):
    frappe.db.set_value(C.ASSET, name, values, update_modified=True)


def components_of(parent):
    return frappe.get_all(C.ASSET, filters={C.INSTALLED_ON_FIELD: parent}, fields=ASSET_FIELDS,
                          order_by=C.INSTALLED_DATE_FIELD + " asc")


def specs(asset_name):
    return frappe.get_all(C.SPEC_DT, filters={"parent": asset_name, "parenttype": C.ASSET},
                          fields=["name", "part_type", "spec", "qty", "note", "idx"],
                          order_by="idx asc")


def replace_specs(asset_name, rows):
    frappe.db.delete(C.SPEC_DT, {"parent": asset_name, "parenttype": C.ASSET})
    for i, r in enumerate(rows, start=1):
        doc = frappe.get_doc({"doctype": C.SPEC_DT, "parent": asset_name, "parenttype": C.ASSET,
                              "parentfield": "ec_spec", "idx": i, "part_type": r["part_type"],
                              "spec": r["spec"], "qty": r.get("qty") or 1, "note": r.get("note")})
        doc.db_insert()


def fixed_asset_items():
    return frappe.get_all(C.ITEM, filters={"is_fixed_asset": 1, "disabled": 0},
                          fields=["name", "item_name", "asset_category"], order_by="item_name")


def insert_asset(values):
    doc = frappe.get_doc(dict(values, doctype=C.ASSET))
    doc.flags.ignore_permissions = True
    doc.insert()
    return doc.name


def default_company():
    return frappe.defaults.get_global_default("company") or \
        frappe.db.get_value("Company", {}, "name")


def default_location():
    return frappe.db.get_value("Location", {}, "name")


# --------------------------------------------------------------- su kien ----
def insert_event(row):
    data = dict(row)
    if isinstance(data.get("checklist"), (list, dict)):
        data["checklist"] = json.dumps(data["checklist"], ensure_ascii=False)
    data.setdefault("event_time", now_datetime())
    data.setdefault("actor", frappe.session.user)
    doc = frappe.get_doc(dict(data, doctype=C.EVENT_DT))
    doc.flags.ignore_permissions = True
    doc.insert()
    return doc.name


def events(asset_name, limit=50):
    return frappe.get_all(C.EVENT_DT, filters={"asset": asset_name},
                          fields=["name", "event_type", "event_time", "actor", "from_status",
                                  "to_status", "from_employee", "to_employee", "ref_doctype",
                                  "ref_name", "related_asset", "condition", "note", "checklist",
                                  "acknowledged_at"],
                          order_by="event_time desc, creation desc", limit_page_length=limit)


def events_for_refs(ref_doctype, names):
    if not names:
        return []
    return frappe.get_all(C.EVENT_DT, filters={"ref_doctype": ref_doctype, "ref_name": ["in", names]},
                          fields=["asset", "event_type", "ref_name", "to_employee", "event_time"])


def latest_event(asset_name, event_type):
    rows = frappe.get_all(C.EVENT_DT, filters={"asset": asset_name, "event_type": event_type},
                          fields=["name", "event_time", "to_employee", "ref_doctype", "ref_name",
                                  "acknowledged_at"],
                          order_by="event_time desc, creation desc", limit_page_length=1)
    return rows[0] if rows else None


def unacknowledged_events(employee):
    return frappe.get_all(C.EVENT_DT,
                          filters={"to_employee": employee, "event_type": ["in", [C.EV_ASSIGN, C.EV_TRANSFER]],
                                   "acknowledged_at": ["is", "not set"]},
                          fields=["name", "asset", "event_time"], order_by="event_time desc")


def set_acknowledged(event_name):
    frappe.db.set_value(C.EVENT_DT, event_name, "acknowledged_at", now_datetime())


def last_event_time(asset_names, event_type):
    if not asset_names:
        return {}
    rows = frappe.db.sql("""select asset, max(event_time) t from `tabEC Asset Event`
                            where event_type=%s and asset in %s group by asset""",
                         (event_type, tuple(asset_names)), as_dict=True)
    return {r.asset: r.t for r in rows}


# --------------------------------------------------------------- sua chua ---
REPAIR_FIELDS = ["name", "asset", "status", "damage_level", "damaged_parts", "description", "holder",
                 "repair_mode", "vendor", "sent_date", "expected_return", "returned_date",
                 "expected_cost", "actual_cost", "result", "loaner_asset", "damage_request", "note",
                 "creation"]


def repairs(filters=None, limit=0):
    return frappe.get_all(C.REPAIR_DT, filters=filters or {}, fields=REPAIR_FIELDS,
                          order_by="creation desc", limit_page_length=limit)


def repair(name):
    rows = frappe.get_all(C.REPAIR_DT, filters={"name": name}, fields=REPAIR_FIELDS)
    if not rows:
        frappe.throw("Không tìm thấy phiếu sửa chữa %s." % name, frappe.DoesNotExistError)
    return rows[0]


def repairs_using_damage_request(request_name):
    return frappe.get_all(C.REPAIR_DT, filters={"damage_request": request_name, "status": ["!=", C.REP_CANCELLED]},
                          pluck="name")


def lock_repair(name):
    frappe.db.sql("select name from `tabEC Asset Repair` where name=%s for update", (name,))


def open_repair_of(asset_name):
    rows = frappe.get_all(C.REPAIR_DT, filters={"asset": asset_name,
                                                 "status": ["in", [C.REP_OPEN, C.REP_IN_REPAIR]]},
                          pluck="name", limit_page_length=1)
    return rows[0] if rows else None


def insert_repair(values):
    doc = frappe.get_doc(dict(values, doctype=C.REPAIR_DT))
    doc.flags.ignore_permissions = True
    doc.insert()
    return doc.name


def set_repair(name, values):
    frappe.db.set_value(C.REPAIR_DT, name, values, update_modified=True)


def repair_cost_by_month(since):
    """{'YYYY-MM': tong chi phi that} theo ngay nhan lai (khong co thi ngay gui)."""
    rows = frappe.db.sql("""select date_format(coalesce(returned_date, sent_date), '%%Y-%%m') m,
                                   sum(actual_cost) c
                            from `tabEC Asset Repair`
                            where status=%s and coalesce(returned_date, sent_date) >= %s
                            group by m""", (C.REP_DONE, since), as_dict=True)
    return {r.m: float(r.c or 0) for r in rows if r.m}


def repair_count_by_asset():
    rows = frappe.db.sql("""select asset, count(*) n from `tabEC Asset Repair`
                            where status != %s group by asset""", (C.REP_CANCELLED,), as_dict=True)
    return {r.asset: r.n for r in rows}


# --------------------------------------------------------------- chot thang -
def monthly_assets(month):
    """Ten cac may DA chot trong thang (job chay lai chi chot may con thieu)."""
    return set(frappe.get_all(C.MONTHLY_DT, filters={"month": month}, pluck="asset"))


def monthly_accumulated(month):
    """{asset: luy ke da chot o thang `month`} - de tinh khau hao thang sau bang chenh lech."""
    return {r.asset: float(r.accumulated or 0) for r in
            frappe.get_all(C.MONTHLY_DT, filters={"month": month}, fields=["asset", "accumulated"])}


def insert_monthly(row):
    doc = frappe.get_doc(dict(row, doctype=C.MONTHLY_DT))
    doc.flags.ignore_permissions = True
    doc.insert()


def monthly_by_department(since_month):
    return frappe.db.sql("""select month, coalesce(department, %s) department,
                                   sum(depreciation) dep, sum(repair_cost) rep, sum(rent) rent
                            from `tabEC Asset Monthly` where month >= %s
                            group by month, coalesce(department, %s)""",
                         (C.STOCK_BUCKET, since_month, C.STOCK_BUCKET), as_dict=True)


# ------------------------------------------------- phieu Approval Center ----
def _approval_status(names):
    names = [n for n in set(names) if n]
    if not names:
        return {}
    rows = frappe.get_all(C.APPROVAL_REQUEST_DT, filters={"name": ["in", names]},
                          fields=["name", "approval_status"])
    return {r.name: r.approval_status for r in rows}


def asset_requests_to_fulfil():
    rows = frappe.get_all(C.SRC_ASSET_REQUEST,
                          filters={"fulfillment_status": ["in", list(C.FULFILL_OPEN)]},
                          fields=["name", "request_title", "request_type", "asset_type", "quantity",
                                  "specifications", "requested_needed_date", "employee", "requested_by",
                                  "department", "fulfillment_status", "fulfillment_owner",
                                  "purpose_of_request"],
                          order_by="requested_needed_date asc")
    return rows


def nsp_upcoming(date_from, date_to):
    rows = frappe.get_all(C.SRC_NSP,
                          filters={"company_laptop": 1, "onboard_date": ["between", [date_from, date_to]]},
                          fields=["name", "candidate_name", "position", "department", "onboard_date",
                                  "new_employee", "approval_request", "line_manager"],
                          order_by="onboard_date asc")
    st = _approval_status([r.approval_request for r in rows])
    return [r for r in rows if st.get(r.approval_request) in C.OPEN_APPROVAL]


def clearances_upcoming(date_from, date_to):
    rows = frappe.get_all(C.SRC_CLEARANCE,
                          filters={"last_working_day": ["between", [date_from, date_to]]},
                          fields=["name", "employee", "employee_name", "employee_email", "department",
                                  "last_working_day", "approval_request"],
                          order_by="last_working_day asc")
    st = _approval_status([r.approval_request for r in rows])
    for r in rows:
        r["approval_status"] = st.get(r.approval_request)
    return [r for r in rows if r.approval_status in C.OPEN_APPROVAL]


def employees_left_between(date_from, date_to):
    """{employee: (ngay lam viec cuoi, ten Clearance | None)} trong [date_from, date_to].

    Clearance CHI tinh khi phieu duyet con hieu luc (OPEN_APPROVAL - phieu bi tu choi / rut lai
    khong thu may cua nguoi van dang lam). Employee.relieving_date la nguon thu hai (HR nhap tay)."""
    rows = frappe.get_all(C.SRC_CLEARANCE,
                          filters={"last_working_day": ["between", [date_from, date_to]]},
                          fields=["name", "employee", "last_working_day", "approval_request"])
    st = _approval_status([r.approval_request for r in rows])
    out = {}
    for r in rows:
        if r.employee and st.get(r.approval_request) in C.OPEN_APPROVAL:
            out[r.employee] = (r.last_working_day, r.name)
    for e in frappe.get_all(C.EMPLOYEE, filters={"relieving_date": ["between", [date_from, date_to]]},
                            fields=["name", "relieving_date"]):
        out.setdefault(e.name, (e.relieving_date, None))
    return out


def damage_requests_approved(since):
    rows = frappe.get_all(C.SRC_DAMAGE, filters={"creation": [">=", since]},
                          fields=["name", "request_title", "asset_code", "asset_type", "incident_type",
                                  "incident_date", "estimated_repair_cost", "employee",
                                  "approval_request"], order_by="creation desc")
    st = _approval_status([r.approval_request for r in rows])
    return [r for r in rows if st.get(r.approval_request) == C.APPROVED]


def damage_request(name):
    """Mot phieu Asset Damage/Loss kem trang thai duyet (None neu khong co)."""
    rows = frappe.get_all(C.SRC_DAMAGE, filters={"name": name},
                          fields=["name", "asset_code", "estimated_repair_cost", "approval_request"])
    if not rows:
        return None
    r = rows[0]
    r["approval_status"] = _approval_status([r.approval_request]).get(r.approval_request)
    return r


# ------------------------------------------------------------------ kiem ke -
def open_count():
    rows = frappe.get_all(C.COUNT_DT, filters={"status": C.CNT_OPEN}, fields=["name", "title", "started_on"],
                          order_by="creation desc", limit_page_length=1)
    return rows[0] if rows else None


def count_doc(name):
    return frappe.get_doc(C.COUNT_DT, name)


def new_count(values):
    doc = frappe.get_doc(dict(values, doctype=C.COUNT_DT))
    doc.flags.ignore_permissions = True
    doc.insert()
    return doc


def lock_count_item(count_name, asset_name):
    """Khoa + doc MOT dong kiem ke (FOR UPDATE). Nhieu nguoi xac nhan cung luc chi khoa dong cua minh,
    khong luu ca phieu (doc.save() cua ca phieu -> TimestampMismatchError khi nhieu nguoi cung bam)."""
    rows = frappe.db.sql("""select name, asset, expected_holder, expected_status, result, actual_holder,
                                   self_confirmed, note
                            from `tabEC Asset Count Item`
                            where parent=%s and parenttype=%s and asset=%s for update""",
                         (count_name, C.COUNT_DT, asset_name), as_dict=True)
    return rows[0] if rows else None


def set_count_item(item_name, values):
    frappe.db.set_value(C.COUNT_ITEM_DT, item_name, values, update_modified=True)


def set_count(name, values):
    frappe.db.set_value(C.COUNT_DT, name, values, update_modified=True)


# --------------------------------------------------------------- thong bao --
def notify(users, subject, link=None):
    """Chuong thong bao Frappe (Notification Log). Loi thong bao KHONG lam hong thao tac chinh."""
    for u in set(u for u in users or [] if u and u not in ("Guest", "Administrator")):
        try:
            doc = frappe.get_doc({"doctype": "Notification Log", "for_user": u, "type": "Alert",
                                  "subject": subject[:140], "email_content": subject,
                                  "link": link, "from_user": frappe.session.user})
            doc.flags.ignore_permissions = True
            doc.insert()
        except Exception:
            frappe.log_error(title="tai_san notify")


def users_with_role(role):
    return frappe.get_all("Has Role", filters={"role": role, "parenttype": "User"},
                          pluck="parent", distinct=True)


def notify_role(role, subject, link=None):
    users = [u for u in users_with_role(role)
             if frappe.db.get_value("User", u, "enabled")]
    notify(users, subject, link)
