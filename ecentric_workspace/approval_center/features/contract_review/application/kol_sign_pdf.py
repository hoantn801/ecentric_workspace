# Copyright (c) 2026, eCentric and contributors
"""O "Ban PDF de ky" tren form 27 (B1 trong ban giao chat Ky so 23/11/2026).

Luong (phuong an b, chot 18/11): nguoi lap tai hop dong .docx -> mo bang Word -> Luu thanh PDF -> tai
len o nay (`attach`). Ngay sau do trang goi `auto_place` (REQUEST RIENG - xem chu thich trong attach)
neu phieu ky qua nen tang ky so (esign_gate.enabled): `placement_service.auto_place` de tu dat o ky theo moc [[KY_BEN_A]] / [[KY_BEN_B]] va hien ket qua:
  * no_text  -> "Xuat lai bang Word -> Luu thanh PDF" (PDF in ra anh / scan: khong doi chieu duoc);
  * mismatch -> ly do cua ham doi chieu (sai so HD / so tien);
  * khong co moc -> keo o ky bang tay o khoi Ky so.
Chua bat ky so cho phieu: van luu tep (khong goi nen tang) - form chay nhu cu.

Tep in du CCCD / STK creator: gan phieu bang `kol_files.claim_upload` (chu tep = Administrator, ai
duoc thi tai qua kol_download_file, co ghi vet) nhu ban sinh tu mau.
"""
import frappe
from frappe import _

from ecentric_workspace.approval_center.features.contract_review.application import esign_gate, kol_lookup
from ecentric_workspace.approval_center.features.contract_review.domain import kol

#: Thong bao theo ma ket qua cua placement_service.auto_place.
_REASON_TEXT = {
    "verify_no_text": "Tệp PDF không có lớp chữ (bản scan / in ra ảnh). Mở hợp đồng bằng Word → Tệp → "
                      "Lưu thành PDF rồi tải lên lại.",
    "no_markers": "Không thấy mốc ký trong tệp - kéo ô ký bằng tay ở phần Ký số bên dưới.",
    "not_pdf": "Tệp không phải PDF.",
    "stale_or_foreign_attachment": "Tệp không còn gắn với phiếu - tải lên lại.",
}


def _doc_for_requester(name, user):
    doc = frappe.get_doc(kol_lookup.CR_DT, name)
    if not kol.is_kol(doc):
        frappe.throw(_("Chỉ hợp đồng KOL/KOC có ô \"Bản PDF để ký\"."))
    # Cung "nguoi lap" voi nen tang ky so (document_setup._requester_of): nhap = chu phieu, da gui =
    # requested_by - lech nhau thi tai len duoc ma dat o ky bi nen tang tu choi.
    if user != (doc.get("requested_by") if doc.get("approval_request") else doc.get("owner")):
        frappe.throw(_("Chỉ người lập phiếu tải bản PDF để ký."), frappe.PermissionError)
    if doc.get("approval_request") and frappe.db.get_value(
            "EC Approval Request", doc.approval_request, "approval_status") != "Information Required":
        # Sau khi gui chi doi duoc luc bi tra lai "Can bo sung" (nen tang ky so con kiem them: goi
        # ky da khoa thi tu tu choi).
        frappe.throw(_("Phiếu đã gửi duyệt - không đổi bản PDF để ký được nữa."))
    if not doc.get("contract_no"):
        frappe.throw(_("Tạo hợp đồng từ mẫu trước, rồi xuất PDF từ tệp đó."))
    return doc


def _file_ref(doc, url):
    return frappe.db.get_value("File", {"file_url": url, "attached_to_doctype": doc.doctype,
                                        "attached_to_name": doc.name}, "name")


def attach(name, file_url, user):
    """Gan PDF vua tai len lam Ban PDF de ky (thay ban cu), roi tu dat o ky neu co ky so."""
    doc = _doc_for_requester(name, user)
    url = str(file_url or "").strip()
    if not url.lower().endswith(".pdf"):
        frappe.throw(_("Bản để ký phải là tệp PDF (Word → Lưu thành PDF)."))
    if url in {doc.get("contract_file"), doc.get("request_attachment")}:
        frappe.throw(_("Đây là tệp hợp đồng .docx của phiếu - tải lên bản PDF xuất từ tệp đó."))
    from ecentric_workspace.approval_center.features.contract_review.application.kol_files import claim_upload
    old = doc.get("sign_pdf")
    url = claim_upload(doc, url, user)
    if old and old != url:
        _drop_old(doc, old)
    doc.db_set("sign_pdf", url)
    doc.add_comment("Info", _("{0} tải bản PDF để ký.").format(user))
    # KHONG goi auto_place o day: ham do rollback truoc khi khoa hang phieu (bo snapshot cu) - goi
    # trong cung request se xoa luon tep vua gan. Trang goi kol_auto_place_sign ngay sau (request rieng).
    esign = esign_gate.enabled(doc.name)
    return {"sign_pdf": url, "esign": esign,
            "message": None if esign else _("Đã lưu bản PDF để ký. Hợp đồng này chưa ký qua ERP - "
                                             "ký trên cổng như hiện nay.")}


def _drop_old(doc, old_url):
    """Go ban PDF cu khoi phieu. Phieu ky so: qua nen tang (go ca dong goi + o ky trong goi Draft);
    khong ky so: xoa File (vao Deleted Document, khoi phuc duoc)."""
    ref = _file_ref(doc, old_url)
    if not ref:
        return
    if esign_gate.enabled(doc.name):
        from ecentric_workspace.platform.esign import document_setup
        document_setup.remove_attachment(doc.doctype, doc.name, ref)
        return
    frappe.delete_doc("File", ref, ignore_permissions=True, delete_permanently=False)


def place(doc):
    """Tu dat o ky cho Ban PDF de ky hien tai. -> {esign, ok, placed, message}."""
    if not esign_gate.enabled(doc.name):
        return {"esign": False, "ok": True, "placed": [],
                "message": _("Đã lưu bản PDF để ký. Hợp đồng này chưa ký qua ERP - ký trên cổng như hiện nay.")}
    ref = _file_ref(doc, doc.get("sign_pdf")) if doc.get("sign_pdf") else None
    if not ref:
        return {"esign": True, "ok": False, "placed": [], "message": _("Chưa có bản PDF để ký.")}
    from ecentric_workspace.platform.esign import placement_service
    res = placement_service.auto_place(doc.doctype, doc.name, ref) or {}
    return summarize(res)


def summarize(res):
    """Ket qua auto_place -> cau tieng Viet cho nguoi lap (THUAN, de test)."""
    placed = list(res.get("placed") or [])
    reason = str(res.get("reason") or "")
    if res.get("ok"):
        if placed:
            msg = _("Đã tự đặt {0} ô ký theo mốc trong tệp. Kiểm lại vị trí ở phần Ký số.").format(len(placed))
        else:
            msg = _("Các ô ký đã có sẵn trên tệp này.")
        return {"esign": True, "ok": True, "placed": placed, "message": msg}
    if reason == "verify_mismatch":
        msg = res.get("message") or _("Nội dung tệp không khớp phiếu.")
        msg = _("Tệp không khớp phiếu: {0}").format(msg)
    elif reason in ("verify_error",):
        msg = res.get("message") or _("Không đối chiếu được tệp với phiếu - thử lại sau.")
    else:
        msg = _REASON_TEXT.get(reason) or res.get("message") or _("Chưa đặt được ô ký ({0}).").format(reason or "?")
    return {"esign": True, "ok": False, "placed": placed, "reason": reason, "message": msg}


def auto_place(name, user):
    """Bam lai "Tu dat o ky" (vd sau khi xoa nham mot o)."""
    doc = _doc_for_requester(name, user)
    return place(doc)


def _created(doc, url):
    if not url:
        return None
    return frappe.db.get_value("File", {"file_url": url, "attached_to_doctype": kol_lookup.CR_DT,
                                        "attached_to_name": doc.get("name")}, "creation")


def is_stale(doc):
    """Hop dong .docx duoc TAO LAI sau khi tai Ban PDF de ky (sua tien / ngay / creator...) -> PDF la
    ban cu, phai xuat lai. So thoi diem tao File cua hai tep."""
    pdf_at, docx_at = _created(doc, doc.get("sign_pdf")), _created(doc, doc.get("contract_file"))
    return bool(pdf_at and docx_at and str(docx_at) > str(pdf_at))


def view(doc, user):
    """Phan "Ban PDF de ky" cho trang chi tiet (khong URL - URL di qua redact_business)."""
    if not kol.is_kol(doc):
        return None
    mine = user == (doc.get("requested_by") if doc.get("approval_request") else doc.get("owner"))
    status = None
    if doc.get("approval_request"):
        status = frappe.db.get_value("EC Approval Request", doc.get("approval_request"), "approval_status")
    return {"has": bool(doc.get("sign_pdf")), "stale": is_stale(doc) if doc.get("sign_pdf") else False,
            "esign": esign_gate.enabled(doc.get("name")),
            "can_edit": bool(mine and doc.get("contract_no")
                             and (not doc.get("approval_request") or status == "Information Required"))}

