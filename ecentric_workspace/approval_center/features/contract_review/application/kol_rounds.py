# Copyright (c) 2026, eCentric and contributors
"""Kho du lieu cac dot nghiem thu (BBNT) cua hop dong KOL/KOC - doctype `EC KOL Acceptance`
(PO chot 24/11/2026: moi dot la mot phieu Approval Center rieng, duyet KTTH -> KTT -> CEO).

Noi DUY NHAT doc / ghi `EC KOL Acceptance`. Truoc 24/11 dot la dong con `acceptances` cua phieu
hop dong; p520 chep sang day (bang con giu lam lich su, an tren form, code khong doc nua).

`rows(business)` tra ban XEM (View, sap theo so dot) - co `idx` = `round_no` de cac ham
domain cu (kol_values: dot cuoi, dot phu het hop dong) doc nhu dong con. Ghi thi lay Document qua
`get()` / `create()` va luu qua `save()` / `delete()` (bat co cho controller).
"""
from contextlib import contextmanager

import frappe
from frappe import _
from frappe.utils import flt

DT = "EC KOL Acceptance"
APPROVAL_TYPE = "KOL_ACCEPTANCE"
#: Khop ec_kol_acceptance.FLAG (controller chan moi lan ghi khong qua kho nay).
FLAG = "ec_kol_round_write"
#: Yeu cau duyet da dong ma khong duyet: dot khong con tinh vao so tien da len ke hoach.
CLOSED_APPROVAL = ("Rejected", "Cancelled")
FIELDS = ("name", "contract", "round_no", "description", "acceptance_date", "amount", "status",
          "bbnt_file", "signed_file", "completed_at", "completed_by", "due_date", "check_note",
          "verified_by", "approval_request", "requested_by", "sign_pdf", "legacy_row")
_CACHE_ATTR = "_ec_kol_rounds"


class View(dict):
    """Ban xem mot dot: dict doc duoc kieu thuoc tinh (r.status) nhu dong con cu."""

    def __getattr__(self, key):
        if key.startswith("__"):
            raise AttributeError(key)
        return self.get(key)

    def as_dict(self):
        return dict(self)


def _name(business):
    if not business:
        return None
    if isinstance(business, str):
        return business
    fn = getattr(business, "is_new", None)
    if callable(fn) and fn():
        return None
    return business.get("name")


def _cache():
    loc = getattr(frappe, "local", None)
    if loc is None:
        return None
    try:
        box = getattr(loc, _CACHE_ATTR, None)
        if box is None:
            box = {}
            setattr(loc, _CACHE_ATTR, box)
        return box
    except Exception:
        return None


def invalidate(contract=None):
    box = _cache()
    if box is None:
        return
    if contract:
        box.pop(contract, None)
    else:
        box.clear()


def _load(contract):
    data = frappe.get_all(DT, filters={"contract": contract}, fields=list(FIELDS),
                          order_by="round_no asc", limit_page_length=0, ignore_permissions=True) or []
    reqs = [r.get("approval_request") for r in data if r.get("approval_request")]
    status = {}
    if reqs:
        for x in frappe.get_all("EC Approval Request", filters={"name": ["in", reqs]},
                                fields=["name", "approval_status"], limit_page_length=0,
                                ignore_permissions=True) or []:
            status[x.get("name")] = x.get("approval_status")
    out = []
    for r in data:
        r = dict(r)
        r["idx"] = r.get("round_no")
        r["approval_status"] = status.get(r.get("approval_request"), "")
        out.append(r)
    return out


def rows(business):
    """Cac dot cua hop dong (ban xem, sap theo so dot). Phieu moi / khong ten -> []."""
    contract = _name(business)
    if not contract:
        return []
    box = _cache()
    data = box.get(contract) if box is not None else None
    if data is None:
        data = _load(contract)
        if box is not None:
            box[contract] = data
    return [View(r) for r in data]


def is_closed(row):
    """Dot co yeu cau duyet da Tu choi / Huy - khong tinh vao ke hoach, gui duyet lai duoc."""
    return (row.get("approval_status") or "") in CLOSED_APPROVAL


def planned_amount(business, exclude=None):
    """Tong so tien cac dot con hieu luc (bo dot bi tu choi / huy va dot `exclude`)."""
    return sum(flt(r.get("amount")) for r in rows(business)
               if r.get("name") != exclude and not is_closed(r))


def find(business, row_name):
    """Ban xem cua mot dot thuoc hop dong nay (theo ten moi, hoac ten dong con cu `legacy_row`)."""
    for r in rows(business):
        if row_name and row_name in (r.get("name"), r.get("legacy_row")):
            return r
    return None


def get(business, row_name):
    """Document cua dot (de ghi). Dot khong thuoc hop dong `business` (doc / ten) -> bao loi."""
    view = find(business, row_name)
    if not view:
        frappe.throw(_("Không tìm thấy đợt nghiệm thu."))
    return frappe.get_doc(DT, view.name)


def lock(round_name):
    """Khoa hang dot (SELECT ... FOR UPDATE) toi het giao dich -> approval_request HIEN TAI. Hai lan bam
    "Gui duyet" cung luc: lan sau doi lan truoc xong roi thay yeu cau da tao (khong tao hai yeu cau)."""
    return frappe.db.get_value(DT, round_name, "approval_request", for_update=True)


def contract_of(round_name):
    return frappe.db.get_value(DT, round_name, "contract") if round_name else None


@contextmanager
def _writing():
    had = frappe.flags.get(FLAG)
    frappe.flags[FLAG] = True
    try:
        yield
    finally:
        frappe.flags[FLAG] = had


def create(contract_doc, values, user):
    """Them dot moi (so dot = lon nhat + 1). `values`: description, acceptance_date, amount, status."""
    no = max([int(r.get("round_no") or 0) for r in rows(contract_doc)] or [0]) + 1
    doc = frappe.get_doc(dict(values, **{
        "doctype": DT, "approval_type": APPROVAL_TYPE, "contract": contract_doc.name, "round_no": no,
        "contract_no": contract_doc.get("contract_no"), "creator": contract_doc.get("creator"),
        "creator_name": contract_doc.get("creator_name"), "brand": contract_doc.get("brand"),
        "company": contract_doc.get("company"), "department": contract_doc.get("department"),
        "requested_by": user,
        "request_title": title(contract_doc, no)}))
    with _writing():
        doc.insert(ignore_permissions=True)
    invalidate(contract_doc.name)
    return doc


def title(contract_doc, round_no):
    who = contract_doc.get("creator_name") or ""
    return ("BBNT đợt %s - %s - %s" % (round_no, contract_doc.get("contract_no") or contract_doc.name, who)
            ).strip(" -")[:140]


def save(round_doc):
    with _writing():
        round_doc.save(ignore_permissions=True)
    invalidate(round_doc.contract)
    return round_doc


def set_values(round_name, values):
    """Ghi thang vai cot (vd approval_request ngay sau engine.submit) - khong qua validate."""
    frappe.db.set_value(DT, round_name, values)
    invalidate(contract_of(round_name))


def delete(round_doc):
    contract = round_doc.contract
    with _writing():
        frappe.delete_doc(DT, round_doc.name, ignore_permissions=True)
    invalidate(contract)


def review_queue(limit=200):
    """Hang doi Ke toan: cac dot dang 'Cho kiem tra'."""
    from ecentric_workspace.approval_center.features.contract_review.domain import kol
    return frappe.get_all(DT, filters={"status": kol.BBNT_REVIEW},
                          fields=["name", "contract", "round_no", "amount", "completed_at"],
                          order_by="completed_at asc", limit_page_length=limit, ignore_permissions=True)


def contract_view(doc, keep=None, base=None):
    """doc.as_dict() + `acceptances` = cac dot CON HIEU LUC (ban xem) - dau vao cho domain kol_values /
    kol_calc (dot cuoi, dot phu het hop dong). Dot bi tu choi / huy khong tinh, tru dot `keep` (dot dang
    xu ly, vd gui duyet lai sau khi bi tu choi). `base`: as_dict da co (tranh dung lai nhieu lan)."""
    d = dict(base) if base is not None else (doc.as_dict() if hasattr(doc, "as_dict") else dict(doc or {}))
    d["acceptances"] = [r for r in rows(doc) if not is_closed(r) or (keep and r.get("name") == keep)]
    return d


def row_view(round_doc):
    """Ban xem cua MOT Document dot (idx = so dot) cho domain."""
    d = round_doc.as_dict() if hasattr(round_doc, "as_dict") else dict(round_doc or {})
    d["idx"] = d.get("round_no") or d.get("idx")
    return View(d)
