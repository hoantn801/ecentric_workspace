# Copyright (c) 2026, eCentric and contributors
"""p001: seed Trung tam Du lieu (PO Hoan chot 09/11/2026).

  1. Role team Data (EC Data Team) - da co tu Daily Target thi giu nguyen.
  2. Bo quy tac v1 "Dang ap dung" (so ngay mac dinh + he so uu tien trong spec).
  3. EC Data Hub Settings: role team Data, nguoi duyet quy tac (SEED_APPROVER - du lieu seed, khong
     phai hang so cua code; quan tri doi tren /app/ec-data-hub-settings), project /pm, bo quy tac.
  4. Project /pm "Trung tam Du lieu" - tao qua pm.api.projects.create (luat PM: company, ec_manager)
     neu chua co project cung ten.
Chay lai bao nhieu lan cung duoc: gia tri da co KHONG bi ghi de. FAIL-SAFE: moi buoc trong try,
loi -> Error Log, khong bao gio chan migrate.
"""
import frappe

from ecentric_workspace.data_hub import constants as C

TITLE = "data_hub p001 seed"
SEED_APPROVER = "hoan.tran@ecentric.vn"
PM_PROJECT_NAME = "Trung tâm Dữ liệu"


def _try(step, fn):
    try:
        return fn()
    except Exception:
        frappe.log_error(title="%s: %s" % (TITLE, step), message=frappe.get_traceback())
        return None


def _role():
    if not frappe.db.exists("Role", C.DEFAULT_DATA_TEAM_ROLE):
        frappe.get_doc({"doctype": "Role", "role_name": C.DEFAULT_DATA_TEAM_ROLE, "desk_access": 0}
                       ).insert(ignore_permissions=True)
    return C.DEFAULT_DATA_TEAM_ROLE


def _rule_set():
    existing = frappe.get_all(C.RULE_DT, filters={"status": C.RULE_ACTIVE}, pluck="name",
                              order_by="version_no desc", limit=1)
    if existing:
        return existing[0]
    if frappe.db.exists(C.RULE_DT, {"version_no": 1}):
        return frappe.db.get_value(C.RULE_DT, {"version_no": 1}, "name")
    doc = frappe.get_doc({
        "doctype": C.RULE_DT, "version_no": 1, "status": C.RULE_ACTIVE,
        "effective_from": frappe.utils.nowdate(), "reason": "Bộ quy tắc đầu tiên (PO chốt 09/11/2026)",
        "mult_urgent": C.MULT_DEFAULTS[C.PRI_URGENT], "mult_high": C.MULT_DEFAULTS[C.PRI_HIGH],
        "mult_normal": C.MULT_DEFAULTS[C.PRI_NORMAL], "mult_low": C.MULT_DEFAULTS[C.PRI_LOW],
        "items": [{"rule_key": key, "label": label, "days": days, "note": note}
                  for key, _t, label, days, note in C.RULE_DEFAULTS],
    })
    doc.insert(ignore_permissions=True)
    return doc.name


def _project():
    rows = frappe.get_all("Project", filters={"project_name": PM_PROJECT_NAME}, pluck="name", limit=1)
    if rows:
        return rows[0]
    from ecentric_workspace.pm.api import projects
    manager = SEED_APPROVER if frappe.db.exists("User", SEED_APPROVER) else None
    out = projects.create(PM_PROJECT_NAME, manager=manager,
                          description="Task của Trung tâm Dữ liệu (/du-lieu) - tạo tự động khi team Data nhận yêu cầu.")
    return out.get("name")


def execute():
    if not frappe.db.exists("DocType", C.SETTINGS_DT):
        return
    role = _try("role", _role)
    rule = _try("rule set", _rule_set)
    project = _try("pm project", _project)

    def settings():
        s = frappe.get_single(C.SETTINGS_DT)
        changed = False
        for field, value in (("data_team_role", role), ("pm_project", project), ("active_rule_set", rule)):
            if value and not s.get(field):
                s.set(field, value)
                changed = True
        if not s.get("rule_approver") and frappe.db.exists("User", SEED_APPROVER):
            s.rule_approver = SEED_APPROVER
            changed = True
        if s.get("pm_sync_enabled") is None:
            s.pm_sync_enabled = 1
            changed = True
        if changed:
            s.flags.ignore_permissions = True
            s.save(ignore_permissions=True)
    _try("settings", settings)
