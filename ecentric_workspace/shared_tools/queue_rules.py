# Copyright (c) 2026, eCentric and contributors
"""Luat hang doi - HAM THUAN (khong frappe, khong DB): nhan danh sach luot dang mo + gio hien tai,
tra ve viec can lam. service.py ap ket qua vao DB; test chay khong can bench.

Luot (dict): name, user, status, joined_at, ready_at, started_at, ends_at, extended.
Cfg (dict): lease, ready, extend, idle (phut).
Host (dict hoac None): {"ok": bool, "vnc_clients": int, "x_idle_ms": int|None, "current_user": str}
  None / ok=False = khong hoi duoc may 24/7 -> KHONG ket thuc vi "de yen" (khong biet that hay khong).
"""
import datetime as dt

from ecentric_workspace.shared_tools import constants as C


class QueueError(Exception):
    """Loi nghiep vu - thong diep tieng Viet hien thang cho nguoi dung."""


def minutes(n):
    return dt.timedelta(minutes=int(n))


def cfg_of(tool):
    tool = tool or {}
    return {
        "lease": int(tool.get("lease_minutes") or C.DEFAULT_LEASE_MIN),
        "ready": int(tool.get("ready_minutes") or C.DEFAULT_READY_MIN),
        "extend": int(tool.get("extend_minutes") or C.DEFAULT_EXTEND_MIN),
        "idle": int(tool.get("idle_minutes") or C.DEFAULT_IDLE_MIN),
    }


def ordered(entries):
    """Luot dang dung / den luot len dau, sau do nguoi cho theo gio vao hang."""
    rank = {C.ST_ACTIVE: 0, C.ST_READY: 1, C.ST_WAITING: 2}
    return sorted((e for e in entries if e["status"] in rank),
                  key=lambda e: (rank[e["status"]], e.get("joined_at") or dt.datetime.max, e["name"]))


def holder(entries):
    for e in entries:
        if e["status"] in (C.ST_ACTIVE, C.ST_READY):
            return e
    return None


def mine(entries, user):
    for e in entries:
        if e["user"] == user and e["status"] in C.OPEN_STATUSES:
            return e
    return None


def waiting_after(entries, entry):
    """So nguoi dang cho SAU luot nay (luot dang dung / den luot: tat ca nguoi cho)."""
    return len([e for e in entries if e["status"] == C.ST_WAITING and e["name"] != entry["name"]])


def _end(e, status, reason, now):
    return {"name": e["name"], "user": e["user"], "was": e["status"],
            "set": {"status": status, "ended_at": now, "end_reason": reason}}


def tick(entries, now, cfg, host=None):
    """Mot vong don hang doi. Tra ve list thay doi theo thu tu ap:
      {"name", "user", "was", "set": {...}, "revoke": bool, "notify": bool}
    - Dang dung qua ends_at -> Completed (het gio).
    - Dang dung, may 24/7 tra loi duoc, nguoi do khong thao tac >= idle phut -> Expired (de yen).
    - Den luot qua ready phut ma chua mo -> Skipped.
    - Khong con ai giu luot -> nguoi cho dau tien thanh Den luot (bao cho ho).
    """
    out = []
    alive = []
    host_ok = bool(host and host.get("ok"))
    for e in ordered(entries):
        if e["status"] == C.ST_ACTIVE:
            if e.get("ends_at") and now >= e["ends_at"]:
                out.append(dict(_end(e, C.ST_COMPLETED, C.END_TIME, now), revoke=True))
                continue
            if host_ok and _idle(e, now, cfg, host):
                out.append(dict(_end(e, C.ST_EXPIRED, C.END_IDLE, now), revoke=True))
                continue
        elif e["status"] == C.ST_READY:
            if e.get("ready_at") and now >= e["ready_at"] + minutes(cfg["ready"]):
                out.append(_end(e, C.ST_SKIPPED, C.END_NO_SHOW, now))
                continue
        alive.append(e)
    if not holder(alive):
        nxt = next((e for e in alive if e["status"] == C.ST_WAITING), None)
        if nxt:
            out.append({"name": nxt["name"], "user": nxt["user"], "was": C.ST_WAITING,
                        "set": {"status": C.ST_READY, "ready_at": now}, "notify": True})
    return out


def _idle(e, now, cfg, host):
    """De yen: khong ai xem man hinh, hoac co xem nhung khong cham chuot / phim, du idle phut
    (tinh tu luc bat dau luot - vua mo ma chua ket noi kip thi khong tinh)."""
    limit = minutes(cfg["idle"])
    if e.get("started_at") and now - e["started_at"] < limit:
        return False
    # Extension dang xuat nhieu trang (tool tu bam, nguoi dung co the da dong tab) -> khong tinh de yen.
    # Het 30 phut van ket thuc binh thuong; cac phan file da gui van o ERP.
    if host.get("busy"):
        return False
    if int(host.get("vnc_clients") or 0) == 0:
        return True
    idle_ms = host.get("x_idle_ms")
    return idle_ms is not None and int(idle_ms) >= limit.total_seconds() * 1000


# ------------------------------------------------------------- lenh nguoi dung --
def can_join(entries, user):
    if mine(entries, user):
        raise QueueError("Bạn đã ở trong hàng đợi rồi.")


def start(entry, now, cfg):
    """Den luot -> Dang dung. Dang dung -> giu nguyen (mo lai link moi)."""
    if entry is None:
        raise QueueError("Bạn chưa vào hàng đợi.")
    if entry["status"] == C.ST_WAITING:
        raise QueueError("Chưa đến lượt bạn.")
    if entry["status"] == C.ST_READY:
        return {"status": C.ST_ACTIVE, "started_at": now, "ends_at": now + minutes(cfg["lease"])}
    if entry["status"] == C.ST_ACTIVE:
        if entry.get("ends_at") and now >= entry["ends_at"]:
            raise QueueError("Lượt của bạn đã hết giờ.")
        return {}
    raise QueueError("Lượt này đã kết thúc.")


def extend_check(entries, entry, now):
    """Ly do KHONG gia han duoc (chuoi) hoac None neu duoc. Dung cho ca nut (disabled + ly do) va lenh."""
    if not entry or entry["status"] != C.ST_ACTIVE:
        return "Chỉ gia hạn được khi đang dùng."
    n = waiting_after(entries, entry)
    if n:
        return "Chưa gia hạn được: có %d người đang chờ sau bạn." % n
    left = (entry["ends_at"] - now) if entry.get("ends_at") else dt.timedelta(0)
    if left > minutes(C.EXTEND_WINDOW_MIN):
        return "Gia hạn được khi còn dưới %d phút." % C.EXTEND_WINDOW_MIN
    return None


def extend(entries, entry, now, cfg):
    why = extend_check(entries, entry, now)
    if why:
        raise QueueError(why)
    return {"ends_at": entry["ends_at"] + minutes(cfg["extend"]),
            "extended": int(entry.get("extended") or 0) + 1}


def leave(entry, now):
    """Roi hang (dang cho) / Bo luot (den luot) / Ket thuc som (dang dung)."""
    if entry is None or entry["status"] not in C.OPEN_STATUSES:
        raise QueueError("Bạn không có lượt nào đang mở.")
    status = {C.ST_WAITING: C.ST_CANCELLED, C.ST_READY: C.ST_SKIPPED,
              C.ST_ACTIVE: C.ST_COMPLETED}[entry["status"]]
    return dict(_end(entry, status, C.END_USER, now), revoke=entry["status"] == C.ST_ACTIVE)


def force_end(entry, now):
    if entry is None or entry["status"] not in C.OPEN_STATUSES:
        raise QueueError("Lượt này đã kết thúc.")
    status = C.ST_EXPIRED if entry["status"] == C.ST_ACTIVE else C.ST_CANCELLED
    return dict(_end(entry, status, C.END_ADMIN, now), revoke=entry["status"] == C.ST_ACTIVE)


def needs_reconcile_revoke(entries, host):
    """May 24/7 con giu nguoi dung (current_user) nhung ERP khong con luot Dang dung cua ho ->
    phai thu hoi (vd lan thu hoi truoc loi mang)."""
    if not (host and host.get("ok") and host.get("current_user")):
        return False
    act = [e for e in entries if e["status"] == C.ST_ACTIVE]
    return not any(e["user"] == host["current_user"] for e in act)


def eta_minutes(entries, entry, now, cfg):
    """Uoc luong so phut phai cho (thoi gian con lai cua nguoi giu + du luot cho nguoi xep truoc)."""
    q = ordered(entries)
    total = dt.timedelta(0)
    for e in q:
        if e["name"] == entry["name"]:
            break
        if e["status"] == C.ST_ACTIVE and e.get("ends_at"):
            total += max(e["ends_at"] - now, dt.timedelta(0))
        elif e["status"] == C.ST_READY:
            total += minutes(cfg["ready"]) + minutes(cfg["lease"])
        else:
            total += minutes(cfg["lease"])
    return int(round(total.total_seconds() / 60.0))
