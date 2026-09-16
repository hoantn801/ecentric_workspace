# Copyright (c) 2026, eCentric and contributors
"""Tab "Tat ca" + export tren CA 28 form phe duyet (16/09, Hoan).

YEU CAU: moi form co mot tab xem duoc TAT CA phieu cua form do, co bo loc, dong hien thi
day thong tin de "nhin vao khong can bam chi tiet cung du de ra quyet dinh", va co nut
export cho ke toan.

PHAM VI DU LIEU KHONG PHAI CAI MOI. Trang /approvals/all-requests da co san mot danh sach
lien form DA duoc kiem soat quyen: `reporting.scope.resolve_scope` phan nguoi dung thanh
bon bac va `scope_predicate` tra ve manh SQL PHAI duoc AND vao moi truy van. Tab nay dung
lai y nguyen bo may do, chi GHIM `approval_type` ve form dang mo (server ghi de, khong
nhan tu client). Khong co mo hinh quyen thu hai. Hau qua can biet truoc: voi nhan vien
thuong, "Tat ca" gan trung "Yeu cau cua toi" - DUNG, khong phai loi.

UI NAM TRON TRONG MOT ASSET DUNG CHUNG (`ec_alltab.bundle.js` + `.css`, khai trong
hooks.py). Moi main_section.html chi them 11 dong: cho phep tab trong `tabAllowed`, mot
dong trong `renderTabs`, mot nhanh trong `render()`, va `renderAll` goi thang vao bundle.
Chep bo loc + bang + export vao 28 file la tu tao ra dot sua 28 cho lan sau - dot 15/09
vua cho thay dieu gi xay ra khi mot trong 28 ban sao bi bo sot.

EXPORT: Hoan chot ai thay duoc tab thi export duoc; an toan den tu `scope_predicate` chu
khong tu viec an nut. Kem theo TRAN 5000 dong (mot cu bam khong duoc keo ca lich su thanh
toan ra file), GHI VET moi luot xuat (tep chua ten nguoi thu huong + so tai khoan ngan
hang), va POST chu khong GET (Frappe hoan tac moi ghi trong request GET, tuc tep van di ra
ma vet bien mat).

Landmark = dieu PHAI CO tren ban song sau khi sync."""
import frappe

_FEATURES = (
    "affiliate_bonus", "ai_topup", "asset_damage_loss", "asset_request", "booking_request",
    "budget_setting", "compensation_leave", "contract_review", "daily_target", "data_request",
    "document_request", "employee_info_update", "employee_referral", "hiring_request",
    "hr_activity", "late_early_out", "lateral_move", "leave", "livestream_sample",
    "livestream_supplies", "outside_work", "payment_request", "promotion", "purchase_request",
    "resignation", "service_referral", "special_bonus", "system_request",
)

# Do DUNG thu dot nay them, khong do mot chuoi chung chung. p200 do "state.boot.tabs" - mot
# chuoi da co san tu truoc - nen van xanh trong khi tinh nang khong chay.
_LANDMARKS = ('window.EcAllTab.render(b,{', 'if(tb.all) defs.push(["all"')


def execute():
    thieu, hong = [], []
    for feature in _FEATURES:
        try:
            mod = frappe.get_module(
                "ecentric_workspace.approval_center.features.%s.infrastructure.page_sync" % feature)
            res = mod.sync()
            if (res or {}).get("action") == "refused":
                hong.append(feature + " (refused)")
                continue
            html = frappe.db.get_value("Web Page", {"route": mod.ROUTE}, "main_section_html") or ""
            for m in _LANDMARKS:
                if m.replace(" ", "") not in html.replace(" ", ""):
                    thieu.append("%s: %s" % (feature, m))
        except Exception:
            hong.append(feature)
            frappe.log_error(frappe.get_traceback(), "p203 resync %s" % feature)
    frappe.log_error("dong bo %d form; loi: %s; thieu dau moc: %s"
                     % (len(_FEATURES), hong or "(khong)", thieu or "(khong)"),
                     "p203 resync tab tat ca")
