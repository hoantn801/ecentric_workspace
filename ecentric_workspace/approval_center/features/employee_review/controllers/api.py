"""Stable API cho Danh gia nhan su (EMPLOYEE_REVIEW, 23/11/2026).

bind() cho phan chung (danh sach, chi tiet, huy, yeu cau bo sung, gui lai). Ghi de:
  * approve / reject       - cap 1/2 phai nop noi dung; khong co Tu choi (service);
  * clone_request          - danh gia sinh tu bang hop dong, khong chep phieu cu.
Them: nop_tu_danh_gia, nop_danh_gia_lm, tra_lai, xac_nhan_ho_so, nhan_nhap, huy_nhap, hang_cho,
tao_nhap. Moi phep kiem quyen nam o application/service.py - o day chi la vo mong."""
import frappe

from ecentric_workspace.approval_center.shared.api_adapter import bind
from ecentric_workspace.approval_center.shared.facade import APPROVAL_FACADE
from ecentric_workspace.approval_center.shared.registry import get_definition
from ecentric_workspace.approval_center.features.employee_review.application import service

globals().update(bind("EMPLOYEE_REVIEW"))

_DEF = get_definition("EMPLOYEE_REVIEW")
_caps = APPROVAL_FACADE.capabilities


def _detail(name):
    return APPROVAL_FACADE.detail(_DEF, name)


def _capabilities(user, biz, req):  # noqa: F811 - duyet nhanh doc ham nay: khong co Tu choi
    caps = dict(_caps.derive(user, biz, req) or {})
    caps["can_reject"] = False
    return caps


@frappe.whitelist(methods=["POST"])
def approve(name, comment=None):  # noqa: F811 - ghi de ban chung cua bind()
    service.approve(name, comment=comment)
    return {"detail": _detail(name)}


@frappe.whitelist(methods=["POST"])
def reject(name, comment=None):  # noqa: F811
    return service.reject(name, comment=comment)


@frappe.whitelist(methods=["POST"])
def clone_request(name):  # noqa: F811
    frappe.throw(frappe._("Phiếu đánh giá được tạo từ bảng hợp đồng trên hồ sơ - không tạo lại từ phiếu cũ."))


@frappe.whitelist(methods=["POST"])
def nop_tu_danh_gia(name, payload=None):
    service.nop_tu_danh_gia(name, payload)
    return {"detail": _detail(name)}


@frappe.whitelist(methods=["POST"])
def nop_danh_gia_lm(name, payload=None):
    res = service.nop_danh_gia_lm(name, payload)
    res["detail"] = _detail(name)
    return res


@frappe.whitelist(methods=["POST"])
def tra_lai(name, ly_do=None):
    res = service.tra_lai(name, ly_do)
    res["detail"] = _detail(name)
    return res


@frappe.whitelist(methods=["POST"])
def xac_nhan_ho_so(name, payload=None):
    res = service.xac_nhan_ho_so(name, payload)
    res["detail"] = _detail(name)
    return res


@frappe.whitelist(methods=["POST"])
def nhan_nhap(name):
    return service.nhan_nhap(name)


@frappe.whitelist(methods=["POST"])
def huy_nhap(name, ly_do=None):
    return service.huy_nhap(name, ly_do)


@frappe.whitelist()
def hang_cho():
    return service.hang_cho()


@frappe.whitelist(methods=["POST"])
def tao_nhap(nhan_vien):
    return service.tao_nhap_tay(nhan_vien)
