# Copyright (c) 2026, eCentric and contributors
"""Lenh cua Cong cu dung chung: vao hang, roi hang, mo Kalodata, gia han, ket thuc, don hang doi.

Moi lenh: kiem quyen -> khoa dong cong cu (SELECT ... FOR UPDATE) -> don hang doi (tick) -> ap luat
(queue_rules) -> ghi -> goi may 24/7 neu can. Loi nghiep vu = queue_rules.QueueError (thong diep tieng
Viet). Nguoi thao tac LUON lay tu phien o tang API, khong nhan tu tham so.
"""
from frappe.utils import now_datetime

from ecentric_workspace.shared_tools import broker_client as B
from ecentric_workspace.shared_tools import constants as C
from ecentric_workspace.shared_tools import queue_rules as Q
from ecentric_workspace.shared_tools import repository as R

LINK = "/" + C.ROUTE


class Ctx:
    def __init__(self, user, roles):
        self.user = user
        self.roles = set(roles or [])

    @property
    def is_manager(self):
        return bool(self.roles & set(C.MANAGER_ROLES))


def load_tool(ctx, key):
    """Ban ghi cong cu neu ctx duoc dung, khong thi QueueError."""
    tool = R.tool(key)
    if not tool:
        raise Q.QueueError("Công cụ này chưa được cài trên ERP.")
    if ctx.is_manager:
        return tool
    if not R.is_system_user(ctx.user):
        raise Q.QueueError("Chỉ nhân viên eCentric dùng được công cụ này.")
    if not tool.enabled:
        raise Q.QueueError("Công cụ đang tạm đóng.")
    if tool.allowed_role and tool.allowed_role not in ctx.roles:
        raise Q.QueueError("Bạn chưa được cấp quyền dùng %s. Liên hệ quản lý công cụ." % tool.title)
    return tool


# ---------------------------------------------------------------- may 24/7 --
def host_state(key, force=False):
    """Trang thai may 24/7 (cache). Hoi lai toi da moi HOST_SYNC_SEC giay, tru khi force."""
    cached = R.cache_get(C.CACHE_HOST % key)
    if cached and not force and not R.try_lock(C.CACHE_SYNC_LOCK % key, C.HOST_SYNC_SEC):
        return cached
    if not B.configured():
        st = {"ok": False, "reason": "not_configured"}
    else:
        try:
            st = dict(B.status(), ok=True)
        except B.HostDown as e:
            st = {"ok": False, "reason": "down", "message": str(e)}
    st["checked_at"] = now_datetime().isoformat()
    R.cache_set(C.CACHE_HOST % key, st, C.HOST_CACHE_TTL)
    return st


def _revoke(key, user, entry):
    try:
        B.revoke()
    except B.HostDown as e:
        # Lan don sau (tick) se thu lai: may con giu current_user ma ERP khong con luot -> thu hoi.
        R.log(key, C.EV_REVOKE_FAIL, user=user, entry=entry, detail={"error": str(e)[:200]})


# --------------------------------------------------------------------- don --
def tick(key, host=None, now=None):
    """Mot vong don hang doi cua cong cu. Tu commit (duoc goi tu GET va tu job)."""
    now = now or now_datetime()
    tool = R.tool(key)
    if not tool:
        return []
    if host is None:
        host = host_state(key)
    R.lock_tool(key)
    entries = R.open_entries(key)
    changes = Q.tick(entries, now, Q.cfg_of(tool), host)
    revokes = _apply(key, tool, changes)
    reconcile = not revokes and Q.needs_reconcile_revoke(
        [e for e in entries if e["name"] not in {c["name"] for c in changes}], host)
    R.commit()
    for user, entry in revokes:
        _revoke(key, user, entry)
    if reconcile:
        _revoke(key, host.get("current_user"), None)
    if changes:
        R.publish_changed(key)
    return changes


def _apply(key, tool, changes, actor=None):
    revokes = []
    for c in changes:
        R.update_entry(c["name"], c["set"])
        if c["set"]["status"] == C.ST_READY:
            R.log(key, C.EV_READY, user=c["user"], entry=c["name"])
            R.notify(c["user"], "Đến lượt bạn dùng %s - mở trong %s phút." % (
                tool.title, Q.cfg_of(tool)["ready"]), LINK)
        else:
            R.log(key, C.EV_LEAVE if c["was"] == C.ST_WAITING else C.EV_END, user=c["user"],
                  entry=c["name"], actor=actor,
                  detail={"from": c["was"], "to": c["set"]["status"], "reason": c["set"].get("end_reason")})
        if c.get("revoke"):
            revokes.append((c["user"], c["name"]))
    return revokes


# --------------------------------------------------------------- nguoi dung --
def join(ctx, key):
    load_tool(ctx, key)
    now = now_datetime()
    R.lock_tool(key)
    Q.can_join(R.open_entries(key), ctx.user)
    name = R.create_entry(key, ctx.user, now)
    R.log(key, C.EV_JOIN, user=ctx.user, entry=name)
    R.commit()
    tick(key)  # khong ai giu luot -> vao la Den luot ngay
    return name


def leave(ctx, key):
    tool = load_tool(ctx, key)
    now = now_datetime()
    R.lock_tool(key)
    change = Q.leave(Q.mine(R.open_entries(key), ctx.user), now)
    revokes = _apply(key, tool, [change], actor=ctx.user)
    R.commit()
    for user, entry in revokes:
        _revoke(key, user, entry)
    tick(key)  # nguoi tiep theo len Den luot
    return change["set"]["status"]


def open_link(ctx, key):
    """Den luot / Dang dung -> xin may 24/7 link moi (song 60 s). URL chi tra ve cho chinh nguoi bam;
    KHONG ghi vao DB / log. May 24/7 loi -> trang thai giu nguyen (Den luot van con)."""
    tool = load_tool(ctx, key)
    if not R.try_lock(C.CACHE_OPEN_LOCK % ctx.user, C.OPEN_LOCK_SEC):
        raise Q.QueueError("Đang mở, chờ vài giây rồi bấm lại.")
    tick(key)
    now = now_datetime()
    R.lock_tool(key)
    entry = Q.mine(R.open_entries(key), ctx.user)
    values = Q.start(entry, now, Q.cfg_of(tool))
    try:
        url = B.grant(ctx.user)
    except B.HostDown as e:
        raise Q.QueueError(str(e))
    if values:
        R.update_entry(entry["name"], values)
    R.bump_opens(entry["name"])
    R.log(key, C.EV_OPEN if values else C.EV_REOPEN, user=ctx.user, entry=entry["name"])
    R.commit()
    R.publish_changed(key)
    return url


def extend(ctx, key):
    tool = load_tool(ctx, key)
    now = now_datetime()
    R.lock_tool(key)
    entries = R.open_entries(key)
    entry = Q.mine(entries, ctx.user)
    values = Q.extend(entries, entry, now, Q.cfg_of(tool))
    R.update_entry(entry["name"], values)
    R.log(key, C.EV_EXTEND, user=ctx.user, entry=entry["name"], detail={"ends_at": values["ends_at"]})
    R.commit()
    return values["ends_at"]


def force_end(ctx, key, entry_name):
    """Quan ly ket thuc luot cua nguoi khac (vd quen dong, may treo)."""
    tool = load_tool(ctx, key)
    if not ctx.is_manager:
        raise Q.QueueError("Chỉ quản lý công cụ mới kết thúc được lượt của người khác.")
    now = now_datetime()
    R.lock_tool(key)
    entry = next((e for e in R.open_entries(key) if e["name"] == entry_name), None)
    change = Q.force_end(entry, now)
    revokes = _apply(key, tool, [change], actor=ctx.user)
    R.commit()
    for user, ename in revokes:
        _revoke(key, user, ename)
    tick(key)
    return change["set"]["status"]
