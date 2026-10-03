# Copyright (c) 2026, eCentric and contributors
"""p001: 6 chu de gop y ban dau (PO Hoan chot 04/10/2026, mockup Ban 1).

Chay lai bao nhieu lan cung duoc: chu de da co (theo ma) thi GIU NGUYEN - quan tri co the da doi
ten / mau / thu tu tren /app, patch khong ghi de. Them chu de moi tren /app/ec-feedback-topic.
FAIL-SAFE: loi mot dong -> Error Log, khong chan migrate.
"""
import frappe

from ecentric_workspace.feedback import constants as C

TITLE = "feedback p001 seed topics"

#: (ma, ten, mau, bieu tuong, goi y)
SEED = (
    ("van-phong", "Văn phòng & CSVC", "teal", "building", "Chỗ ngồi, điều hoà, wifi, gửi xe"),
    ("chinh-sach", "Chính sách & phúc lợi", "pink", "heart", "Nghỉ phép, phúc lợi, bảo hiểm"),
    ("quy-trinh", "Quy trình", "purple", "flow", "Cách làm việc giữa các phòng"),
    ("cong-cu", "Công cụ / ERP", "navy", "monitor", "Phần mềm, máy móc, tài khoản"),
    ("van-hoa", "Văn hoá & con người", "orange", "users", "Sự kiện, gắn kết, ghi nhận"),
    ("khac", "Khác", "gray", "dots", "Không thuộc các mục trên"),
)


def execute():
    if not frappe.db.exists("DocType", C.TOPIC_DT):
        return
    created = []
    for order, (slug, name, color, icon, hint) in enumerate(SEED, start=1):
        try:
            if frappe.db.exists(C.TOPIC_DT, slug):
                continue
            frappe.get_doc({"doctype": C.TOPIC_DT, "slug": slug, "topic_name": name, "enabled": 1,
                            "sort_order": order * 10, "color": color, "icon": icon, "hint": hint,
                            }).insert(ignore_permissions=True)
            created.append(slug)
        except Exception:
            frappe.log_error(title="%s: %s" % (TITLE, slug))
    if created:
        frappe.logger("feedback").info("p001 tao chu de: %s" % ", ".join(created))
