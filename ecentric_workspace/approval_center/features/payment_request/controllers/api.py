"""Stable compatibility API for Payment Request."""
import frappe

from ecentric_workspace.approval_center.shared.fulfillment_api_adapter import bind_fulfillment
from ecentric_workspace.approval_center.features.payment_request.application import funding

# bind_fulfillment = bind(...) + list_fulfillment_queue / claim_fulfillment / complete_fulfillment
# cho buoc 6 "Finance xu ly UNC" (07/09). Hang cho xep theo ngay thanh toan gan nhat truoc.
globals().update(bind_fulfillment("PAYMENT_REQUEST",
    ("name", "request_title", "requested_by", "payee_full_name", "payment_amount", "payment_date",
     "fulfillment_status", "fulfillment_owner", "fulfillment_due_at"),
    "payment_date asc, fulfillment_due_at asc"))


@frappe.whitelist(methods=["POST"])
def claim_fulfillment_unc(name, payment_date, unc_date):
    """Nhan xu ly UNC kem HAI ngay cam ket (09/09, y Hoan).

    `bind_fulfillment` sinh ra mot `claim_fulfillment(name)` dung chung cho 8 form. De nghi
    thanh toan la form DUY NHAT can khai them ngay, nen them mot diem vao RIENG o day thay vi
    luon mot tham so qua bon tang dung chung cho ca bay form kia.

    Duong dung chung khong bi bo lai: `service.claim_fulfillment` nem loi khi thieu ngay, nen
    bam qua endpoint cu chi nhan mot cau bao ro rang chu khong lang le nhan viec ma khong co
    han xu ly.
    """
    from ecentric_workspace.approval_center.features.payment_request.application import service
    res = service.claim_fulfillment(name, payment_date=payment_date, unc_date=unc_date)
    # Tra ve DUNG hinh dang ma `claim_fulfillment` chung tra ve, de giao dien khong phai
    # biet minh vua goi duong nao: {claimed, owner, detail}.
    return {"claimed": True, "owner": res.get("owner"), "detail": get_detail(name)}


@frappe.whitelist(methods=["POST"])
def replace_unc_attachment(name, url, reason, summary=None):
    """Thay file UNC tren phieu DA HOAN TAT (dinh nham) — phieu van Hoan tat.

    POST, khong phai GET: day la duong GHI (doi con tro file, ghi lich su, bao nguoi de
    nghi). Tra ve `detail` da tuoi de man hinh khong phai goi them mot vong nua roi hien
    file cu trong khi da thay xong.
    """
    from ecentric_workspace.approval_center.features.payment_request.application import service
    res = service.replace_unc_attachment(name, url, reason, summary=summary)
    return {"replaced": True, "superseded": res.get("superseded"), "detail": get_detail(name)}


@frappe.whitelist(methods=["POST"])
def create_next_installment(name):
    """Thanh toan chia dot: tao phieu NHAP dot ke tu phieu dot truoc (da chi UNC)."""
    from ecentric_workspace.approval_center.features.payment_request.application import service
    return service.create_next_installment(name)


@frappe.whitelist()
def list_approved_purchase_requests():
    """Legacy shape kept for older clients: approved ĐNMH as {value,label} only.

    New clients call `list_funding_sources`, which also returns the amounts needed to
    autofill and to show the remaining balance. Delegates so both paths share one filter.
    """
    rows = funding.list_sources("EC Purchase Request")
    return {"rows": [{"value": r["value"], "label": r["label"]} for r in rows]}


@frappe.whitelist()
def list_funding_sources(source_doctype=None):
    """Approved commitments of the caller, each with total / paid / remaining.

    Read-only and permission-aware (see funding.list_sources). Returns the source-type
    catalog too, so the form does not hardcode the list of supported types.
    """
    if not source_doctype:
        return {"types": funding.supported_sources(), "rows": []}
    return {"types": funding.supported_sources(),
            "rows": funding.list_sources(source_doctype)}


@frappe.whitelist()
def funding_source_summary(source_doctype, source_name, exclude_request=None):
    """Fresh total/paid/remaining for one commitment.

    The form calls this when a source is picked, so the number shown is current even if
    somebody else charged the same commitment while this form was open.
    """
    if not frappe.has_permission(source_doctype, "read", doc=source_name):
        frappe.throw(frappe._("Bạn không có quyền xem chứng từ nguồn này."))
    return funding.describe_source(source_doctype, source_name, exclude_request or None)


# [TEMP-WORKAROUND 2026-09-04] xoa du lieu test truoc go-live - SM, POST, dry_run mac dinh,
# cau xac nhan, chi owner test, het han 30/09. Xem infrastructure/purge_test_data.py.
@frappe.whitelist(methods=["POST"])
def purge_test_data(confirm=None, dry_run=1, owners=None):
    from ecentric_workspace.approval_center.features.payment_request.infrastructure import (
        purge_test_data as purge)
    return purge.purge(confirm, dry_run=int(dry_run or 0), owners=owners or purge.DEFAULT_OWNERS)
