# Copyright (c) 2026, eCentric and contributors
"""Loc lich su thay doi (Version) theo quyen permlevel cua NGUOI XEM. Ham thuan, khong goi frappe.

VI SAO CAN (VA_BAO_MAT_2026-09-25.md muc 1)
    Form Desk tai 10 Version gan nhat qua `frappe.desk.form.load.get_docinfo`, va Frappe tra
    NGUYEN ban diff - khong loc theo permlevel. Moi nhan vien mo form Employee cua dong nghiep
    deu doc duoc "phu cap tu X thanh Y", SDT, email ca nhan... du chinh cac o do bi an tren form.
    Ngay 28/09 da phai tat track_changes cua Employee de chan tam.

LUAT
    * `changed`      [field, cu, moi]                    -> giu neu nguoi xem doc duoc `field`
    * `added/removed`[bang, {dong}]                       -> giu neu doc duoc bang; trong dong
                                                              chi giu cot doc duoc
    * `row_changed`  [bang, ten_dong, idx, [[cot,cu,moi]]] -> nhu tren, bo cot khong doc duoc
    * Ban ghi Version con lai RONG (moi thay doi deu bi loc) thi BO HAN - khong de lai dong
      "X da sua" trong rong, vi chinh viec "co nguoi vua sua" cung la thong tin.
    * Ban ghi khong co bon khoa tren (Version luc tao / import) chi mang ten nguoi va thoi diem,
      khong co gia tri field -> giu nguyen.
    * Doc khong duoc JSON -> BO (dong cua khi nghi ngo).
"""
import json

DIFF_KEYS = ("changed", "added", "removed", "row_changed")
# Cot he thong cua mot dong bang con - khong phai du lieu nghiep vu.
ROW_META_KEYS = frozenset({"name", "idx", "doctype", "parent", "parentfield", "parenttype",
                           "owner", "creation", "modified", "modified_by", "docstatus"})


def filter_versions(rows, readable, readable_child):
    """rows: [{"name","owner","creation","data"(json)}]. readable: set ten field cua doc cha
    nguoi xem doc duoc. readable_child: {ten_field_bang: set cot doc duoc} - chi chua bang ma
    chinh field bang do doc duoc."""
    out = []
    for row in rows or []:
        data = _load(row.get("data"))
        if data is None:
            continue
        kept = filter_diff(data, readable, readable_child)
        if kept is None:
            continue
        new = dict(row)
        new["data"] = json.dumps(kept, separators=(",", ":"), ensure_ascii=False, default=str)
        out.append(new)
    return out


def filter_diff(data, readable, readable_child):
    """Tra ve diff da loc, hoac None neu khong con gi nguoi xem duoc phep thay."""
    if not any(k in data for k in DIFF_KEYS):
        return data
    kept = {k: v for k, v in data.items() if k not in DIFF_KEYS}
    kept["changed"] = [c for c in data.get("changed") or [] if _field(c) in readable]
    for key in ("added", "removed"):
        kept[key] = [r for r in (_row(item, readable_child) for item in data.get(key) or []) if r]
    kept["row_changed"] = [r for r in (_row_change(item, readable_child)
                                       for item in data.get("row_changed") or []) if r]
    if not any(kept[k] for k in DIFF_KEYS):
        return None
    return kept


def _load(raw):
    if isinstance(raw, dict):
        return raw
    try:
        data = json.loads(raw or "{}")
    except (TypeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _field(item):
    return item[0] if isinstance(item, (list, tuple)) and item else None


def _row(item, readable_child):
    table = _field(item)
    if table not in readable_child or len(item) < 2 or not isinstance(item[1], dict):
        return None
    cols = readable_child[table]
    return [table, {k: v for k, v in item[1].items() if k in cols or k in ROW_META_KEYS}]


def _row_change(item, readable_child):
    table = _field(item)
    if table not in readable_child or len(item) < 4:
        return None
    cols = readable_child[table]
    changes = [c for c in item[3] or [] if _field(c) in cols]
    if not changes:
        return None
    return [table, item[1], item[2], changes]
