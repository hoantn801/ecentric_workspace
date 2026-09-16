# Copyright (c) 2026, eCentric and contributors
"""Thanh tab ve ra nhung BAM KHONG DOI GI - sua dinh tuyen cho ca 28 form (16/09).

p200 mo lai thanh tab tren 28 form va bai test `test_tabs_all_features.mjs` xanh voi 118
assertion. Nhung do tren production 16/09: bam mot tab thi URL doi thanh `?tab=my-requests`,
con man hinh van dung o form "Tao moi", va KHONG co loi console, KHONG co goi API nao.

Hai nguyen nhan, hai nua khac nhau, cong lai thanh: khong form nao chay duoc.

  27 form: `readRoute()` doc tham so vao bien `t` roi khong dung no -
      var t=q.get("tab"); state.tab = state.id?"detail":"create";
    `state.tab` bi gan cung. `tabAllowed(t)` nam ngay duoi cung chua bao gio duoc goi. Hai
    ky hieu chet nam canh nhau; JS khong noi gi ve bien gan roi bo, va khong co cong nao
    quet dieu do (cong pyflakes chi soi Python).

  booking_request: `readRoute` DUNG, nhung `boot()` khong gan listener `[data-tab]` nao ca.
    27 form kia deu co dong do, rieng form nay thieu. Nut hoan toan tro.

VI SAO TEST CU KHONG BAT DUOC: 118 assertion deu chi hoi "renderTabs co ve du nut khong".
Khong assertion nao bam vao nut roi kiem man hinh doi. Test dung thu da viet ra, khong test
hanh vi nguoi dung can. `tests/js/test_tabs_route.mjs` (dot nay) bam that va doi `state.tab`
phai doi + dung endpoint danh sach phai duoc goi.

KHONG gop vao dot nay: tab "Toi xu ly" cho payment_request va booking_request. Ca hai
DocType co `fulfillment_status`, va payment_request da bind fulfillment API o server, nhung
UI cua ca hai KHONG co `renderFulfillment`. Bat tab len se dan toi mot man hinh trong - te
hon la khong co tab. Ghi vao 03_BUGS_AND_NEXT_STEPS.md, dung rieng.

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

# Dau moc phai co tren ban SONG. `tabAllowed(t)` trong bieu thuc gan `state.tab` la thu p200
# thieu - do chinh no, khong do mot chuoi chung chung nhu "state.boot.tabs" (p200 do chuoi do
# va van xanh trong khi tinh nang khong chay).
_LANDMARKS = (
    'tabAllowed(t)?t:"create"',
    'closest("[data-tab]")',
)


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
            frappe.log_error(frappe.get_traceback(), "p202 resync %s" % feature)
    frappe.log_error("dong bo %d form; loi: %s; thieu dau moc: %s"
                     % (len(_FEATURES), hong or "(khong)", thieu or "(khong)"),
                     "p202 resync tab route")
