# Copyright (c) 2026, eCentric and contributors
"""Doc chinh sach SLA va tinh HAN. Day la cho duy nhat noi `domain.due_rules`
gap Frappe.

Diem quan trong nhat cua file nay: CHUP chinh sach (`snapshot`) vao tung nghia
vu luc mo. Ly do khong phai ky thuat ma la cong bang: neu hom nay HR doi SLA
buoc duyet tu 8 gio xuong 4 gio, thi moi buoc duyet cua thang truoc KHONG duoc
bien thanh tre hang loat. Nguoi ta da lam viec theo luat cua luc do. Lich su
phai bat bien - neu khong, khong ai tin bang diem, va mot bang diem khong ai tin
thi khong dang dung.
"""
import json

import frappe

from ecentric_workspace.sla.constants import (
    DT_POLICY, DT_TYPE, DUE_BUSINESS_HOURS,
)
from ecentric_workspace.sla.domain import due_rules

_SNAPSHOT_FIELDS = ("policy_code", "due_rule", "duration_hours", "fixed_time",
                    "offset_days", "grace_minutes", "business_calendar", "holiday_list")


def get_type(type_code):
    """Loai nghia vu (dict) hoac None."""
    return frappe.db.get_value(
        DT_TYPE, {"type_code": type_code},
        ["name", "type_code", "type_name", "group_key", "counts_toward_sla",
         "min_sample", "default_policy", "unit_label", "active"], as_dict=True)


def get_policy(policy_code):
    """Chinh sach (dict) hoac None. Chi lay ban dang bat."""
    if not policy_code:
        return None
    return frappe.db.get_value(
        DT_POLICY, {"policy_code": policy_code, "active": 1},
        ["name"] + list(_SNAPSHOT_FIELDS), as_dict=True)


def snapshot(policy):
    """Chinh sach -> chuoi JSON de chup vao nghia vu. `fixed_time` co the la
    timedelta (Frappe tra ve kieu do cho Time) nen phai ep str truoc khi dump."""
    if not policy:
        return None
    out = {}
    for f in _SNAPSHOT_FIELDS:
        v = policy.get(f)
        out[f] = str(v) if v is not None and not isinstance(v, (int, float, str)) else v
    return json.dumps(out, ensure_ascii=False, sort_keys=True)


def _business_due_fn(policy, employee=None, company=None):
    """Bom phep tinh gio lam viec cua Approval Center vao domain. Import TRE:
    mot chinh sach khong dung gio lam viec khong phai nap lich lam viec."""
    def _fn(start_dt, duration_hours):
        from ecentric_workspace.approval_center.shared.workflow import business_hours as bh
        from ecentric_workspace.approval_center.shared.workflow import holidays as hol
        cal = frappe.get_cached_doc("EC Approval Business Calendar", policy["business_calendar"])
        hl = hol.resolve_holiday_list(employee=employee, company=company,
                                      override=policy.get("holiday_list"))
        return bh.calculate_business_due_at(
            start_dt, duration_hours, bh.build_periods(cal.working_periods),
            hol.holiday_dates(hl) if hl else set())
    return _fn


def compute_due(policy, opened_at, explicit_due=None, employee=None, company=None):
    """Han cua mot nghia vu. `policy` la dict (tu get_policy hoac tu snapshot da
    giai ma) - KHONG doc lai DB o day, de tinh lai lich su bang dung luat cu."""
    if not policy:
        return None
    return due_rules.resolve_due(
        rule=policy.get("due_rule"),
        opened_at=opened_at,
        duration_hours=policy.get("duration_hours"),
        fixed_time=policy.get("fixed_time"),
        offset_days=policy.get("offset_days") or 0,
        grace_minutes=policy.get("grace_minutes") or 0,
        explicit_due=explicit_due,
        business_due_fn=(_business_due_fn(policy, employee, company)
                         if policy.get("due_rule") == DUE_BUSINESS_HOURS else None),
    )


def resolve_for_type(type_code, policy_code=None):
    """(type_dict, policy_dict). `policy_code` uu tien; khong co thi lay chinh
    sach mac dinh cua loai. Ca hai co the None - nghia vu khong han van mo duoc,
    no chi khong bao gio tre (dung cho nhom chi de DEM)."""
    t = get_type(type_code)
    if not t:
        return None, None
    pol = get_policy(policy_code) if policy_code else None
    if not pol and t.get("default_policy"):
        pol = frappe.db.get_value(DT_POLICY, {"name": t["default_policy"], "active": 1},
                                  ["name"] + list(_SNAPSHOT_FIELDS), as_dict=True)
    return t, pol
