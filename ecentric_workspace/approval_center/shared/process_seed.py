# Copyright (c) 2026, eCentric and contributors
"""Dung process V2 tu MOT khai bao + doi V1 -> V2 trong MOT giao dich (23/11/2026, HR v2).

Vi sao co file nay. Truoc day moi feature tu viet `_upsert` rieng (offer / nsp / resignation /
clearance moi file ~60 dong giong nhau) va CHUA feature nao co duong "ngung V1, bat V2". Dot HR v2
doi luong bon form mot luc, nen gom ve mot cho:

  * `rows(entries, ...)`      seed "role:<Role>" / email -> dong EC Approval Participant.
  * `check_entries(...)`      kiem seed: role ton tai + co nguoi dang bat; email la System User bat.
                              Muc `optional` khong dat -> bo ra kem canh bao (khong chan).
  * `upsert_process(spec)`    tao/cap nhat process o trang thai Draft. KHONG BAO GIO ghi de mot
                              process dang Active hay da Retired (tra ve ly do, khong nem).
  * `validate_process(code)`  doc lai cau hinh THAT tren site (khong tin spec) truoc khi bat.
  * `swap_active(...)`        V1 (moi process Active khac cua loai do) -> Retired, V2 -> Active,
                              cung giao dich, qua doc.save() de controller dat active_process_key.

Phieu dang chay KHONG bi anh huong: engine chot snapshot luc gui (transitions.build_snapshot), gui
lai / lam lai tu dau van dung snapshot cu. Khong xoa V1 - chi Retired (truy vet + quay lui duoc).
Khong co email nao trong file nay: nguoi duyet la seed do setup cua tung feature truyen vao."""
import frappe
from frappe import _
from frappe.utils import nowdate

from ecentric_workspace.approval_center.shared.workflow.participants import (
    active_role_users, participant_rows)

ROLE_PREFIX = "role:"


def require_sm():
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Chỉ System Manager được chạy thao tác cấu hình quy trình."),
                     frappe.PermissionError)


def _active_user(user):
    row = frappe.db.get_value("User", user, ["enabled", "user_type"], as_dict=True)
    return bool(row and row.enabled and row.user_type == "System User")


def entry_ok(entry):
    """(ok, ly_do) cho mot muc seed."""
    e = (entry or "").strip()
    if e.lower().startswith(ROLE_PREFIX):
        role = e[len(ROLE_PREFIX):].strip()
        if not frappe.db.exists("Role", role):
            return False, "Role %s chưa có trên site" % role
        if not active_role_users(role):
            return False, "Role %s chưa có người dùng đang bật" % role
        return True, ""
    if not _active_user(e):
        return False, "%s không phải System User đang bật" % e
    return True, ""


def check_entries(label, entries, rep, optional=()):
    """Loc seed: muc bat buoc hong -> errors; muc trong `optional` hong -> bo ra + warnings."""
    keep = []
    for e in entries or []:
        ok, why = entry_ok(e)
        if ok:
            keep.append(e)
        elif e in optional:
            rep["warnings"].append("%s: bỏ %s (%s)" % (label, e, why))
        else:
            rep["errors"].append("%s: %s" % (label, why))
    if not keep:
        rep["errors"].append("%s: không còn người duyệt nào hợp lệ." % label)
    return keep


def rows(entries, purpose="Approver", group_label=None, start=0):
    out = []
    for i, r in enumerate(participant_rows(entries)):
        r.update({"participant_purpose": purpose, "sort_order": start + i})
        if group_label:
            r["group_label"] = group_label
        out.append(r)
    return out


def upsert_process(spec):
    """-> "APPLIED" | "SKIP_ACTIVE" | "SKIP_RETIRED". Ghi Draft; khong commit (ben goi commit)."""
    code = spec["code"]
    cur = frappe.db.get_value("EC Approval Process", code, "status")
    if cur == "Active":
        return "SKIP_ACTIVE"
    if cur == "Retired":
        return "SKIP_RETIRED"
    proc = frappe.get_doc("EC Approval Process", code) if cur else frappe.new_doc("EC Approval Process")
    if not proc.process_code:
        proc.process_code = code
    proc.title = spec["title"]
    proc.approval_type = spec["approval_type"]
    proc.version_no = spec.get("version_no") or 2
    proc.status = "Draft"
    proc.description = spec.get("description")
    proc.set("participants", [])
    for r in spec.get("process_participants") or []:
        proc.append("participants", dict(r))
    proc.save(ignore_permissions=True)
    wanted = {l["level_no"] for l in spec["levels"]}
    for old in frappe.get_all("EC Approval Level", filters={"approval_process": code},
                              fields=["name", "level_no"]):
        if old.level_no not in wanted:
            frappe.delete_doc("EC Approval Level", old.name, ignore_permissions=True)
    for spec_l in spec["levels"]:
        ex = frappe.get_all("EC Approval Level",
                            filters={"approval_process": code, "level_no": spec_l["level_no"]},
                            pluck="name")
        lvl = frappe.get_doc("EC Approval Level", ex[0]) if ex else frappe.new_doc("EC Approval Level")
        lvl.approval_process = code
        lvl.level_no = spec_l["level_no"]
        lvl.level_name = spec_l["level_name"]
        lvl.mandatory = 1 if spec_l.get("mandatory", 1) else 0
        lvl.approval_mode = spec_l.get("approval_mode") or "Any One"
        lvl.minimum_approvals = spec_l.get("minimum_approvals",
                                           0 if lvl.approval_mode == "Each Group" else 1)
        lvl.allows_amount_adjustment = 0
        lvl.sla_policy = spec_l.get("sla_policy") or None
        lvl.set("participants", [])
        for r in spec_l["participants"]:
            lvl.append("participants", dict(r))
        lvl.save(ignore_permissions=True)
    return "APPLIED"


def validate_process(code, expect_levels=None):
    """Doc cau hinh THAT. -> {"ok", "checks":[{check, ok}], "warnings":[...]}."""
    checks, warns = [], []

    def c(cond, msg):
        checks.append({"check": msg, "ok": bool(cond)})

    proc = frappe.db.get_value("EC Approval Process", code, ["name", "status", "approval_type"],
                               as_dict=True)
    c(bool(proc), "process %s tồn tại" % code)
    if not proc:
        return {"ok": False, "checks": checks, "warnings": warns}
    c(proc.status in ("Draft", "Active"), "%s ở Draft/Active (đang %s)" % (code, proc.status))
    levels = frappe.get_all("EC Approval Level", filters={"approval_process": code},
                            fields=["name", "level_no", "level_name", "approval_mode", "sla_policy"],
                            order_by="level_no asc")
    nos = [l.level_no for l in levels]
    c(bool(nos) and nos == list(range(1, len(nos) + 1)), "cấp liên tục 1..n")
    if expect_levels is not None:
        c(len(nos) == expect_levels, "đúng %d cấp" % expect_levels)
    for l in levels:
        parts = frappe.get_all("EC Approval Participant",
                               filters={"parent": l.name, "parenttype": "EC Approval Level",
                                        "participant_purpose": "Approver"},
                               fields=["source_type", "user", "role", "group_label",
                                       "reference_field", "fallback_user"])
        c(bool(parts), "L%s có người duyệt" % l.level_no)
        if l.approval_mode == "Each Group":
            labels = [p.group_label for p in parts]
            c(len(parts) >= 2 and all(labels) and len(labels) == len(set(labels)),
              "L%s: mỗi nhóm một tên riêng, >= 2 nhóm" % l.level_no)
        for p in parts:
            if p.source_type == "User":
                c(_active_user(p.user), "L%s: %s đang bật" % (l.level_no, p.user))
            elif p.source_type == "Role":
                c(bool(active_role_users(p.role)), "L%s: role %s có người" % (l.level_no, p.role))
            elif p.fallback_user:
                c(_active_user(p.fallback_user), "L%s: dự phòng %s đang bật" % (l.level_no, p.fallback_user))
        if l.sla_policy:
            c(frappe.db.get_value("EC Approval SLA Policy", l.sla_policy, "active"),
              "L%s: SLA %s đang bật" % (l.level_no, l.sla_policy))
    for p in frappe.get_all("EC Approval Participant",
                            filters={"parent": code, "parenttype": "EC Approval Process",
                                     "participant_purpose": "Notify"},
                            fields=["source_type", "user", "role"]):
        # Nguoi theo doi khong chan bat process (engine chua doc Notify thi dong nay chi nam cho).
        if p.source_type == "Role" and not active_role_users(p.role):
            warns.append("Người theo dõi: role %s chưa có người" % p.role)
    return {"ok": all(x["ok"] for x in checks), "checks": checks, "warnings": warns}


def swap_active(approval_type, new_code, dry_run=True, extra_blockers=(), expect_levels=None):
    """Ngung moi process Active khac cua `approval_type` (-> Retired) va bat `new_code` (-> Active)
    trong CUNG giao dich. Khong commit (ben goi commit/rollback). Khong nem khi bi chan."""
    v = validate_process(new_code, expect_levels=expect_levels)
    blockers = [x["check"] for x in v["checks"] if not x["ok"]] + list(extra_blockers or ())
    olds = frappe.get_all("EC Approval Process",
                          filters={"approval_type": approval_type, "status": "Active",
                                   "name": ["!=", new_code]}, pluck="name")
    cur = frappe.db.get_value("EC Approval Process", new_code, "status")
    rep = {"approval_type": approval_type, "new": new_code, "new_status": cur, "retire": olds,
           "validation": v, "blockers": blockers, "mode": "dry_run" if dry_run else "apply"}
    if cur == "Active" and not olds:
        rep["result"] = "ALREADY_ACTIVE"
        return rep
    if blockers:
        rep["result"] = "BLOCKED"
        return rep
    if dry_run:
        rep["result"] = "DRY_RUN_OK"
        return rep
    today = nowdate()
    for name in olds:
        doc = frappe.get_doc("EC Approval Process", name)
        doc.status = "Retired"
        doc.effective_to = today
        doc.save(ignore_permissions=True)
        doc.add_comment("Comment", _("Ngừng dùng: thay bằng {0} ({1}).").format(new_code, frappe.session.user))
    doc = frappe.get_doc("EC Approval Process", new_code)
    doc.status = "Active"
    doc.effective_from = today
    doc.save(ignore_permissions=True)
    doc.add_comment("Comment", _("Bật dùng, thay cho {0} ({1}).").format(", ".join(olds) or "—",
                                                                       frappe.session.user))
    rep["result"] = "SWAPPED"
    return rep


def new_report(dry):
    return {"mode": "dry_run" if dry else "apply", "planned": [], "errors": [], "warnings": [],
            "notes": [], "result": None}


def finish_setup(rep, dry, spec_fn, approval_type):
    """Phan duoi chung cua moi setup_*_v2: chan khi loi seed / thieu loai phieu; dry-run khong ghi;
    apply -> upsert Draft + commit. `spec_fn()` dung spec (chi goi khi apply - co the tao SLA policy)."""
    if not frappe.db.exists("EC Approval Type", approval_type):
        rep["errors"].append("EC Approval Type %s chưa có." % approval_type)
    rep["blockers"] = rep["errors"]
    if rep["errors"]:
        rep["result"] = "BLOCKED"
        return rep
    if dry:
        rep["result"] = "DRY_RUN_OK (không ghi gì)"
        return rep
    spec = spec_fn()
    res = upsert_process(spec)
    rep["notes"].append("%s: %s" % (spec["code"], res))
    frappe.db.commit()
    rep["result"] = {"APPLIED": "APPLIED (process Draft)", "SKIP_ACTIVE": "ALREADY_ACTIVE (giữ nguyên)",
                     "SKIP_RETIRED": "RETIRED (giữ nguyên)"}[res]
    return rep


def run_swap(approval_type, new_code, dry_run=1, apply=0, extra_blockers=(), expect_levels=None):
    """Endpoint-side cua swap_active: SM, dry-run mac dinh, commit/rollback tron goi."""
    require_sm()
    dry = int(apply or 0) != 1
    try:
        rep = swap_active(approval_type, new_code, dry_run=dry, extra_blockers=extra_blockers,
                          expect_levels=expect_levels)
        if not dry and rep.get("result") == "SWAPPED":
            frappe.db.commit()
        return rep
    except Exception:
        frappe.db.rollback()
        raise
