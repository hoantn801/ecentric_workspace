# Copyright (c) 2026, eCentric and contributors
"""Ai duoc xem / lam gi trong module tai san - kiem O SERVER (trang chi an nut, khong phai bien gioi).

  * Nhan vien: may minh dang giu (Tai san cua toi), xac nhan da nhan, bao hong.
  * Truong phong (Department.manager_email): thiet bi cua phong minh, KHONG thay gia.
  * EC Asset Manager / System Manager: toan bo, ke ca gia; moi thao tac van hanh.
  * EC HOF / EC Finance / EC CEO: xem toan bo + gia; HOF / Finance duoc thanh ly (ghi giam).
"""
from ecentric_workspace.tai_san import constants as C


class Ctx:
    def __init__(self, user, roles, employee=None, managed_departments=None):
        self.user = user
        self.roles = set(roles or [])
        self.employee = employee            # dict {name, employee_name, department} hoac None
        self.managed_departments = list(managed_departments or [])

    @property
    def employee_id(self):
        return self.employee.get("name") if self.employee else None

    @property
    def can_manage(self):
        return bool(self.roles & set(C.MANAGER_ROLES))

    @property
    def can_see_cost(self):
        return bool(self.roles & set(C.COST_ROLES))

    @property
    def can_finance(self):
        return bool(self.roles & set(C.FINANCE_ROLES))

    @property
    def can_overview(self):
        return self.can_see_cost or bool(self.managed_departments)

    def department_scope(self):
        """None = thay moi phong; list = chi cac phong nay."""
        if self.can_see_cost:
            return None
        return self.managed_departments

    def can_view_asset(self, asset):
        if self.can_see_cost:
            return True
        if self.employee_id and asset.get("custodian") == self.employee_id:
            return True
        return bool(asset.get("department")) and asset.get("department") in self.managed_departments

    def flags(self):
        return {"manage": self.can_manage, "see_cost": self.can_see_cost,
                "finance": self.can_finance, "overview": self.can_overview,
                "employee": self.employee_id}


class AccessDenied(Exception):
    pass


def require(ok, message="Bạn không có quyền thực hiện thao tác này."):
    if not ok:
        raise AccessDenied(message)
