# Copyright (c) 2026, eCentric and contributors
"""Alert Center (5 trang /alerts*): HTML server ve dung trang thai cuoi, het goi API lap - 29/09/2026.

Brief NHIEU_LOP/brief_alert_center.md (chat Trang chu/Shell). Do bang NHIEU_LOP/do_lop_trang.js
tren live TRUOC khi sua (tab an, giong baseline cua brief):

  trang                        gone  id/mv   api  trung lap                             khoi chen
  /alerts                         2  24/21    22  by_dimension x3, list_alerts x2              4
  /alerts/policies               25  19/17    39  policy_missing_skus x21                      4
  /alerts/rules                   4   8/6     14  -                                            4
  /alerts/locks                   2  22/20    27  list_actions x14                             4
  /alerts/integration-health     12   7/5     14  -                                            4
  (ca 5 trang con "(frappe.call qua /?cmd) x2" = notification_center get_preferences +
   get_unread_count: HAI method khac nhau cua chuong thong bao, khong thuoc Alert Center.)

Goc va cach sua:
  - Dai 28px tren moi trang = <p id="al-scope-line"> rong (cao 0) duoc JS dien sau my_scope
    -> CSS giu san 1 dong 24px, cat "..." neu dai.
  - Bang Price Setup / Integration Health auto-layout no rong theo du lieu (1.946 / 1.993px)
    -> tieu de cot bi day ra ngoai man hinh: table-layout:fixed + <colgroup>.
  - Phan trang + Gift Exemptions (policies), Advanced Exceptions (rules) bi hang du lieu day
    xuong: khung bang / #ru-defaults giu cho 60vh. Locks: phan trang dat TREN bang.
  - ih-refresh lech 157px: khoi dung luong (chi System Manager) hien ra phia tren -> dat duoi bang.
  - Goi lap -> endpoint gop: api_sku_catalog.policy_coverage_summary, api_actions.lock_queue,
    api_dashboard.by_dimensions; /alerts chi tai danh sach alert khi dang mo; locks doi hash
    bang replaceState (truoc: gan hash -> hashchange -> tai lai lan 2).
  - Khoi chen: CSS + JS thanh asset cua app (public/alerts/*, ?v=<sha>); bo
    <script id="ec-csrf-fetch-patch"> (goi API qua window.ecApi.post).
  - Donut brand co id "ec-brand" trung quy tac #ec-brand{position:fixed} trong skin dang nhap
    (Website Settings > head_html) -> donut troi o dau trang; doi id sang al-ch-*, luoi 3 donut
    tu khai min-width:0.

Mo phong truoc deploy (HTML moi khong JS vs DOM live sau JS, ca hai ap CSS/markup moi, tren
chinh tab live): ca 5 trang gone 2 (the "Tai khoan" cua menu chung), mv 0, khong khoi nao mat.

Idempotent: sync_all() tra ve "unchanged" tren site da co san ban nay. Khong bao gio raise
(bai hoc p116: mot exception trong patch lam chet ca lan migrate).
"""
import frappe

#: Moi trang phai co cac dau moc nay sau khi dong bo (ban moi da toi noi).
_EXPECT = {
    "alerts": ('/assets/ecentric_workspace/alerts/ec_alert_overview.js?v=', 'id="al-ch-brand"'),
    "alerts/policies": ('/assets/ecentric_workspace/alerts/ec_alert_policies.js?v=', 'al-tbl-fixed al-tbl-pl'),
    "alerts/rules": ('/assets/ecentric_workspace/alerts/ec_alert_rules.js?v=',),
    "alerts/locks": ('/assets/ecentric_workspace/alerts/ec_alert_locks.js?v=',),
    "alerts/integration-health": ('/assets/ecentric_workspace/alerts/ec_alert_health.js?v=', 'al-tbl-fixed al-tbl-ih'),
}


def execute():
    try:
        from ecentric_workspace.alerts.site_pages import sync as site_sync
        results = site_sync.sync_all()
        frappe.log_error("p223 alert pages: %s" % [(r.get("route") or r.get("page"), r.get("action"))
                                                   for r in results], "p223 alert nhieu lop")
        refused = [r for r in results if r.get("action") in ("refused", "error")]
        if refused:
            frappe.log_error(
                "p223: %d trang KHONG cap nhat (khoa chong troi / loi): %s. Live dang giu ban khong "
                "nam trong BASELINE/SUPERSEDES - doi chieu live_sha roi them vao SUPERSEDES_SHA256 "
                "cua trang do." % (len(refused), refused), "p223 REFUSED")
        for route, marks in _EXPECT.items():
            html = frappe.db.get_value("Web Page", {"route": route}, "main_section_html") or ""
            missing = [m for m in marks if m not in html]
            if 'id="ec-csrf-fetch-patch"' in html:
                missing.append("(van con ec-csrf-fetch-patch)")
            if missing:
                frappe.log_error("p223 %s: thieu landmark=%s" % (route, missing), "p223 KHONG toi noi")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p223 failed")
