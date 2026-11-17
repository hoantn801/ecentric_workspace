# Copyright (c) 2026, eCentric and contributors
"""17/11/2026 (PO): tep hop dong (tep NGUOI GUI dinh kem) vao chu ky duyet cua phieu hop dong thuong
(service._signature, "__files"): doi tep luc bo sung = duyet lai tu dau.

Phieu thuong dang CHO DUYET luu chu ky tinh theo cong thuc cu (khong co tep): khong co patch nay thi
gui lai sau bo sung luon "doi noi dung" -> duyet lai tu cap 1 du khong ai doi gi. Tinh lai CHI khi
chu ky dang luu khop du lieu hien tai theo cong thuc cu (chua ai sua). Chi phieu Pending - phieu
"Can bo sung" co the vua bi doi tep truoc khi patch chay (cung ly do p387). Loi -> Error Log, KHONG nem."""
import hashlib
import json

import frappe

_DT = "EC Contract Review Request"
_KOL = "KOL/KOC / Creator (EC)"


def _old_sig(row, fields):
    vals = {f: str(row.get(f) or "") for f in fields}
    return hashlib.sha1(json.dumps(vals, sort_keys=True).encode("utf-8")).hexdigest()


def execute():
    if not frappe.db.exists("DocType", _DT):
        return
    try:
        svc = frappe.get_module("ecentric_workspace.approval_center.features.contract_review.application.service")
        fields = list(svc.MATERIAL_FIELDS)
        rows = frappe.get_all(_DT, filters={"contract_type": ["!=", _KOL], "approval_request": ["is", "set"]},
                              fields=["name", "approval_request", "material_signature", "requested_by",
                                      "contract_type"] + fields, limit_page_length=0)
        doi = 0
        for r in rows:
            status = frappe.db.get_value("EC Approval Request", r.approval_request, "approval_status")
            if status != "Pending" or not r.material_signature:
                continue
            if r.material_signature == _old_sig(r, fields):
                frappe.db.set_value(_DT, r.name, "material_signature", svc._signature(r), update_modified=False)
                doi += 1
        frappe.logger("approval_center").info("p397: tinh lai chu ky duyet %s / %s phieu hop dong thuong"
                                              % (doi, len(rows)))
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p397 chu ky duyet hop dong (tep)")
