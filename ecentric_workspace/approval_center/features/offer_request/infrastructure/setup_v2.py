# Copyright (c) 2026, eCentric and contributors
"""OFFER_REQUEST-V2 (23/11/2026, Hoan chot): TA -> Line Manager -> CnB/HR -> [HOF co dieu kien] -> CEO.

  L1 Line Manager   Reference User Field `line_manager` (chep tu Hiring - nguoi gui khong chon)
  L2 CnB/HR         Role EC CnB + Role HR (Any One; role HR chua co nguoi -> bo + canh bao)
  L3 HOF            Role EC HOF, mandatory=0: service bo cap nay (submit(skip_level_nos), co audit)
                    khi luong offer <= muc da duyet tren Hiring; thieu du lieu so sanh -> GIU HOF.
  L4 CEO            Role EC CEO
  SLA moi cap 1 ngay lam viec (policy HR_1_NGAY_LV - chi gan khi an toan).
CEO duyet -> tu tao New Staff Preparation (V2: CEO la nguoi theo doi o NSP)."""
import json

import frappe

from ecentric_workspace.approval_center.shared import process_seed as ps
from ecentric_workspace.approval_center.shared import sla_ngay_lam_viec as sla

PROCESS_CODE = "OFFER_REQUEST-V2"
APPROVAL_TYPE = "OFFER_REQUEST"
LM_FIELD = "line_manager"
#: service.py tim cap HOF theo TEN nay (khong theo so cap) - doi ten o day la doi ca hai.
HOF_LEVEL_NAME = "HOF (khi lương vượt mức Hiring)"
LEVEL_NAMES = ("Line Manager", "CnB/HR", HOF_LEVEL_NAME, "CEO")
DEFAULT_CNB = ["role:EC CnB", "role:HR"]
OPTIONAL = ("role:HR",)
DEFAULT_HOF = ["role:EC HOF"]
DEFAULT_CEO = ["role:EC CEO"]
SLA_DAYS = 1


def _parse(v, default):
    if v is None:
        return list(default)
    if isinstance(v, str):
        v = json.loads(v) if v.strip().startswith("[") else [x.strip() for x in v.split(",") if x.strip()]
    return list(dict.fromkeys(v or []))


@frappe.whitelist()
def setup_offer_request_v2(cnb=None, hof=None, ceo=None, dry_run=1, apply=0):
    ps.require_sm()
    dry = int(apply or 0) != 1
    rep = ps.new_report(dry)
    cnb_e = ps.check_entries("CnB/HR", _parse(cnb, DEFAULT_CNB), rep, optional=OPTIONAL)
    hof_e = ps.check_entries("HOF", _parse(hof, DEFAULT_HOF), rep)
    ceo_e = ps.check_entries("CEO", _parse(ceo, DEFAULT_CEO), rep)
    rep["planned"] = ["process %s (Draft)" % PROCESS_CODE,
                      "L1 Line Manager (line_manager)", "L2 CnB/HR %s" % cnb_e,
                      "L3 HOF %s (không bắt buộc - bỏ khi lương <= Hiring)" % hof_e, "L4 CEO %s" % ceo_e,
                      "SLA %d ngày làm việc mỗi cấp" % SLA_DAYS]

    def spec():
        pol = sla.ensure_policy(SLA_DAYS, rep)
        return {"code": PROCESS_CODE, "title": "Offer Request V2", "approval_type": APPROVAL_TYPE,
                "version_no": 2,
                "description": "LM -> CnB/HR -> HOF (chỉ khi lương offer > mức Hiring) -> CEO.",
                "levels": [
                    {"level_no": 1, "level_name": LEVEL_NAMES[0], "sla_policy": pol,
                     "participants": [{"participant_purpose": "Approver",
                                       "source_type": "Reference User Field",
                                       "reference_field": LM_FIELD, "sort_order": 0}]},
                    {"level_no": 2, "level_name": LEVEL_NAMES[1], "sla_policy": pol,
                     "participants": ps.rows(cnb_e)},
                    {"level_no": 3, "level_name": LEVEL_NAMES[2], "sla_policy": pol, "mandatory": 0,
                     "participants": ps.rows(hof_e)},
                    {"level_no": 4, "level_name": LEVEL_NAMES[3], "sla_policy": pol,
                     "participants": ps.rows(ceo_e)},
                ]}
    return ps.finish_setup(rep, dry, spec, APPROVAL_TYPE)


@frappe.whitelist()
def validate_offer_request_v2():
    return ps.validate_process(PROCESS_CODE, expect_levels=4)


@frappe.whitelist()
def activate_offer_request_v2(dry_run=1, apply=0):
    return ps.run_swap(APPROVAL_TYPE, PROCESS_CODE, dry_run=dry_run, apply=apply, expect_levels=4)
