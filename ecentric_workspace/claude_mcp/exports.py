# Copyright (c) 2026, eCentric and contributors
"""Xuất dữ liệu cho Claude (kế toán / quản lý): phiếu Approval Center, tình trạng thanh toán, PnL.

Không truy vấn mới, không quyền mới - mỗi bộ dữ liệu đi qua ĐÚNG đường mà màn hình đang dùng:
  * Phiếu: tab "Tất cả" của từng form (approval_center/shared/requests/all_list.py):
    reporting.scope (4 bậc quyền) + ghim approval_type + TRẦN EXPORT_MAX + GHI VẾT mỗi lượt xuất.
    Cột giống hệt tệp xuất trên web (không có số tài khoản ngân hàng - cố ý, xem docstring all_list).
  * Tình trạng thanh toán: tập phiếu ĐỀ NGHỊ THANH TOÁN người đó xem được (như trên), đọc thêm các
    trường xử lý UNC của chính những phiếu đó.
  * PnL: chạy đúng Server Script API (`ec_pnl_data`, `ec_pnl_chi_phi`) - quyền, luật K_MIN chống suy
    lương cá nhân, phạm vi phòng ban nằm trong script; ở đây không đụng.

Kết quả: một phần dòng ngay trong câu trả lời (để Claude đổi sang mẫu người dùng đưa) + LINK TỆP
XLSX đầy đủ (File riêng tư của chính người xuất - người khác không mở được).
"""
import json

import frappe
from frappe.utils import get_url, now_datetime

from ecentric_workspace.claude_mcp.protocol import ToolError

INLINE_MAX = 300
PNL_TEXT_CAP = 60000


def _save_private_file(filename, content):
    doc = frappe.get_doc({"doctype": "File", "file_name": filename, "is_private": 1, "content": content})
    doc.insert(ignore_permissions=True)
    return get_url(doc.file_url)


def _filters(date_from, date_to, status, department, requester, extra):
    f = {}
    if date_from and date_to:
        f["date_from"], f["date_to"] = str(date_from)[:10], str(date_to)[:10]
    elif date_from or date_to:
        raise ToolError("Cần cả date_from và date_to (YYYY-MM-DD), hoặc bỏ cả hai.")
    for k, v in (("status", status), ("department", department), ("requester", requester)):
        if v not in (None, "", []):
            f[k] = v
    if isinstance(extra, dict):
        for k, v in extra.items():
            if k not in f and v not in (None, ""):
                f[k] = v
    return f


def _rows_in_scope(definition, filters, search):
    from ecentric_workspace.approval_center.shared.requests import all_list as al
    scope = al._scope.resolve_scope(frappe.session.user)
    f = al._pinned_filters(definition, filters, search or None)
    total = al._q.count_requests(scope, f, search or None)
    if total > al.EXPORT_MAX:
        raise ToolError("Bộ lọc khớp %s phiếu, vượt mức %s cho một lần xuất. Thu hẹp khoảng ngày hoặc thêm bộ lọc."
                        % (total, al.EXPORT_MAX))
    out = al._service.list_requests(scope, f, start=0, page_length=al.EXPORT_MAX, search=search or None)
    rows = al._viet_hoa(out.get("rows") or [])
    return al, scope, f, rows


def export_requests(code, date_from=None, date_to=None, status=None, department=None, requester=None,
                    search=None, extra_filters=None, offset=0, limit=100, make_file=True):
    from ecentric_workspace.claude_mcp.approvals import _definition
    definition = _definition(code)
    filters = _filters(date_from, date_to, status, department, requester, extra_filters)
    al, scope, f, rows = _rows_in_scope(definition, filters, search)
    cot = al._cot_hien(definition, frappe.get_meta(definition.business_doctype))
    al._gan_cot_them(definition, rows, cot)
    headers = [lab for _k, lab in al._COT] + [n for n, _fn, _k in cot]
    table = [al._o_xuat(v, cot) for v in rows]
    al._ghi_vet(definition, scope, f, search or None, len(rows), "claude")
    out = {"form": definition.code, "filters": filters, "total": len(rows), "headers": headers}
    off = max(0, int(offset or 0))
    n = max(1, min(int(limit or 100), INLINE_MAX))
    out["rows"] = [dict(zip(headers, r)) for r in table[off:off + n]]
    out["rows_shown"] = "%s-%s / %s" % (off + 1 if table else 0, min(off + n, len(table)), len(table))
    if make_file and table:
        name = "%s_%s.xlsx" % (definition.code.lower(), now_datetime().strftime("%Y%m%d_%H%M%S"))
        out["download_xlsx"] = _save_private_file(name, al._xlsx([headers] + table, definition.code))
    out["note"] = ("Chỉ gồm phiếu bạn được xem. Cần đúng mẫu riêng: dùng rows (gọi lại với offset để lấy tiếp) "
                   "hoặc tệp download_xlsx để dựng lại theo mẫu.")
    return out


_PAY_FIELDS = ("name", "request_title", "payee_full_name", "payment_amount", "payment_date", "payment_mode",
               "installment_no", "installment_of", "fulfillment_status", "fulfillment_payment_date",
               "fulfillment_unc_date", "fulfillment_due_at", "ec_brand", "ec_loai_chi_phi", "ec_ky_chi_phi",
               "ec_vat_pct", "department")
_PAY_VI = {"name": "Ma phieu", "request_title": "Tieu de", "payee_full_name": "Nguoi nhan",
           "payment_amount": "So tien", "payment_date": "Ngay de nghi TT", "payment_mode": "Hinh thuc",
           "installment_no": "Dot", "installment_of": "Tong so dot", "fulfillment_status": "Trang thai chi",
           "fulfillment_payment_date": "Ngay chi (cam ket)", "fulfillment_unc_date": "Ngay UNC",
           "fulfillment_due_at": "Han xu ly", "ec_brand": "Brand", "ec_loai_chi_phi": "Loai chi phi",
           "ec_ky_chi_phi": "Ky chi phi", "ec_vat_pct": "VAT %", "department": "Phong ban"}


def payment_status(date_from=None, date_to=None, approval_status=None, paid=None, offset=0, limit=100,
                   make_file=True):
    """paid: None = tất cả, True = đã chi xong (Completed), False = chưa chi xong."""
    from ecentric_workspace.claude_mcp.approvals import _definition
    definition = _definition("PAYMENT_REQUEST")
    filters = _filters(date_from, date_to, approval_status, None, None, None)
    al, scope, f, rows = _rows_in_scope(definition, filters, None)
    by_ref = {r.get("reference_name"): r for r in rows if r.get("reference_doctype") == definition.business_doctype}
    meta = frappe.get_meta(definition.business_doctype)
    fields = [x for x in _PAY_FIELDS if x == "name" or meta.has_field(x)]
    data = frappe.get_all(definition.business_doctype, filters={"name": ["in", list(by_ref) or [""]]},
                          fields=fields, order_by="payment_date desc", limit_page_length=0) if by_ref else []
    if paid is not None and "fulfillment_status" in fields:
        data = [d for d in data if (d.get("fulfillment_status") == "Completed") == bool(paid)]
    headers = [_PAY_VI.get(x, x) for x in fields] + ["Trang thai duyet"]
    table = []
    for d in data:
        table.append([str(d.get(x)) if x.endswith(("_date", "_at")) and d.get(x) else d.get(x) for x in fields]
                     + [(by_ref.get(d["name"]) or {}).get("status_label")])
    al._ghi_vet(definition, scope, f, None, len(table), "claude_payment_status")
    off = max(0, int(offset or 0))
    n = max(1, min(int(limit or 100), INLINE_MAX))
    out = {"filters": filters, "paid": paid, "total": len(table), "headers": headers,
           "rows": [dict(zip(headers, r)) for r in table[off:off + n]],
           "rows_shown": "%s-%s / %s" % (off + 1 if table else 0, min(off + n, len(table)), len(table)),
           "total_amount": sum(float(d.get("payment_amount") or 0) for d in data)}
    if make_file and table:
        name = "tinh_trang_thanh_toan_%s.xlsx" % now_datetime().strftime("%Y%m%d_%H%M%S")
        out["download_xlsx"] = _save_private_file(name, al._xlsx([headers] + table, "Thanh toan"))
    return out


_PNL_SCRIPTS = {"revenue_pnl": "ec_pnl_data", "costs": "ec_pnl_chi_phi"}


def pnl_data(dataset="costs", date_from=None, date_to=None, brands=None):
    """Chạy Server Script API của Dashboard PnL dưới quyền người gọi; trả JSON của nó."""
    method = _PNL_SCRIPTS.get(dataset)
    if not method:
        raise ToolError("dataset phải là: " + ", ".join(_PNL_SCRIPTS))
    script = frappe.db.get_value("Server Script", {"api_method": method, "script_type": "API", "disabled": 0}, "name")
    if not script:
        raise ToolError("Dữ liệu PnL '%s' chưa bật trên site này." % dataset)
    args = {}
    if date_from:
        args["date_from"] = str(date_from)[:10]
    if date_to:
        args["date_to"] = str(date_to)[:10]
    if brands:
        args["action"] = "scenario"
        args["brands"] = ",".join(brands) if isinstance(brands, (list, tuple)) else str(brands)
    old_fd, old_msg = frappe.local.form_dict, frappe.response.get("message")
    try:
        frappe.local.form_dict = frappe._dict(args)          # KHÔNG bao giờ truyền debug_as_user
        frappe.response.pop("message", None)
        frappe.get_doc("Server Script", script).execute_method()
        res = frappe.response.get("message")
    finally:
        frappe.local.form_dict = old_fd
        if old_msg is None:
            frappe.response.pop("message", None)
        else:
            frappe.response["message"] = old_msg
    if isinstance(res, dict) and res.get("error"):
        raise ToolError("PnL từ chối: %s" % res.get("error"))
    text = json.dumps(res, ensure_ascii=False, default=str)
    if len(text) > PNL_TEXT_CAP:
        return {"dataset": dataset, "truncated": True, "size_chars": len(text),
                "data_preview": text[:PNL_TEXT_CAP],
                "note": "Dữ liệu lớn, đã cắt. Thu hẹp khoảng tháng (date_from/date_to) để lấy đủ."}
    return {"dataset": dataset, "filters": args, "data": res}
