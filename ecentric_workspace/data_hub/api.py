# Copyright (c) 2026, eCentric and contributors
"""Cua HTTP DUY NHAT cua Trung tam Du lieu (/du-lieu). Moi ham:
  * lay nguoi dung tu PHIEN - khong nhan tham so `user`;
  * ghi bang POST (GET cua Frappe khong commit);
  * tra {success, message, data}; loi nguoi dung = success False + thong diep tieng Viet, khong de
    traceback lot ra trinh duyet.
"""
import base64
import json

import frappe
from frappe import _

from ecentric_workspace.data_hub import ops_service as O
from ecentric_workspace.data_hub import service as S


def _ok(data=None, message=""):
    return {"success": True, "message": message, "data": data}


def _fail(message, status=None):
    try:
        frappe.db.rollback()
    except Exception:
        pass
    if status:
        frappe.local.response["http_status_code"] = status
    return {"success": False, "message": message, "data": None}


def _run(fn, *args, **kwargs):
    try:
        return _ok(fn(*args, **kwargs))
    except S.Forbidden as e:
        return _fail(str(e) or _("Bạn không có quyền làm việc này."), 403)
    except S.NotFound:
        return _fail(_("Không tìm thấy yêu cầu này (có thể mã sai hoặc đã bị xoá)."), 404)
    except S.DataHubError as e:
        return _fail(str(e))
    except frappe.PermissionError:
        frappe.clear_last_message()
        return _fail(_("Bạn không có quyền làm việc này."), 403)
    except frappe.ValidationError as e:
        frappe.clear_last_message()
        return _fail(str(e).replace("<br>", "\n"))


def _me():
    return frappe.session.user


def _json(data):
    if isinstance(data, str):
        try:
            data = json.loads(data or "{}")
        except ValueError:
            raise S.DataHubError(_("Dữ liệu gửi lên không hợp lệ."))
    if not isinstance(data, dict):
        raise S.DataHubError(_("Dữ liệu gửi lên không hợp lệ."))
    return data


def _list(v):
    if isinstance(v, str):
        try:
            v = json.loads(v or "[]")
        except ValueError:
            v = [x for x in v.split(",") if x.strip()]
    return v if isinstance(v, list) else []


def _files(raw):
    """[{name, data: base64}] -> [{name, content, size}]. Kiem loai / dung luong o domain.check_files."""
    out = []
    for f in raw or []:
        if not isinstance(f, dict):
            raise S.DataHubError(_("Tệp đính kèm không hợp lệ."))
        try:
            content = base64.b64decode((f.get("data") or "").split(",")[-1], validate=True)
        except (ValueError, TypeError):
            raise S.DataHubError(_("Tệp đính kèm không đọc được: {0}").format(f.get("name") or "?"))
        name = (f.get("name") or "tep").replace("/", "_").replace("\\", "_")[:120]
        out.append({"name": name, "content": content, "size": len(content)})
    return out


def _code(code):
    return str(code or "").strip().upper()


# ------------------------------------------------------------------ nhan vien ---------------
def _create(data):
    data = _json(data)
    return S.create(_me(), data, _files(data.get("files")))


@frappe.whitelist(methods=["POST"])
def create(data):
    """Gui yeu cau. data = JSON {request_type, proposed_priority, urgent_reason, title, description,
    data_used, reference_link, files: [{name, data(base64)}]}."""
    return _run(_create, data)


@frappe.whitelist()
def get_ticket(code):
    return _run(S.detail, _me(), _code(code))


@frappe.whitelist()
def list_tickets():
    return _run(S.list_rows, _me())


@frappe.whitelist()
def gantt(start=None):
    return _run(S.gantt_data, _me(), str(start or "") or None)


def _message(code, body, mentions, files):
    return S.send_message(_me(), _code(code), str(body or ""), _list(mentions), _files(_list(files)))


@frappe.whitelist(methods=["POST"])
def send_message(code, body="", mentions=None, files=None):
    return _run(_message, code, body, mentions, files)


@frappe.whitelist(methods=["POST"])
def follow(code, on=1):
    return _run(S.follow, _me(), _code(code), on)


@frappe.whitelist(methods=["POST"])
def respond(code, verdict, reason=""):
    """Nguoi gui nghiem thu: verdict = "Đạt" | "Chưa đạt" (+ ly do)."""
    return _run(S.respond, _me(), _code(code), str(verdict or ""), str(reason or ""))


@frappe.whitelist(methods=["POST"])
def cancel(code, reason=""):
    return _run(S.cancel, _me(), _code(code), str(reason or ""))


@frappe.whitelist()
def people(q=""):
    """Goi y @ten trong khung trao doi (nhan vien Active)."""
    def run():
        S.require_internal(S._repo(None), _me())
        from ecentric_workspace.data_hub import repository as R
        return R.people(str(q or "")[:60])
    return _run(run)


@frappe.whitelist()
def download(code, file):
    """Tai tep dinh kem (private) cua yeu cau. Moi nhan vien doc duoc yeu cau thi tai duoc tep cua no;
    tep KHONG mo qua /private/files (DocType chi System Manager) - day la duong tai duy nhat."""
    try:
        fname, content = S.download(_me(), _code(code), str(file or ""))
    except (S.Forbidden, frappe.PermissionError):
        return _fail(_("Bạn không có quyền tải tệp này."), 403)
    except S.NotFound:
        return _fail(_("Không tìm thấy tệp."), 404)
    frappe.local.response.filename = fname
    frappe.local.response.filecontent = content
    frappe.local.response.type = "download"
    frappe.local.response.display_content_as = "attachment"


# ------------------------------------------------------------------ team Data ---------------
@frappe.whitelist(methods=["POST"])
def accept(code, assignee="", start_date="", due_date="", priority="", reason=""):
    return _run(O.accept, _me(), _code(code), str(assignee or ""), str(start_date or ""), str(due_date or ""),
                str(priority or ""), str(reason or ""))


@frappe.whitelist()
def preview_due(code, start_date="", priority=""):
    return _run(S.preview_due, _me(), _code(code), str(start_date or "") or None, str(priority or "") or None)


@frappe.whitelist(methods=["POST"])
def update(code, data):
    """O "Cap nhat": data = JSON {status, priority, assignee, start_date, due_date, reason, note, output_link}."""
    return _run(lambda: O.update(_me(), _code(code), _json(data)))


@frappe.whitelist(methods=["POST"])
def pause(code, note=""):
    return _run(O.pause, _me(), _code(code), str(note or ""))


@frappe.whitelist(methods=["POST"])
def resume(code):
    return _run(O.resume, _me(), _code(code))


@frappe.whitelist(methods=["POST"])
def mark_done(code, output_link="", note=""):
    return _run(O.mark_done, _me(), _code(code), str(output_link or ""), str(note or ""))


# ------------------------------------------------------------------ dot 2: Data availability --
# Data availability (/du-lieu/san-co), de xuat data can crawl, ke hoach bo sung DA-, Thu vien bao cao,
# goi y "da co dashboard tuong tu". Quyen kiem o avail_service (nhan vien / team Data).
def _avail():
    from ecentric_workspace.data_hub import avail_service
    return avail_service


def _propose(data):
    data = _json(data)
    files = _files(data.pop("files", None))
    return _avail().create_proposal(_me(), data, files)


@frappe.whitelist(methods=["POST"])
def propose(data):
    """Moi nhan vien: de xuat data can crawl. data = JSON {department, data_type, platforms[], other_platform,
    source_links, scope, frequency, data_from, data_to, channels[], needed_by, purpose, urgency, urgency_reason,
    files: [{name, data(base64)}]}."""
    return _run(_propose, data)


@frappe.whitelist()
def download_proposal_file(name, file):
    """Tai anh / file huong dan cua de xuat (private): nguoi de xuat, team Data, System Manager."""
    try:
        fname, content = _avail().download_proposal_file(_me(), str(name or "").strip(), str(file or ""))
    except (S.Forbidden, frappe.PermissionError):
        return _fail(_("Bạn không có quyền tải tệp này."), 403)
    except S.NotFound:
        return _fail(_("Không tìm thấy tệp."), 404)
    frappe.local.response.filename = fname
    frappe.local.response.filecontent = content
    frappe.local.response.type = "download"
    frappe.local.response.display_content_as = "attachment"


@frappe.whitelist(methods=["POST"])
def review_proposal(name, verdict, reason=""):
    """Team Data: verdict = "Đã duyệt" | "Từ chối" (+ ly do bat buoc)."""
    return _run(_avail().review_proposal, _me(), str(name or "").strip(), str(verdict or ""), str(reason or ""))


@frappe.whitelist(methods=["POST"])
def plan_availability(data):
    """Team Data: len ke hoach bo sung. data = JSON {team, data_type, platforms[], other_platform, channels[],
    assignee, method, start_date, due_date, note, priority, proposal}."""
    return _run(lambda: _avail().plan(_me(), _json(data)))


@frappe.whitelist()
def plan_defaults(start_date="", priority=""):
    def run():
        S.require_operate(S._repo(None), _me())
        return _avail().plan_defaults(_avail()._repo(None), str(start_date or "") or None, str(priority or "") or None)
    return _run(run)


@frappe.whitelist(methods=["POST"])
def save_availability(data):
    """Team Data: them / sua mot dong ma tran (co `name` = sua)."""
    return _run(lambda: _avail().save_row(_me(), _json(data)))


@frappe.whitelist(methods=["POST"])
def add_availability(data):
    """Team Data: "+ Thêm dữ liệu đã có" tren ma tran - nhieu san mot lan, khong qua de xuat."""
    return _run(lambda: _avail().add_rows(_me(), _json(data)))


@frappe.whitelist(methods=["POST"])
def save_library(data):
    """Team Data: them / sua muc Thu vien bao cao (co `name` = sua)."""
    return _run(lambda: _avail().save_library(_me(), _json(data)))


@frappe.whitelist(methods=["POST"])
def library_active(name, active=1):
    return _run(_avail().set_library_active, _me(), str(name or "").strip(), active)


@frappe.whitelist()
def suggest(q=""):
    """Form tao yeu cau: goi y dashboard / yeu cau dang mo tuong tu theo tieu de."""
    return _run(_avail().suggest, _me(), str(q or ""))

# ====================================================================== DOT 3 (09/11/2026) ===
# Noi them cuoi file (dot 2 sua song song). Quy tac thoi han: rules_service; phieu cu: migration.
def _rules():
    from ecentric_workspace.data_hub import rules_service
    return rules_service


@frappe.whitelist(methods=["POST"])
def save_rule_draft(data):
    """Team Data luu ban nhap quy tac. data = JSON {days: {rule_key: n}, mult: {muc: x}, reason, submit}."""
    return _run(lambda: _rules().save_draft(_me(), _json(data)))


@frappe.whitelist(methods=["POST"])
def submit_rule(name, reason=""):
    return _run(lambda: _rules().submit(_me(), str(name or ""), str(reason or "")))


@frappe.whitelist(methods=["POST"])
def decide_rule(name, verdict, note=""):
    """Nguoi duyet quy tac (Settings.rule_approver): verdict = "approve" | "reject" (+ ly do)."""
    return _run(lambda: _rules().decide(_me(), str(name or ""), str(verdict or ""), str(note or "")))


@frappe.whitelist(methods=["POST"])
def cancel_rule(name, reason=""):
    return _run(lambda: _rules().cancel(_me(), str(name or ""), str(reason or "")))


@frappe.whitelist()
def legacy_migration_report():
    """System Manager: chay lai DRY RUN chuyen phieu Data Request cu - chi doc, tra bao cao."""
    from ecentric_workspace.data_hub import migration
    return _run(lambda: migration.run_for(_me(), dry_run=1))


@frappe.whitelist(methods=["POST"])
def run_legacy_migration():
    """System Manager: chuyen THAT cac phieu chua chuyen (chay lai an toan - phieu da co ticket bo qua)."""
    from ecentric_workspace.data_hub import migration
    return _run(lambda: migration.run_for(_me(), dry_run=0))
