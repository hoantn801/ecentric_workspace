# Copyright (c) 2026, eCentric and contributors
"""Nut "Tao token moi" tren form may: sinh token, luu SHA-256, tra token 1 lan. Token cu het hieu luc ngay."""
import secrets

from ecentric_workspace.host_qc.constants import messages as M
from ecentric_workspace.host_qc.constants.roles import MANAGE
from ecentric_workspace.host_qc.constants.rules import TOKEN_BYTES
from ecentric_workspace.host_qc.exceptions import ForbiddenError, NotFoundError
from ecentric_workspace.host_qc.repositories.machine_repository import MachineRepository
from ecentric_workspace.host_qc.services.verify_machine_token_service import token_hash
from ecentric_workspace.host_qc.utils.time import now


class IssueMachineTokenService:
    def __init__(self, machines=None, clock=now):
        self.machines = machines or MachineRepository()
        self.clock = clock

    def execute(self, machine_id, user, roles):
        if not set(roles or ()) & set(MANAGE):
            raise ForbiddenError(M.NEED_MANAGER)
        if not self.machines.exists(machine_id):
            raise NotFoundError(M.NO_MACHINE % machine_id)
        token = secrets.token_hex(TOKEN_BYTES)
        self.machines.set_token(machine_id, token_hash(token), user, self.clock())
        return {"machine_id": machine_id, "token": token}
