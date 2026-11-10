# Copyright (c) 2026, eCentric and contributors
"""Trung tam Du lieu dot 2 - doc/ghi DB cua Data availability, de xuat crawl, Thu vien bao cao.

Mo rong repository.py (dot 1): `from repository import *` nen avail_service chi can MOT doi tuong repo
(ca ham dot 1: settings / roles / insert_ticket / lock / notify ... lan ham dot 2 duoi day). Van la
cho DUY NHAT cham DB; service da kiem quyen TRUOC khi goi vao day nen dung ignore_permissions.
Moi ten ham dot 2 co tien to avail_ / proposal_ / library_ (khong de len ham dot 1).
"""
import frappe

from ecentric_workspace.data_hub import constants as C
from ecentric_workspace.data_hub.repository import *  # noqa: F401,F403  (ham dot 1: cung mot repo)

AVAIL_FIELDS = ["name", "team", "data_type", "platform", "in_sharepoint", "in_dw", "in_powerbi", "front_priority",
                "note", "last_updated", "frequency", "data_owner", "planned_ticket", "creation", "modified"]
PROPOSAL_FIELDS = ["name", "team", "data_type", "platforms", "purpose", "urgency", "urgency_note", "proposer",
                   "status", "due_at", "decided_by", "decided_at", "reason", "resulting_ticket", "rule_version",
                   "creation", "modified",
                   # 10/11/2026: chi tiet cho team Data
                   "department", "frequency", "needed_by", "urgency_reason", "data_from", "data_to", "channels",
                   "source_links", "scope"]
LIBRARY_FIELDS = ["name", "title", "link", "report_owner", "team", "data_sources", "from_ticket", "tags", "active",
                  "added_by", "creation", "modified"]


def _rows(dt, fields, filters=None, order_by="creation asc", limit=0):
    return [dict(r) for r in frappe.get_all(dt, filters=filters or {}, fields=fields, order_by=order_by,
                                            limit_page_length=limit or 0)]


def _insert(dt, values):
    doc = frappe.get_doc(dict(values, doctype=dt))
    doc.insert(ignore_permissions=True)
    return doc.name


def _save(dt, name, values):
    """Qua doc.save() de Frappe kiem Select / Link va ghi Version (track_changes)."""
    doc = frappe.get_doc(dt, name)
    doc.update(values)
    doc.flags.ignore_permissions = True
    doc.save(ignore_permissions=True)


# ------------------------------------------------------------------ availability ----------
def avail_rows():
    """Moi dong ma tran, theo thu tu tao (= thu tu seed Excel)."""
    return _rows(C.AVAIL_DT, AVAIL_FIELDS, order_by="creation asc, name asc")


def avail_get(name):
    rows = _rows(C.AVAIL_DT, AVAIL_FIELDS, {"name": name}, limit=1) if name else []
    return rows[0] if rows else None


def avail_lock(names):
    """Khoa cac dong (SELECT ... FOR UPDATE) roi doc lai - hai nguoi cung len ke hoach mot o."""
    names = [n for n in names or () if n]
    if not names:
        return []
    frappe.db.sql("select name from `tabEC Data Availability` where name in %s for update", (tuple(names),))
    return _rows(C.AVAIL_DT, AVAIL_FIELDS, {"name": ["in", names]})


def avail_insert(values):
    return _insert(C.AVAIL_DT, values)


def avail_set(name, values):
    _save(C.AVAIL_DT, name, values)


# ------------------------------------------------------------------ de xuat ---------------
def proposal_rows(limit=0):
    """De xuat moi nhat truoc."""
    return _rows(C.PROPOSAL_DT, PROPOSAL_FIELDS, order_by="creation desc", limit=limit)


def proposal_pending():
    return _rows(C.PROPOSAL_DT, PROPOSAL_FIELDS, {"status": C.PROP_PENDING})


def proposal_get(name):
    rows = _rows(C.PROPOSAL_DT, PROPOSAL_FIELDS, {"name": name}, limit=1) if name else []
    return rows[0] if rows else None


def proposal_lock(name):
    if not name:
        return None
    frappe.db.sql("select name from `tabEC Data Proposal` where name = %s for update", (name,))
    return proposal_get(name)


def proposal_by_ticket(code):
    rows = _rows(C.PROPOSAL_DT, PROPOSAL_FIELDS, {"resulting_ticket": code}, limit=1) if code else []
    return rows[0] if rows else None


def proposal_sent_today(user, day):
    return frappe.db.count(C.PROPOSAL_DT, {"proposer": user, "creation": [">=", str(day)]})


def proposal_insert(values):
    return _insert(C.PROPOSAL_DT, values)


def proposal_set(name, values):
    _save(C.PROPOSAL_DT, name, values)


def proposal_add_files(name, files, by):
    """Anh / file huong dan crawl: File private gan vao de xuat + dong bang con attachments (EC Data Ticket
    File - cung bang con voi yeu cau). -> [ten dong]."""
    if not files:
        return []
    doc = frappe.get_doc(C.PROPOSAL_DT, name)
    doc.flags.ignore_permissions = True
    for f in files:
        fd = frappe.get_doc({"doctype": "File", "file_name": f["name"], "content": f["content"], "is_private": 1,
                             "attached_to_doctype": C.PROPOSAL_DT, "attached_to_name": name})
        fd.flags.ignore_existing_file_check = True
        fd.insert(ignore_permissions=True)
        doc.append("attachments", {"file_url": fd.file_url, "file_name": fd.file_name, "file_size": fd.file_size,
                                   "message": "", "uploaded_by": by})
    doc.save(ignore_permissions=True)
    return [r.name for r in doc.get("attachments")[-len(files):]]


def proposal_files(names):
    """-> {ten de xuat: [{name, file_name, file_size}]} (KHONG tra file_url - tai qua api)."""
    names = [n for n in names or () if n]
    out = {}
    if not names:
        return out
    for r in frappe.get_all(C.FILE_DT, filters={"parent": ["in", names], "parenttype": C.PROPOSAL_DT},
                            fields=["name", "parent", "file_name", "file_size"], order_by="idx asc",
                            limit_page_length=0):
        out.setdefault(r.parent, []).append({"name": r.name, "file_name": r.file_name,
                                             "file_size": int(r.file_size or 0)})
    return out


def proposal_file_content(name, row_name):
    """-> (ten tep, bytes) cua tep thuoc DUNG de xuat nay, hoac None."""
    url = frappe.db.get_value(C.FILE_DT, {"name": row_name, "parent": name, "parenttype": C.PROPOSAL_DT},
                              "file_url")
    if not url:
        return None
    rows = frappe.get_all("File", filters={"file_url": url, "attached_to_doctype": C.PROPOSAL_DT,
                                           "attached_to_name": name}, pluck="name", limit=1)
    if not rows:
        return None
    f = frappe.get_doc("File", rows[0])
    return f.file_name, f.get_content()


def departments():
    """Phong ban ERP dang dung (khong phai nhom) -> [{name, label}] theo ten. label = department_name."""
    fields = ["name", "department_name"]
    try:
        rows = frappe.get_all("Department", filters={"is_group": 0, "disabled": 0}, fields=fields,
                              order_by="department_name asc", limit_page_length=0)
    except Exception:
        # ban ERPNext khong co cot disabled
        rows = frappe.get_all("Department", filters={"is_group": 0}, fields=fields,
                              order_by="department_name asc", limit_page_length=0)
    out = []
    for r in rows:
        if r.name in ("All Departments",):
            continue
        out.append({"name": r.name, "label": r.department_name or r.name})
    return out


# ------------------------------------------------------------------ thu vien bao cao ------
def library_rows(include_inactive=False):
    filters = {} if include_inactive else {"active": 1}
    return _rows(C.LIBRARY_DT, LIBRARY_FIELDS, filters, order_by="modified desc")


def library_get(name):
    rows = _rows(C.LIBRARY_DT, LIBRARY_FIELDS, {"name": name}, limit=1) if name else []
    return rows[0] if rows else None


def library_by_link(link):
    rows = _rows(C.LIBRARY_DT, LIBRARY_FIELDS, {"link": link}, limit=1) if link else []
    return rows[0] if rows else None


def library_by_ticket(code):
    rows = _rows(C.LIBRARY_DT, LIBRARY_FIELDS, {"from_ticket": code}, limit=1) if code else []
    return rows[0] if rows else None


def library_insert(values):
    return _insert(C.LIBRARY_DT, values)


def library_set(name, values):
    _save(C.LIBRARY_DT, name, values)
