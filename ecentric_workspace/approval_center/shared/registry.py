"""Explicit composition root for Approval Center request definitions."""
from types import MappingProxyType

from ecentric_workspace.approval_center.shared.requests.contracts import validate_definition
from ecentric_workspace.approval_center.asset_damage_loss.definition import ASSET_DAMAGE_LOSS_DEFINITION
from ecentric_workspace.approval_center.ai_topup.definition import AI_TOPUP_DEFINITION
from ecentric_workspace.approval_center.compensation_leave.definition import COMPENSATION_LEAVE_DEFINITION
from ecentric_workspace.approval_center.employee_referral.definition import EMPLOYEE_REFERRAL_DEFINITION
from ecentric_workspace.approval_center.employee_info_update.definition import EMPLOYEE_INFO_UPDATE_DEFINITION
from ecentric_workspace.approval_center.affiliate_bonus.definition import AFFILIATE_BONUS_DEFINITION
from ecentric_workspace.approval_center.budget_setting.definition import BUDGET_SETTING_DEFINITION
from ecentric_workspace.approval_center.payment_request.definition import PAYMENT_REQUEST_DEFINITION
from ecentric_workspace.approval_center.purchase_request.definition import PURCHASE_REQUEST_DEFINITION
from ecentric_workspace.approval_center.asset_request.definition import ASSET_REQUEST_DEFINITION
from ecentric_workspace.approval_center.data_request.definition import DATA_REQUEST_DEFINITION
from ecentric_workspace.approval_center.document_request.definition import DOCUMENT_REQUEST_DEFINITION
from ecentric_workspace.approval_center.resignation.definition import RESIGNATION_DEFINITION
from ecentric_workspace.approval_center.system_request.definition import SYSTEM_REQUEST_DEFINITION
from ecentric_workspace.approval_center.hr_activity.definition import HR_ACTIVITY_DEFINITION
from ecentric_workspace.approval_center.late_early_out.definition import LATE_EARLY_OUT_DEFINITION
from ecentric_workspace.approval_center.leave.definition import LEAVE_DEFINITION
from ecentric_workspace.approval_center.livestream_sample.definition import LIVESTREAM_SAMPLE_DEFINITION
from ecentric_workspace.approval_center.hiring_request.definition import HIRING_REQUEST_DEFINITION
from ecentric_workspace.approval_center.promotion.definition import PROMOTION_DEFINITION
from ecentric_workspace.approval_center.special_bonus.definition import SPECIAL_BONUS_DEFINITION
from ecentric_workspace.approval_center.daily_target.definition import DAILY_TARGET_DEFINITION
from ecentric_workspace.approval_center.lateral_move.definition import LATERAL_MOVE_DEFINITION
from ecentric_workspace.approval_center.livestream_supplies.definition import LIVESTREAM_SUPPLIES_DEFINITION
from ecentric_workspace.approval_center.outside_work.definition import OUTSIDE_WORK_DEFINITION
from ecentric_workspace.approval_center.service_referral.definition import SERVICE_REFERRAL_DEFINITION


_DEFINITIONS = (
    LEAVE_DEFINITION,
    LATE_EARLY_OUT_DEFINITION,
    COMPENSATION_LEAVE_DEFINITION,
    EMPLOYEE_REFERRAL_DEFINITION,
    EMPLOYEE_INFO_UPDATE_DEFINITION,
    AFFILIATE_BONUS_DEFINITION,
    BUDGET_SETTING_DEFINITION,
    PAYMENT_REQUEST_DEFINITION,
    PURCHASE_REQUEST_DEFINITION,
    ASSET_REQUEST_DEFINITION,
    DATA_REQUEST_DEFINITION,
    DOCUMENT_REQUEST_DEFINITION,
    RESIGNATION_DEFINITION,
    SYSTEM_REQUEST_DEFINITION,
    LIVESTREAM_SAMPLE_DEFINITION,
    HR_ACTIVITY_DEFINITION,
    ASSET_DAMAGE_LOSS_DEFINITION,
    AI_TOPUP_DEFINITION,
    DAILY_TARGET_DEFINITION,
    LATERAL_MOVE_DEFINITION,
    LIVESTREAM_SUPPLIES_DEFINITION,
    OUTSIDE_WORK_DEFINITION,
    SERVICE_REFERRAL_DEFINITION,
    HIRING_REQUEST_DEFINITION,
    PROMOTION_DEFINITION,
    SPECIAL_BONUS_DEFINITION,
)


def _build_registry(definitions):
    by_code = {}
    by_doctype = {}
    for definition in definitions:
        validate_definition(definition)
        if definition.code in by_code:
            raise ValueError("duplicate approval code: %s" % definition.code)
        if definition.business_doctype in by_doctype:
            raise ValueError("duplicate business DocType: %s" % definition.business_doctype)
        by_code[definition.code] = definition
        by_doctype[definition.business_doctype] = definition
    return MappingProxyType(by_code), MappingProxyType(by_doctype)


APPROVAL_DEFINITIONS, BUSINESS_DOCTYPE_DEFINITIONS = _build_registry(_DEFINITIONS)


def get_definition(code):
    try:
        return APPROVAL_DEFINITIONS[code]
    except KeyError:
        raise KeyError("unregistered approval code: %s" % code) from None


def get_definition_for_doctype(doctype):
    try:
        return BUSINESS_DOCTYPE_DEFINITIONS[doctype]
    except KeyError:
        raise KeyError("unregistered approval business DocType: %s" % doctype) from None


