# Copyright (c) 2026, eCentric and contributors
"""Setup idempotent cho hai process cua BRAND_WEIGHT.

BRAND_WEIGHT-V1 (moi nguoi): cap 1 lead truc tiep, cap 2 truong phong. Ca hai cap
mandatory=0 vi engine chi cho bo cap KHONG mandatory (submit(skip_level_nos)) - xem
application/routing.py cho luat bo cap. Viec bo cap duoc ghi audit kem skip_reason.

BRAND_WEIGHT-SELF-V1 (8 nguoi phong Management - chot voi Hoan 26/09): mot cap, nguoi
duyet = chinh nguoi nop (Reference User Field -> requested_by). Nop xong service tu
approve, nhat ky ghi "tu chot". Vi sao KHONG dung V1 roi bo het cap: engine bat buoc
phieu con it nhat mot cap, va cap truong phong cua phong Management chinh la anh Lam -
dung dieu Hoan yeu cau tranh.

Hai process cung Active cho mot approval type, nen MOI lan submit phai truyen
process_code (application/service.py). resolve_process khong co process_code se lay
dong dau tien bat ky - khong duoc de xay ra.

Nguoi duyet resolve luc chay, khong hardcode ai. Non-destructive, chay lai an toan."""
import frappe
from frappe import _

APPROVAL_TYPE = "BRAND_WEIGHT"
PROCESS_CODE = "BRAND_WEIGHT-V1"
SELF_PROCESS_CODE = "BRAND_WEIGHT-SELF-V1"
PROCESSES = (
    (PROCESS_CODE, "Brand Weight V1", (
        (1, "Direct Lead", {"source_type": "Requester Manager"}, 0),
        (2, "Department Manager Review", {"source_type": "Department Manager"}, 0),
    )),
    (SELF_PROCESS_CODE, "Brand Weight Self Confirm V1", (
        (1, "Self Confirm", {"source_type": "Reference User Field",
                             "reference_field": "requested_by"}, 1),
    )),
)


def _require_sm():
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may run Brand Weight setup."),
                     frappe.PermissionError)


@frappe.whitelist()
def setup_brand_weight_v1(apply=0):
    _require_sm()
    dry = int(apply or 0) != 1
    steps = []
    if not frappe.db.exists("EC Approval Type", APPROVAL_TYPE):
        return {"mode": "dry_run" if dry else "apply", "ok": False,
                "steps": ["[ERR] EC Approval Type %s chua ton tai" % APPROVAL_TYPE]}
    for code, title, levels in PROCESSES:
        proc = frappe.db.get_value("EC Approval Process", {"process_code": code}, "name")
        if proc:
            steps.append("[OK] process %s da ton tai (khong sua)" % code)
        else:
            steps.append("[NEW] tao process %s (status Draft)" % code)
            if not dry:
                proc = frappe.get_doc({
                    "doctype": "EC Approval Process", "process_code": code, "title": title,
                    "approval_type": APPROVAL_TYPE, "version_no": 1, "status": "Draft",
                }).insert(ignore_permissions=True).name
        for no, name, part, mandatory in levels:
            if proc and frappe.db.exists("EC Approval Level", {"approval_process": proc, "level_no": no}):
                steps.append("[OK] %s cap %d (%s) da ton tai" % (code, no, name))
                continue
            steps.append("[NEW] %s cap %d %s <- %s" % (code, no, name, part["source_type"]))
            if not dry and proc:
                lvl = frappe.get_doc({
                    "doctype": "EC Approval Level", "approval_process": proc, "level_no": no,
                    "level_name": name, "mandatory": mandatory, "approval_mode": "Any One",
                    "minimum_approvals": 1, "allows_amount_adjustment": 0,
                })
                lvl.append("participants", dict(part, participant_purpose="Approver", sort_order=1))
                lvl.insert(ignore_permissions=True)
    return {"mode": "dry_run" if dry else "apply", "ok": True, "steps": steps}


def _levels(proc_name):
    return frappe.get_all("EC Approval Level", filters={"approval_process": proc_name},
                          fields=["name", "level_no", "mandatory"], order_by="level_no asc")


@frappe.whitelist()
def validate_brand_weight_v1():
    checks = []

    def c(ok, msg):
        checks.append({"check": msg, "ok": bool(ok)})

    for code, _title, levels in PROCESSES:
        proc = frappe.db.get_value("EC Approval Process", {"process_code": code},
                                   ["name", "status"], as_dict=True)
        c(proc, "%s ton tai" % code)
        if not proc:
            continue
        c(proc.status in ("Draft", "Active"), "%s status Draft hoac Active" % code)
        got = _levels(proc.name)
        c([l.level_no for l in got] == [l[0] for l in levels], "%s dung %d cap" % (code, len(levels)))
        if code == PROCESS_CODE:
            c(all(not l.mandatory for l in got), "%s: ca hai cap mandatory=0 (de bo duoc cap)" % code)
    others = frappe.get_all("EC Approval Process",
                            filters={"approval_type": APPROVAL_TYPE, "status": "Active",
                                     "process_code": ["not in", [p[0] for p in PROCESSES]]},
                            pluck="name")
    c(not others, "khong co process Active la nao khac cho %s" % APPROVAL_TYPE)
    return {"ok": all(x["ok"] for x in checks), "checks": checks}
