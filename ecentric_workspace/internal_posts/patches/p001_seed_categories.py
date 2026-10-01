# Copyright (c) 2026, eCentric and contributors
"""p001: 4 chuyen muc Tin noi bo ban dau (PO Hoan chot 01/10/2026, mockup v5).

Chay lai bao nhieu lan cung duoc: chuyen muc da co (theo ma) thi GIU NGUYEN - HR co the da doi
ten / mau / thu tu tren /app, patch khong ghi de. HR them chuyen muc moi tren /app/ec-post-category.
FAIL-SAFE: loi mot dong -> Error Log, khong chan migrate.
"""
import frappe

from ecentric_workspace.internal_posts import constants as C

TITLE = "internal_posts p001 seed categories"

#: (ma, ten, mau nen, bieu tuong, loai popup trang chu, mo ta)
SEED = (
    ("thong-bao", "Thông báo", "navy", "megaphone", "Thông báo",
     "Thông báo chung của công ty: lịch, sự kiện, thay đổi vận hành."),
    ("huong-dan", "Hướng dẫn", "green", "book", "Tính năng mới",
     "Cách dùng ERP và quy trình. Gồm cả các bài hướng dẫn cũ ở /huong-dan."),
    ("tool-moi", "Tool / Module mới", "pink", "star", "Module mới",
     "Giới thiệu công cụ, module mới trên ERP."),
    ("chinh-sach", "Chính sách mới", "yellow", "doc", "Chính sách",
     "Quy chế, chính sách mới ban hành hoặc sửa đổi."),
)


def execute():
    if not frappe.db.exists("DocType", C.CATEGORY_DT):
        return
    created = []
    for order, (slug, name, color, icon, home_cat, desc) in enumerate(SEED, start=1):
        try:
            if frappe.db.exists(C.CATEGORY_DT, slug):
                continue
            frappe.get_doc({
                "doctype": C.CATEGORY_DT, "slug": slug, "category_name": name, "enabled": 1,
                "sort_order": order * 10, "color": color, "icon": icon,
                "home_category": home_cat, "description": desc,
            }).insert(ignore_permissions=True)
            created.append(slug)
        except Exception:
            frappe.log_error(title="%s: %s" % (TITLE, slug))
    if created:
        frappe.logger("internal_posts").info("p001 tao chuyen muc: %s" % ", ".join(created))
