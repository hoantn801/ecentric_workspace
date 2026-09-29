# Copyright (c) 2026, eCentric and contributors
"""Ham Jinja cho trang chu (hooks.py jinja.methods).

Trang chu la Web Page Jinja render theo tung nguoi (A67 §3). Ham nay cho trang biet TRUOC
lan ve dau: hom nay trang tri muc nao cho nguoi xem nay, va popup co gi de hien khong - de
trang tri nam san trong markup (khong JS dung/doi bo cuc sau khi tai, A65 §5) va JS popup
khong goi API khi khong co gi.

Khong bao gio nem loi (service.celebration tu nuot loi, tra muc 0)."""
import frappe

from ecentric_workspace.home_today import service


def home_today_celebration():
    return service.celebration(frappe.session.user)
