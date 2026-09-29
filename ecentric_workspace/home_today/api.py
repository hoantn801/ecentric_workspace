# Copyright (c) 2026, eCentric and contributors
"""Cua HTTP DUY NHAT cua popup "Hom nay o eCentric". Nguoi dung lay tu phien - khong ham nao
nhan tham so `user` (A66 §7: whitelist + tham so nguoi thao tac = mao danh duoc)."""
import frappe

from ecentric_workspace.home_today import service


@frappe.whitelist()
def get_today():
    """Du lieu popup cho nguoi dang dang nhap. Chi doc."""
    return service.today(frappe.session.user)


@frappe.whitelist(methods=["POST"])
def toggle_reaction(target, kind):
    """Bat/tat mot cam xuc (tim / hoa / banh / phao) tren mot muc cua hom nay."""
    try:
        return service.toggle(frappe.session.user, str(target or ""), str(kind or ""))
    except service.HomeTodayError as e:
        frappe.throw(str(e), exc=frappe.ValidationError)
