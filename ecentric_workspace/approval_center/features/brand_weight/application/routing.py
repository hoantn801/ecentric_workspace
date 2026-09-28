# Copyright (c) 2026, eCentric and contributors
"""Quyet dinh cap nao duoc bo cho RIENG mot phieu ty trong luong.

Luong chot voi Hoan 25/09: buoc 1 lead truc tiep, buoc 2 truong phong cua phong do.
Moi phong deu phai nop, ke ca Management.

Hai luat bo cap, va mot luat KHONG bo:

1. KHONG CO LEAD -> bo buoc 1. CEO khong co `reports_to`; neu giu buoc 1 thi phieu
   cua ong treo vinh vien khong ai bam duoc. Cung ap cho truong hop lead trung voi
   chinh nguoi nop.
2. NGUOI NOP CHINH LA TRUONG PHONG -> bo buoc 2 (Hoan chon cho tu duyet).
3. KHONG BAO GIO bo ca hai. Engine nem loi khi process khong con cap nao, va quan
   trong hon: mot phieu khong qua bat ky mat nguoi nao thi khong con la phieu duyet.
   Truong hop nay (vua khong co lead vua la truong phong - hien chi CEO) giu lai
   buoc 2 de chinh nguoi do bam xac nhan. Mot cu click, co dau vet trong audit.

Vi sao nem loi khi phong chua co truong phong, thay vi de phieu chay: `Department
Manager` resolve qua `Department.manager_email` (field `department_head` KHONG ton tai
tren site nay - duong resolve thu nhat chet lang). Khong co email -> khong ai duyet ->
phieu treo im. Don nghi cuoi cua phuong.nguyen treo hai tuan dung vi kieu loi nay, nen
o day chan ngay luc nop."""
from frappe import _

import frappe

from ecentric_workspace.approval_center.shared.workflow.transitions import (
    resolve_department_manager_user,
)
from ecentric_workspace.approval_center.features.brand_weight.infrastructure import (
    employee_reader,
)

LEVEL_LEAD = 1
LEVEL_DEPT_HEAD = 2

# Chot voi Hoan 26/09: 8 nguoi phong nay (ban lanh dao) TU DIEN VA TU CHOT phieu cua
# minh, khong qua duyet - "dung de anh Lam duyet". Hai truong phong nam NGOAI phong nay
# (Merchandise, Service) van di luong thuong: lead cua ho duyet, cap truong phong tu bo.
# Doi ten phong tren Department thi phai doi o day, neu khong nhom nay se quay ve luong
# thuong va phieu cua ho lai nam cho anh Lam.
MANAGEMENT_DEPT = "Management - EC"


def is_self_final(department):
    """Nguoi nop thuoc phong Management -> phieu tu chot, khong co nguoi duyet nao khac."""
    return (department or "").strip() == MANAGEMENT_DEPT


class ResolveBrandWeightSkipLevelsService:
    def __init__(self, reader=employee_reader, head_resolver=resolve_department_manager_user):
        self.reader = reader
        self.head_resolver = head_resolver

    def execute(self, employee, department, requester_user):
        head = self.head_resolver(department)
        if not head:
            frappe.throw(_(
                "Phòng {0} chưa có trưởng phòng nên không ai duyệt được bước 2. "
                "Nhờ HR điền người phụ trách cho phòng này trước khi nộp."
            ).format(department or "(trống)"))

        lead = self.reader.lead_user(employee)
        skip, reasons = [], []
        if not lead or lead == requester_user:
            skip.append(LEVEL_LEAD)
            reasons.append("khong co quan ly truc tiep dung duoc" if not lead
                           else "quan ly truc tiep trung voi nguoi nop")
        if head == requester_user:
            skip.append(LEVEL_DEPT_HEAD)
            reasons.append("nguoi nop chinh la truong phong")

        if len(skip) == 2:
            skip = [LEVEL_LEAD]
            reasons.append("giu lai buoc truong phong de nguoi nop tu xac nhan, "
                           "khong bo ca hai cap")
        return skip, "; ".join(reasons)
