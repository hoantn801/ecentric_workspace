# Copyright (c) 2026, eCentric and contributors
"""p001: 3 CLB ban dau cho Bang tin (PO 04/10/2026: "bat dau voi 3 - 4 CLB co that" de khong co CLB
trong trong "chet"). Chi tao khi CHUA co CLB nao - khong ghi de gi. Chua co nguoi phu trach: HR chon
o /bang-tin/quan-ly?tab=clb. Mo ta viet chung chung, HR sua lai cho dung lich sinh hoat that."""
import frappe

CLUBS = (
    ("Chạy bộ", "chay-bo", "\U0001f3c3", "green", "Rủ nhau chạy bộ, chia sẻ cung đường và thành tích, cùng đăng ký giải chạy."),
    ("Bóng đá", "bong-da", "⚽", "pink", "Đá bóng giao lưu sau giờ làm, rủ người đủ đội, hẹn sân."),
    ("Cầu lông", "cau-long", "\U0001f3f8", "navy", "Đánh cầu lông sau giờ làm, xếp cặp đánh đôi, rủ người mới chơi."),
)


def execute():
    if not frappe.db.table_exists("EC Club") or frappe.db.count("EC Club"):
        return
    for title, slug, emoji, color, desc in CLUBS:
        frappe.get_doc({"doctype": "EC Club", "club_name": title, "slug": slug, "emoji": emoji, "color": color,
                        "category": "Thể thao", "description": desc, "status": "Đang hoạt động"}
                       ).insert(ignore_permissions=True)
