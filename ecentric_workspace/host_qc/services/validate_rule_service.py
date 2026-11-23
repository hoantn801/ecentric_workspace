# Copyright (c) 2026, eCentric and contributors
"""Kiem ma luat (VOI-01, SAL-04, GENERAL-01...)."""
from ecentric_workspace.host_qc.constants import messages as M
from ecentric_workspace.host_qc.constants.rules import RULE_CODE_RE
from ecentric_workspace.host_qc.exceptions import InvalidInput


class ValidateRuleService:
    def execute(self, doc):
        code = (doc.code or "").strip().upper()
        if not RULE_CODE_RE.match(code):
            raise InvalidInput(M.BAD_RULE_CODE)
        doc.code = code
