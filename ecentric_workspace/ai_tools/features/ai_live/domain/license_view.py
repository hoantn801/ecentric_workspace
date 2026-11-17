# Copyright (c) 2026, eCentric and contributors
"""Dung du lieu tra cho trang Ban quyen (thuan Python). KHONG tra token, khoa, ma phan cung hay dau van tay may."""
import re

from ecentric_workspace.ai_tools.features.ai_live import license_constants as L

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
NO_DIST = "__none__"


def _s(v):
    return str(v) if v not in (None, "") else ""


def apps(installs):
    """3 icon eLive / eSync / eVoice: da cai = co dong; tooltip ban build + lan bao cuoi."""
    by = {i.get("product"): i for i in installs or []}
    return [{"product": p, "label": L.PRODUCT_LABEL[p], "installed": p in by,
             "build_id": _s((by.get(p) or {}).get("build_id")), "last_checkin": _s((by.get(p) or {}).get("last_checkin")),
             "waiting": bool((by.get(p) or {}).get("pending_hw"))} for p in L.PRODUCTS]


def machine_row(r, dist_labels, machine_labels):
    did, parent = r.get("source_dist") or "", r.get("parent_machine") or ""
    return {"name": r["name"], "label": _s(r.get("label")), "host": _s(r.get("host")), "win_user": _s(r.get("win_user")),
            "status": r.get("status") or L.Status.PENDING, "apps": apps(r.get("installs")),
            "dist": {"name": did, "label": dist_labels.get(did, "") if did else ""},
            "parent": {"name": parent, "label": machine_labels.get(parent, "") if parent else ""},
            "reason": _s(r.get("reason")), "last_ip": _s(r.get("last_ip")), "last_seen": _s(r.get("last_seen")),
            "first_seen": _s(r.get("first_seen")), "clone_warning": int(r.get("clone_warning") or 0),
            "blocked_manual": int(r.get("blocked_manual") or 0), "via_checkin": int(r.get("via_checkin") or 0)}


def install_row(i):
    return {"product": i.get("product"), "label": L.PRODUCT_LABEL.get(i.get("product"), i.get("product")),
            "build_id": _s(i.get("build_id")), "app_dir": _s(i.get("app_dir")),
            "license_issued_at": _s(i.get("license_issued_at")), "last_checkin": _s(i.get("last_checkin")),
            "last_checkin_ip": _s(i.get("last_checkin_ip")), "reissued_at": _s(i.get("reissued_at")),
            "waiting": bool(i.get("pending_hw"))}


def event_row(e):
    return {"at": _s(e.get("at")), "machine": _s(e.get("machine")), "product": _s(e.get("product")),
            "kind": _s(e.get("kind")), "ip": _s(e.get("ip")), "user": _s(e.get("user")), "detail": _s(e.get("detail"))}


def as_bool(v):
    return str(v).strip().lower() in ("1", "true", "yes", "on")


def machine_filters(f, dt_running, dt_stale):
    """-> (filters Frappe, q, order_by). f tu trang (chuoi); sai -> LicenseError."""
    f = f if isinstance(f, dict) else {}
    tab = f.get("tab") or "pending"
    if tab not in ("pending", "all"):
        raise L.LicenseError(L.Msg.BAD_FILTER % "tab")
    flt = {}
    status = "" if tab == "all" else L.Status.PENDING
    status = f.get("status") or status
    if status:
        if status not in L.STATUSES:
            raise L.LicenseError(L.Msg.BAD_FILTER % "status")
        flt["status"] = status
    dist = str(f.get("dist") or "")[:64]
    if dist == NO_DIST:
        flt["source_dist"] = ["is", "not set"]
    elif dist:
        flt["source_dist"] = dist
    if as_bool(f.get("stale")):
        flt["last_seen"] = ["<", dt_stale]
    elif as_bool(f.get("running")):
        flt["last_seen"] = [">=", dt_running]
    if as_bool(f.get("clone")):
        flt["clone_warning"] = 1
    q = re.sub(r"[%_\\]", "", str(f.get("q") or "")).strip()[:80]
    order = "creation desc" if tab == "pending" else "last_seen desc, creation desc"
    return flt, q, order


def event_filters(f):
    f = f if isinstance(f, dict) else {}
    out = {"machine": str(f.get("machine") or "")[:20], "product": f.get("product") or "", "kind": f.get("kind") or "",
           "date_from": f.get("date_from") or "", "date_to": f.get("date_to") or ""}
    if out["product"] and out["product"] not in L.PRODUCTS:
        raise L.LicenseError(L.Msg.BAD_FILTER % "app")
    if out["kind"] and out["kind"] not in L.KINDS:
        raise L.LicenseError(L.Msg.BAD_FILTER % "loại")
    for k in ("date_from", "date_to"):
        if out[k] and not DATE_RE.match(out[k]):
            raise L.LicenseError(L.Msg.BAD_FILTER % "ngày")
    return out


def page_no(page):
    try:
        return max(0, min(int(page or 0), 10000))
    except (TypeError, ValueError):
        return 0
