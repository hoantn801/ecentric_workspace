# Copyright (c) 2026, eCentric and contributors
"""CONTRACT_REVIEW-V2 (24/11/2026, PO chot cau D ban giao chat Ky so): them cap Nhan su cho hop dong
lao dong. Moi loai hop dong khac chay Y HET V1.

  L1 Department Manager Review   chep NGUYEN tu process dang Active (V1) - nguoi duyet + SLA
  L2 Finance Team Review         chep nguyen
  L3 Head of Finance Review      chep nguyen
  L4 HR & C&B Review             MOI: Role EC CnB + Role HR (Any One; role HR chua co nguoi -> bo +
                                 canh bao), SLA = SLA cua L3 V1. Chi hop dong lao dong di qua.
  L5 CEO Review                  chep nguyen (V1 L4)
Moi cap mandatory=0: service (domain/routing.plan) quyet dinh bo cap nao, engine ghi audit
"Skipped" kem ly do. Lao dong: Nhan su -> CEO. Loai khac: Truong phong -> Finance -> HOF -> CEO (CEO
bo khi chi dieu chinh hop dong san co - nhu V1).

Chep tu process DANG CHAY tren site (khong ghi cung email trong code): ai dang duyet V1 thi duyet V2.
Phieu dang chay giu snapshot V1 (engine) - khong vo. V1 chi Retired, khong xoa (quay lui duoc).
Luu y Ky so: CEO o V2 la CAP 5 (V1 la cap 4) - ho so ky hop dong tao SAU khi V2 bat."""
import json

import frappe

from ecentric_workspace.approval_center.features.contract_review.domain import routing
from ecentric_workspace.approval_center.shared import process_seed as ps

PROCESS_CODE = "CONTRACT_REVIEW-V2"
APPROVAL_TYPE = "CONTRACT_REVIEW"
DEFAULT_HR = ["role:EC CnB", "role:HR"]
OPTIONAL = ("role:HR",)
#: Cap chep tu process dang Active, theo TEN (V1 dung dung cac ten nay).
COPY = (routing.DEPT, routing.FINANCE, routing.HOF, routing.CEO)
LEVELS = 5


def _parse(v, default):
    if v is None:
        return list(default)
    if isinstance(v, str):
        v = json.loads(v) if v.strip().startswith("[") else [x.strip() for x in v.split(",") if x.strip()]
    return list(dict.fromkeys(v or []))


def _source_process():
    rows = frappe.get_all("EC Approval Process", filters={"approval_type": APPROVAL_TYPE, "status": "Active",
                                                          "name": ["!=", PROCESS_CODE]}, pluck="name")
    return rows[0] if rows else None


def _source_levels(code):
    """{level_name: {"sla_policy", "approval_mode", "participants": [dict]}} cua process nguon."""
    out = {}
    for l in frappe.get_all("EC Approval Level", filters={"approval_process": code},
                            fields=["name", "level_name", "sla_policy", "approval_mode"], order_by="level_no asc"):
        doc = frappe.get_doc("EC Approval Level", l.name)
        parts = []
        for p in doc.participants or []:
            parts.append({k: p.get(k) for k in ("participant_purpose", "source_type", "user", "role", "department",
                                                  "department_field", "reference_field", "fallback_user",
                                                  "group_label", "sort_order")})
        out[l.level_name] = {"sla_policy": l.sla_policy, "approval_mode": l.approval_mode or "Any One",
                             "participants": parts}
    return out


@frappe.whitelist()
def setup_contract_review_v2(hr=None, dry_run=1, apply=0):
    ps.require_sm()
    dry = int(apply or 0) != 1
    rep = ps.new_report(dry)
    cur = frappe.db.get_value("EC Approval Process", PROCESS_CODE, "status")
    if cur in ("Active", "Retired"):
        rep["result"] = "%s (giữ nguyên)" % cur.upper()
        return rep
    src = _source_process()
    levels = _source_levels(src) if src else {}
    if not src:
        rep["errors"].append("Không có process CONTRACT_REVIEW đang Active để chép người duyệt.")
    for nm in COPY:
        if src and nm not in levels:
            rep["errors"].append("%s thiếu cấp '%s' - không chép được." % (src, nm))
        elif src and not [p for p in levels[nm]["participants"] if p.get("participant_purpose") == "Approver"]:
            rep["errors"].append("%s cấp '%s' không có người duyệt." % (src, nm))
    hr_e = ps.check_entries("Nhân sự (C&B)", _parse(hr, DEFAULT_HR), rep, optional=OPTIONAL)
    rep["planned"] = ["process %s (Draft), chép L1-L3 + CEO từ %s" % (PROCESS_CODE, src or "—"),
                      "L4 %s %s (chỉ hợp đồng lao động)" % (routing.HR, hr_e),
                      "L5 %s (V1 là L4)" % routing.CEO, "mọi cấp mandatory=0 (service bỏ cấp theo loại HĐ)"]

    def spec():
        hof_sla = (levels.get(routing.HOF) or {}).get("sla_policy")

        def copied(no, nm):
            s = levels[nm]
            return {"level_no": no, "level_name": nm, "mandatory": 0, "approval_mode": s["approval_mode"],
                    "sla_policy": s["sla_policy"], "participants": [dict(p) for p in s["participants"]]}
        return {"code": PROCESS_CODE, "title": "Contract Review V2", "approval_type": APPROVAL_TYPE,
                "version_no": 2,
                "description": "Như V1; thêm cấp Nhân sự (C&B) cho hợp đồng lao động: Nhân sự -> CEO.",
                "levels": [copied(1, routing.DEPT), copied(2, routing.FINANCE), copied(3, routing.HOF),
                           {"level_no": 4, "level_name": routing.HR, "mandatory": 0, "sla_policy": hof_sla,
                            "participants": ps.rows(hr_e)},
                           copied(5, routing.CEO)]}
    return ps.finish_setup(rep, dry, spec, APPROVAL_TYPE)


@frappe.whitelist()
def validate_contract_review_v2():
    return ps.validate_process(PROCESS_CODE, expect_levels=LEVELS)


@frappe.whitelist()
def activate_contract_review_v2(dry_run=1, apply=0):
    return ps.run_swap(APPROVAL_TYPE, PROCESS_CODE, dry_run=dry_run, apply=apply, expect_levels=LEVELS)
