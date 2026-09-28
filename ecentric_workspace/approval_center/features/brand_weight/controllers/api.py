# Copyright (c) 2026, eCentric and contributors
"""API cua trang Nhan su > Phan bo cong viec. Moi ham: goi service -> boc envelope.

VI SAO rollback khi bat loi: bat exception trong ham whitelist nghia la Frappe KHONG tu
rollback nua. decide_weights ghi ty trong truoc roi moi goi engine.approve (engine moi
la noi kiem nguoi duyet) - neu khong rollback o day, so do lead khong co quyen ghi van
duoc commit du engine da tu choi."""
import frappe

from ecentric_workspace.approval_center.shared.api_adapter import bind
from ecentric_workspace.approval_center.features.brand_weight.application import (
    period_service as ps, team_service as ts,
)

globals().update(bind("BRAND_WEIGHT"))

MSG_UNKNOWN = "Không thực hiện được. Thử lại sau ít phút, nếu vẫn lỗi thì báo IT."


def _run(fn):
    try:
        return {"success": True, "message": "", "data": fn()}
    except (frappe.ValidationError, frappe.PermissionError) as e:
        frappe.db.rollback()
        return {"success": False, "message": frappe.utils.strip_html(str(e)) or MSG_UNKNOWN, "data": None}
    except Exception:
        frappe.db.rollback()
        frappe.log_error(title="brand_weight api")
        return {"success": False, "message": MSG_UNKNOWN, "data": None}


@frappe.whitelist(methods=["GET"])
def get_my_period(period: str = None):
    return _run(lambda: ps.GetMyPeriodService().execute(frappe.session.user, period or ps.default_period()))


@frappe.whitelist(methods=["POST"])
def submit_weights(period: str, weights: str):
    return _run(lambda: ps.SubmitWeightsService().execute(frappe.session.user, str(period), weights))


@frappe.whitelist(methods=["GET"])
def get_team_period(period: str = None):
    return _run(lambda: ts.GetTeamPeriodService().execute(frappe.session.user, period or ps.default_period()))


@frappe.whitelist(methods=["POST"])
def decide_weights(name: str, action: str, weights: str = None, note: str = None):
    return _run(lambda: ts.DecideWeightsService().execute(
        frappe.session.user, str(name), str(action), weights, note))
