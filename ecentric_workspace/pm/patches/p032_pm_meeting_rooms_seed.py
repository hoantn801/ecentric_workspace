"""p032 - 5 phòng họp văn phòng mới (PO 05/11/2026) vào EC Meeting Room.

Each row = a Microsoft 365 room mailbox created by phong_hop/tao_phong_hop_exchange.ps1.
Idempotent: a room that already exists is left as is (admins may have edited it in Desk);
never deletes. Logs, never raises."""

import frappe

ROOMS = [
    # code, title, email, floor, note, sort
    ("5.1", "Phong", "room.phong@ecentric.vn", "Lầu 5", "Phòng lớn", 10),
    ("1.1", "Hoả", "room.hoa@ecentric.vn", "Lầu 1", "Lớn", 20),
    ("1.2", "Thổ", "room.tho@ecentric.vn", "Lầu 1", "Vừa", 30),
    ("1.3", "Thuỷ", "room.thuy@ecentric.vn", "Lầu 1", "Nhỏ", 40),
    ("5.2", "Cabin", "room.cabin@ecentric.vn", "Lầu 5", "Cabin cách âm", 50),
]


def execute():
    try:
        if not frappe.db.exists("DocType", "EC Meeting Room"):
            frappe.reload_doc("ecentric_workspace", "doctype", "ec_meeting_room")
        made = []
        for code, title, email, floor, note, sort in ROOMS:
            if frappe.db.exists("EC Meeting Room", code) or frappe.db.exists("EC Meeting Room", {"email": email}):
                continue
            frappe.get_doc({"doctype": "EC Meeting Room", "room_code": code, "room_title": title,
                            "email": email, "floor": floor, "note": note, "sort_order": sort,
                            "enabled": 1}).insert(ignore_permissions=True)
            made.append(code)
        print("[p032] meeting rooms created: %s" % (", ".join(made) or "none"))
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p032 meeting rooms seed")
