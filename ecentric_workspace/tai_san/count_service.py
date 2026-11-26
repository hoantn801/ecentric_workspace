# Copyright (c) 2026, eCentric and contributors
"""Kiem ke dinh ky (dot 3): mo mot dot -> moi nhan vien tu xac nhan may minh giu tren "Tai san
cua toi"; Ops danh dau may trong kho / may khong ai xac nhan; dong dot -> bao cao lech.

Kiem ke KHONG tu sua so: dong lech (sai nguoi giu, khong tim thay, hong) hien ra de Ops xu ly
bang cac thao tac thuong (dieu chuyen, bao mat, bao hong) - moi thay doi van co su kien rieng.
"""
from frappe.utils import now_datetime, nowdate

from ecentric_workspace.tai_san import access as A
from ecentric_workspace.tai_san import constants as C
from ecentric_workspace.tai_san import lifecycle as L
from ecentric_workspace.tai_san import repository as R

COUNTABLE = tuple(s for s in C.STATUSES if s not in (C.ST_DISPOSED, C.ST_LOST))


def open_count(ctx, title=None):
    A.require(ctx.can_manage)
    if R.open_count():
        raise L.TransitionError("Đang có một đợt kiểm kê chưa đóng.")
    items = [{"asset": a["name"], "expected_holder": a.get("custodian"),
              "expected_status": a.get(C.OPS_STATUS_FIELD)}
             for a in R.assets() if a.get(C.OPS_STATUS_FIELD) in COUNTABLE and not a.get(C.INSTALLED_ON_FIELD)]
    doc = R.new_count({"title": title or ("Kiểm kê " + nowdate()), "status": C.CNT_OPEN,
                       "started_on": nowdate(), "started_by": ctx.user, "items": items})
    holders = {i["expected_holder"] for i in items if i["expected_holder"]}
    users = [u for u in (R.employee_user(h) for h in holders) if u]
    R.notify(users, "Kiểm kê thiết bị: vào Tài sản của tôi bấm xác nhận máy bạn đang giữ.", "/" + C.ROUTE_MINE)
    return {"count": doc.name, "items": len(items)}


def _row_of(count_name, asset_name):
    it = R.lock_count_item(count_name, asset_name)
    if not it:
        raise L.TransitionError("Thiết bị không nằm trong đợt kiểm kê này.")
    return it


def self_confirm(ctx, asset_name, ok=True, note=None):
    cnt = R.open_count()
    if not cnt:
        raise L.TransitionError("Không có đợt kiểm kê nào đang mở.")
    A.require(ctx.employee_id, "Tài khoản chưa gắn hồ sơ nhân viên.")
    it = _row_of(cnt.name, asset_name)
    A.require(it.expected_holder == ctx.employee_id, "Máy này không ghi cho bạn giữ.")
    result = C.CR_OK if ok else C.CR_WRONG_STATUS
    R.set_count_item(it.name, {"result": result, "actual_holder": ctx.employee_id, "self_confirmed": 1,
                               "counted_by": ctx.user, "counted_at": now_datetime(),
                               "note": (note or "")[:500] or None})
    return {"result": result}


def mark(ctx, asset_name, result, actual_holder=None, note=None):
    A.require(ctx.can_manage)
    if result not in C.COUNT_RESULTS:
        raise L.TransitionError("Kết quả kiểm kê không hợp lệ.")
    cnt = R.open_count()
    if not cnt:
        raise L.TransitionError("Không có đợt kiểm kê nào đang mở.")
    if actual_holder and not R.employees([actual_holder]).get(actual_holder):
        raise L.TransitionError("Không tìm thấy nhân viên %s." % actual_holder)
    it = _row_of(cnt.name, asset_name)
    R.set_count_item(it.name, {"result": result, "actual_holder": actual_holder or it.expected_holder,
                               "counted_by": ctx.user, "counted_at": now_datetime(),
                               "note": (note or "")[:500] or None})
    a = R.asset(asset_name)
    R.insert_event({"asset": asset_name, "event_type": C.EV_COUNT, "to_status": a.get(C.OPS_STATUS_FIELD),
                    "ref_doctype": C.COUNT_DT, "ref_name": cnt.name,
                    "note": "%s%s" % (C.COUNT_RESULT_LABELS[result], (": " + note) if note else ""),
                    "actor": ctx.user})
    return {"result": result}


def summary(ctx, name=None):
    A.require(ctx.can_manage or ctx.can_see_cost)
    cnt = R.count_doc(name) if name else (R.count_doc(R.open_count().name) if R.open_count() else None)
    if not cnt:
        return {"count": None, "can": ctx.flags()}
    items = list(cnt.items)
    info = {a["name"]: a for a in R.assets({"name": ["in", [i.asset for i in items]]})} if items else {}
    emps = R.employees([i.expected_holder for i in items] + [i.actual_holder for i in items])

    def ename(e):
        return emps[e].employee_name if e in emps else None

    rows = [{"asset": i.asset, "tag": (info.get(i.asset) or {}).get(C.TAG_FIELD),
             "asset_name": (info.get(i.asset) or {}).get("asset_name"),
             "expected_holder": i.expected_holder, "expected_holder_name": ename(i.expected_holder),
             "expected_status": i.expected_status,
             "result": i.result, "result_label": C.COUNT_RESULT_LABELS.get(i.result) if i.result else None,
             "actual_holder": i.actual_holder, "actual_holder_name": ename(i.actual_holder),
             "self_confirmed": i.self_confirmed, "note": i.note,
             "counted_at": str(i.counted_at)[:16] if i.counted_at else None} for i in items]
    done = sum(1 for r in rows if r["result"])
    mismatch = [r for r in rows if r["result"] and r["result"] != C.CR_OK]
    return {"count": {"name": cnt.name, "title": cnt.title, "status": cnt.status,
                      "started_on": str(cnt.started_on) if cnt.started_on else None},
            "rows": rows, "done": done, "total": len(rows), "mismatch": len(mismatch),
            "result_labels": C.COUNT_RESULT_LABELS, "can": ctx.flags()}


def my_confirmations(employee_id):
    """{asset: "ok" | "wrong"} - may nhan vien da tu xac nhan trong dot dang mo (trang Cua toi)."""
    cnt = R.open_count()
    if not (cnt and employee_id):
        return {}
    return {i.asset: ("ok" if i.result == C.CR_OK else "wrong") for i in R.count_doc(cnt.name).items
            if i.self_confirmed and i.expected_holder == employee_id}


def close(ctx):
    A.require(ctx.can_manage)
    cnt = R.open_count()
    if not cnt:
        raise L.TransitionError("Không có đợt kiểm kê nào đang mở.")
    R.set_count(cnt.name, {"status": C.CNT_CLOSED, "closed_on": nowdate()})
    doc = R.count_doc(cnt.name)
    return {"count": doc.name, "unchecked": sum(1 for i in doc.items if not i.result)}
