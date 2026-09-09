# Copyright (c) 2026, eCentric and contributors
"""Tieu de that + so tien cua tung phieu, cho bang "Tat ca yeu cau" (09/09, Hoan).

Truoc do bang hub khong he lay tieu de: cot "Tieu de" hien approval_title cua LOAI phieu
("Payment Request") con cot "Loai" hien MA loai ("PAYMENT_REQUEST"). Nhin ca trang 15 dong
thi ca 15 dong giong het nhau, khong phan biet duoc phieu nao voi phieu nao.

`EC Approval Request` khong luu tieu de lan so tien - chung nam o DocType nghiep vu cua tung
form. Nen doc theo LO: gom theo reference_doctype roi mot truy van cho moi DocType (toi da
vai truy van cho mot trang 50 dong), thay vi mot truy van moi dong.

CHI DE HIEN THI. Khong doi du lieu, khong noi rong quyen: chi doc dung nhung phieu da nam
trong pham vi ma truy van hub tra ve (da qua scope_predicate).

So tien: chot voi Hoan 09/09 la lay SO DE NGHI BAN DAU, khong phai so thuc te sau duyet -
de mot phieu nhin trong danh sach khong doi so theo thoi gian, doi chieu moi de. Form nao
khong co tien thi de trong (dung bia so 0 - trong va 0 la hai chuyen khac nhau).
"""
#: DocType nghiep vu -> (truong so tien, truong tien te hoac None)
AMOUNT_FIELDS = {
    "EC Payment Request": ("payment_amount", None),
    "EC Purchase Request": ("payment_amount", None),
    "EC AI Topup Request": ("requested_amount", "currency"),
    "EC Contract Review Request": ("contract_value", None),
    "EC Affiliate Bonus Request": ("total_amount", None),
    "EC Special Bonus Request": ("total_bonus", None),
    "EC HR Activity Request": ("estimated_budget", None),
    "EC Asset Damage Loss Request": ("estimated_repair_cost", None),
    "EC Budget Setting Request": ("approved_budget_current_period", None),
    "EC Service Referral Request": ("estimated_contract_value", None),
}

TITLE_FIELD = "request_title"


def _group_by_doctype(views):
    by_dt = {}
    ref_of = {}
    for v in views:
        dt, ref = v.get("reference_doctype"), v.get("reference_name")
        if dt and ref:
            by_dt.setdefault(dt, []).append(ref)
            ref_of[(dt, ref)] = v["name"]
    return by_dt, ref_of


def fetch(views):
    """{request_name: {"title":..., "amount":..., "currency":...}} cho ca trang."""
    import frappe
    out = {}
    by_dt, ref_of = _group_by_doctype(views)
    for dt, refs in by_dt.items():
        try:
            meta = frappe.get_meta(dt)
            fields = ["name"]
            if meta.has_field(TITLE_FIELD):
                fields.append(TITLE_FIELD)
            amt_f, cur_f = AMOUNT_FIELDS.get(dt, (None, None))
            if amt_f and meta.has_field(amt_f):
                fields.append(amt_f)
            else:
                amt_f = None
            if cur_f and meta.has_field(cur_f):
                fields.append(cur_f)
            else:
                cur_f = None
            if len(fields) == 1:
                continue
            for row in frappe.get_all(dt, filters={"name": ["in", refs]}, fields=fields):
                key = ref_of.get((dt, row["name"]))
                if not key:
                    continue
                out[key] = {
                    "title": (row.get(TITLE_FIELD) or "") if TITLE_FIELD in fields else "",
                    "amount": row.get(amt_f) if amt_f else None,
                    "currency": (row.get(cur_f) or "") if cur_f else "",
                }
        except Exception:
            # Mot form loi khong duoc lam trang trang: bang van hien, chi thieu tieu de/so tien.
            frappe.log_error(frappe.get_traceback(), "business_summary %s" % dt)
    return out


def apply(views):
    """Gan title/amount/currency vao tung dong. Khong ghi de gia tri da co."""
    if not views:
        return
    data = fetch(views)
    for v in views:
        d = data.get(v["name"]) or {}
        v["title"] = d.get("title") or ""
        v["amount"] = d.get("amount")
        v["currency"] = d.get("currency") or ""
