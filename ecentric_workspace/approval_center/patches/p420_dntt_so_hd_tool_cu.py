# Copyright (c) 2026, eCentric and contributors
"""20/11/2026 (PO): DNTT Booking KOL ngoai le "hop dong ky o tool cu" luu so HD cu vao
EC Payment Request.ec_legacy_contract_no de trang DNTT hien cho nguoi duyet cac DNTT khac cung so
(ngoai le khong co tran chi). Dien lai cho phieu DA GUI truoc ngay deploy: chon "No", loai TT_KOL,
o ly do co so HD dang tool cu. Idempotent: chi dien o dang trong. Loi -> Error Log, khong nem.
"""
import frappe

_DT = "EC Payment Request"


def execute():
    if not frappe.db.has_column(_DT, "ec_legacy_contract_no"):
        return
    try:
        from ecentric_workspace.approval_center.features.contract_review.application.kol_funding import old_numbers
        rows = frappe.get_all(_DT, filters={"has_purchase_request": "No", "ec_loai_chi_phi": "TT_KOL",
                                            "approval_request": ["is", "set"]},
                              fields=["name", "no_purchase_request_reason", "ec_legacy_contract_no"],
                              limit_page_length=0)
        n = 0
        for r in rows:
            if (r.ec_legacy_contract_no or "").strip():
                continue
            nos = old_numbers(r.no_purchase_request_reason)
            if nos:
                frappe.db.set_value(_DT, r.name, "ec_legacy_contract_no", ", ".join(nos), update_modified=False)
                n += 1
        frappe.logger("approval_center").info("p420: dien so HD tool cu cho %s/%s DNTT" % (n, len(rows)))
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p420 dntt so hd tool cu")
