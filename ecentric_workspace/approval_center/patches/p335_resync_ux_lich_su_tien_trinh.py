# Copyright (c) 2026, eCentric and contributors
"""p335: dot UX "de dung cho nhan vien" tren trang phe duyet (03/11/2026, Hoan).

Asset dung chung moi `public/js/ec_approval_ui.bundle.js` (hooks.py web_include_js) - 31 trang
form + trang hub chi them dong UY QUYEN cho no (ban cu giu lam du phong):
  * Lich su: nhan tieng Viet cho DU 15 option cua EC Approval Action.action (truoc day con
    "Attachment Added", "Reminded", "System Transition"... chu tieng Anh tho), gio dd/mm/yyyy,
    trang thai chuyen doi tieng Viet. Hub: moi nhat len dau + co gio (truoc doc sai truong).
  * Thanh tien trinh: cham tron cap duyet hien DUNG so cap engine ("Cap 1 · <ten>"); "Da gui" /
    "Hoan tat" khong danh so (truoc: Cap 1 hien so 2 -> mot lan ho tro nham). Cot "Tien do"
    trong danh sach: "Cap X/<so cap>" thay cho "Buoc X/N" dem ca "Da gui".
  * Loi ky thuat (Traceback, NoneType, SQL, CSRF) -> cau tieng Viet; loi mo chi tiet noi ro ly do.

Chi RESYNC trang (khong doi du lieu). Landmark = dieu PHAI CO tren ban song sau sync. Trang bi
tu choi (lech khoa) / loi -> ghi log, KHONG BAO GIO nem: mot trang hong khong duoc lam gay migrate.
"""
import frappe

MOC = "EcApprovalUI"
_FEATURES = (
    "affiliate_bonus",
    "ai_topup",
    "asset_damage_loss",
    "asset_request",
    "booking_request",
    "budget_setting",
    "clearance_request",
    "compensation_leave",
    "contract_review",
    "daily_target",
    "data_request",
    "document_request",
    "employee_info_update",
    "employee_referral",
    "hiring_request",
    "hr_activity",
    "late_early_out",
    "lateral_move",
    "leave",
    "livestream_sample",
    "livestream_supplies",
    "new_staff_preparation",
    "offer_request",
    "outside_work",
    "payment_request",
    "promotion",
    "purchase_request",
    "resignation",
    "service_referral",
    "special_bonus",
    "system_request",
)
_TRANG = tuple(
    ("ecentric_workspace.approval_center.features.%s.infrastructure.page_sync" % f, f)
    for f in _FEATURES
) + (("ecentric_workspace.approval_center.ui.all_requests.page_sync", "all_requests"),)


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    ket, hong = [], []
    for mod_path, ten in _TRANG:
        try:
            mod = frappe.get_module(mod_path)
            res = mod.sync() or {}
            if res.get("action") == "refused":
                hong.append(ten + " (refused)")
                continue
            html = frappe.db.get_value("Web Page", {"route": mod.ROUTE}, "main_section_html") or ""
            if MOC not in html:
                hong.append(ten + " (thieu dau moc)")
            else:
                ket.append(ten)
        except Exception:
            hong.append(ten + " (loi)")
            frappe.log_error(frappe.get_traceback(), "p335 resync %s" % ten)
    msg = "ok %d/%d; hong: %s" % (len(ket), len(_TRANG), hong)
    frappe.logger("approval_center").info("p335_resync_ux_lich_su_tien_trinh: " + msg)
    if hong:
        frappe.log_error(title="p335 resync UX lich su/tien trinh", message=msg)
