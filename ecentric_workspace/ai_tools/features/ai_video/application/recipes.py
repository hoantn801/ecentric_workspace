# Copyright (c) 2026, eCentric and contributors
"""Cong thuc prompt theo BRAND + DONG SAN PHAM (12/10/2026).

Moi brand co nhieu dong SP (vd FRISO · Lon sua bot, FRISO · Hop giay 180ml). Moi dong = 1 cong thuc: kieu cam,
tay do, kieu tay trong clip, ghi chu rieng cho anh cam / clip cam / clip ha, goi y khung, khoi luong.
- Dang thu: dung prompt chung moi nhat; SKU dau tien cua dong tu dung cho duyet (nhu nhom "dang thu").
- Da chot: worker KHOA ban prompt day du luc chot -> sua prompt chung sau nay khong doi dong da chot.
- Brand moi giong dong cu: Sao chep (ban sao o trang thai Dang thu, test lai roi chot).
Worker luu cong thuc + lich su; ERP chi kiem quyen va lam sach du lieu. SKU chon cong thuc o buoc 1."""

import frappe

from ecentric_workspace.ai_tools.features.ai_video.application import service as svc
from ecentric_workspace.ai_tools.features.ai_video.domain import flow
from ecentric_workspace.ai_tools.features.ai_video.infrastructure import worker_client as wc


def recipes_get():
    r = wc.call("recipes_get")
    brands = sorted({(b or "").strip() for b in frappe.get_all(svc.P, pluck="brand") if (b or "").strip()})
    return {"recipes": r.get("recipes") or {}, "history": r.get("history") or {}, "can_edit": svc.is_admin(),
            "brands": brands}


def _key(key):
    if not flow.recipe_key_ok(key):
        raise frappe.ValidationError("Mã công thức không hợp lệ.")
    return key


def recipes_set(data):
    svc.check_admin()
    d = svc._j(data)
    if not isinstance(d, dict) or not isinstance(d.get("data") or {}, dict):
        raise frappe.ValidationError("Dữ liệu công thức không hợp lệ.")
    try:
        clean = flow.clean_recipe(d.get("data") or {})
    except ValueError as e:
        raise frappe.ValidationError(str(e))
    args = {"data": clean, "by": frappe.session.user, "note": str(d.get("note") or "")[:200]}
    if d.get("key"):
        args["key"] = _key(d.get("key"))
    elif not clean.get("brand") or not clean.get("line"):
        raise frappe.ValidationError("Cần tên brand và tên dòng sản phẩm.")
    if d.get("relock"):
        args["relock"] = True
    return wc.call("recipes_set", **args)


def recipes_copy(data):
    svc.check_admin()
    d = svc._j(data)
    if not isinstance(d, dict):
        raise frappe.ValidationError("Dữ liệu sao chép không hợp lệ.")
    brand, line = str(d.get("brand") or "").strip()[:60], str(d.get("line") or "").strip()[:80]
    if not brand or not line:
        raise frappe.ValidationError("Cần brand và tên dòng sản phẩm mới.")
    return wc.call("recipes_copy", **{"from": _key(d.get("from")), "brand": brand, "line": line, "by": frappe.session.user})


def recipes_rollback(key, v):
    svc.check_admin()
    try:
        v = int(v)
    except (TypeError, ValueError):
        raise frappe.ValidationError("Phiên bản không hợp lệ.")
    return wc.call("recipes_rollback", key=_key(key), v=v, by=frappe.session.user)
