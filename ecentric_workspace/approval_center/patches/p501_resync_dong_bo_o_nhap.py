# Copyright (c) 2026, eCentric and contributors
"""p501_resync_dong_bo_o_nhap (24/11/2026, Hoan: "o mail nay khong co dropdown", "mot so form chi la
mot nut tai tep rat xau", "dropdown rat xau, dong bo voi toan ERP"): sync lai 6 trang form tu nguon repo
(A65) - cac o nhap email nguoi trong cong ty khai data-ec-people (o chon nguoi dung chung, asset
public/js|css/ec_people_picker.bundle.*). Vung keo-tha tep + combobox cho moi select trong form do asset
ec_formkit dam nhan (khong can sync trang).

Moi trang mot khoi try; trang nao lech live (khoa chong troi tu choi) -> ghi Error Log, trang khac van
chay. KHONG nem loi, KHONG xoa du lieu, KHONG goi ra ngoai."""
import frappe

FEATURES = (
    "booking_request",
    "contract_review",
    "employee_info_update",
    "hiring_request",
    "lateral_move",
    "resignation",
)


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    ket = []
    for f in FEATURES:
        mod = "ecentric_workspace.approval_center.features.%s.infrastructure.page_sync" % f
        try:
            res = frappe.get_module(mod).sync() or {}
            act = res.get("action") if isinstance(res, dict) else res
            ket.append("%s: %s" % (f, act))
            frappe.db.commit()
        except Exception:
            frappe.db.rollback()
            ket.append("%s LOI\n%s" % (f, frappe.get_traceback()))
    frappe.log_error(title="p501 dong bo o nhap form", message="\n".join(ket))
