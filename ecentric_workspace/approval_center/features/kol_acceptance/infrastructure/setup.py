# Copyright (c) 2026, eCentric and contributors
"""Seed luong KOL_ACCEPTANCE-V1 - BBNT tung dot hop dong KOL/KOC (PO chot 24/11/2026). System-Manager
only, dry-run mac dinh. KHONG ghi de process Active / Retired (process_seed.upsert_process).

  L1 General Accountant Review   Ke toan tong hop: tham so `ktth` (email hoac "role:<Role>") - PO chi
                                 dinh nguoi cu the, truyen tu patch, khong ghi trong code nghiep vu.
                                 SLA = SLA cap Finance Team Review cua CONTRACT_REVIEW dang Active.
  L2 Chief Accountant Review     Ke toan truong: chep nguoi duyet + SLA cap "Head of Finance Review"
                                 cua CONTRACT_REVIEW dang Active.
  L3 CEO Review                  chep cap "CEO Review" cua CONTRACT_REVIEW dang Active.
Moi cap mandatory=1 (PO 24/11 cau 1: BBNT LUON qua du 3 cap, ke ca khi chua ky so).
Chep tu process DANG CHAY tren site: ai dang duyet hop dong thi duyet BBNT."""
import frappe
from frappe import _

from ecentric_workspace.approval_center.shared import process_seed as ps

PROCESS_CODE = "KOL_ACCEPTANCE-V1"
APPROVAL_TYPE = "KOL_ACCEPTANCE"
SOURCE_TYPE = "CONTRACT_REVIEW"
KTTH = "General Accountant Review"
KTT = "Chief Accountant Review"
CEO = "CEO Review"
#: Ten cap ben CONTRACT_REVIEW (V1 / V2 deu dung cac ten nay - contract_review.domain.routing).
SRC_FINANCE, SRC_HOF, SRC_CEO = "Finance Team Review", "Head of Finance Review", "CEO Review"
LEVELS = 3
_PART_KEYS = ("participant_purpose", "source_type", "user", "role", "department", "department_field",
              "reference_field", "fallback_user", "group_label", "sort_order")


def _require_sm():
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Chỉ System Manager được cấu hình quy trình BBNT."), frappe.PermissionError)


def _source_process():
    rows = frappe.get_all("EC Approval Process", filters={"approval_type": SOURCE_TYPE, "status": "Active"},
                          pluck="name")
    return rows[0] if rows else None


def _source_levels(code):
    out = {}
    for l in frappe.get_all("EC Approval Level", filters={"approval_process": code},
                            fields=["name", "level_name", "sla_policy", "approval_mode"], order_by="level_no asc"):
        doc = frappe.get_doc("EC Approval Level", l.name)
        parts = [{k: p.get(k) for k in _PART_KEYS} for p in doc.participants or []
                 if p.get("participant_purpose") == "Approver"]
        out[l.level_name] = {"sla_policy": l.sla_policy, "approval_mode": l.approval_mode or "Any One",
                             "participants": parts}
    return out


def _entries(ktth):
    if not ktth:
        return []
    if isinstance(ktth, str):
        return [x.strip() for x in ktth.split(",") if x.strip()]
    return [x for x in ktth if x]


@frappe.whitelist()
def setup_kol_acceptance_v1(ktth=None, dry_run=1, apply=0):
    _require_sm()
    dry = int(apply or 0) != 1
    rep = ps.new_report(dry)
    cur = frappe.db.get_value("EC Approval Process", PROCESS_CODE, "status")
    if cur in ("Active", "Retired"):
        rep["result"] = "%s (giữ nguyên)" % cur.upper()
        return rep
    src = _source_process()
    levels = _source_levels(src) if src else {}
    if not src:
        rep["errors"].append("Không có process %s đang Active để chép người duyệt." % SOURCE_TYPE)
    for nm in (SRC_HOF, SRC_CEO):
        if src and not (levels.get(nm) or {}).get("participants"):
            rep["errors"].append("%s thiếu cấp '%s' (hoặc cấp không có người duyệt)." % (src, nm))
    if not _entries(ktth):
        rep["errors"].append("Thiếu tham số ktth (Kế toán tổng hợp: email hoặc role:<Role>).")
    k_e = ps.check_entries("Kế toán tổng hợp", _entries(ktth), rep) if _entries(ktth) else []
    rep["planned"] = ["process %s (Draft)" % PROCESS_CODE,
                      "L1 %s %s" % (KTTH, k_e),
                      "L2 %s (chép '%s' của %s)" % (KTT, SRC_HOF, src or "—"),
                      "L3 %s (chép '%s' của %s)" % (CEO, SRC_CEO, src or "—"),
                      "mọi cấp mandatory=1"]

    def spec():
        def copied(no, name, src_name):
            s = levels[src_name]
            return {"level_no": no, "level_name": name, "mandatory": 1, "approval_mode": s["approval_mode"],
                    "sla_policy": s["sla_policy"], "participants": [dict(p) for p in s["participants"]]}
        return {"code": PROCESS_CODE, "title": "BBNT KOL/KOC V1", "approval_type": APPROVAL_TYPE,
                "version_no": 1,
                "description": "Mỗi đợt nghiệm thu hợp đồng KOL/KOC: Kế toán tổng hợp -> Kế toán trưởng -> CEO.",
                "levels": [{"level_no": 1, "level_name": KTTH, "mandatory": 1,
                            "sla_policy": (levels.get(SRC_FINANCE) or {}).get("sla_policy"),
                            "participants": ps.rows(k_e)},
                           copied(2, KTT, SRC_HOF), copied(3, CEO, SRC_CEO)]}
    return ps.finish_setup(rep, dry, spec, APPROVAL_TYPE)


@frappe.whitelist()
def validate_kol_acceptance_v1():
    _require_sm()
    return ps.validate_process(PROCESS_CODE, expect_levels=LEVELS)
