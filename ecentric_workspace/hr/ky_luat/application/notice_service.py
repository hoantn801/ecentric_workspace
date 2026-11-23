# Copyright (c) 2026, eCentric and contributors
"""The vang (EC HR Notice) - nhac nho noi bo, NGOAI engine duyet.

LM (cua team) hoac HR gui -> NV bam "Da doc" hoac viet phan hoi -> qua N ngay lam viec (mac dinh
3, Settings) ma van "Cho phan hoi" thi job 09:00 tu ghi "Da thong bao, NV khong phan hoi".
Khong tru luong, khong la can cu tai pham, khong tu gop thanh the do: du 3 the trong 90 ngay
chi hien GOI Y cho HR. Moi doi trang thai ghi mot dong nhat ky (logs).

Tieu de (Hoan chot 23/11): bat buoc khi gui the MOI; the cu chua co tieu de hien tieu de du phong
(rules.notice_title). Nguoi gui / HR sua tieu de khi NV chua phan hoi - ghi nhat ky cu -> moi."""
from ecentric_workspace.hr.ky_luat import constants as C
from ecentric_workspace.hr.ky_luat.application import access as A
from ecentric_workspace.hr.ky_luat.application.common import (
    found, hr_users, int_setting, log, require_own_files, route_notice, text)
from ecentric_workspace.hr.ky_luat.domain import dates as D
from ecentric_workspace.hr.ky_luat.domain import rules as R
from ecentric_workspace.hr.ky_luat.domain.errors import FieldErrors, KyLuatError


def issue(repo, ctx, payload):
    p = payload or {}
    emp = found(repo.employee(text(p.get("employee"))), "nhân viên")
    A.require(A.can_issue_notice(ctx, emp["name"]),
              "Chỉ quản lý trực tiếp của nhân viên hoặc HR gửi được thẻ vàng.")
    today = repo.today()
    errors = {}
    title = R.clean_title(p.get("title"))
    behavior, content = text(p.get("behavior"), 140), text(p.get("content"), 5000)
    if not title:
        errors["title"] = "Nhập tiêu đề (vd “%s”)." % C.TITLE_PLACEHOLDER
    if not behavior:
        errors["behavior"] = "Nhập hành vi."
    if not content:
        errors["content"] = "Nhập nội dung nhắc nhở."
    try:
        incident = D.as_date(p.get("incident_date"))
    except ValueError:
        incident = None
    if not incident:
        errors["incident_date"] = "Chọn ngày xảy ra."
    elif incident > today:
        errors["incident_date"] = "Ngày xảy ra không được sau hôm nay."
    rule = repo.rule(text(p.get("rule"))) if p.get("rule") else None
    if p.get("rule") and not rule:
        errors["rule"] = "Điều khoản nội quy không tồn tại."
    if errors:
        raise FieldErrors(errors)
    require_own_files(repo, ctx, {"evidence": text(p.get("evidence"), 500)})
    days = int_setting(repo.settings(), "notice_reply_days", C.DEFAULT_NOTICE_REPLY_DAYS)
    row = {
        "employee": emp["name"], "employee_name": emp.get("employee_name"),
        "employee_user": emp.get("user"), "department": emp.get("department"),
        "line_manager_user": emp.get("reports_to_user"),
        "issued_by": ctx.user, "issuer_role": C.ISSUER_LM if ctx.manages(emp["name"]) else C.ISSUER_HR,
        "title": title, "behavior": behavior, "content": content, "incident_date": incident,
        "rule": rule["name"] if rule else None, "evidence": text(p.get("evidence"), 500) or None,
        "status": C.NOTICE_PENDING, "sent_at": repo.now(),
        "reply_due": D.reply_due(today, days, repo.holidays()),
    }
    name = repo.insert_notice(row, log(repo, ctx.user, "Gửi thẻ vàng", "%s - %s" % (title, behavior)))
    repo.notify([emp.get("user")], "Bạn nhận một thẻ vàng (nhắc nhở nội bộ): %s" % title, C.NOTICE,
                name, message="Vui lòng bấm “Đã đọc” hoặc phản hồi trước %s." % row["reply_due"],
                url=route_notice(name))
    hint = R.yellow_hint(repo.notice_dates(emp["name"]), today)
    if hint:
        repo.notify(hr_users(repo), "Gợi ý xem xét: %s - %s (thẻ mới: %s)" % (emp.get("employee_name"), hint, title),
                    C.NOTICE, name, url=route_notice(name))
    return {"name": name, "hint": hint, "reply_due": str(row["reply_due"])}


def _owned_open(repo, ctx, name):
    n = found(repo.get_notice(name), "thẻ vàng")
    A.require(A.is_notice_owner(ctx, n), "Chỉ nhân viên nhận thẻ mới xác nhận / phản hồi được.")
    return n


def mark_read(repo, ctx, name):
    n = _owned_open(repo, ctx, name)
    if n["status"] != C.NOTICE_PENDING:
        return {"name": name, "status": n["status"]}
    repo.update_notice(name, {"status": C.NOTICE_READ, "read_at": repo.now()},
                       log(repo, ctx.user, "Nhân viên đã đọc"))
    return {"name": name, "status": C.NOTICE_READ}


def reply(repo, ctx, name, message):
    n = _owned_open(repo, ctx, name)
    msg = text(message, 3000)
    if not msg:
        raise FieldErrors({"response": "Nhập nội dung phản hồi."})
    if n["status"] not in (C.NOTICE_PENDING, C.NOTICE_READ):
        raise KyLuatError("Thẻ vàng này đã đóng (%s), không phản hồi được nữa." % n["status"])
    vals = {"status": C.NOTICE_REPLIED, "response": msg, "responded_at": repo.now()}
    if not n.get("read_at"):
        vals["read_at"] = vals["responded_at"]
    repo.update_notice(name, vals, log(repo, ctx.user, "Nhân viên phản hồi", msg))
    repo.notify([n.get("issued_by")], "%s đã phản hồi thẻ vàng “%s”" % (n.get("employee_name") or "", R.notice_title(n)),
                C.NOTICE, name, message=msg[:300], url=route_notice(name))
    return {"name": name, "status": C.NOTICE_REPLIED}


def can_retitle(ctx, n):
    """Nguoi gui hoac HR; chi khi NV chua phan hoi (con "Cho phan hoi")."""
    return (ctx.is_hr or n.get("issued_by") == ctx.user) and n.get("status") in C.NOTICE_RETITLE_STATUSES


def retitle(repo, ctx, name, title):
    """Sua tieu de the vang. Ghi nhat ky (tieu de cu -> moi) - khong doi trang thai."""
    n = found(repo.get_notice(name), "thẻ vàng")
    A.require(A.can_view_notice(ctx, n))
    A.require(ctx.is_hr or n.get("issued_by") == ctx.user, "Chỉ người gửi hoặc HR sửa được tiêu đề thẻ vàng.")
    if n.get("status") not in C.NOTICE_RETITLE_STATUSES:
        raise KyLuatError("Nhân viên đã phản hồi (%s) - không sửa tiêu đề được nữa." % n.get("status"))
    new = R.clean_title(title)
    if not new:
        raise FieldErrors({"title": "Nhập tiêu đề."})
    old = R.clean_title(n.get("title"))
    if new == old:
        return {"name": name, "title": new, "changed": False}
    repo.update_notice(name, {"title": new}, log(repo, ctx.user, "Sửa tiêu đề",
                                                 "“%s” → “%s”" % (old or R.notice_title(n), new)))
    return {"name": name, "title": new, "changed": True}


def cancel(repo, ctx, name, reason):
    n = found(repo.get_notice(name), "thẻ vàng")
    A.require(ctx.is_hr or n.get("issued_by") == ctx.user, "Chỉ người gửi hoặc HR huỷ được thẻ vàng.")
    why = text(reason, 1000)
    if not why:
        raise FieldErrors({"reason": "Nhập lý do huỷ."})
    if n["status"] == C.NOTICE_CANCELLED:
        return {"name": name, "status": n["status"]}
    repo.update_notice(name, {"status": C.NOTICE_CANCELLED, "cancel_reason": why},
                       log(repo, ctx.user, "Huỷ thẻ vàng", why))
    return {"name": name, "status": C.NOTICE_CANCELLED}


def auto_close_overdue(repo):
    """Job 09:00: the con "Cho phan hoi" da qua han -> "Khong phan hoi" (ghi nhat ky he thong).
    Idempotent: lan chay sau khong con the nao o trang thai cho. Loi mot the khong chan the khac."""
    done = 0
    for n in repo.overdue_notices(repo.today()):
        try:
            repo.update_notice(n["name"], {"status": C.NOTICE_NO_REPLY, "response": C.NOTICE_AUTO_TEXT,
                                           "auto_closed_at": repo.now()},
                               log(repo, None, C.NOTICE_AUTO_TEXT,
                                   "Quá hạn phản hồi %s" % n.get("reply_due")))
            repo.notify([n.get("issued_by")], "%s: %s (%s)" % (n.get("employee_name") or n["employee"],
                                                               C.NOTICE_AUTO_TEXT, R.notice_title(n)),
                        C.NOTICE, n["name"], url=route_notice(n["name"]))
            done += 1
        except Exception:
            repo.log_error("ky_luat: tu dong dong the vang %s" % n.get("name"))
    return done
