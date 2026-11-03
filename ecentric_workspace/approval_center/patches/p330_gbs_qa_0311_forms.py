# Copyright (c) 2026, eCentric and contributors
"""Form GBS SO + PO: QA dem 03/11/2026 (chat GBS) - sua logic + UX.

SO (/gbs-so-form-v2): kiem tra gom loi canh truong truoc khi gui, nut "dang gui / da gui" + link phieu,
nhap SO rieng (ec_gbs_so_draft_v1; nut Luu nhap truoc day hong), chan roi trang khi dang nhap,
ban phim cho Muc uu tien/combobox, nhan tieng Viet; Sua & gui lai: giu priority, khong ghi de thue,
chan file dang tai, gui file moi dang dict.
PO (/gbs-po-form-v2): khoa loai PO khi tao tu SO / sua, nhap PO rieng (bo doc mso_draft), chong tao
PO so EC trung khi buoc trinh duyet loi, bo payload from_so lech SO, escape banner from_so, chan SL<=0
va ngay nguoc, mo /approval dung phieu sau khi gui. Giu 3 moc p227.

Idempotent: sync() tra ve "unchanged" tren site da co ban nay.
"""
import frappe

_EXPECT = {
    "gbs_so_form_v2": ("gbs-so-form-v2", ("ec_gbs_so_draft_v1", "window.ecSoUx")),
    "gbs_po_form_v2": ("gbs-po-form-v2", ('id="ecAddSoBox"', "ec_gbs_po_draft_v1", "sales_order: tr.getAttribute('data-so')")),
}


def execute():
    import importlib
    for mod, (route, marks) in _EXPECT.items():
        try:
            ps = importlib.import_module("ecentric_workspace.legacy_pages.%s.page_sync" % mod)
            res = ps.sync()
            action = (res or {}).get("action")
            frappe.log_error("p330 %s sync=%s" % (route, action), "p330 gbs qa 0311")
            if action == "refused":
                frappe.log_error("p330 %s: upsert TU CHOI GHI (khoa chong troi) - live dang giu ban "
                                 "khong nam trong BASELINE/SUPERSEDES." % route, "p330 REFUSED")
                continue
            html = frappe.db.get_value("Web Page", {"route": route}, "main_section_html") or ""
            missing = [m for m in marks if m not in html]
            if missing:
                frappe.log_error("p330 %s: thieu landmark=%s" % (route, missing), "p330 KHONG toi noi")
        except Exception:
            frappe.log_error(frappe.get_traceback(), "p330 %s failed" % route)
