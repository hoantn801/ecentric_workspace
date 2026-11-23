# Copyright (c) 2026, eCentric and contributors
"""Doc thong tin xac thuc tu request: token may (header X-HostQC-Token), IP, role nguoi dang nhap, tep tai len."""
import frappe

from ecentric_workspace.host_qc.constants import messages as M
from ecentric_workspace.host_qc.exceptions import AuthError, ForbiddenError, InvalidInput
from ecentric_workspace.host_qc.services.verify_machine_token_service import VerifyMachineTokenService

TOKEN_HEADER = "X-HostQC-Token"


def machine(claimed_id=None):
    """May goi API. claimed_id (machine_id trong than) neu co phai khop may cua token."""
    m = VerifyMachineTokenService().execute(frappe.get_request_header(TOKEN_HEADER), frappe.local.request_ip)
    if claimed_id and str(claimed_id) != m["machine_id"]:
        raise ForbiddenError(M.WRONG_MACHINE)
    return m


def user_roles():
    if frappe.session.user == "Guest":
        raise AuthError(M.LOGIN)
    return frappe.get_roles(frappe.session.user)


def obj(value):
    """Than multipart / query: dict, list gui duoi dang chuoi JSON."""
    if isinstance(value, str) and value[:1] in ("{", "["):
        try:
            return frappe.parse_json(value)
        except ValueError:
            raise InvalidInput(M.BAD_JSON)
    return value


def upload(field, limit):
    """Tep multipart -> {content, content_type, filename}; doc toi limit+1 byte de service chan qua co."""
    f = (frappe.request.files or {}).get(field) if frappe.request else None
    if not f:
        return None
    return {"content": f.stream.read(limit + 1), "content_type": f.mimetype or "", "filename": f.filename or ""}
