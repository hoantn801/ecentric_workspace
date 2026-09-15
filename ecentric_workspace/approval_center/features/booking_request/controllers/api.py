"""Stable compatibility API backed by the shared request application layer."""
import frappe
from frappe import _

from ecentric_workspace.approval_center.shared.api_adapter import bind
from ecentric_workspace.approval_center.features.booking_request.application import service

globals().update(bind("BOOKING_REQUEST"))

_DT = "EC Booking Request"


@frappe.whitelist(methods=["POST"])
def claim_booking(name, expected_date):
    """Nhan xu ly KEM ngay cam ket.

    Phai co endpoint rieng: `fulfillment_service.claim` dung chung goi `claim_fulfillment(name)`
    khong kem tham so nao, ma o day ngay cam ket la BAT BUOC ngay tai buoc nhan viec (giong
    Payment Request voi hai ngay UNC)."""
    return service.claim_fulfillment(name, expected_date=expected_date)


@frappe.whitelist()
def brand_owners(brand):
    """Nguoi phu trach cua mot brand, de form hien ra truoc khi gui.

    CHI tra hai email noi bo, khong tra gi khac cua brand. Yeu cau dang nhap (whitelist mac
    dinh da chan khach), va brand khong ton tai thi tra rong chu khong bao lo su ton tai."""
    booking, account = service.brand_owners(brand)
    return {"booking_owner": booking or "", "account_owner": account or ""}


@frappe.whitelist()
def booking_users(query=None):
    """Danh sach nguoi co the lam Booking phu trach - dung khi Account tao brand MOI.

    Nguon la Role EC Booking. Khong co role do / chua ai duoc gan thi tra RONG, va form se
    noi ro la chua cau hinh - khong tu dong do sang "moi nguoi trong cong ty", vi nhu vay
    Account se gan bua mot ai do va phieu di sai nguoi ngay tu dau."""
    users = frappe.get_all("Has Role", filters={"role": service.FULFILLER_ROLE,
                                                "parenttype": "User"},
                           fields=["parent"], distinct=True, limit_page_length=0)
    ten = {u.name: (u.full_name or u.name) for u in frappe.get_all(
        "User", filters={"name": ["in", [u.parent for u in users]] or [""], "enabled": 1},
        fields=["name", "full_name"], limit_page_length=0)}
    rows = [{"value": k, "label": v} for k, v in sorted(ten.items(), key=lambda x: x[1].lower())]
    if query:
        q = query.lower()
        rows = [r for r in rows if q in r["label"].lower() or q in r["value"].lower()]
    return {"rows": rows[:50], "role": service.FULFILLER_ROLE}


@frappe.whitelist(methods=["POST"])
def complete_fulfillment(name, payload=None):
    """Hoan tat buoc Booking. Vo mong quanh service - moi phep kiem (chu viec / trang thai /
    phai co ghi chu hoac tep) nam o service, khong chep lai o day."""
    return service.complete_fulfillment(name, payload=payload)
