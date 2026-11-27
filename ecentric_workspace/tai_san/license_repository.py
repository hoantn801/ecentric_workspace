# Copyright (c) 2026, eCentric and contributors
"""Truy cap du lieu ban quyen phan mem - noi duy nhat cua phan ban quyen goi frappe.db (tach khoi
repository.py cho gon; cung quy uoc: service quyet dinh, repository chi doc / ghi)."""
import frappe
from frappe.utils import now_datetime, nowdate

from ecentric_workspace.tai_san import constants as C
from ecentric_workspace.tai_san import repository as R

LICENSE_FIELDS = ["name", "product", "license_name", "vendor", "category", "license_type", "billing_cycle", "status",
                  "seats", "start_date", "current_term_start", "expiry_date", "auto_renew", "owner_employee",
                  "department", "account", "key_location", "cost_per_cycle", "currency", "cost_fc", "exchange_rate",
                  "supplier_invoice",
                  "alert_stage", "alert_for_expiry", "note", "modified"]
PRODUCT_FIELDS = ["name", "product_name", "name_key", "vendor", "category", "license_type", "billing_cycle",
                  "disabled", "note"]
SEAT_FIELDS = ["name", "license", "employee", "employee_name", "status", "assigned_on", "assigned_by",
               "revoked_on", "revoked_by", "ref_doctype", "ref_name", "note"]


def licenses(filters=None):
    return frappe.get_all(C.LICENSE_DT, filters=filters or {}, fields=LICENSE_FIELDS,
                          order_by="expiry_date asc, license_name asc", limit_page_length=0)


def license(name):
    rows = frappe.get_all(C.LICENSE_DT, filters={"name": name}, fields=LICENSE_FIELDS)
    if not rows:
        frappe.throw("Không tìm thấy bản quyền %s." % name, frappe.DoesNotExistError)
    return rows[0]


def lock_license(name):
    """Khoa dong ban quyen va tra ve ban MOI NHAT (doc co khoa - xem repository.locked_rows)."""
    rows = R.locked_rows("tabEC Software License", LICENSE_FIELDS, "name=%s", (name,))
    if not rows:
        frappe.throw("Không tìm thấy bản quyền %s." % name, frappe.DoesNotExistError)
    return rows[0]


def lock_active_seats(license_name):
    """Cho dang cap cua mot ban quyen - doc co khoa, goi SAU lock_license: dem cho / tim trung nguoi
    tren du lieu moi nhat (hai nguoi cung cap cho cuoi khong cung lot)."""
    return R.locked_rows("tabEC Software License Seat", SEAT_FIELDS, "license=%s and status=%s",
                         (license_name, C.SEAT_ACTIVE))


def lock_seat(name):
    rows = R.locked_rows("tabEC Software License Seat", SEAT_FIELDS, "name=%s", (name,))
    if not rows:
        frappe.throw("Không tìm thấy chỗ bản quyền %s." % name, frappe.DoesNotExistError)
    return rows[0]


def set_license_if(name, expiry, values):
    """Ghi CO DIEU KIEN: chi khi han van la `expiry` (job nhac han doc danh sach tu truoc - neu ai do
    vua gia han thi bo qua, khong danh dau Het han nham). Tra ve True neu da ghi."""
    row = R.locked_rows("tabEC Software License", ["name", "expiry_date"], "name=%s", (name,))
    if not row or str(row[0].expiry_date or "")[:10] != str(expiry or "")[:10]:
        return False
    frappe.db.set_value(C.LICENSE_DT, name, values, update_modified=True)
    return True


def insert_license(values):
    doc = frappe.get_doc(dict(values, doctype=C.LICENSE_DT))
    doc.flags.ignore_permissions = True
    doc.insert()
    return doc.name


def set_license(name, values):
    frappe.db.set_value(C.LICENSE_DT, name, values, update_modified=True)


def add_renewal(name, row):
    """Them mot dong lich su gia han (bang con) ma khong save ca phieu."""
    idx = frappe.db.count(C.LICENSE_RENEWAL_DT, {"parent": name, "parenttype": C.LICENSE_DT}) + 1
    doc = frappe.get_doc({"doctype": C.LICENSE_RENEWAL_DT, "parent": name, "parenttype": C.LICENSE_DT,
                          "parentfield": "renewals", "idx": idx, **row})
    doc.name = frappe.generate_hash(length=10)
    doc.db_insert()


def renewals(name):
    return frappe.get_all(C.LICENSE_RENEWAL_DT, filters={"parent": name, "parenttype": C.LICENSE_DT},
                          fields=["renewed_on", "old_expiry", "new_expiry", "cost", "currency", "cost_fc", "exchange_rate",
                                  "renewed_by", "note"],
                          order_by="creation desc")


def latest_rates(currencies, to):
    """Ty gia goi y = dong Currency Exchange moi nhat (tu -> VND) cho moi ngoai te. Thieu thi bo qua."""
    out = {}
    for cur in currencies:
        if cur == to:
            continue
        rows = frappe.get_all("Currency Exchange", filters={"from_currency": cur, "to_currency": to},
                              fields=["exchange_rate", "date"], order_by="date desc", limit_page_length=1)
        if rows and rows[0].exchange_rate:
            out[cur] = {"rate": float(rows[0].exchange_rate), "date": str(rows[0].date)}
    return out


# ---------------------------------------------------------- danh muc phan mem ----
def products(include_disabled=False):
    f = {} if include_disabled else {"disabled": 0}
    return frappe.get_all(C.PRODUCT_DT, filters=f, fields=PRODUCT_FIELDS, order_by="product_name asc",
                          limit_page_length=0)


def product(name):
    rows = frappe.get_all(C.PRODUCT_DT, filters={"name": name}, fields=PRODUCT_FIELDS)
    if not rows:
        frappe.throw("Không tìm thấy phần mềm %s." % name, frappe.DoesNotExistError)
    return rows[0]


def product_by_key(key):
    rows = frappe.get_all(C.PRODUCT_DT, filters={"name_key": key}, fields=PRODUCT_FIELDS)
    return rows[0] if rows else None


def lock_product(name):
    rows = R.locked_rows("tabEC Software Product", PRODUCT_FIELDS, "name=%s", (name,))
    if not rows:
        frappe.throw("Không tìm thấy phần mềm %s." % name, frappe.DoesNotExistError)
    return rows[0]


def insert_product(values):
    """name_key unique o DB: hai nguoi tao cung ten cung luc -> mot nguoi loi trung, khong sinh hai dong."""
    doc = frappe.get_doc(dict(values, doctype=C.PRODUCT_DT))
    doc.flags.ignore_permissions = True
    doc.insert()
    return doc.name


def set_product(name, values):
    frappe.db.set_value(C.PRODUCT_DT, name, values, update_modified=True)


def license_names_of_product(product_name):
    return frappe.get_all(C.LICENSE_DT, filters={"product": product_name}, pluck="name", limit_page_length=0)


def licenses_without_product():
    return frappe.get_all(C.LICENSE_DT, filters={"product": ["is", "not set"]}, fields=LICENSE_FIELDS,
                          limit_page_length=0)


def add_product_log(name, text, user):
    doc = frappe.get_doc({"doctype": "Comment", "comment_type": "Info", "reference_doctype": C.PRODUCT_DT,
                          "reference_name": name, "content": text[:2000], "comment_email": user})
    doc.flags.ignore_permissions = True
    doc.insert()


# ------------------------------------------------------------------- cho ----
def seats(filters=None):
    return frappe.get_all(C.LICENSE_SEAT_DT, filters=filters or {}, fields=SEAT_FIELDS,
                          order_by="creation desc", limit_page_length=0)


def active_seats(license_name=None, employees=None):
    f = {"status": C.SEAT_ACTIVE}
    if license_name:
        f["license"] = license_name
    if employees is not None:
        f["employee"] = ["in", list(employees) or [""]]
    return seats(f)


def seat(name):
    rows = frappe.get_all(C.LICENSE_SEAT_DT, filters={"name": name}, fields=SEAT_FIELDS)
    if not rows:
        frappe.throw("Không tìm thấy chỗ bản quyền %s." % name, frappe.DoesNotExistError)
    return rows[0]


def insert_seat(values):
    doc = frappe.get_doc(dict(values, doctype=C.LICENSE_SEAT_DT))
    doc.flags.ignore_permissions = True
    doc.insert()
    return doc.name


def revoke_seat(name, user, note=None, ref_doctype=None, ref_name=None):
    values = {"status": C.SEAT_REVOKED, "revoked_on": nowdate(), "revoked_by": user}
    if note:
        values["note"] = note[:500]
    if ref_doctype:
        values.update({"ref_doctype": ref_doctype, "ref_name": ref_name})
    frappe.db.set_value(C.LICENSE_SEAT_DT, name, values, update_modified=True)


def department_exists(name):
    return bool(frappe.db.exists("Department", name))


def add_log(name, text, user):
    """Dau vet sua ban quyen (set_value khong tao Version): mot Comment loai Info tren timeline Desk -
    chi nguoi doc duoc ban quyen (role xem chi phi / quan ly) moi thay."""
    doc = frappe.get_doc({"doctype": "Comment", "comment_type": "Info", "reference_doctype": C.LICENSE_DT,
                          "reference_name": name, "content": text[:2000], "comment_email": user})
    doc.flags.ignore_permissions = True
    doc.insert()


def user_names(users):
    users = [u for u in set(users or []) if u]
    if not users:
        return {}
    return {r.name: r.full_name or r.name for r in
            frappe.get_all("User", filters={"name": ["in", users]}, fields=["name", "full_name"])}


def now():
    return now_datetime()


def license_logs(name, limit=50):
    """Nhat ky sua cua ban quyen (Comment Info do add_log ghi), moi nhat truoc."""
    return frappe.get_all("Comment", filters={"reference_doctype": C.LICENSE_DT, "reference_name": name,
                                              "comment_type": "Info"},
                          fields=["content", "comment_email", "creation"], order_by="creation desc",
                          limit_page_length=limit)
