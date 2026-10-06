# Copyright (c) 2026, eCentric and contributors
"""Cong DUY NHAT tu app nay vao Raven. Chi goi ham CONG KHAI cua Raven (cac ham whitelist ma
web app cua chinh Raven goi), chay DUOI PHIEN nguoi dung hien tai:

    raven.api.raven_channel.get_all_channels       kenh + DM nguoi nay la thanh vien / thay duoc
    raven.api.raven_message.get_unread_count_for_channels   so tin chua doc theo kenh
    raven.api.raven_users.get_list                 ten + anh nguoi dung Raven (co kiem quyen)

Khong doc bang cua Raven truc tiep, khong ignore_permissions: kenh rieng / DM cua nguoi khac
khong bao gio di qua day vi Raven da loc. Raven doi ten ham o ban sau -> loi duoc bat o
api.py va tra "khong tai duoc", khong lam vo trang ERP.
"""
import frappe

from ecentric_workspace.chat import constants as C
from ecentric_workspace.chat import inbox as I

_FN_CHANNELS = "raven.api.raven_channel.get_all_channels"
_FN_UNREAD = "raven.api.raven_message.get_unread_count_for_channels"
_FN_USERS = "raven.api.raven_users.get_list"


def kill_switch_on():
    return bool(frappe.conf.get(C.KILL_SWITCH))


def raven_installed():
    try:
        return C.RAVEN_APP in (frappe.get_installed_apps() or [])
    except Exception:
        return False


def chat_enabled():
    """Co hien loi vao chat (bieu tuong thanh tren, muc menu) hay khong. KHONG theo nguoi:
    HTML trang dung chung cache cho moi nguoi; nguoi chua co quyen bam vao se thay loi
    huong dan tren trang /chat."""
    try:
        return (not kill_switch_on()) and raven_installed()
    except Exception:
        return False


def has_role(user=None):
    return C.RAVEN_ROLE in (frappe.get_roles(user or frappe.session.user) or [])


def state(user=None):
    return I.access_state(kill_switch_on(), raven_installed(), has_role(user))


def list_channels():
    res = frappe.get_attr(_FN_CHANNELS)(hide_archived=True) or {}
    return list(res.get("channels") or []), list(res.get("dm_channels") or [])


def unread_rows():
    return list(frappe.get_attr(_FN_UNREAD)() or [])


def user_cards():
    """{user_id: {full_name, user_image}} - CHI hai truong nay; bo so dien thoai / trang thai."""
    out = {}
    for u in frappe.get_attr(_FN_USERS)() or []:
        uid = u.get("name")
        if uid:
            out[uid] = {"full_name": u.get("full_name") or "", "user_image": u.get("user_image") or ""}
    return out
