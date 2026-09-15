# Copyright (c) 2026, eCentric and contributors
"""Mo lai thanh tab quan ly tren CA 28 form phe duyet (15/09, Hoan).

TRUOC DOT NAY moi form chi ve MOT nut "Tao yeu cau". Trong khi do backend VAN tinh quyen cho
bon tab theo tung nguoi (`query_service` tra `tabs: {create, my_requests, my_approvals,
fulfillment}` bang `has_any_approver_row` va `_can_fulfil`), `tabAllowed` van doc dung bo quyen
do, va `render()` van dieu huong duoc - chi thieu duong bam vao. Go tay `?tab=my-requests` tren
URL thi van ra man hinh day du.

Tuc la mot manh chuc nang bi bo quen: luat dung, tinh dung, gui xuong tan man hinh roi khong
ai hien thi. Cung ho voi "helper khong ai goi", va cung kho thay y het - vi khong co gi DO.

SUA: thanh tab lay DUNG `state.boot.tabs` lam nguon, cung nguon voi `tabAllowed` - khong dung
mot danh sach thu hai roi hai ben troi nhau. Bat tab theo TUNG FORM co that:
  * 28/28 form: "Yeu cau cua toi"
  * form co nguoi duyet: "Cho toi duyet"
  * 6 form co buoc xu ly: "Toi xu ly"
Booking Request (form 28) truoc do khong co bo may danh sach nao - dot nay dung moi, dung
`list_my_requests` / `list_need_my_approval` ma `bind()` sinh san cho MOI form.

Bat mot tab ma form do khong co ham ve la goi ham ma - dung loi mac 08/09 khi chep JS sang ca
nhom. `tests/js/test_tabs_all_features.mjs` quet ca 28 form va chan viec do.

Landmark = dieu PHAI CO tren ban song sau khi sync."""
import frappe

_FEATURES = (
    "affiliate_bonus",
    "ai_topup",
    "asset_damage_loss",
    "asset_request",
    "booking_request",
    "budget_setting",
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
    "outside_work",
    "payment_request",
    "promotion",
    "purchase_request",
    "resignation",
    "service_referral",
    "special_bonus",
    "system_request",
)

_LANDMARKS = ("Y\u00eau c\u1ea7u c\u1ee7a t\u00f4i", "state.boot.tabs")


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
            html = frappe.db.get_value("Web Page", {"route": mod.ROUTE},
                                       "main_section_html") or ""
            for m in _LANDMARKS:
                if m not in html:
                    thieu.append("%s: %s" % (feature, m))
        except Exception:
            hong.append(feature)
            frappe.log_error(frappe.get_traceback(), "p200 resync %s" % feature)
    frappe.log_error("dong bo %d form; loi: %s; thieu dau moc: %s"
                     % (len(_FEATURES), hong or "(khong)", thieu or "(khong)"),
                     "p200 resync tabs")
