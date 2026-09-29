# Copyright (c) 2026, eCentric and contributors
"""API cua trang Tong quan (/tong-quan). Moi ham: chan quyen -> goi service -> boc envelope.

  GET ecentric_workspace.hr.overview.api.get_cards        - the nao nguoi xem duoc thay
  GET ecentric_workspace.hr.overview.api.get_hr_overview  - du lieu 3 tab cua the Nhan su
  GET ecentric_workspace.hr.overview.api.get_hr_profile   - ho so 1 nguoi (khung ben phai)

Quyen: the Nhan su chi mo cho HR_CARD_ROLES. Trong the, truong nao tra ve do permlevel
cua Employee quyet dinh (L0 danh ba / L2 noi bo HR / L1 ca nhan) - xem repository.
Khong endpoint nao tra ve so luong. Nguoi dung duoc lay tu session, client khong truyen."""
import frappe
from frappe.utils import nowdate

from ecentric_workspace.hr.overview import constants as C
from ecentric_workspace.hr.overview import repository as repo
from ecentric_workspace.hr.overview.profile_service import GetHrProfileService
from ecentric_workspace.hr.overview.service import BuildHrOverviewService


def _ok(data):
    return {"success": True, "message": "", "data": data}


def _fail(message):
    return {"success": False, "message": message, "data": None}


def _guard():
    user = frappe.session.user
    if not user or user == "Guest":
        frappe.response["http_status_code"] = 401
        raise frappe.PermissionError(C.MSG_FORBIDDEN)
    if not (repo.user_roles(user) & set(C.HR_CARD_ROLES)):
        raise frappe.PermissionError(C.MSG_FORBIDDEN)


def _run(fn):
    try:
        return _ok(fn())
    except frappe.PermissionError:
        return _fail(C.MSG_FORBIDDEN)
    except Exception:
        frappe.log_error(title="hr overview api")
        return _fail(C.MSG_UNKNOWN)


def _access():
    """-> (tap truong duoc doc, tap 'muc' cho service). Muc 1 = co truong ca nhan, muc 2 =
    doc duoc bang hop dong. Truong nao khong doc duoc (khac permlevel hoac bi mask) thi
    KHONG duoc lay tu DB - service chi kiem nhung truong co mat."""
    readable, children = repo.readable_fields()
    fields = tuple(f for f in C.L0_FIELDS + C.L2_FIELDS + C.L1_FIELDS if f == "name" or f in readable)
    levels = {0}
    if any(f in readable for f in C.L1_FIELDS):
        levels.add(1)
    if "ec_contracts" in children and {"loai_hop_dong", "tu_ngay", "den_ngay"} <= children["ec_contracts"]:
        levels.add(2)
    return fields, levels


@frappe.whitelist(methods=["GET"])
def get_cards():
    user = frappe.session.user
    if not user or user == "Guest":
        frappe.response["http_status_code"] = 401
        return _fail(C.MSG_FORBIDDEN)
    return _ok({"cards": [{"key": "nhan-su", "label": "Nhân sự",
                           "enabled": bool(repo.user_roles(user) & set(C.HR_CARD_ROLES))}]})


@frappe.whitelist(methods=["GET"])
def get_hr_overview():
    def build():
        _guard()
        fields, levels = _access()
        emps = repo.employees(fields)
        cons = repo.contracts() if 2 in levels else []
        data = BuildHrOverviewService().execute(emps, cons, repo.departments(),
                                                repo.management_memberships(), levels, nowdate())
        data["links"] = {"salary": repo.can_read(C.SSA), "slips": repo.can_read(C.SALARY_SLIP)}
        return data
    return _run(build)


@frappe.whitelist(methods=["GET"])
def get_hr_profile(employee: str):
    def build():
        _guard()
        fields, levels = _access()
        emp = repo.employee(str(employee), fields)
        if not emp:
            raise frappe.DoesNotExistError
        mgr = repo.employee(emp.get("reports_to"), ("name", "employee_name")) if emp.get("reports_to") else None
        cons = repo.contracts([emp["name"]]) if 2 in levels else []
        return GetHrProfileService().execute(emp, cons, levels, (mgr or {}).get("employee_name") or "")
    return _run(build)
