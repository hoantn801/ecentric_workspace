"""Explicit composition root for Approval Center request definitions."""
from types import MappingProxyType

from ecentric_workspace.approval_center.shared.requests.contracts import validate_definition
from ecentric_workspace.approval_center.features.asset_damage_loss.domain.definition import ASSET_DAMAGE_LOSS_DEFINITION
from ecentric_workspace.approval_center.features.ai_topup.domain.definition import AI_TOPUP_DEFINITION
from ecentric_workspace.approval_center.features.compensation_leave.domain.definition import COMPENSATION_LEAVE_DEFINITION
from ecentric_workspace.approval_center.features.employee_referral.domain.definition import EMPLOYEE_REFERRAL_DEFINITION
from ecentric_workspace.approval_center.features.employee_info_update.domain.definition import EMPLOYEE_INFO_UPDATE_DEFINITION
from ecentric_workspace.approval_center.features.affiliate_bonus.domain.definition import AFFILIATE_BONUS_DEFINITION
from ecentric_workspace.approval_center.features.budget_setting.domain.definition import BUDGET_SETTING_DEFINITION
from ecentric_workspace.approval_center.features.payment_request.domain.definition import PAYMENT_REQUEST_DEFINITION
from ecentric_workspace.approval_center.features.purchase_request.domain.definition import PURCHASE_REQUEST_DEFINITION
from ecentric_workspace.approval_center.features.asset_request.domain.definition import ASSET_REQUEST_DEFINITION
from ecentric_workspace.approval_center.features.data_request.domain.definition import DATA_REQUEST_DEFINITION
from ecentric_workspace.approval_center.features.document_request.domain.definition import DOCUMENT_REQUEST_DEFINITION
from ecentric_workspace.approval_center.features.resignation.domain.definition import RESIGNATION_DEFINITION
from ecentric_workspace.approval_center.features.system_request.domain.definition import SYSTEM_REQUEST_DEFINITION
from ecentric_workspace.approval_center.features.hr_activity.domain.definition import HR_ACTIVITY_DEFINITION
from ecentric_workspace.approval_center.features.late_early_out.domain.definition import LATE_EARLY_OUT_DEFINITION
from ecentric_workspace.approval_center.features.leave.domain.definition import LEAVE_DEFINITION
from ecentric_workspace.approval_center.features.livestream_sample.domain.definition import LIVESTREAM_SAMPLE_DEFINITION
from ecentric_workspace.approval_center.features.hiring_request.domain.definition import HIRING_REQUEST_DEFINITION
from ecentric_workspace.approval_center.features.promotion.domain.definition import PROMOTION_DEFINITION
from ecentric_workspace.approval_center.features.special_bonus.domain.definition import SPECIAL_BONUS_DEFINITION
from ecentric_workspace.approval_center.features.daily_target.domain.definition import DAILY_TARGET_DEFINITION
from ecentric_workspace.approval_center.features.lateral_move.domain.definition import LATERAL_MOVE_DEFINITION
from ecentric_workspace.approval_center.features.livestream_supplies.domain.definition import LIVESTREAM_SUPPLIES_DEFINITION
from ecentric_workspace.approval_center.features.outside_work.domain.definition import OUTSIDE_WORK_DEFINITION
from ecentric_workspace.approval_center.features.service_referral.domain.definition import SERVICE_REFERRAL_DEFINITION


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


