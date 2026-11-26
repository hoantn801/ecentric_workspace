# Copyright (c) 2026, eCentric and contributors
"""Vong doi thiet bi - bang chuyen trang thai DUY NHAT (khong import frappe).

Moi thay doi trang thai di qua `plan(action, asset, ...)`: kiem tra duoc phep, tra ve
{to_status, holder} + ma su kien. Service chi ghi theo ke hoach nay va de lai EC Asset Event.
"""
from ecentric_workspace.tai_san import constants as C


class TransitionError(Exception):
    """Thao tac khong hop le voi trang thai hien tai (thong diep tieng Viet cho nguoi dung)."""


# action: (trang thai duoc phep, trang thai dich, quy tac nguoi giu, ma su kien)
#   holder: "set" = can nhan vien moi · "keep" = giu nguyen · "clear" = go nguoi giu
#           "keep_or_clear" = giu neu con nguoi giu (tra lai nguoi dang dung), khong thi ve kho
TRANSITIONS = {
    C.A_RESERVE: ((C.ST_AVAILABLE,), C.ST_RESERVED, "keep", C.EV_RESERVE),
    C.A_UNRESERVE: ((C.ST_RESERVED,), C.ST_AVAILABLE, "keep", C.EV_UNRESERVE),
    C.A_ASSIGN: ((C.ST_AVAILABLE, C.ST_RESERVED), C.ST_IN_USE, "set", C.EV_ASSIGN),
    C.A_TRANSFER: ((C.ST_IN_USE,), C.ST_IN_USE, "set", C.EV_TRANSFER),
    C.A_RETURN: ((C.ST_IN_USE, C.ST_RESERVED), C.ST_PENDING_CHECK, "clear", C.EV_RETURN),
    C.A_CHECK_PASS: ((C.ST_PENDING_CHECK,), C.ST_AVAILABLE, "clear", C.EV_CHECK_PASS),
    C.A_CHECK_FAIL: ((C.ST_PENDING_CHECK,), C.ST_BROKEN, "clear", C.EV_CHECK_FAIL),
    C.A_BREAK: ((C.ST_IN_USE, C.ST_AVAILABLE, C.ST_PENDING_CHECK, C.ST_RESERVED), C.ST_BROKEN,
                "keep", C.EV_BREAK),
    C.A_REPAIR_START: ((C.ST_BROKEN, C.ST_IN_USE, C.ST_AVAILABLE, C.ST_PENDING_CHECK),
                       C.ST_UNDER_REPAIR, "keep", C.EV_REPAIR_START),
    C.A_REPAIR_DONE: ((C.ST_UNDER_REPAIR,), None, "keep_or_clear", C.EV_REPAIR_DONE),
    C.A_REPAIR_FAIL: ((C.ST_UNDER_REPAIR,), C.ST_BROKEN, "clear", C.EV_REPAIR_FAIL),
    C.A_LOST: ((C.ST_IN_USE, C.ST_AVAILABLE, C.ST_RESERVED, C.ST_PENDING_CHECK, C.ST_BROKEN),
               C.ST_LOST, "keep", C.EV_LOST),
    C.A_FOUND: ((C.ST_LOST,), C.ST_PENDING_CHECK, "clear", C.EV_FOUND),
    C.A_DISPOSE: ((C.ST_BROKEN, C.ST_LOST, C.ST_AVAILABLE, C.ST_RETIRED), C.ST_DISPOSED,
                  "clear", C.EV_DISPOSE),
    C.A_RETIRE: ((C.ST_AVAILABLE,), C.ST_RETIRED, "clear", C.EV_RETIRE),
}

# Thao tac chi Finance / HOF duoc lam (ghi giam tai san).
FINANCE_ACTIONS = (C.A_DISPOSE,)


def allowed_actions(status):
    return [a for a, (src, _to, _h, _e) in TRANSITIONS.items() if status in src]


def plan(action, status, holder, new_holder=None, is_component=False):
    """Ke hoach mot lan chuyen. Tra ve dict {to_status, holder, event}; nem TransitionError neu
    khong hop le. Linh kien dang lap trong may khac khong cap / thu hoi rieng duoc."""
    if action not in TRANSITIONS:
        raise TransitionError("Thao tác không hợp lệ.")
    src, to_status, holder_rule, event = TRANSITIONS[action]
    if status not in src:
        raise TransitionError("Không thể %s khi thiết bị đang ở trạng thái \"%s\"." % (
            C.ACTION_LABELS[action].lower(), C.STATUS_LABELS.get(status, status or "trống")))
    if is_component:
        # Linh kien dang lap CHI di theo may me (service.transition lan sang). Thao tac rieng (hong,
        # thanh ly, mat...) tren no se lam lech trang thai voi may me -> phai thao ra truoc.
        raise TransitionError("Linh kiện đang lắp trong máy khác: tháo ra trước rồi mới thao tác riêng.")
    if holder_rule == "set":
        if not new_holder:
            raise TransitionError("Chọn nhân viên nhận thiết bị.")
        if action == C.A_TRANSFER and new_holder == holder:
            raise TransitionError("Người nhận trùng người đang giữ.")
        out_holder = new_holder
    elif holder_rule == "clear":
        out_holder = None
    elif holder_rule == "keep_or_clear":
        out_holder = holder or None
        to_status = C.ST_IN_USE if holder else C.ST_AVAILABLE
    else:
        out_holder = holder
    return {"to_status": to_status, "holder": out_holder, "event": event}
