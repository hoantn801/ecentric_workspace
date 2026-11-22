# Copyright (c) 2026, eCentric and contributors
"""Seed luong EMPLOYEE_REVIEW (Draft), System-Manager only, dry-run mac dinh.

HAI process cho cung mot loai phieu - chi khac SLA (Hoan chot 23/11, so ngay lam viec):
    EMPLOYEE_REVIEW_TV-V1  thu viec / thuc tap : NV 2 · LM 3 · CEO 2
    EMPLOYEE_REVIEW_HD-V1  hop dong            : NV 3 · LM 5 · CEO 3
Service chon process theo `review_type` (engine.submit(process_code=...)). SLA dat qua
sla.application.policy_import.apply (ma process = phan truoc "-V").

Moi process 3 cap, deu mandatory:
    L1 Nhan vien tu danh gia   Reference User Field `employee_user`
    L2 Line Manager danh gia   Reference Employee Manager (`employee_user`) - KHONG fallback: khong
                               co LM thi phieu khong duoc tao (hang cho C&B), khong do bua cho ai
    L3 CEO duyet               Role EC CEO
Nguoi theo doi (participant_purpose = Notify): Role EC CnB - engine nen cua Agent A doc dong nay
(nhan thong bao + quyen doc). KHONG hardcode email nao."""
import json

import frappe
from frappe import _

APPROVAL_TYPE = "EMPLOYEE_REVIEW"
PROCESSES = (
    ("EMPLOYEE_REVIEW_TV-V1", "Đánh giá thử việc / thực tập V1", (2, 3, 2)),
    ("EMPLOYEE_REVIEW_HD-V1", "Đánh giá hợp đồng V1", (3, 5, 3)),
)
PROCESS_CODE = PROCESSES[0][0]
CEO_ROLE = "EC CEO"
NOTIFY_ROLE = "EC CnB"
LEVELS = (
    (1, "Nhân viên tự đánh giá", {"source_type": "Reference User Field", "reference_field": "employee_user"}),
    (2, "Line Manager đánh giá", {"source_type": "Reference Employee Manager", "reference_field": "employee_user"}),
    (3, "CEO duyệt", {"source_type": "Role", "role": CEO_ROLE}),
)
GIO_MOT_NGAY_LV = 8


def _require_sm():
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may run Employee Review setup."), frappe.PermissionError)


def sla_rows():
    """Dong cau hinh SLA cho policy_import.apply (gio lam viec = so ngay LV x 8)."""
    rows = []
    for code, _title, days in PROCESSES:
        base = code.rsplit("-V", 1)[0]
        for (lvl, label, _src), d in zip(LEVELS, days):
            rows.append({"key": "%s#%d" % (base, lvl), "process_code": base, "level_no": lvl,
                         "fulfillment": False, "label": label, "hours": d * GIO_MOT_NGAY_LV,
                         "unit": "giờ làm việc", "reminder_hours": GIO_MOT_NGAY_LV // 2})
    return rows


@frappe.whitelist()
def setup_employee_review_v1(dry_run=1, apply=0):
    _require_sm()
    dry = int(apply or 0) != 1
    rep = {"mode": "dry_run" if dry else "apply", "planned": [], "errors": [], "warnings": [],
           "notes": [], "result": None}
    if not frappe.db.exists("EC Approval Type", APPROVAL_TYPE):
        rep["errors"].append("EC Approval Type %s missing (chay patch seed truoc)." % APPROVAL_TYPE)
    if not frappe.db.exists("Role", CEO_ROLE):
        rep["errors"].append("Role %s chua ton tai." % CEO_ROLE)
    elif not frappe.db.exists("Has Role", {"role": CEO_ROLE, "parenttype": "User"}):
        rep["warnings"].append("Chua ai giu Role %s - cap CEO se khong giai duoc." % CEO_ROLE)
    active = [c for c, _t, _d in PROCESSES if frappe.db.get_value("EC Approval Process", c, "status") == "Active"]
    if active:
        rep["notes"].append("ALREADY_ACTIVE %s (khong doi gi)" % active)
        rep["result"] = "ALREADY_ACTIVE"
        rep["blockers"] = rep["errors"]
        return rep
    rep["planned"] = ["process %s (Draft) - SLA NV/LM/CEO %s ngay LV" % (c, d) for c, _t, d in PROCESSES]
    rep["planned"] += ["L%d %s" % (n, name) for n, name, _s in LEVELS]
    rep["blockers"] = rep["errors"]
    if rep["errors"]:
        rep["result"] = "BLOCKED"
        return rep
    if dry:
        rep["result"] = "DRY_RUN_OK (khong ghi gi)"
        return rep
    for code, title, _d in PROCESSES:
        _upsert(code, title)
    try:
        from ecentric_workspace.sla.application import policy_import
        rep["sla"] = {k: v for k, v in (policy_import.apply(rows=sla_rows()) or {}).items() if v}
    except Exception:
        rep["warnings"].append("SLA chua dat duoc - xem Error Log")
        frappe.log_error(frappe.get_traceback(), "employee_review setup SLA")
    frappe.db.commit()
    rep["result"] = "APPLIED (process Draft; the chua hien)"
    return rep


def _upsert(code, title):
    proc = frappe.get_doc("EC Approval Process", code) if frappe.db.exists(
        "EC Approval Process", code) else frappe.new_doc("EC Approval Process")
    if not proc.process_code:
        proc.process_code = code
    proc.title = title
    proc.approval_type = APPROVAL_TYPE
    proc.version_no = proc.version_no or 1
    proc.status = "Draft"
    proc.set("participants", [])
    proc.append("participants", {"participant_purpose": "Notify", "source_type": "Role",
                                 "role": NOTIFY_ROLE, "sort_order": 0})
    proc.save(ignore_permissions=True)
    for level_no, level_name, src in LEVELS:
        existing = frappe.get_all("EC Approval Level",
                                  filters={"approval_process": code, "level_no": level_no}, pluck="name")
        lvl = frappe.get_doc("EC Approval Level", existing[0]) if existing \
            else frappe.new_doc("EC Approval Level")
        lvl.approval_process = code
        lvl.level_no = level_no
        lvl.level_name = level_name
        lvl.mandatory = 1
        lvl.approval_mode = "Any One"
        lvl.minimum_approvals = 1
        lvl.allows_amount_adjustment = 0
        lvl.set("participants", [])
        lvl.append("participants", dict({"participant_purpose": "Approver", "sort_order": 0}, **src))
        lvl.save(ignore_permissions=True)


@frappe.whitelist()
def validate_employee_review_v1():
    _require_sm()
    checks = []

    def chk(name, ok, detail=""):
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    chk("approval_type", frappe.db.exists("EC Approval Type", APPROVAL_TYPE))
    chk("business_doctype", frappe.db.exists("DocType", "EC Employee Review"))
    for code, _t, _d in PROCESSES:
        proc = frappe.db.get_value("EC Approval Process", code, ["status"], as_dict=True)
        chk("process_exists:%s" % code, bool(proc), code)
        levels = frappe.get_all("EC Approval Level", filters={"approval_process": code},
                                fields=["level_no", "level_name"], order_by="level_no")
        chk("has_3_levels:%s" % code, len(levels) == 3, json.dumps([l.level_name for l in levels],
                                                                   ensure_ascii=False))
    chk("ceo_role_has_members",
        bool(frappe.db.exists("Has Role", {"role": CEO_ROLE, "parenttype": "User"})), CEO_ROLE)
    return {"ok": all(c["ok"] for c in checks), "checks": checks}


#: Mau tieu chi TAM (Hoan gui bo tieu chi chinh thuc sau - 22/11). Chi tao khi chua co mau nao.
MAU_TAM = "Mẫu tạm - tiêu chí chung"
TIEU_CHI_TAM = (
    ("Kết quả công việc", "Mức độ hoàn thành mục tiêu / KPI được giao trong kỳ."),
    ("Kiến thức & kỹ năng chuyên môn", "Nắm công việc, công cụ, quy trình của vị trí."),
    ("Tinh thần trách nhiệm & chủ động", "Đúng hạn, tự giác, chủ động đề xuất và giải quyết vấn đề."),
    ("Phối hợp & giao tiếp", "Làm việc nhóm, phối hợp với phòng ban khác, báo cáo rõ ràng."),
    ("Tuân thủ nội quy & văn hoá", "Chấp hành nội quy, giờ giấc, phù hợp văn hoá công ty."),
)


def dam_bao_mau_tieu_chi_tam():
    """Seed mau tieu chi tam (5 tieu chi, ap dung 'Tat ca', danh dau mau_tam). Idempotent:
    da co BAT KY mau nao thi khong tao (HR da tu cau hinh). Tra ve ten mau vua tao hoac None."""
    if not frappe.db.exists("DocType", "EC Employee Review Template"):
        return None
    if frappe.db.count("EC Employee Review Template"):
        return None
    doc = frappe.new_doc("EC Employee Review Template")
    doc.ten_mau = MAU_TAM
    doc.ap_dung_cho = "Tất cả"
    doc.dang_dung = 1
    doc.mau_tam = 1
    doc.ghi_chu = "Mẫu tạm do hệ thống tạo - HR thay bằng bộ tiêu chí chính thức (Hoàn gửi sau)."
    for ten, mo_ta in TIEU_CHI_TAM:
        doc.append("tieu_chi", {"tieu_chi": ten, "mo_ta": mo_ta, "trong_so": 1})
    doc.insert(ignore_permissions=True)
    return doc.name
