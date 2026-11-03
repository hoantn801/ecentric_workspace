# Copyright (c) 2026, eCentric and contributors
"""Diem vao whitelist cua gbs_attachments.

  enqueue_push(doctype, name, reason)  - Server Script sync goi sau khi phieu len boxme
  preview(doctype, name)               - CHI DOC: ke hoach se lam (System Manager)
  push_now(doctype, name)              - chay dong bo, cho script sua tay (System Manager)
  resubmit_on_gbs(doctype, name)       - phieu bi GBS tu choi vi file: gui lai ben boxme (System Manager)
"""

import frappe

from ecentric_workspace.gbs_attachments import constants as C


def _guard(doctype, name, admin=False, trusted_caller=False):
    """trusted_caller: duoc goi tu Server Script (code do admin viet), khong phai tu trinh duyet."""
    if doctype not in C.BOXME_DOCTYPE:
        frappe.throw("doctype khong ho tro", frappe.ValidationError)
    if admin:
        frappe.only_for(C.ADMIN_ROLES)
    elif trusted_caller:
        if not frappe.db.exists(doctype, name):
            frappe.throw("Khong thay phieu " + str(name), frappe.DoesNotExistError)
    elif not frappe.has_permission(doctype, "read", name):
        frappe.throw("Khong co quyen voi phieu nay", frappe.PermissionError)


def _called_from_server_script():
    """frappe.call() trong Server Script chay duoi safe_exec_flags -> flags.in_safe_exec > 0.
    Request HTTP thang tu trinh duyet khong bao gio co co nay (Frappe tu dung no de bo qua
    kiem HTTP method cho frappe.call trong sandbox). Khong co co -> coi nhu goi tu ngoai."""
    try:
        return bool(frappe.flags.in_safe_exec)
    except Exception:
        return False


# Khong gioi han HTTP method: ham nay duoc goi qua frappe.call tu Server Script,
# ca trong request lan trong job nen.
#
# QA 03/11/2026: hook After Save sync_gbs_*_outgoing chay duoi session cua NGUOI DUYET
# (approval_decision_override -> doc.save). Nguoi duyet co the KHONG co DocPerm doc
# GBS SO/PO (57/119 user la Website User) -> has_permission False -> frappe.throw bi
# Server Script nuot thanh "v18_enqueue_fail", file goc khong bao gio sang boxme, va
# nguoi duyet thay popup loi du phieu da duyet xong. Goi tu Server Script thi chi can
# phieu ton tai; goi tu trinh duyet van phai co quyen doc nhu cu.
@frappe.whitelist()
def enqueue_push(doctype: str, name: str, reason: str = ""):
    _guard(doctype, name, trusted_caller=_called_from_server_script())
    frappe.enqueue(C.JOB_METHOD, queue=C.JOB_QUEUE, timeout=C.JOB_TIMEOUT, enqueue_after_commit=True,
                   job_id="gbs_att_push::" + doctype + "::" + name, deduplicate=True,
                   doctype=doctype, name=name, reason=str(reason or "")[:40])
    return {"success": True, "message": "queued", "data": {"doctype": doctype, "name": name}}


@frappe.whitelist(methods=["GET", "POST"])
def preview(doctype: str, name: str):
    _guard(doctype, name, admin=True)
    from ecentric_workspace.gbs_attachments.application.push_service import PushOriginalsService
    return {"success": True, "message": "", "data": PushOriginalsService().execute(doctype, name, dry_run=True)}


@frappe.whitelist(methods=["POST"])
def push_now(doctype: str, name: str, reason: str = "manual"):
    _guard(doctype, name, admin=True)
    from ecentric_workspace.gbs_attachments.application.push_service import PushOriginalsService
    return {"success": True, "message": "", "data": PushOriginalsService().execute(doctype, name, reason=reason)}


@frappe.whitelist(methods=["POST"])
def resubmit_on_gbs(doctype: str, name: str, note: str = ""):
    _guard(doctype, name, admin=True)
    from ecentric_workspace.gbs_attachments.application.resubmit_service import ResubmitAfterFileFixService
    return {"success": True, "message": "", "data": ResubmitAfterFileFixService().execute(doctype, name, note=note)}
