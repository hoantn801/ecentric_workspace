"""Stable compatibility API backed by the shared request application layer."""
import json

import frappe

from ecentric_workspace.approval_center.shared.api_adapter import bind
from ecentric_workspace.approval_center.shared.workflow.permissions import can_view_request

globals().update(bind("CONTRACT_REVIEW"))

_DT = "EC Contract Review Request"
_CODE = "CONTRACT_REVIEW"
_FILL_FIELDS = ["name", "request_title", "contract_type", "request_type", "brand",
                "justification", "contract_value", "contract_start_date",
                "contract_end_date", "request_details"]


@frappe.whitelist()
def search_previous_contracts(query=None):
    """Hợp đồng đã DUYỆT XONG của chính người dùng (hoặc mọi người nếu là SM) để chọn làm
    gốc điều chỉnh. Chỉ trả bản đã Approved — điều chỉnh một bản đang chờ duyệt là vô nghĩa."""
    user = frappe.session.user
    filters = [["approval_request", "is", "set"]]
    if "System Manager" not in frappe.get_roles(user):
        filters.append(["requested_by", "=", user])
    if query:
        filters.append(["request_title", "like", "%%%s%%" % query])
    rows = frappe.get_all(_DT, filters=filters,
                          fields=["name", "request_title", "brand", "contract_value",
                                  "approval_request"],
                          order_by="modified desc", limit_page_length=100)
    req_names = [r.approval_request for r in rows if r.approval_request]
    approved = set()
    if req_names:
        approved = {r.name for r in frappe.get_all(
            "EC Approval Request",
            filters={"name": ["in", req_names], "approval_status": "Approved"},
            fields=["name"])}
    out = [r for r in rows if r.approval_request in approved][:20]
    return {"rows": [{"value": r.name,
                      "label": "%s — %s (%s)" % (r.name, r.request_title or "", r.brand or "")}
                     for r in out]}


@frappe.whitelist()
def get_previous_contract(name):
    """Dữ liệu hợp đồng gốc để tự điền + đối chiếu highlight phía form.

    PHẢI kiểm quyền THỦ CÔNG. frappe.db.get_value bỏ qua toàn bộ permission, mà mã hồ sơ
    chạy TUẦN TỰ (EC-CTR-2026-00001, 00002...) — không kiểm thì bất kỳ nhân viên nào đã
    đăng nhập cũng đổi số trên URL để đọc hết giá trị + điều khoản hợp đồng của mọi phòng.
    Đúng lớp lỗi đã siết cho Đề nghị thanh toán 01/09 (xem chú thích dài trong
    workflow/permissions.py). Dùng hàm kiểm quyền CHUẨN của engine, không tự chế luật thứ hai."""
    row = frappe.db.get_value(
        _DT, name, _FILL_FIELDS + ["requested_by", "approval_request"], as_dict=True)
    if not row:
        frappe.throw(frappe._("Không tìm thấy hợp đồng gốc."))
    if not can_view_request(row.get("approval_request"), business_doctype=_DT,
                            requested_by=row.get("requested_by"),
                            approval_type=_CODE, business_name=name):
        frappe.throw(frappe._("Bạn không có quyền xem hợp đồng này."), frappe.PermissionError)
    # Hai trường này chỉ dùng để kiểm quyền, không đưa ra ngoài.
    row.pop("requested_by", None)
    row.pop("approval_request", None)
    return row


# --------------------------------------------------------------------------- #
# Dua dinh kem len SharePoint de review online (14/09)
# --------------------------------------------------------------------------- #
@frappe.whitelist()
def thu_sharepoint(name=None, apply=0):
    """Endpoint DO, danh cho System Manager chay tay truoc khi bat tinh nang.

    Vi sao co ham nay: sandbox cua Claude KHONG goi duoc Microsoft Graph, nen toan bo phan
    Graph duoc viet ma CHUA chay thu lan nao. Thay vi noi vao luong gui roi hy vong, ta do
    truoc tren tenant that: `apply=0` chi kiem nhung thu doc duoc (token, duong dan, danh sach
    nguoi se duoc cap quyen) va KHONG ghi gi len SharePoint; `apply=1` moi thuc su tai mot tep.

    Tra ve tung buoc mot, buoc nao hong thi thay ngay buoc do chu khong phai mot chu "loi".
    """
    from ecentric_workspace.approval_center.features.contract_review.infrastructure import (
        sharepoint_sync as sp)

    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(frappe._("Chi System Manager duoc chay phep do nay."), frappe.PermissionError)

    ghi = int(apply or 0) == 1
    bao = {"che_do": "ghi that" if ghi else "chi doc", "buoc": []}

    def buoc(ten, ok, chi_tiet=""):
        bao["buoc"].append({"buoc": ten, "ok": bool(ok), "chi_tiet": str(chi_tiet)[:400]})
        return ok

    try:
        token = sp.wr_sp.get_app_token()
        buoc("lay token app-only", bool(token), "do dai=%d" % len(token or ""))
    except Exception as e:
        buoc("lay token app-only", False, e)
        return bao

    if not name:
        buoc("chon phieu", False, "truyen ?name=EC-CTR-...")
        return bao

    row = frappe.db.get_value(_DT, name, ["name", "requested_by", "approval_request"], as_dict=True)
    if not buoc("doc phieu", bool(row), name):
        return bao

    tep = frappe.get_all("File", filters={"attached_to_doctype": _DT, "attached_to_name": name},
                         fields=["file_name", "file_url"], order_by="creation asc")
    if not buoc("co dinh kem", bool(tep), "%d tep" % len(tep)):
        return bao

    nguoi = nguoi_duoc_xem(name, row)
    buoc("danh sach nguoi se duoc cap quyen", bool(nguoi), ", ".join(nguoi))

    t = tep[0]
    bao["tep_thu"] = t.file_name
    bao["duong_dan_se_dung"] = sp.duong_dan(name, t.file_name)
    if not ghi:
        buoc("DUNG o day (apply=0)", True, "them ?apply=1 de thuc su tai len")
        return bao

    try:
        kq = sp.tai_len(t.file_url, t.file_name, name, token=token)
        buoc("tai len SharePoint", bool(kq.get("item_id")), kq.get("web_url"))
    except Exception as e:
        buoc("tai len SharePoint", False, e)
        return bao
    try:
        da = sp.cap_quyen(kq["item_id"], nguoi, token=token)
        buoc("cap quyen sua cho dung nguoi", True, ", ".join(da))
    except Exception as e:
        buoc("cap quyen sua cho dung nguoi", False, e)
    try:
        sp.ghi_lien_ket(t.file_url, name, kq, nguoi)
        buoc("luu lien ket trong ERP", True, kq.get("web_url"))
    except Exception as e:
        buoc("luu lien ket trong ERP", False, e)
    bao["web_url"] = kq.get("web_url")
    return bao


def nguoi_duoc_xem(name, row=None):
    """Nguoi gui + cac cap duyet cua phieu + CC. KHONG mo cho ca cong ty.

    Doc tu `EC Approval Request Approver` - dung bang ma engine that su dung de quyet dinh ai
    duoc duyet, khong tu dung mot danh sach thu hai."""
    row = row or frappe.db.get_value(_DT, name, ["requested_by", "approval_request", "cc_to"],
                                     as_dict=True) or {}
    ra = [row.get("requested_by")]
    if row.get("approval_request"):
        ra += frappe.get_all("EC Approval Request Approver",
                             filters={"approval_request": row["approval_request"]},
                             pluck="approver")
    for e in (frappe.db.get_value(_DT, name, "cc_to") or "").replace(";", ",").split(","):
        e = e.strip()
        if e:
            ra.append(e)
    return [e for e in dict.fromkeys(ra) if e and "@" in e]
