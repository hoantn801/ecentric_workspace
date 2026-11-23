# Copyright (c) 2026, eCentric and contributors
"""Xac thuc may studio bang header X-HostQC-Token: <machine_id>.<token> (anh Vinh chot 24/11).

Khong dung `Authorization`: Frappe tu xu ly header do va tra 401 truoc khi vao ham. ERP chi luu SHA-256
cua token, so sanh hang thoi gian. Sai 30 lan / 10 phut / IP thi chan ca token dung."""
import hashlib
import hmac

from ecentric_workspace.host_qc.constants import messages as M
from ecentric_workspace.host_qc.constants.rules import AUTH_FAIL_LIMIT
from ecentric_workspace.host_qc.exceptions import AuthError, TooManyAttempts
from ecentric_workspace.host_qc.repositories.auth_attempt_repository import AuthAttemptRepository
from ecentric_workspace.host_qc.repositories.machine_repository import MachineRepository


def token_hash(token):
    return hashlib.sha256((token or "").encode("utf-8")).hexdigest()


class VerifyMachineTokenService:
    def __init__(self, machines=None, attempts=None):
        self.machines = machines or MachineRepository()
        self.attempts = attempts or AuthAttemptRepository()

    def execute(self, header, ip):
        if self.attempts.failures(ip) >= AUTH_FAIL_LIMIT:
            raise TooManyAttempts(M.TOO_MANY)
        raw = (header or "").strip()
        if not raw:
            raise AuthError(M.NO_TOKEN)
        machine_id, _, token = raw.rpartition(".")
        m = self.machines.get_auth(machine_id) if machine_id and token else None
        ok = bool(m and m.get("enabled") and m.get("token_hash")
                  and hmac.compare_digest(token_hash(token), m["token_hash"]))
        if not ok:
            self.attempts.add_failure(ip)
            raise AuthError(M.BAD_TOKEN)
        return {"machine_id": m["machine_id"] or m["name"], "name": m["name"]}
