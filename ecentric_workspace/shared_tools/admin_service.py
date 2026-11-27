# Copyright (c) 2026, eCentric and contributors
"""Viec cua quan ly cong cu: doi tai khoan Kalodata (bao tri) va mo / dong cong cu cho moi nguoi.

Doi tai khoan:
  1. Dong cong cu voi nhan vien (enabled = 0); quan ly van vao duoc.
  2. Ket thuc moi luot dang mo (dang dung -> thu hoi), bao chuong cho nguoi bi ket thuc.
  3. May 24/7 xoa ho so Chromium (broker /ec/reset-profile) -> Kalodata ve trang thai chua dang nhap.
  4. Quan ly vao hang -> Mo Kalodata -> dang nhap tai khoan moi -> Mo lai cho moi nguoi.
Mat khau Kalodata chi go truc tiep vao trang Kalodata; ERP khong bao gio thay.
"""
from frappe.utils import now_datetime

from ecentric_workspace.shared_tools import broker_client as B
from ecentric_workspace.shared_tools import constants as C
from ecentric_workspace.shared_tools import queue_rules as Q
from ecentric_workspace.shared_tools import repository as R
from ecentric_workspace.shared_tools import service as S

MSG_MAINT = "Kalodata đang bảo trì (đổi tài khoản). Bạn quay lại sau ít phút nhé."


def _manager(ctx, key):
    tool = S.load_tool(ctx, key)
    if not ctx.is_manager:
        raise Q.QueueError("Chỉ quản lý công cụ mới làm được việc này.")
    return tool


def reset_account(ctx, key):
    tool = _manager(ctx, key)
    now = now_datetime()
    R.lock_tool(key)
    R.set_tool_enabled(key, False)
    changes = [Q.force_end(e, now) for e in R.open_entries(key)]
    revokes = S._apply(key, tool, changes, actor=ctx.user)
    R.log(key, C.EV_MAINT, user=ctx.user, actor=ctx.user, detail={"action": "reset_account", "ended": len(changes)})
    R.commit()
    for c in changes:
        if c["user"] != ctx.user:
            R.notify(c["user"], MSG_MAINT, S.LINK)
    try:
        B.reset_profile()
    except B.HostDown as e:
        raise Q.QueueError("Đã đóng công cụ nhưng máy Kalodata chưa xoá được phiên cũ: %s Thử lại sau." % e)
    R.publish_changed(key)
    return {"ended": len(changes), "revoked": len(revokes)}


def set_enabled(ctx, key, on):
    _manager(ctx, key)
    R.set_tool_enabled(key, bool(on))
    R.log(key, C.EV_MAINT, user=ctx.user, actor=ctx.user, detail={"action": "open" if on else "close"})
    R.commit()
    R.publish_changed(key)
    return bool(on)
