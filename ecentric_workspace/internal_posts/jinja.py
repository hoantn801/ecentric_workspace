# Copyright (c) 2026, eCentric and contributors
"""Ham Jinja cho trang chu (hooks.py jinja.methods): khoi "Tin noi bo".

Trang chu la Web Page Jinja render theo tung nguoi. Ham tra the bai NGUOI XEM duoc doc
(frappe.get_list - permission query cua internal_posts/permissions.py), ghim truoc roi moi
nhat, toi da 4 (PO chot 6a). KHONG BAO GIO nem loi: loi o day = trang chu 500 cho ca cong
ty. Loi -> danh sach rong + Error Log (toi da 1 lan / 10 phut)."""
import frappe

FAIL_KEY = "ec_internal_posts:home_fail"
FAIL_TTL = 600


def internal_posts_home():
    user = frappe.session.user
    if not user or user == "Guest":
        return []
    try:
        # Tai khoan khong co quyen doc (portal / khong role Employee): get_list se nem
        # PermissionError - tra rong cho RIENG nguoi do, khong bat co loi chung cua ca site.
        if not frappe.has_permission("EC Internal Post", "read", user=user):
            return []
        if frappe.cache().get_value(FAIL_KEY):
            return []
        from ecentric_workspace.internal_posts import service
        return service.home_block(user)
    except Exception:
        try:
            frappe.cache().set_value(FAIL_KEY, 1, expires_in_sec=FAIL_TTL)
            frappe.log_error(title="internal_posts.home_block")
        except Exception:
            pass
        return []
