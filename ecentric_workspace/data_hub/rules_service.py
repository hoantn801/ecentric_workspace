# Copyright (c) 2026, eCentric and contributors
"""Trung tam Du lieu dot 3 - SUA + DUYET quy tac thoi han (PO Hoan chot 09/11/2026).

Luong:  team Data sua (ban nhap, MOT thay doi mo moi luc) -> "Gửi duyệt" (ly do bat buoc) ->
        nguoi duyet quy tac (EC Data Hub Settings.rule_approver - KHONG hardcode) Duyet / Tu choi.
  * Duyet: ban moi "Đang áp dụng" (ap dung tu hom nay), ban cu "Hết hiệu lực",
    Settings.active_rule_set tro ban moi. Chi YEU CAU MOI dung ban moi: yeu cau da tao giu
    rule_version cua minh (service.ticket_rules - ca luc team Data nhan viec).
  * Tu choi (ly do bat buoc) -> bao nguoi de xuat. Nguoi de xuat rut lai ban nhap / ban dang cho
    duyet -> "Đã huỷ" (khong xoa - con dau vet).
  * Quy tac cu chay toi khi ban moi duoc duyet.
Quyen (kiem o day, DocType chi System Manager co quyen Desk):
  * xem trang: team Data / System Manager / nguoi duyet quy tac (service.is_rule_viewer);
  * sua / gui / rut lai: team Data + System Manager; ban nhap cua ai thi nguoi do (hoac System
    Manager) sua / gui / rut lai;
  * duyet / tu choi: DUNG nguoi duyet trong Settings. Chua cau hinh nguoi duyet -> System Manager.
Dau vet: proposed_by / reason / submitted_at / decided_by / decided_at / decision_note tren ban
ghi + Version (track_changes) cho moi lan sua; lich su hien v1, v2... kem cu -> moi.
Moi ghi deu khoa (repo.lock_rules = SELECT ... FOR UPDATE tren Settings) truoc khi doc lai trang thai:
hai nguoi bam cung luc thi nguoi sau thay trang thai moi.
"""
from ecentric_workspace.data_hub import constants as C
from ecentric_workspace.data_hub import domain as D
from ecentric_workspace.data_hub import rules_domain as RD
from ecentric_workspace.data_hub import service as S

APPROVE = ("approve", "Duyệt")
REJECT = ("reject", "Từ chối")


# ------------------------------------------------------------------ quyen -----------------
def approver(repo):
    return (repo.settings().get("rule_approver") or "").strip()


def can_decide(repo, user):
    """DUNG nguoi duyet quy tac trong Settings; chua cau hinh thi System Manager."""
    if not user or user == "Guest":
        return False
    who = approver(repo)
    return user == who if who else repo.is_admin(user)


def _owner_or_admin(repo, user, rs):
    return user == rs.get("proposed_by") or repo.is_admin(user)


# ------------------------------------------------------------------ doc -------------------
def active(repo):
    return repo.rule_set() or {}


def open_change(repo):
    """Ban nhap / ban cho duyet dang mo (toi da mot)."""
    rows = repo.rule_versions(statuses=list(C.RULE_OPEN), limit=1)
    return rows[0] if rows else None


def _load(repo, name):
    rs = repo.rule_doc(name) if name else None
    if not rs:
        S._fail("Không tìm thấy bản đề xuất quy tắc này. Tải lại trang.")
    return rs


def _names(repo, users):
    try:
        return repo.full_names([u for u in users if u])
    except Exception:
        return {}


def _invalid(e):
    S._fail(e.errors)


# ------------------------------------------------------------------ thong bao ---------------
def _send(repo, event, recipients, title, message, rs, key, actor):
    sent = []
    for r in recipients:
        if not r or r == actor or r in sent or r in ("Guest", C.SYSTEM_USER):
            continue
        try:
            repo.notify_ref(event, r, title, message, C.ROUTE_RULES, C.RULE_DT, rs["name"],
                            "datahub|rule|%s|%s|%s|%s" % (key, rs["name"], r, _stamp(repo)), actor=actor)
            sent.append(r)
        except Exception:
            repo.log_error("Data Hub rule notify %s %s" % (key, rs.get("name")))
    return sent


def _stamp(repo):
    try:
        return repo.now().strftime("%Y%m%d%H%M%S%f")
    except Exception:
        return ""


def _label(rs):
    return "v%s" % (rs.get("version_no") or "?")


# ------------------------------------------------------------------ ghi ---------------------
def save_draft(user, data, repo=None):
    """Team Data luu ban nhap (tao moi hoac sua ban nhap cua minh). data = {days{key}, mult{muc},
    reason, submit}. submit=1 -> gui duyet luon. -> {name, version, status}."""
    repo = S._repo(repo)
    S.require_operate(repo, user)
    data = data or {}
    repo.lock_rules()
    cur_active = active(repo)
    av = RD.view(cur_active)
    try:
        v = RD.normalize_input(data, av)
    except D.Invalid as e:
        _invalid(e)
    if not RD.diff(av, v):
        S._fail("Chưa có gì thay đổi so với quy tắc đang áp dụng.")
    cur = open_change(repo)
    values = RD.to_doc(v, av["labels"])
    values["reason"] = v["reason"]
    if cur:
        if cur.get("status") == C.RULE_PENDING:
            S._fail("Đang có thay đổi {0} chờ duyệt - chờ duyệt / từ chối hoặc rút lại trước khi sửa tiếp.".format(
                _label(cur)))
        if not _owner_or_admin(repo, user, cur):
            who = _names(repo, [cur.get("proposed_by")]).get(cur.get("proposed_by")) or cur.get("proposed_by")
            S._fail("{0} đang có bản nháp {1} - mỗi lúc chỉ một thay đổi quy tắc.".format(who, _label(cur)))
        repo.update_rule(cur["name"], values)
        name, version = cur["name"], cur.get("version_no")
    else:
        version = repo.next_rule_version()
        values.update({"version_no": version, "status": C.RULE_DRAFT, "proposed_by": user,
                       "supersedes": cur_active.get("name") or None})
        name = repo.insert_rule(values)
    if data.get("submit") in (1, "1", True, "true"):
        return submit(user, name, v["reason"], repo=repo)
    return {"name": name, "version": version, "status": C.RULE_DRAFT}


def submit(user, name, reason="", repo=None):
    """Ban nhap -> Cho duyet. Ly do bat buoc. Bao nguoi duyet quy tac (ERP + Teams)."""
    repo = S._repo(repo)
    S.require_operate(repo, user)
    repo.lock_rules()
    rs = _load(repo, name)
    if rs.get("status") != C.RULE_DRAFT:
        S._fail("Bản {0} không còn là bản nháp (đang: {1}). Tải lại trang.".format(_label(rs), rs.get("status")))
    if not _owner_or_admin(repo, user, rs):
        raise S.Forbidden("Chỉ người tạo bản nháp mới gửi duyệt được.")
    reason = D.clean_text(reason, C.RULE_REASON_MAX) or (rs.get("reason") or "").strip()
    if not reason:
        S._fail("Ghi lý do thay đổi để người duyệt quy tắc xem xét.")
    who = approver(repo)
    if not who:
        S._fail("Chưa cấu hình người duyệt quy tắc (EC Data Hub Settings). Báo quản trị hệ thống.")
    changes = RD.diff(RD.view(active(repo)), RD.view(rs))
    if not changes:
        S._fail("Bản nháp giống hệt quy tắc đang áp dụng - sửa lại hoặc huỷ bản nháp.")
    repo.update_rule(name, {"status": C.RULE_PENDING, "reason": reason, "submitted_at": repo.now()})
    rs.update({"status": C.RULE_PENDING, "reason": reason})
    me = _names(repo, [user]).get(user) or user
    _send(repo, C.EV_RULE_REVIEW, [who], "Cần duyệt quy tắc thời hạn %s" % _label(rs),
          "%s đề xuất: %s. Lý do: %s" % (me, RD.summary(changes), reason[:300]), rs, "submit", user)
    return {"name": name, "version": rs.get("version_no"), "status": C.RULE_PENDING, "approver": who}


def decide(user, name, verdict, note="", repo=None):
    """Nguoi duyet quy tac: Duyet -> ban moi Dang ap dung (cu Het hieu luc); Tu choi + ly do."""
    repo = S._repo(repo)
    if not can_decide(repo, user):
        raise S.Forbidden("Chỉ người duyệt quy tắc mới duyệt được thay đổi này.")
    repo.lock_rules()
    rs = _load(repo, name)
    if rs.get("status") != C.RULE_PENDING:
        S._fail("Bản {0} không ở trạng thái chờ duyệt (đang: {1}). Tải lại trang.".format(_label(rs), rs.get("status")))
    note = D.clean_text(note, C.RULE_REASON_MAX)
    now = repo.now()
    proposer = rs.get("proposed_by")
    if verdict in APPROVE:
        old = active(repo)
        changes = RD.diff(RD.view(old), RD.view(rs))
        repo.update_rule(name, {"status": C.RULE_ACTIVE, "effective_from": repo.today(), "decided_by": user,
                                "decided_at": now, "decision_note": note,
                                "supersedes": rs.get("supersedes") or old.get("name") or None})
        if old.get("name") and old["name"] != name:
            repo.update_rule(old["name"], {"status": C.RULE_EXPIRED})
        repo.set_settings({"active_rule_set": name})
        title = "Quy tắc thời hạn %s đã được duyệt" % _label(rs)
        msg = "%s. Áp dụng cho yêu cầu MỚI từ %s; yêu cầu đã gửi giữ hạn cũ." % (
            RD.summary(changes), D.fmt_date_full(repo.today()))
        audience = [proposer] + list(S.members(repo))
        _send(repo, C.EV_RULE_UPDATE, audience, title, msg, rs, "approved", user)
        return {"name": name, "status": C.RULE_ACTIVE, "previous": old.get("name") or ""}
    if verdict in REJECT:
        if not note:
            S._fail("Ghi lý do từ chối để team Data biết cần sửa gì.")
        repo.update_rule(name, {"status": C.RULE_REJECTED, "decided_by": user, "decided_at": now,
                                "decision_note": note})
        _send(repo, C.EV_RULE_UPDATE, [proposer], "Quy tắc thời hạn %s bị từ chối" % _label(rs),
              "Lý do: " + note[:300] + ". Quy tắc đang áp dụng giữ nguyên.", rs, "rejected", user)
        return {"name": name, "status": C.RULE_REJECTED}
    S._fail("Chọn Duyệt hoặc Từ chối.")


def cancel(user, name, reason="", repo=None):
    """Nguoi de xuat (hoac System Manager) rut lai ban nhap / ban dang cho duyet -> Da huy."""
    repo = S._repo(repo)
    S.require_internal(repo, user)
    repo.lock_rules()
    rs = _load(repo, name)
    if rs.get("status") not in C.RULE_OPEN:
        S._fail("Bản {0} đã {1} - không rút lại được.".format(_label(rs), (rs.get("status") or "").lower()))
    if not _owner_or_admin(repo, user, rs):
        raise S.Forbidden("Chỉ người đề xuất mới rút lại được thay đổi này.")
    was = rs.get("status")
    note = D.clean_text(reason, C.RULE_REASON_MAX)
    repo.update_rule(name, {"status": C.RULE_CANCELLED, "decided_by": user, "decided_at": repo.now(),
                            "decision_note": note or "Người đề xuất rút lại"})
    if was == C.RULE_PENDING:
        me = _names(repo, [user]).get(user) or user
        _send(repo, C.EV_RULE_UPDATE, [approver(repo)], "Đã rút lại đề xuất quy tắc %s" % _label(rs),
              "%s rút lại đề xuất - không cần duyệt nữa.%s" % (me, (" " + note[:200]) if note else ""),
              rs, "cancelled", user)
    return {"name": name, "status": C.RULE_CANCELLED}


# ------------------------------------------------------------------ trang /du-lieu/quy-tac ---
def _when(v):
    return D.fmt_dt(v) if D.as_datetime(v) else ""


def history(repo, names_out=None):
    """Lich su phien ban (moi nhat truoc, bo ban nhap): v2, v1... kem cu -> moi."""
    rows = repo.rule_versions(limit=30)
    by_name = {r["name"]: r for r in rows}
    out = []
    for r in rows:
        st = r.get("status")
        if st == C.RULE_DRAFT:
            continue
        base = by_name.get(r.get("supersedes")) or (repo.rule_doc(r["supersedes"]) if r.get("supersedes") else None)
        changes = RD.diff(RD.view(base), RD.view(r)) if base else []
        if st in (C.RULE_ACTIVE, C.RULE_EXPIRED):
            when = D.fmt_date_full(r.get("effective_from"))
        elif st == C.RULE_PENDING:
            when = _when(r.get("submitted_at"))
        else:
            when = _when(r.get("decided_at"))
        out.append({"name": r["name"], "label": _label(r), "status": st,
                    "status_label": C.RULE_STATUS_LABEL.get(st, st), "status_css": C.RULE_STATUS_CSS.get(st, "gray"),
                    "when": when, "reason": r.get("reason") or "", "note": r.get("decision_note") or "",
                    "proposed_by": r.get("proposed_by") or "", "decided_by": r.get("decided_by") or "",
                    "submitted": _when(r.get("submitted_at")), "decided": _when(r.get("decided_at")),
                    "changes": [dict(c, old_fmt=_val(c, "old"), new_fmt=_val(c, "new")) for c in changes],
                    "first": not base})
    if names_out is not None:
        for h in out:
            names_out.update([h["proposed_by"], h["decided_by"]])
    return out


def _val(c, side):
    v = c[side]
    return ("×" + RD.fmt_mult(v)) if c["kind"] == "mult" else "%d ngày" % int(v)


def page_context(repo, user):
    """Du lieu trang /du-lieu/quy-tac (server ve san trang thai dau). -> (ctx, boot)."""
    cur = active(repo)
    av = RD.view(cur)
    op = open_change(repo)
    ov = RD.view(op) if op else None
    changes = RD.diff(av, ov) if ov else []
    changed = {c["key"] for c in changes}
    users = {user, approver(repo)}
    if op:
        users.add(op.get("proposed_by"))
    hist = history(repo, users)
    names = _names(repo, users)
    for h in hist:
        h["proposed_by_name"] = names.get(h["proposed_by"]) or h["proposed_by"]
        h["decided_by_name"] = names.get(h["decided_by"]) or h["decided_by"]
    operate = S.can_operate(repo, user)
    mine = bool(op) and (op.get("proposed_by") == user or repo.is_admin(user))
    is_draft = bool(op) and op.get("status") == C.RULE_DRAFT
    is_pending = bool(op) and op.get("status") == C.RULE_PENDING
    who = approver(repo)
    can = {
        "propose": operate and not op,
        "edit": operate and is_draft and mine,
        "submit": operate and is_draft and mine,
        "cancel": bool(op) and mine,
        "decide": is_pending and can_decide(repo, user),
    }
    rows = []
    for key, _t, _l, _d, _n in C.RULE_DEFAULTS:
        rows.append({"key": key, "label": av["labels"][key], "days": av["days"][key], "note": av["notes"][key],
                     "proposed": ov["days"][key] if ov else None, "changed": key in changed})
    mult = [{"priority": p, "value": RD.fmt_mult(av["mult"][p]), "raw": av["mult"][p],
             "proposed": RD.fmt_mult(ov["mult"][p]) if ov else "", "proposed_raw": ov["mult"][p] if ov else None,
             "changed": p in changed} for p in C.PRIORITIES]
    pending = None
    if op:
        pending = {"name": op["name"], "label": _label(op), "status": op.get("status"),
                   "status_label": C.RULE_STATUS_LABEL.get(op.get("status"), op.get("status")),
                   "proposed_by": op.get("proposed_by"),
                   "proposed_by_name": names.get(op.get("proposed_by")) or op.get("proposed_by") or "",
                   "submitted": _when(op.get("submitted_at")), "reason": op.get("reason") or "",
                   "summary": RD.summary(changes), "changes": len(changes), "mine": mine}
    ctx = {
        "rule_rows": rows, "mult": mult, "rule_version": cur.get("name") or "v1 (mặc định)",
        "rule_label": _label(cur) if cur.get("version_no") else "v1 (mặc định)",
        "rule_status": cur.get("status") or C.RULE_ACTIVE, "rule_from": D.fmt_date_full(cur.get("effective_from")),
        "mult_text": " · ".join("%s ×%s" % (m["priority"], m["value"]) for m in mult),
        "proposal_mult_text": " · ".join(("%s ×%s" % (m["priority"], m["proposed"])) for m in mult) if ov else "",
        "mult_changed": any(m["changed"] for m in mult),
        "history": hist, "pending": pending, "rule_can": can, "show_proposal": bool(op) or can["propose"],
        "approver": who, "approver_name": (names.get(who) or who) if who else "",
        "is_approver": bool(who) and user == who, "limits": _limits(),
    }
    draft = None
    if can["edit"]:
        draft = {"name": op["name"], "days": ov["days"], "mult": ov["mult"], "reason": op.get("reason") or ""}
    boot = {"page": "rules", "me": user, "active": {"name": cur.get("name") or "", "days": av["days"], "mult": av["mult"]},
            "draft": draft, "pending": pending["name"] if pending else "", "can": can, "limits": ctx["limits"],
            "approver_name": ctx["approver_name"], "labels": av["labels"], "keys": RD.rule_keys(),
            "priorities": list(C.PRIORITIES)}
    return ctx, boot


def _limits():
    return {"days_min": C.RULE_DAYS_MIN, "days_max": C.RULE_DAYS_MAX, "mult_min": C.RULE_MULT_MIN,
            "mult_max": C.RULE_MULT_MAX, "reason_max": C.RULE_REASON_MAX}
