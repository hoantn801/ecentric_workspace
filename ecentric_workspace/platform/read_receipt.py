# Copyright (c) 2026, eCentric and contributors
"""Luot xem DUNG CHUNG (DocType `EC Read Receipt`) - "ai da mo ban ghi nao".

Tin noi bo dung hom nay (01/10/2026, PO chot: mo bai = da xem, khong co nut xac nhan).
Thu vien tai lieu ISO dung lai sau, theo `version` (moi phien ban mot luot rieng). Neu
ISO can xac nhan CHU DONG thi them cot `kind` vao DocType - khong lam lai cho nay.

MOT dong cho moi (loai, ban ghi, phien ban, nguoi) - khoa `dedupe_key` UNIQUE o DB, nen
hai tab mo cung luc khong de ra hai dong. Lan mo sau chi cap nhat last_seen + seen_count.

Ghi la viec cua HE THONG (nguoi xem khong co quyen ghi bang nay), nen dung
ignore_permissions; nguoi goi PHAI kiem quyen doc ban ghi truoc khi goi mark_seen().
"""
import frappe

DT = "EC Read Receipt"


def _key(ref_doctype, ref_name, user, version=""):
    return "%s|%s|%s|%s" % (ref_doctype, ref_name, version or "", user)


def mark_seen(ref_doctype, ref_name, user, version=""):
    """Ghi / cap nhat luot xem. -> True neu day la lan DAU nguoi nay mo."""
    if not user or user == "Guest":
        return False
    now = frappe.utils.now_datetime()
    key = _key(ref_doctype, ref_name, user, version)
    name = frappe.db.get_value(DT, {"dedupe_key": key}, "name")
    if name:
        frappe.db.sql("update `tabEC Read Receipt` set last_seen=%s, seen_count=ifnull(seen_count,0)+1 "
                      "where name=%s", (now, name))
        return False
    try:
        frappe.get_doc({"doctype": DT, "reference_doctype": ref_doctype, "reference_name": ref_name,
                        "version": version or "", "user": user, "first_seen": now, "last_seen": now,
                        "seen_count": 1, "dedupe_key": key}).insert(ignore_permissions=True)
        return True
    except (frappe.DuplicateEntryError, frappe.UniqueValidationError):
        return False            # tab kia vua ghi xong - coi nhu da co


def seen_users(ref_doctype, ref_name, version=""):
    """Tap user da mo ban ghi nay."""
    return set(frappe.get_all(DT, filters={"reference_doctype": ref_doctype, "reference_name": ref_name,
                                           "version": version or ""},
                              pluck="user", limit_page_length=0))


def seen_by(user, ref_doctype, ref_names):
    """Trong cac ban ghi nay, nguoi nay da mo nhung ban nao (nhan "Chua xem" tren the)."""
    if not user or not ref_names:
        return set()
    return set(frappe.get_all(DT, filters={"reference_doctype": ref_doctype, "user": user,
                                           "reference_name": ["in", list(ref_names)]},
                              pluck="reference_name", limit_page_length=0))


def counts(ref_doctype, ref_names):
    """{ten: so nguoi da mo} cho nhieu ban ghi (trang quan ly). Chua loc theo pham vi."""
    if not ref_names:
        return {}
    rows = frappe.db.sql(
        "select reference_name, count(distinct user) from `tabEC Read Receipt` "
        "where reference_doctype=%s and reference_name in %s group by reference_name",
        (ref_doctype, tuple(ref_names)))
    return {r[0]: int(r[1]) for r in rows}


def seen_users_many(ref_doctype, ref_names):
    """{ten: tap user da mo} - de dem DUNG theo pham vi tung bai."""
    out = {n: set() for n in ref_names or ()}
    if not ref_names:
        return out
    for r in frappe.get_all(DT, filters={"reference_doctype": ref_doctype,
                                         "reference_name": ["in", list(ref_names)]},
                            fields=["reference_name", "user"], limit_page_length=0):
        out.setdefault(r.reference_name, set()).add(r.user)
    return out
