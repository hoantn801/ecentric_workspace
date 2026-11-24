# Copyright (c) 2026, eCentric and contributors
"""Kiem ma may: chu hoa, so, . _ - (dung lam tien to token <machine_id>.<token>)."""
from ecentric_workspace.host_qc.constants import messages as M
from ecentric_workspace.host_qc.constants.rules import MACHINE_ID_RE
from ecentric_workspace.host_qc.exceptions import InvalidInput


class ValidateMachineService:
    def execute(self, doc):
        mid = (doc.machine_id or "").strip()
        if not MACHINE_ID_RE.match(mid):
            raise InvalidInput(M.BAD_MACHINE_ID)
        doc.machine_id = mid
