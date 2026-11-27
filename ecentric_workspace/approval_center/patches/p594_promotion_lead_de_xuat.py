# Copyright (c) 2026, eCentric and contributors
"""Promotion "huong 2" (27/11/2026, Hoan chot): Lead de xuat cho nguoi minh quan ly (cap duoi truc
tiep + gian tiep) nhung KHONG thay / KHONG nhap luong; nguoi duyet dau tien co quyen xem luong dien
luong khi duyet (salary_pending).

Schema (salary_pending / salary_filled_by / salary_filled_at + permlevel 1 cho 3 o luong) do bench
migrate tu dong bo tu DocType JSON - patch nay KHONG dung toi schema. Phieu dang chay: salary_pending
mac dinh 0 -> giu nguyen hanh vi cu.

Patch chi resync HAI trang tu nguon repo:
  1. /approvals/promotion                       - an o luong khi nhan su chon la cap duoi khong xem
                                                  duoc luong; o dien luong cho nguoi duyet co quyen.
  2. /huong-dan/thang-chuc-dieu-chinh-luong     - doan ngan theo luat moi.
Idempotent; moi trang mot try; ket qua ghi Error Log, KHONG nem (patch nem = migrate dung lai)."""
import frappe

_PAGES = (
    ("promotion", "ecentric_workspace.approval_center.features.promotion.infrastructure.page_sync",
     "approvals/promotion", ("fill_salary", "_salary_note")),
    ("huong-dan", "ecentric_workspace.guides.pages.thang_chuc_dieu_chinh_luong.page_sync",
     "huong-dan/thang-chuc-dieu-chinh-luong", ("người mình quản lý", "Cập nhật 27/11/2026")),
)


def execute():
    ket = []
    for label, module, route, marks in _PAGES:
        try:
            res = frappe.get_module(module).sync() or {}
            ket.append("%s: %s" % (label, res.get("action")))
        except Exception:
            ket.append("%s LOI\n%s" % (label, frappe.get_traceback()))
            continue
        html = frappe.db.get_value("Web Page", {"route": route}, "main_section_html") or ""
        missing = [m for m in marks if m not in html]
        if missing:
            ket.append("%s: thieu landmark %s" % (label, missing))
    frappe.log_error(title="p594 promotion lead de xuat", message="\n".join(ket))
