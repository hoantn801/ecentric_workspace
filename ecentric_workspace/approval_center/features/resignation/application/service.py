# Copyright (c) 2026, eCentric and contributors
"""Resignation orchestration over the shared approval engine. Business-type-specific:
requester context, email/date validation, material-change restart, and a post-approval
HR fulfillment queue (claim + complete with an HR processing note). Approvers/fulfillers
are resolved from EC Approval Process participants (config) - never hardcoded here.
L1 Direct Manager resolves from employee_email via the shared Reference Employee Manager
resolver (+ config fallback_user). No external integration."""
import hashlib
import json
import re

import frappe
from frappe import _
from frappe.utils import now_datetime

from ecentric_workspace.approval_center.shared.workflow import transitions as engine

BUSINESS_DT = "EC Resignation Request"
APPROVAL_TYPE = "RESIGNATION"

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MATERIAL_FIELDS = ["resignation_for", "employee_email", "personal_email", "last_working_day",
                   "resignation_reason"]
REQUIRED_AT_SUBMIT = ["request_title", "resignation_for", "employee_email", "personal_email",
                      "last_working_day", "resignation_reason", "workplace_environment_rating",
                      "benefit_policy_rating", "corporate_culture_rating"]
_RATING_FIELDS = ["workplace_environment_rating", "benefit_policy_rating", "corporate_culture_rating"]


def _signature(doc):
    vals = {f: str(doc.get(f) or "") for f in MATERIAL_FIELDS}
    return hashlib.sha1(json.dumps(vals, sort_keys=True).encode("utf-8")).hexdigest()


def _requester_context(user):
    return frappe.db.get_value("Employee", {"user_id": user},
                               ["name", "department", "company"], as_dict=True)


def _valid_rating(v):
    v = (v or "").strip()
    if not v:
        return False
    d = v[0]
    return d.isdigit() and 1 <= int(d) <= 5


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
    emp = _requester_context(user)
    if emp:
        doc.employee = emp.name
        doc.department = doc.department or emp.department
        doc.company = doc.company or emp.company
    missing = [f for f in REQUIRED_AT_SUBMIT if not doc.get(f)]
    if missing:
        frappe.throw(_("Vui long nhap day du cac truong bat buoc truoc khi gui."))
    if not _EMAIL_RE.match((doc.employee_email or "").strip()):
        frappe.throw(_("Email cong ty (Employee Email) khong hop le."))
    if not _EMAIL_RE.match((doc.personal_email or "").strip()):
        frappe.throw(_("Email ca nhan (Personal Email) khong hop le."))
    for f in _RATING_FIELDS:
        if not _valid_rating(doc.get(f)):
            frappe.throw(_("Vui long chon danh gia (1-5) day du."))
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


# --------------------------------------------------------------------------- #
# HR Fulfillment (post-final-approval queue) - dispatched by engine.complete_approval
# --------------------------------------------------------------------------- #
def on_final_approval(name):
    """29/09/2026 (Hoan chot, file Excel): Don nghi viec duyet xong thi DI TIEP Clearance Request
    (Line Manager / Operation / HR / HOF ban giao song song) - thay cho buoc "HR xu ly" rieng
    truoc day. Ghi ngay nghi vao ho so + tao Clearance chay NEN sau commit: loi o hai viec do
    khong bao gio lam hong luot duyet. Don da o hang doi HR tu truoc van xu ly nhu cu."""
    frappe.enqueue("ecentric_workspace.approval_center.features.resignation.application.service."
                   "after_approval", queue="short", enqueue_after_commit=True, name=name)


def after_approval(name):
    """(1) Ghi Employee.resignation_letter_date / relieving_date (module HR - job 00:30 khoa tai
    khoan doc relieving_date). (2) Tao Clearance. Moi viec mot try: viec nay hong khong chan viec kia."""
    doc = frappe.get_doc(BUSINESS_DT, name)
    ket = []
    try:
        from ecentric_workspace.hr.offboarding import service as offboarding
        ket.append(offboarding.mark_resignation(
            doc.employee_email, letter_date=doc.submitted_at or doc.creation,
            relieving_date=doc.last_working_day, source=name))
        frappe.db.commit()
    except Exception:
        frappe.db.rollback()
        frappe.log_error(title="Resignation %s: khong ghi duoc ngay nghi vao ho so" % name,
                         message=frappe.get_traceback())
        ket.append("LOI ghi ho so")
    from ecentric_workspace.approval_center.features.clearance_request.application import (
        service as clearance)
    clr = clearance.create_from_resignation(name)
    ket.append("clearance=%s" % (clr or "LOI"))
    if doc.approval_request:
        engine.log_action(doc.approval_request, "Commented", "Administrator",
                          comment="; ".join(str(k) for k in ket))
        frappe.db.commit()
    if not clr:
        hr = frappe.get_all("EC Approval Request Approver",
                            filters={"approval_request": doc.approval_request}, pluck="approver")
        engine.notify(sorted(set(hr + [doc.requested_by])),
                      _("Chưa tạo được Clearance cho {0} - báo quản trị viên.").format(name),
                      BUSINESS_DT, name)
        frappe.db.commit()
    return ket


def claim_fulfillment(name, user=None):
    """Idempotent claim. First claim of an Assigned request logs exactly one "Started" timeline
    entry; a repeat claim by the SAME owner returns success without a duplicate entry and without
    resetting owner/status; a claim while another user owns it is blocked. complete_fulfillment
    behavior is unchanged."""
    user = user or frappe.session.user
    if not frappe.db.exists("ToDo", {"reference_type": BUSINESS_DT, "reference_name": name,
                                     "allocated_to": user, "status": "Open"}) \
            and "System Manager" not in frappe.get_roles(user):
        frappe.throw(_("Ban khong thuoc nhom HR xu ly yeu cau nay."))
    cur = frappe.db.get_value(BUSINESS_DT, name,
                              ["fulfillment_status", "fulfillment_owner"], as_dict=True) or {}
    status, owner = cur.get("fulfillment_status"), cur.get("fulfillment_owner")
    # Idempotent: already claimed by this user -> no duplicate timeline, no state reset.
    if status == "In Progress" and owner == user:
        return {"owner": user, "claimed": True, "idempotent": True}
    # Already owned by someone else -> block (do not steal).
    if owner and owner != user:
        frappe.throw(_("Yeu cau nay da duoc nguoi khac nhan xu ly."))
    if status == "Completed":
        frappe.throw(_("Yeu cau nay da hoan tat."))
    # Waiting (Assigned): atomic claim; the WHERE guard also settles concurrent double-claims.
    frappe.db.sql(
        """update `tabEC Resignation Request` set fulfillment_owner=%s, fulfillment_status='In Progress'
           where name=%s and fulfillment_status='Assigned'""", (user, name))
    if not frappe.db.sql("select 1 from `tabEC Resignation Request` where name=%s and fulfillment_owner=%s",
                         (name, user)):
        frappe.throw(_("Yeu cau nay da duoc nguoi khac nhan xu ly."))
    engine.ensure_sole_todo(BUSINESS_DT, name, user, _("Resignation HR fulfillment queue"),
                            date=frappe.db.get_value(BUSINESS_DT, name, "fulfillment_due_at"))
    doc = frappe.get_doc(BUSINESS_DT, name)
    engine.log_action(doc.approval_request, "Started", user, comment=_("HR fulfillment claimed"),
                      new_status="In Progress")
    engine.notify([doc.requested_by], _("HR da nhan xu ly boi {0}: {1}").format(user, engine.request_label(BUSINESS_DT, name)),
                  BUSINESS_DT, name)
    return {"owner": user, "claimed": True}


def complete_fulfillment(name, user=None, payload=None):
    user = user or frappe.session.user
    data = frappe.parse_json(payload) if isinstance(payload, str) else (payload or {})
    doc = frappe.get_doc(BUSINESS_DT, name)
    if doc.fulfillment_owner != user and "System Manager" not in frappe.get_roles(user):
        frappe.throw(_("Chi nguoi nhan xu ly hoac System Manager moi duoc hoan tat."))
    summary = (data.get("fulfillment_summary") or doc.fulfillment_summary or "").strip()
    if not summary:
        frappe.throw(_("Vui long nhap Ghi chu xu ly cua HR truoc khi hoan tat."))
    doc.fulfillment_summary = summary
    if "completed_attachment" in data:
        doc.completed_attachment = data.get("completed_attachment")
    doc.fulfillment_status = "Completed"
    doc.completed_by = user
    doc.completed_at = now_datetime()
    from ecentric_workspace.approval_center.shared.requests.command_service import (
        attach_extra_files)
    # Tep duoc tai len KHONG kem doctype/docname: `upload_file` co hai truong do se kiem quyen
    # GHI tren chinh DocType ho so, ma cac DocType nay chi cho System Manager ghi - nguoi xu ly
    # that (Dong, Linh Vuong, Thuong, Tuan) deu khong co, nen ho khong tai duoc file (08/09).
    # Doi lai, file sinh ra la File mo coi; gan vao ho so o day - TRUOC khi save - de hook
    # attach_files_to_document cua Frappe nhan ra va khong tao dong thu hai.
    attach_extra_files(doc, [u for u in (doc.completed_attachment,) if u])
    doc.save(ignore_permissions=True)
    engine.close_fulfillment_todos(BUSINESS_DT, name)
    engine.notify([doc.requested_by, doc.fulfillment_owner],
                  _("Yeu cau nghi viec da hoan tat: {0}").format(engine.request_label(BUSINESS_DT, name)), BUSINESS_DT, name)
    return {"completed": True}
