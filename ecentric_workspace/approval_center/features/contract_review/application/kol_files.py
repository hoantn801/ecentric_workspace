# Copyright (c) 2026, eCentric and contributors
"""Sinh tep hop dong / BBNT (.docx) tu mau `EC Contract Template`.

Tep sinh ra DINH KEM vao phieu -> luc gui, `sharepoint_mirror` day len SharePoint de nguoi
duyet sua bang Word Online; moi lan duyet `sharepoint_snapshot` chup ban doi chung (.docx +
PDF do Graph chuyen). Ban PDF cuoi vi the do Word xuat, KHONG sinh bang ReportLab (0/6 ky
duoc tren SCTS ngay 30/09).
"""
import hashlib
import json

import frappe
from frappe import _

from ecentric_workspace.approval_center.features.contract_review.application import kol_lookup
from ecentric_workspace.approval_center.features.contract_review.application.kol_service import (
    can_manage, creator_row)
from ecentric_workspace.approval_center.features.contract_review.domain import docx_fill, kol

KIND_CONTRACT = "Hợp đồng"
KIND_BBNT = "BBNT"


def file_bytes(file_url):
    """Doc tep MAU (EC Contract Template) - chi goi voi URL lay tu ban ghi mau, khong tu nguoi dung."""
    name = frappe.db.get_value("File", {"file_url": file_url}, "name")
    if not name:
        frappe.throw(_("Không tìm thấy tệp: {0}").format(file_url))
    return frappe.get_doc("File", name).get_content()


def doc_file_bytes(doc, file_url):
    """Doc tep CUA PHIEU: chi tep dang gan vao chinh phieu nay. URL nam trong truong nguoi dung
    sua duoc (request_attachment) - khong kiem thi go URL tep rieng tu cua nguoi khac la doc
    duoc qua AI (QC 11/11)."""
    name = frappe.db.get_value("File", {"file_url": file_url, "attached_to_doctype": doc.doctype,
                                        "attached_to_name": doc.name}, "name")
    if not name:
        frappe.throw(_("Tệp {0} không thuộc phiếu này.").format(file_url), frappe.PermissionError)
    return frappe.get_doc("File", name).get_content()


def attach(doc, file_name, content):
    f = frappe.get_doc({"doctype": "File", "file_name": file_name, "is_private": 1,
                        "attached_to_doctype": doc.doctype, "attached_to_name": doc.name,
                        "content": content})
    f.insert(ignore_permissions=True)
    return f.file_url


def claim_upload(doc, file_url, user):
    """Gan tep nguoi dung vua tai len (upload_file rieng tu, chua gan phieu) vao phieu.

    Chi nhan tep CUA CHINH nguoi do tai len (hoac Ke toan): khong cho tro vao tep rieng tu cua
    nguoi khac bang cach go URL."""
    row = frappe.db.get_value("File", {"file_url": file_url}, ["name", "owner", "attached_to_name"],
                              as_dict=True)
    if not row:
        frappe.throw(_("Không tìm thấy tệp vừa tải lên."))
    if row.owner != user and not kol_lookup.is_finance(user):
        frappe.throw(_("Tệp này không phải do bạn tải lên."), frappe.PermissionError)
    if row.attached_to_name and row.attached_to_name != doc.name:
        frappe.throw(_("Tệp này đang gắn với chứng từ khác."))
    frappe.db.set_value("File", row.name, {"attached_to_doctype": doc.doctype,
                                           "attached_to_name": doc.name})
    return file_url


def template_for(doc, kind):
    chosen = doc.get("contract_template") if kind == KIND_CONTRACT else None
    if chosen:
        t = frappe.db.get_value("EC Contract Template", chosen,
                                ["kind", "is_active", "creator_type"], as_dict=True)
        if not t or not t.is_active or t.kind != KIND_CONTRACT \
                or t.creator_type != doc.get("creator_type"):
            frappe.throw(_("Mẫu {0} không dùng được cho creator {1} (mẫu ngừng dùng hoặc khác loại). "
                           "Chọn lại mẫu hoặc để trống cho hệ thống tự chọn.")
                         .format(chosen, doc.get("creator_type") or "?"))
        return chosen
    name = kol_lookup.pick_template(kind, doc.get("creator_type"), doc.get("service_type"),
                                    doc.get("payment_schedule") == kol.PAY_ADVANCE)
    if not name:
        frappe.throw(_("Chưa có mẫu {0} đang dùng cho creator {1} / {2}. Nhờ Kế toán thêm mẫu.")
                     .format(kind, doc.get("creator_type") or "?", doc.get("service_type") or "?"))
    return name


def _safe(text):
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in (text or ""))[:80]


def generate_contract(name, user):
    doc = frappe.get_doc(kol_lookup.CR_DT, name)
    if not kol.is_kol(doc) or not can_manage(doc, user):
        frappe.throw(_("Bạn không được tạo hợp đồng cho phiếu này."), frappe.PermissionError)
    if doc.get("approval_request"):
        from ecentric_workspace.approval_center.features.contract_review.application.kol_service import approval_status
        if approval_status(doc) not in ("Information Required",):
            frappe.throw(_("Chỉ tạo lại hợp đồng khi phiếu đang nháp hoặc cần bổ sung."))
    if doc.get("request_type") != kol.TEMPLATE_EC:
        frappe.throw(_("Phiếu dùng mẫu của creator: tải tệp lên thay vì tạo từ mẫu."))
    from ecentric_workspace.approval_center.features.contract_review.application import kol_service
    kol_service.prepare_draft(doc)
    kol_service.apply_amounts(doc, strict=True)
    out = build_contract(doc, force=True)
    doc.save(ignore_permissions=True)
    return out


def _fingerprint(tpl, values):
    raw = json.dumps({"tpl": tpl.name, "file": tpl.template_file, "v": tpl.get("version") or "",
                      "values": values}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def build_contract(doc, force=False):
    """Sinh (lai) hop dong tu DU LIEU HIEN TAI cua phieu. Khong luu - nguoi goi luu.

    Dau van tay (`contract_fingerprint`) = mau + moi gia tri dien vao. Luc gui / gui lai, dau
    van tay lech = tep dang dinh kem khong con khop so tien / creator / SO tren phieu -> sinh
    lai, de van ban gui ky luon dung voi con so duoc duyet va tran DNTT (QC 11/11)."""
    creator = creator_row(doc.get("creator"))
    if not creator:
        frappe.throw(_("Chọn creator trước khi tạo hợp đồng."))
    from ecentric_workspace.approval_center.features.contract_review.application import kol_service
    kol_service.assign_number(doc, creator)
    tpl = frappe.get_doc("EC Contract Template", template_for(doc, KIND_CONTRACT))
    values = kol.placeholders(doc.as_dict(), creator, kol_lookup.brand_code(doc.get("brand")),
                              doc.get("so_label"))
    fp = _fingerprint(tpl, values)
    if not force and doc.get("contract_file") and doc.get("contract_fingerprint") == fp:
        return {"contract_file": doc.contract_file, "contract_no": doc.contract_no,
                "missing": _missing_list(doc), "template": tpl.name, "regenerated": False}
    data = file_bytes(tpl.template_file)
    content, unknown = docx_fill.fill_docx(data, values)
    used = docx_fill.find_placeholders(data)
    missing = sorted(set(unknown) | set(kol.empty_required(values, used, doc.get("creator_type"))))
    old = doc.get("contract_file")
    doc.contract_template = tpl.name
    doc.contract_file = attach(doc, "HDDV_%s.docx" % _safe(doc.contract_no), content)
    # Dinh kem chinh = hop dong moi; bo ban sinh truoc (khong de nguoi duyet thay hai phien ban).
    if not doc.get("request_attachment") or doc.get("request_attachment") == old:
        doc.request_attachment = doc.contract_file
    if old and old != doc.contract_file:
        _drop_generated(doc, old)
    doc.contract_fingerprint = fp
    doc.missing_placeholders = ", ".join(missing) or None
    return {"contract_file": doc.contract_file, "contract_no": doc.contract_no,
            "missing": missing, "template": tpl.name, "regenerated": True}


def _missing_list(doc):
    return [x.strip() for x in (doc.get("missing_placeholders") or "").split(",") if x.strip()]


def _drop_generated(doc, file_url):
    """Go ban hop dong do HE THONG sinh truoc do (chi tep HDDV_ gan vao chinh phieu nay)."""
    name = frappe.db.get_value("File", {"file_url": file_url, "attached_to_doctype": doc.doctype,
                                        "attached_to_name": doc.name}, "name")
    # Phieu da tung gui (co approval_request): GIU tep cu lam vet - ban do co the da len
    # SharePoint / da duoc chup doi chung. Chi don ban nhap chua ai thay.
    if doc.get("approval_request"):
        return
    if name and (frappe.db.get_value("File", name, "file_name") or "").startswith("HDDV_"):
        frappe.delete_doc("File", name, ignore_permissions=True, force=True)


def generate_acceptance(doc, row, creator):
    tpl = frappe.get_doc("EC Contract Template", template_for(doc, KIND_BBNT))
    values = kol.acceptance_placeholders(doc.as_dict(), creator, row.as_dict(),
                                         kol_lookup.brand_code(doc.get("brand")), doc.get("so_label"))
    data = file_bytes(tpl.template_file)
    content, unknown = docx_fill.fill_docx(data, values)
    used = docx_fill.find_placeholders(data)
    missing = sorted(set(unknown) | set(kol.empty_required(values, used, doc.get("creator_type"))))
    url = attach(doc, "BBNT_%s_dot%s.docx" % (_safe(doc.contract_no), row.idx), content)
    return url, missing


def inspect_template(tpl):
    """Goi tu controller EC Contract Template luc luu: liet ke placeholder, bao ten la."""
    if not tpl.get("template_file"):
        return
    if not tpl.template_file.lower().endswith(".docx"):
        frappe.throw(_("Mẫu phải là tệp .docx."))
    found = docx_fill.find_placeholders(file_bytes(tpl.template_file))
    known = kol.known_placeholders(tpl.get("kind") == KIND_BBNT)
    tpl.placeholders = ", ".join(found) or None
    tpl.unknown_placeholders = ", ".join(p for p in found if p not in known) or None
