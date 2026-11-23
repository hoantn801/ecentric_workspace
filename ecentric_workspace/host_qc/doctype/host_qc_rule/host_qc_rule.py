# Copyright (c) 2026, eCentric and contributors
"""Host QC Rule - 1 dong bang huong dan (1 ma loi). Sua/xoa -> doi rules_version de may tai lai luat."""
from frappe.model.document import Document

from ecentric_workspace.host_qc.services.bump_rules_version_service import BumpRulesVersionService
from ecentric_workspace.host_qc.services.validate_rule_service import ValidateRuleService
from ecentric_workspace.host_qc.utils.desk import run


class HostQCRule(Document):
    def validate(self):
        run(ValidateRuleService(), self)

    def on_update(self):
        BumpRulesVersionService().execute()

    def on_trash(self):
        BumpRulesVersionService().execute()
