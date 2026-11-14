# Copyright (c) 2026, eCentric and contributors
"""15/11/2026: QC dem - `partner_signer_email` vao chu ky duyet cua phieu KOL (service.KOL_MATERIAL_FIELDS).

Phieu KOL dang chay (gui tu 12/11, dang cho duyet / can bo sung) luu chu ky tinh theo danh sach CU:
khong co patch nay thi gui lai sau bo sung luon "doi noi dung" -> duyet lai tu cap 1 du khong ai sua.
Tinh lai CHI khi chu ky dang luu khop dung du lieu hien tai theo danh sach cu (nghia la chua ai sua
tu luc gui) - khop thi ghi chu ky moi (co email). Khong khop thi giu nguyen (de duyet lai, an toan).
Loi -> Error Log, KHONG nem."""
import hashlib
import json

import frappe

_DT = "EC Contract Review Request"
_OPEN = ("Pending", "Information Required")
_NEW_FIELD = "partner_signer_email"


def _sig(row, fields):
    vals = {f: str(row.get(f) or "") for f in fields}
    return hashlib.sha1(json.dumps(vals, sort_keys=True).encode("utf-8")).hexdigest()


def execute():
    if not frappe.db.exists("DocType", _DT):
        return
    try:
        svc = frappe.get_module("ecentric_workspace.approval_center.features.contract_review.application.service")
        new_fields = svc.MATERIAL_FIELDS + svc.KOL_MATERIAL_FIELDS
        old_fields = [f for f in new_fields if f != _NEW_FIELD]
        rows = frappe.get_all(_DT, filters={"contract_type": "KOL/KOC / Creator (EC)",
                                            "approval_request": ["is", "set"]},
                              fields=["name", "approval_request", "material_signature"] + new_fields,
                              limit_page_length=0)
        doi = 0
        for r in rows:
            status = frappe.db.get_value("EC Approval Request", r.approval_request, "approval_status")
            if status not in _OPEN or not r.material_signature:
                continue
            if r.material_signature == _sig(r, old_fields):
                frappe.db.set_value(_DT, r.name, "material_signature", _sig(r, new_fields), update_modified=False)
                doi += 1
        frappe.logger("approval_center").info("p383: tinh lai chu ky duyet %s / %s phieu KOL" % (doi, len(rows)))
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p383 chu ky duyet KOL")
