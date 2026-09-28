# Copyright (c) 2026, eCentric and contributors
"""Tang duy nhat cua feature brand_weight duoc goi frappe.db (rule 4.3). Chi truy van
va ghi, khong quyet dinh nghiep vu. Tra ve dict, khong tra object Frappe ra ngoai."""
import frappe

BUSINESS_DT = "EC Brand Weight Request"
CLOSED = ("Rejected", "Cancelled")
EMP_FIELDS = ["name", "employee_name", "user_id", "department", "company", "reports_to"]


def employee_of(user):
    return frappe.db.get_value("Employee", {"user_id": user, "status": "Active"}, EMP_FIELDS, as_dict=True)


def user_of_employee(employee):
    return employee and frappe.db.get_value("Employee", employee, "user_id")


def full_name(user):
    return user and (frappe.db.get_value("User", user, "full_name") or user)


def active_brands():
    """[{id, label}] - id la ten Brand (gia tri luu), label la ten hien thi cho nguoi dung.
    Vi sao tach: brand chuan mang ma kieu 'FLD-VN' (alerts/tich hop can ma do), nhung nguoi
    nhap can thay 'France Lait'. Hien ma thi ho di tim ban co ten de doc - dung cach da de
    ra ba cap brand trung (France Lait / FLD-VN ...)."""
    rows = frappe.get_all("Brand", filters={"ec_status": "Active"},
                          fields=["name", "ec_brand_name"], order_by="name asc")
    out = [{"id": r.name, "label": (r.ec_brand_name or "").strip() or r.name} for r in rows]
    return sorted(out, key=lambda b: b["label"].lower())


def active_brand_ids():
    return {b["id"] for b in active_brands()}


def find_doc(employee, period):
    """Phieu con song cua (nhan vien, ky). Bo qua phieu da Tu choi/Huy de nop lai duoc."""
    rows = frappe.get_all(BUSINESS_DT, filters={"employee": employee, "period": period},
                          fields=["name", "approval_request"], order_by="creation desc")
    for r in rows:
        st = r.approval_request and frappe.db.get_value(
            "EC Approval Request", r.approval_request, "approval_status")
        if st not in CLOSED:
            return r.name
    return None


def latest_closed(employee, period):
    """Phieu gan nhat da Rut/Tu choi cua ky - de dien san so cu khi nop lai, khong mat cong nhap."""
    rows = frappe.get_all(BUSINESS_DT, filters={"employee": employee, "period": period,
                                                "approval_request": ["is", "set"]},
                          pluck="name", order_by="creation desc", limit=5)
    for name in rows:
        p = payload(name)
        if p["approval_status"] in CLOSED:
            return p
    return None


def capabilities_for(user, name):
    from ecentric_workspace.approval_center.shared.requests import capabilities
    doc = frappe.get_doc(BUSINESS_DT, name)
    req = doc.approval_request and frappe.get_doc("EC Approval Request", doc.approval_request)
    caps = capabilities.derive(user, doc, req or None)
    return {"can_edit": bool(caps.get("can_edit")), "can_cancel": bool(caps.get("can_cancel"))}


def payload(name):
    doc = frappe.get_doc(BUSINESS_DT, name)
    req = doc.approval_request and frappe.db.get_value(
        "EC Approval Request", doc.approval_request,
        ["name", "approval_status", "current_level"], as_dict=True)
    status = req.approval_status if req else None
    return {
        "name": doc.name, "employee": doc.employee, "period": doc.period,
        "weights": {r.brand: r.weight for r in doc.details},
        "proposed": {r.brand: r.proposed_weight for r in doc.details if r.proposed_weight},
        "lead": {r.brand: r.lead_weight for r in doc.details if r.lead_weight},
        "request": req.name if req else None,
        "approval_status": status,
        "current_level": req.current_level if req else None,
        "note": _return_note(req.name) if status == "Information Required" else "",
    }


def _return_note(req_name):
    rows = frappe.get_all("EC Approval Action",
                          filters={"approval_request": req_name, "action": "Information Requested"},
                          fields=["comment"], order_by="creation desc", limit=1)
    return (rows[0].comment or "") if rows else ""


def team_employees(user, me):
    """Nguoi bao cao truc tiep cho `me` + nhan vien cac phong ma `user` la truong phong."""
    rows = []
    if me:
        rows += frappe.get_all("Employee", filters={"status": "Active", "reports_to": me},
                               fields=EMP_FIELDS)
    depts = frappe.get_all("Department", filters={"manager_email": user}, pluck="name")
    if depts:
        rows += frappe.get_all("Employee", filters={"status": "Active", "department": ["in", depts]},
                               fields=EMP_FIELDS)
    seen, out = set(), []
    for r in rows:
        if r.name not in seen:
            seen.add(r.name)
            out.append(r)
    return sorted(out, key=lambda r: r.employee_name or "")


def employees_by_name(names):
    if not names:
        return []
    return frappe.get_all("Employee", filters={"name": ["in", list(names)]}, fields=EMP_FIELDS)


def pending_for(user):
    """{ten phieu nghiep vu: level_no} ma `user` dang la nguoi duyet Pending o DUNG cap hien tai."""
    rows = frappe.db.sql(
        """select r.reference_name, r.current_level
           from `tabEC Approval Request Approver` ap
           inner join `tabEC Approval Request` r on r.name = ap.approval_request
           where ap.approver = %s and ap.status = 'Pending' and r.approval_status = 'Pending'
             and ap.level_no = r.current_level and r.reference_doctype = %s""",
        (user, BUSINESS_DT), as_dict=True)
    return {r.reference_name: r.current_level for r in rows}


def doc_owner(name):
    return frappe.db.get_value(BUSINESS_DT, name, ["employee", "period"], as_dict=True)


def get_doc(name):
    return frappe.get_doc(BUSINESS_DT, name)


def save_doc(doc):
    doc.flags.ignore_permissions = True
    doc.save()


def link_request(name, req_name):
    frappe.db.set_value(BUSINESS_DT, name, "approval_request", req_name)


def create_doc(emp, period, user):
    doc = frappe.get_doc({"doctype": BUSINESS_DT, "period": period, "employee": emp.name,
                          "requested_by": user, "department": emp.department, "company": emp.company,
                          "request_title": "Ty trong brand %s - %s" % (period, emp.employee_name)})
    return doc


def write_weights(doc_or_name, weights, stage):
    """Ghi ty trong. stage: 'submit' (ghi ca de xuat), 'lead' (ghi ca so lead), 'head'.
    Giu so de xuat cu cua dong da co; dong moi lead/truong phong them co de xuat = 0."""
    doc = frappe.get_doc(BUSINESS_DT, doc_or_name) if isinstance(doc_or_name, str) else doc_or_name
    old = {r.brand: r for r in (doc.details or [])}
    doc.set("details", [])
    for brand, w in weights.items():
        o = old.get(brand)
        doc.append("details", {
            "brand": brand, "weight": w,
            "proposed_weight": w if stage == "submit" else (o.proposed_weight if o else 0),
            "lead_weight": w if stage == "lead" else (0 if stage == "submit" else (o.lead_weight if o else 0)),
        })
    doc.flags.ignore_permissions = True
    if doc.is_new():
        doc.insert()
    else:
        doc.save()
    return doc.name
