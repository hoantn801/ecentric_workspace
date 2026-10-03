# Copyright (c) 2026, eCentric and contributors
"""Luot xem DUNG CHUNG (DocType `EC Read Receipt`) - "ai da mo ban ghi nao".

Tin noi bo dung hom nay (01/10/2026, PO chot: mo bai = da xem). Thu vien tai lieu ISO dung
lai sau, theo `version` (moi phien ban mot luot rieng).

HAI LOAI (`kind`, them 03/10/2026):
  * "seen" - mo ban ghi la tinh (mac dinh, moi ham cu giu nguyen hanh vi);
  * "ack"  - nguoi doc CHU DONG bam "Toi da doc va hieu" (Tin noi bo bat buoc xac nhan;
             ISO sau nay dung lai dung cho nay, khong lam bang moi).
Khoa cua "seen" giu dung dang cu (dong da co khong bi trung lap); "ack" them duoi "|ack".

MOT dong cho moi (loai, ban ghi, phien ban, nguoi) - khoa `dedupe_key` UNIQUE o DB, nen
hai tab mo cung luc khong de ra hai dong. Lan mo sau chi cap nhat last_seen + seen_count.

Ghi la viec cua HE THONG (nguoi xem khong co quyen ghi bang nay), nen dung
ignore_permissions; nguoi goi PHAI kiem quyen doc ban ghi truoc khi goi mark_seen().
"""
import frappe

DT = "EC Read Receipt"


SEEN = "seen"
ACK = "ack"


def _key(ref_doctype, ref_name, user, version="", kind=SEEN):
    key = "%s|%s|%s|%s" % (ref_doctype, ref_name, version or "", user)
    return key if (kind or SEEN) == SEEN else key + "|" + kind


def mark_seen(ref_doctype, ref_name, user, version="", kind=SEEN):
    """Ghi / cap nhat luot xem (hoac xac nhan, kind="ack"). -> True neu day la lan DAU."""
    if not user or user == "Guest":
        return False
    now = frappe.utils.now_datetime()
    key = _key(ref_doctype, ref_name, user, version, kind)
    name = frappe.db.get_value(DT, {"dedupe_key": key}, "name")
    if name:
        frappe.db.sql("update `tabEC Read Receipt` set last_seen=%s, seen_count=ifnull(seen_count,0)+1 "
                      "where name=%s", (now, name))
        return False
    try:
        frappe.get_doc({"doctype": DT, "reference_doctype": ref_doctype, "reference_name": ref_name,
                        "version": version or "", "kind": kind or SEEN, "user": user,
                        "first_seen": now, "last_seen": now,
                        "seen_count": 1, "dedupe_key": key}).insert(ignore_permissions=True)
        return True
    except (frappe.DuplicateEntryError, frappe.UniqueValidationError):
        return False            # tab kia vua ghi xong - coi nhu da co


def mark_ack(ref_doctype, ref_name, user, version=""):
    """Nguoi doc bam "Toi da doc va hieu". -> True neu lan dau. Nguoi goi da kiem quyen doc."""
    return mark_seen(ref_doctype, ref_name, user, version, kind=ACK)


def seen_users(ref_doctype, ref_name, version="", kind=SEEN):
    """Tap user da mo (hoac da xac nhan, kind="ack") ban ghi nay."""
    return set(frappe.get_all(DT, filters={"reference_doctype": ref_doctype, "reference_name": ref_name,
                                           "version": version or "", "kind": kind},
                              pluck="user", limit_page_length=0))


def seen_times(ref_doctype, ref_name, version="", kind=SEEN):
    """{user: first_seen} - xuat Excel "ai xac nhan luc nao"."""
    return {r.user: r.first_seen for r in frappe.get_all(
        DT, filters={"reference_doctype": ref_doctype, "reference_name": ref_name, "version": version or "",
                     "kind": kind}, fields=["user", "first_seen"], limit_page_length=0)}


def seen_by(user, ref_doctype, ref_names, kind=SEEN):
    """Trong cac ban ghi nay, nguoi nay da mo nhung ban nao (nhan "Chua xem" tren the)."""
    if not user or not ref_names:
        return set()
    return set(frappe.get_all(DT, filters={"reference_doctype": ref_doctype, "user": user, "kind": kind,
                                           "reference_name": ["in", list(ref_names)]},
                              pluck="reference_name", limit_page_length=0))


def counts(ref_doctype, ref_names, kind=SEEN):
    """{ten: so nguoi da mo} cho nhieu ban ghi (trang quan ly). Chua loc theo pham vi."""
    if not ref_names:
        return {}
    rows = frappe.db.sql(
        "select reference_name, count(distinct user) from `tabEC Read Receipt` "
        "where reference_doctype=%s and reference_name in %s and ifnull(kind, 'seen')=%s "
        "group by reference_name",
        (ref_doctype, tuple(ref_names), kind))
    return {r[0]: int(r[1]) for r in rows}


def seen_users_many(ref_doctype, ref_names, kind=SEEN):
    """{ten: tap user da mo} - de dem DUNG theo pham vi tung bai."""
    out = {n: set() for n in ref_names or ()}
    if not ref_names:
        return out
    for r in frappe.get_all(DT, filters={"reference_doctype": ref_doctype, "kind": kind,
                                         "reference_name": ["in", list(ref_names)]},
                            fields=["reference_name", "user"], limit_page_length=0):
        out.setdefault(r.reference_name, set()).add(r.user)
    return out
