# Copyright (c) 2026, eCentric and contributors
"""Rut ra MOI (doctype, field) ma mot request list/search/count NHAC TOI - trong filters,
or_filters, fields, order_by, group_by... Ham thuan, khong goi frappe (test khong can bench).

Dung boi filter_guard.py de chan "do gia tri bang filter" tren field permlevel cao.

CAC DANG DAU VAO (frappe v16):
    filters  {"f": v} | {"f": ["like", "9%"]} | [["f","like","9%"]] | [["Employee","f","like","9%"]]
             | [["Child DT","f","=",x,False]] | chuoi JSON cua cac dang tren | ten ban ghi (get_value)
    fields   ["name", "`tabEmployee`.`f`", "sum(f) as x", "ec_contracts.so_hop_dong", "*"]
    order_by "`tabEmployee`.`f` desc, modified asc"  (group_by, field, searchfield... cung kieu)
Bieu thuc duoc tach thanh dinh danh. Dinh danh KHONG phai field cua doctype (ham SQL, alias, tu
khoa) bi bo qua o buoc `violations` - nen o day cu tra het ra, thua con hon sot.
"""
import json
import re

FILTER_KEYS = ("filters", "or_filters", "current_filters")
# `fields` / `fieldname` (SELECT) CO Y khong nam o day: frappe v16 tu bo cot khong doc duoc khoi
# SELECT, ke ca cot nam trong ham (db_query.apply_fieldlevel_read_permissions), va get_value cung
# di qua get_list. Tu choi ca request vi `fields` thi report "Ho so nhan su" (33 cot, co cot L1)
# se gay han voi HR User - ma khong chan them duoc gi. Cai lo la WHERE / ORDER BY / GROUP BY.
LIST_KEYS = ("stats", "filter_fields")
EXPR_KEYS = ("order_by", "sort_by", "group_by", "field", "searchfield", "aggregate_on_field")

_STRING = re.compile(r"'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"")
_TAB_QUOTED = re.compile(r"`tab([^`]+)`\s*\.\s*`?([A-Za-z_]\w*)`?")
_TAB_PLAIN = re.compile(r"\btab([A-Za-z_]\w*)\s*\.\s*([A-Za-z_]\w*)")
_DOTTED = re.compile(r"\b([A-Za-z_]\w*)\s*\.\s*([A-Za-z_]\w*)")
_IDENT = re.compile(r"[A-Za-z_]\w*")


def referenced_fields(params, base_doctype, table_to_child):
    """params: form_dict. table_to_child: {field bang cua base: DocType con}.
    Tra ve set cac cap (doctype, field)."""
    refs = set()
    for key in FILTER_KEYS:
        if params.get(key) not in (None, ""):
            refs |= _filter_refs(_json(params[key]), base_doctype, table_to_child)
    for key in LIST_KEYS:
        value = _json(params.get(key))
        items = value if isinstance(value, (list, tuple)) else _split(value)
        for item in items:
            if isinstance(item, str):
                refs |= expr_refs(item, base_doctype, table_to_child)
    for key in EXPR_KEYS:
        if isinstance(params.get(key), str):
            refs |= expr_refs(params[key], base_doctype, table_to_child)
    return refs


def expr_refs(expr, base_doctype, table_to_child):
    """Cac (doctype, field) trong mot bieu thuc SQL nho (field, order_by, group_by...)."""
    refs = set()
    text = _STRING.sub(" ", expr or "")
    for rx in (_TAB_QUOTED, _TAB_PLAIN):
        for dt, field in rx.findall(text):
            refs.add((dt.strip(), field))
        text = rx.sub(" ", text)
    text = text.replace("`", "")
    for left, field in _DOTTED.findall(text):
        refs.add((table_to_child.get(left, left), field))
    text = _DOTTED.sub(" ", text)
    for ident in _IDENT.findall(text):
        refs.add((base_doctype, ident))
    return refs


def violations(refs, restricted):
    """restricted: {doctype: set field nguoi goi KHONG doc duoc}.
    Tra ve danh sach 'doctype.field' vi pham, da sap xep."""
    return sorted("%s.%s" % (dt, f) for dt, f in refs if f in restricted.get(dt, ()))


def _filter_refs(filters, base_doctype, table_to_child):
    refs = set()
    if isinstance(filters, dict):
        for key in filters:
            refs |= expr_refs(str(key), base_doctype, table_to_child)
    elif isinstance(filters, (list, tuple)):
        if filters and all(isinstance(x, str) for x in filters[:2]) and len(filters) >= 3 \
                and not isinstance(filters[0], (list, tuple, dict)):
            # mot dieu kien don le khong boc trong list: ["f", "like", "9%"]
            return _filter_refs([filters], base_doctype, table_to_child)
        for item in filters:
            if isinstance(item, dict):
                refs |= _filter_refs(item, base_doctype, table_to_child)
            elif isinstance(item, str):
                refs |= expr_refs(item, base_doctype, table_to_child)
            elif isinstance(item, (list, tuple)) and item and isinstance(item[0], str):
                if len(item) >= 4 and isinstance(item[1], str):
                    refs |= expr_refs(item[1], item[0], table_to_child)
                else:
                    refs |= expr_refs(item[0], base_doctype, table_to_child)
    return refs


def _json(value):
    if isinstance(value, str):
        stripped = value.strip()
        if stripped[:1] in ("[", "{"):
            try:
                return json.loads(stripped)
            except ValueError:
                # JSON hong: bo dau nhay roi soi nhu mot bieu thuc - khong de lot (dong cua)
                return [stripped.replace('"', " ").replace("'", " ")]
    return value


def _split(value):
    if isinstance(value, str):
        return [part for part in value.split(",") if part.strip()]
    return []
