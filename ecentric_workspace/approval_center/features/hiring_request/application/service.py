# Copyright (c) 2026, eCentric and contributors
"""Hiring orchestration over the shared engine. Direct Manager -> HR -> CEO (User participants
from process config; no fulfillment). Governance: the Direct Manager approver resolves from
Employee.reports_to (blocked at submit if unresolved; never requester-chosen). Department must be
a real Department master record. line_manager is BUSINESS INFO about the future hire's manager and
must be an active System User - it is NOT used as an approval resolver. No hardcoded approvers."""
import hashlib
import json
import re

import frappe
from frappe import _
from frappe.utils import now_datetime

from ecentric_workspace.approval_center.shared.workflow import transitions as engine

BUSINESS_DT = "EC Hiring Request"
APPROVAL_TYPE = "HIRING_REQUEST"

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MATERIAL_FIELDS = ["position", "number_of_vacancy", "reason", "employment_type", "education",
                   "department", "line_manager", "suggested_salary"]
REQUIRED_AT_SUBMIT = ["request_title", "position", "reason", "employment_type", "education",
                      "department", "line_manager"]


def _signature(doc):
    vals = {f: str(doc.get(f) or "") for f in MATERIAL_FIELDS}
    return hashlib.sha1(json.dumps(vals, sort_keys=True).encode("utf-8")).hexdigest()


def _ctx(user):
    return frappe.db.get_value("Employee", {"user_id": user}, ["name", "department", "company"], as_dict=True)


def _is_active_system_user(user):
    row = user and frappe.db.get_value("User", user, ["enabled", "user_type"], as_dict=True)
    return bool(row and row.enabled and row.user_type == "System User")


def _direct_manager_user(user):
    emp = frappe.db.get_value("Employee", {"user_id": user}, ["name", "reports_to"], as_dict=True)
    mgr = emp and emp.reports_to and frappe.db.get_value("Employee", emp.reports_to, "user_id")
    return mgr if (mgr and _is_active_system_user(mgr)) else None


@frappe.whitelist(methods=["POST"])
def submit(name):
    doc = frappe.get_doc(BUSINESS_DT, name)
    if doc.approval_request:
        frappe.throw(_("Yeu cau nay da duoc gui."))
    if doc.requested_by and doc.requested_by != frappe.session.user \
            and "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Ban chi co the gui yeu cau cua chinh minh."))
    user = doc.requested_by or frappe.session.user
    doc.requested_by = user
    emp = _ctx(user)
    if emp:
        doc.employee = emp.name
        doc.company = doc.company or emp.company
    missing = [f for f in REQUIRED_AT_SUBMIT if not doc.get(f)]
    if doc.number_of_vacancy is None:
        missing.append("number_of_vacancy")
    if doc.suggested_salary is None:
        missing.append("suggested_salary")
    if missing:
        frappe.throw(_("Vui long nhap day du cac truong bat buoc truoc khi gui."))
    if not frappe.db.exists("Department", doc.department):
        frappe.throw(_("Phong ban khong hop le. Vui long chon phong ban tu danh sach."))
    try:
        if int(doc.number_of_vacancy) <= 0:
            frappe.throw(_("So luong tuyen dung phai lon hon 0."))
    except (TypeError, ValueError):
        frappe.throw(_("So luong tuyen dung phai la so nguyen."))
    try:
        if float(doc.suggested_salary) <= 0:
            frappe.throw(_("Muc luong de xuat phai lon hon 0."))
    except (TypeError, ValueError):
        frappe.throw(_("Muc luong de xuat phai la so."))
    # line_manager is business info about the future hire; validate it is an active System User.
    lm = (doc.line_manager or "").strip()
    if not _EMAIL_RE.match(lm):
        frappe.throw(_("Email quan ly truc tiep (Line manager) khong hop le."))
    if not _is_active_system_user(lm):
        frappe.throw(_("Quan ly truc tiep (Line manager) phai la nguoi dung dang hoat dong trong he thong."))
    # Approval L1 Direct Manager must resolve (never requester-chosen).
    if not _direct_manager_user(user):
        frappe.throw(_("Khong xac dinh duoc Quan ly truc tiep cua ban. Vui long lien he HR/Admin de cap "
                       "nhat 'Bao cao cho' (reports_to) trong ho so nhan su truoc khi gui yeu cau."))
    doc.submitted_at = now_datetime()
    doc.material_signature = _signature(doc)
    doc.save(ignore_permissions=True)
    req_name = engine.submit(BUSINESS_DT, doc.name, APPROVAL_TYPE, user)
    frappe.db.set_value(BUSINESS_DT, doc.name, "approval_request", req_name)
    return req_name


def resubmit(name, actor=None):
    doc = frappe.get_doc(BUSINESS_DT, name)
    if not doc.approval_request:
        frappe.throw(_("Yeu cau chua duoc gui."))
    new_sig = _signature(doc)
    material_changed = new_sig != (doc.material_signature or "")
    engine.resubmit(doc.approval_request, actor=actor or frappe.session.user, restart=material_changed)
    frappe.db.set_value(BUSINESS_DT, doc.name, "material_signature", new_sig)
    return {"restarted": material_changed}


# =============================================================================
# Buoc "HR tuyen dung" sau khi CEO duyet (28/09/2026, Hoan)
#
# Quy trinh that (Power Automate cu): Hiring duyet xong -> nhan vien tuyen dung tim ung
# vien -> voi MOI ung vien chot duoc thi lap mot Offer Request -> Offer duyet xong -> New
# Staff Preparation. Tren ERP: Hiring duyet xong thi sang hang doi cua Role `EC Recruiter`
# (buoc xu ly, cung khuon Resignation/System Request); tren phieu co nut "Tao Offer". Mot
# Hiring N vi tri co the co nhieu Offer - ERP dem "da offer x/N" nhung KHONG chan khi du N:
# ung vien tu choi sau khi offer da duyet la chuyen thuong, chan cung thi HR bi ket.
# HR bam "Hoan tat tuyen dung" khi da tuyen du hoac dung tuyen (bat buoc ghi chu).
# =============================================================================
FULFILLER_ROLE = "EC Recruiter"
OFFER_DT = "EC Offer Request"
_OFFER_SONG = ("Pending", "Information Required", "Approved")


def on_final_approval(name):
    doc = frappe.get_doc(BUSINESS_DT, name)
    proc_name = frappe.db.get_value("EC Approval Request", doc.approval_request, "approval_process")
    proc = frappe.get_doc("EC Approval Process", proc_name)
    fulfillers = [u for u, _lbl in engine.resolve_participants(
        [p for p in proc.participants if p.participant_purpose == "Fulfiller"], doc.requested_by)]
    emp = frappe.db.get_value("Employee", {"user_id": doc.requested_by}, ["name", "company"], as_dict=True)
    sla = engine.resolve_sla(proc.fulfillment_sla_policy,
                             employee=emp.name if emp else None,
                             company=(emp.company if emp else None) or doc.company)
    frappe.db.set_value(BUSINESS_DT, name, {
        "fulfillment_status": "Assigned",
        "fulfillment_due_at": sla["due_at"] if sla else None,
        "fulfillment_sla_calendar": sla["calendar"] if sla else None,
        "fulfillment_sla_holiday_list": sla["holiday_list"] if sla else None,
    })
    if fulfillers:
        engine.assign(BUSINESS_DT, name, fulfillers, _("Hiring - HR tuyen dung"),
                      date=sla["due_at"] if sla else None, fulfillment=True)
    else:
        # Chua ai giu role EC Recruiter: phieu van o "Assigned" (System Manager nhan duoc),
        # nhung phai co tieng - im lang thi vi tri duoc duyet ma khong ai di tuyen.
        frappe.log_error(title="Hiring: chua co ai giu role %s" % FULFILLER_ROLE,
                         message="%s da duyet nhung khong co nguoi tuyen dung nhan viec." % name)
    engine.notify([doc.requested_by] + fulfillers,
                  _("Da duyet - chuyen HR tuyen dung: {0}").format(engine.request_label(BUSINESS_DT, name)),
                  BUSINESS_DT, name)


def _may_work(user, name):
    """Nguoi duoc lam viec tuyen dung tren phieu nay: co ToDo dang mo, Fulfiller da cau hinh
    tren quy trinh (Role EC Recruiter), hoac System Manager."""
    return bool(frappe.db.exists("ToDo", {"reference_type": BUSINESS_DT, "reference_name": name,
                                          "allocated_to": user, "status": "Open"})
                or engine.is_active_process_fulfiller(APPROVAL_TYPE, user)
                or "System Manager" in frappe.get_roles(user))


def claim_fulfillment(name, user=None):
    user = user or frappe.session.user
    if not _may_work(user, name):
        frappe.throw(_("Ban khong thuoc nhom tuyen dung (EC Recruiter) cua yeu cau nay."))
    cur = frappe.db.get_value(BUSINESS_DT, name, ["fulfillment_status", "fulfillment_owner"],
                              as_dict=True) or {}
    if cur.get("fulfillment_status") == "In Progress" and cur.get("fulfillment_owner") == user:
        return {"owner": user, "claimed": True, "idempotent": True}
    if cur.get("fulfillment_owner") and cur.get("fulfillment_owner") != user:
        frappe.throw(_("Yeu cau nay da duoc nguoi khac nhan xu ly."))
    if cur.get("fulfillment_status") == "Completed":
        frappe.throw(_("Yeu cau nay da hoan tat."))
    frappe.db.sql(
        """update `tabEC Hiring Request` set fulfillment_owner=%s, fulfillment_status='In Progress'
           where name=%s and fulfillment_status='Assigned'""", (user, name))
    if not frappe.db.sql("select 1 from `tabEC Hiring Request` where name=%s and fulfillment_owner=%s",
                         (name, user)):
        frappe.throw(_("Yeu cau nay da duoc nguoi khac nhan xu ly."))
    engine.ensure_sole_todo(BUSINESS_DT, name, user, _("Hiring - HR tuyen dung"),
                            date=frappe.db.get_value(BUSINESS_DT, name, "fulfillment_due_at"))
    doc = frappe.get_doc(BUSINESS_DT, name)
    engine.log_action(doc.approval_request, "Started", user, comment=_("HR nhan tuyen dung"),
                      new_status="In Progress")
    engine.notify([doc.requested_by], _("HR da nhan tuyen dung boi {0}: {1}").format(
        user, engine.request_label(BUSINESS_DT, name)), BUSINESS_DT, name)
    return {"owner": user, "claimed": True}


def complete_fulfillment(name, user=None, payload=None):
    user = user or frappe.session.user
    data = frappe.parse_json(payload) if isinstance(payload, str) else (payload or {})
    doc = frappe.get_doc(BUSINESS_DT, name)
    if doc.fulfillment_owner != user and "System Manager" not in frappe.get_roles(user):
        frappe.throw(_("Chi nguoi nhan tuyen dung hoac System Manager moi duoc hoan tat."))
    if doc.fulfillment_status not in ("Assigned", "In Progress"):
        frappe.throw(_("Yeu cau nay khong o buoc tuyen dung."))
    summary = (data.get("fulfillment_summary") or doc.fulfillment_summary or "").strip()
    if not summary:
        frappe.throw(_("Vui long ghi chu ket qua tuyen dung (da tuyen du / dung tuyen / ly do) truoc khi hoan tat."))
    doc.fulfillment_summary = summary
    doc.fulfillment_status = "Completed"
    doc.completed_by = user
    doc.completed_at = now_datetime()
    # Tep kem (vd bang tong hop ung vien) tai len KHONG kem doctype/docname - gan vao ho so
    # TRUOC save, cung ly do voi cac form co buoc xu ly khac (xem system_request).
    from ecentric_workspace.approval_center.shared.requests.command_service import (
        attach_extra_files)
    attach_extra_files(doc, data.get("_attachments"))
    doc.save(ignore_permissions=True)
    engine.close_fulfillment_todos(BUSINESS_DT, name)
    engine.log_action(doc.approval_request, "Completed", user, comment=summary, new_status="Completed")
    engine.notify([doc.requested_by, doc.fulfillment_owner],
                  _("Hiring da hoan tat tuyen dung: {0}").format(engine.request_label(BUSINESS_DT, name)),
                  BUSINESS_DT, name)
    return {"completed": True}


def offers_of(name, user=None):
    """Cac Offer cua mot Hiring, cho man hinh chi tiet. KHONG tra muc luong - nguoi xem
    Hiring (quan ly de nghi tuyen) duoc biet da offer ai, khong duoc biet offer bao nhieu.
    Ban nhap chi hien cho chinh nguoi tao."""
    user = user or frappe.session.user
    if not frappe.db.exists("DocType", OFFER_DT):
        return []
    rows = frappe.get_all(OFFER_DT, filters={"hiring_request": name},
                          fields=["name", "candidate_name", "onboard_date", "approval_request",
                                  "requested_by", "new_staff_preparation", "creation"],
                          order_by="creation asc", limit_page_length=0)
    out = []
    for r in rows:
        st = r.approval_request and frappe.db.get_value(
            "EC Approval Request", r.approval_request, "approval_status")
        if not st and r.requested_by != user:
            continue
        out.append({"name": r.name, "candidate_name": r.candidate_name,
                    "onboard_date": r.onboard_date, "approval_status": st or "Draft",
                    "new_staff_preparation": r.new_staff_preparation})
    return out


def can_create_offer(name, user=None):
    """Tao Offer tu mot Hiring: Hiring da duyet xong, dang o buoc tuyen dung (chua hoan tat),
    va nguoi bam la nguoi tuyen dung cua phieu (ToDo / EC Recruiter) hoac System Manager."""
    user = user or frappe.session.user
    row = frappe.db.get_value(BUSINESS_DT, name, ["approval_request", "fulfillment_status"],
                              as_dict=True)
    if not row or not row.approval_request:
        return False
    if frappe.db.get_value("EC Approval Request", row.approval_request, "approval_status") != "Approved":
        return False
    if row.fulfillment_status not in ("Assigned", "In Progress"):
        return False
    return _may_work(user, name)


def hiring_block(business, request):
    """Khoi doc them cho man hinh chi tiet Hiring (detail_extender)."""
    offers = offers_of(business.name)
    return {
        "offers": offers,
        "vacancy": business.number_of_vacancy,
        "offered": len([o for o in offers if o["approval_status"] in _OFFER_SONG]),
        "can_create_offer": can_create_offer(business.name),
        "offer_route": "/approvals/offer-request?hiring=%s" % business.name,
    }
