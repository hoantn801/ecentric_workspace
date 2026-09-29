# Copyright (c) 2026, eCentric and contributors
"""Tin noi bo (News Post) len popup "Hom nay o eCentric" - PO Hoan chot 29/09/2026.

Them vao News Post:
  * ec_show_in_popup  (Check) "Dua len popup trang chu"
  * ec_popup_until    (Date)  "Hien tren popup den ngay" - de trong = 7 ngay tu ngay dang
  * lua chon "MODULE MỚI" cho truong category (nhan xanh "Module moi" tren popup)

News Post / Company Policy la DocType cua SITE (tao tu thoi dashboard 05/2026, khong co trong
repo). Patch nay KHONG tao chung neu chua co - popup van chay, chi khong co o Thong bao.
  * DocType custom (tao tren Desk) -> them DocField thang vao DocType (Custom Field khong ap
    cho DocType custom);
  * DocType chuan cua mot app -> Custom Field.
Idempotent: truong da co thi bo qua. Loi -> Error Log, KHONG chan ca dot deploy.
"""
import frappe

DT = "News Post"
MODULE_OPTION = "MODULE MỚI"
FIELDS = [
    {"fieldname": "ec_popup_section", "fieldtype": "Section Break", "label": "Popup trang chủ"},
    {"fieldname": "ec_show_in_popup", "fieldtype": "Check", "label": "Đưa lên popup trang chủ",
     "description": "Tích để tin hiện ở ô Thông báo của popup Hôm nay ở eCentric."},
    {"fieldname": "ec_popup_until", "fieldtype": "Date", "label": "Hiện trên popup đến ngày",
     "depends_on": "eval:doc.ec_show_in_popup",
     "description": "Để trống = hiện 7 ngày kể từ ngày đăng."},
]


def _add_option(field):
    opts = [o for o in (field.options or "").split("\n")]
    if MODULE_OPTION in opts:
        return False
    field.options = "\n".join([o for o in opts if o] + [MODULE_OPTION])
    return True


def execute():
    try:
        if not frappe.db.exists("DocType", DT):
            frappe.log_error("home_today p001: site chua co DocType %s - bo qua" % DT, "home_today p001 skip")
            return
        dt = frappe.get_doc("DocType", DT)
        have = {f.fieldname for f in dt.fields}
        if dt.custom:
            changed = False
            for f in FIELDS:
                if f["fieldname"] not in have:
                    dt.append("fields", dict(f))
                    changed = True
            cat = next((f for f in dt.fields if f.fieldname == "category" and f.fieldtype == "Select"), None)
            if cat is not None and _add_option(cat):
                changed = True
            if changed:
                dt.save(ignore_permissions=True)
        else:
            from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
            prev = "content" if "content" in have else None
            todo = []
            for f in FIELDS:
                if f["fieldname"] in have or frappe.db.exists("Custom Field", {"dt": DT, "fieldname": f["fieldname"]}):
                    continue
                row = dict(f)
                if prev:
                    row["insert_after"] = prev
                prev = f["fieldname"]
                todo.append(row)
            if todo:
                create_custom_fields({DT: todo}, update=True)
        frappe.clear_cache(doctype=DT)
        meta = frappe.get_meta(DT)
        miss = [f["fieldname"] for f in FIELDS if not meta.has_field(f["fieldname"])]
        if miss:
            frappe.log_error("home_today p001: van thieu %s" % miss, "home_today p001 KHONG toi noi")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "home_today p001 failed")
