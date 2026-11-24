# Copyright (c) 2026, eCentric and contributors
"""Lop noi Approval Center <-> dot nghiem thu (BBNT) cua hop dong KOL/KOC (PO chot 24/11/2026).

Nghiep vu dot (tao, gui duyet, tai ban ky, kiem) nam o contract_review.application.kol_acceptance
(the KOL tren form 27); file nay chi la cac callback cua KOL_ACCEPTANCE_DEFINITION:
  * tao / sua chung (save_draft): chan - dot chi tao tu the KOL;
  * submit / resubmit chung (nut "Gui" / "Gui lai" o hub): DI QUA kol_acceptance.send_acceptance
    (cung cac chot: hop dong da duyet + ky du, kiem thieu thong tin creator, sinh lai BBNT);
  * chi tiet: khoi tom tat dot + che URL tep du PII (tai qua nut tren the KOL, co ghi vet);
  * duyet xong: ghi vet tren hop dong + buoc tiep theo.
Phu thuoc MOT chieu: feature nay -> contract_review (khong nguoc lai).
"""
import frappe
from frappe import _

_CR_APP = "ecentric_workspace.approval_center.features.contract_review.application."
_PII_FIELDS = ("bbnt_file", "signed_file", "sign_pdf")


def _app(module):
    from importlib import import_module
    return import_module(_CR_APP + module)


def _contract_of(name):
    contract = _app("kol_rounds").contract_of(name)
    if not contract:
        frappe.throw(_("Không tìm thấy đợt nghiệm thu."))
    return contract


def prepare_draft(document):
    """`draft_preparer`: dot KHONG tao / sua qua form chung (so dot, so tien, tep BBNT do the KOL chot)."""
    where = document.get("contract") or _("hợp đồng")
    frappe.throw(_("Đợt nghiệm thu chỉ tạo / sửa từ thẻ KOL của {0} (trang Hợp đồng).").format(where))


def submit(name):
    """`submitter` (nut "Gui" chung): cung duong voi nut "Gui duyet" tren the KOL."""
    res = _app("kol_acceptance").send_acceptance(_contract_of(name), frappe.session.user, name)
    return res.get("approval_request")


def resubmit(name, actor=None):
    """`resubmitter` (nut "Gui lai" chung sau "Can bo sung"): cung duong voi the KOL."""
    res = _app("kol_acceptance").send_acceptance(_contract_of(name), actor or frappe.session.user, name)
    return {"restarted": bool(res.get("regenerated"))}


def _contract_doc(business):
    return frappe.get_doc(_app("kol_lookup").CR_DT, business.get("contract"))


def _may_download(business, user):
    """Nguoi duoc tai ban du cua dot: nguoi duoc tai ban du cua hop dong (nguoi lap, nguoi tao creator,
    Ke toan) hoac nguoi trong luong duyet dot (PO 24/11 cau 3)."""
    access = _app("kol_access")
    contract = _contract_doc(business)
    if access.can_download_full(contract, user):
        return True
    req = business.get("approval_request")
    return bool(req and frappe.db.exists("EC Approval Request Approver",
                                         {"approval_request": req, "approver": user}))


def round_block(business, request):
    """`detail_extender`: tom tat dot + duong mo the KOL cua hop dong (khong PII)."""
    user = frappe.session.user
    return {"kol_round": {
        "contract": business.get("contract"), "contract_no": business.get("contract_no"),
        "round_no": business.get("round_no"), "amount": business.get("amount"),
        "status": business.get("status"), "due_date": str(business.get("due_date") or ""),
        "has_bbnt": bool(business.get("bbnt_file")), "has_signed": bool(business.get("signed_file")),
        "can_download": _may_download(business, user),
        "route": "/approvals/contract-review?id=%s&bbnt=%s" % (business.get("contract"), business.get("name")),
    }}


def redact_business(business, request=None):
    """`business_redactor`: KHONG tra URL tep du CCCD / STK trong chi tiet chung - ke ca nguoi duoc tai:
    ho tai qua nut tren the KOL (POST, ghi vet - QC 17/11). Giu co has_* de giao dien biet da co tep."""
    for f in _PII_FIELDS:
        business["has_" + f] = bool(business.get(f))
        business[f] = None


def redact_attachments(attachments, business, request=None):
    """`attachment_redactor`: tep gan phieu dot (Ban PDF de ky cua dot - C3) co PII: chi nguoi duoc tai
    ban du (xem `_may_download`) thay; tep he thong sinh / chu Administrator an voi nguoi khac."""
    if _may_download(business, frappe.session.user):
        return attachments
    access = _app("kol_access")
    pii = {business.get(f) for f in _PII_FIELDS} - {None, ""}
    return [a for a in attachments or []
            if a.get("owner") != "Administrator" and a.get("file_url") not in pii
            and not access.is_generated(a.get("file_name") or a.get("file_url"))]


def on_final_approval(name):
    """Duyet xong (engine `_FULFILLMENT_HANDLERS`): ghi vet tren hop dong + buoc tiep theo. Nguoi lap da
    nhan tin "da duyet" tu engine."""
    row = frappe.db.get_value(_app("kol_rounds").DT, name, ["contract", "round_no"], as_dict=True)
    if not row:
        return
    try:
        contract = frappe.get_doc(_app("kol_lookup").CR_DT, row.contract)
        contract.add_comment("Info", _("BBNT đợt {0} đã duyệt xong (Kế toán tổng hợp → Kế toán trưởng → CEO). "
                                       "Tiếp theo: ký BBNT rồi tải bản ký lên thẻ KOL.").format(row.round_no))
    except Exception:
        frappe.log_error(frappe.get_traceback(), "kol bbnt final approval %s" % name)
