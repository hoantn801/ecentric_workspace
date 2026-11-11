# Copyright (c) 2026, eCentric and contributors
"""Doc/ghi Supplier nhom creator. Noi DUY NHAT cua module nay goi frappe.db / get_all.

Doc bang ignore_permissions: nguoi lam affiliate KHONG co quyen doc Supplier tren Desk (DocPerm
chuan chi cho Purchase/Accounts/Stock), moi quyen cua creator master nam o service.py.
"""
from importlib import import_module

from ecentric_workspace.approval_center.shared.creators import domain

DT = "Supplier"
_IDENTITY_FIELDS = ["name", "supplier_name", "ec_cr_misa_code"] + list(domain.HARD_KEYS) + [
    f for f in domain.SOFT_KEYS if f != "supplier_name"]


def _frappe():
    return import_module("frappe")


class InsertError(Exception):
    """Frappe tu choi ban ghi luc ghi - thong bao da lam sach cho nguoi dung."""


def _clean_msg(err):
    import re
    text = re.sub(r"<[^>]+>", " ", str(err) or err.__class__.__name__)
    return re.sub(r"\s+", " ", text).strip()[:300] or "Không ghi được creator."


class CreatorRepository:
    def identity_rows(self, exclude=None):
        filters = {"supplier_group": domain.CREATOR_GROUP}
        if exclude:
            filters["name"] = ["!=", exclude]
        return _frappe().get_all(DT, filters=filters, fields=_IDENTITY_FIELDS,
                                 limit_page_length=0)

    def search(self, query, limit):
        frappe = _frappe()
        filters = {"supplier_group": domain.CREATOR_GROUP, "disabled": 0}
        fields = list(domain.PUBLIC_FIELDS)
        if not query:
            return frappe.get_all(DT, filters=filters, fields=fields,
                                  order_by="modified desc", limit_page_length=limit)
        like = "%%%s%%" % query
        or_filters = [["supplier_name", "like", like], ["ec_cr_tiktok_id", "like", like],
                      ["ec_cr_shopee_id", "like", like], ["ec_cr_misa_code", "like", like],
                      ["name", "like", like]]
        return frappe.get_all(DT, filters=filters, or_filters=or_filters, fields=fields,
                              order_by="modified desc", limit_page_length=limit)

    def get(self, name):
        fields = list(dict.fromkeys(list(domain.PUBLIC_FIELDS) + list(domain.WRITABLE_FIELDS)
                                    + ["owner", "supplier_group", "creation"]))
        row = _frappe().db.get_value(DT, name, fields, as_dict=True)
        return row if row and row.get("supplier_group") == domain.CREATOR_GROUP else None

    def insert(self, values):
        """Them Supplier. Loi validate cua Frappe (email sai, trung ten khi dat ten theo ten NCC...)
        -> InsertError, va CHI dong nay bi huy (savepoint): nhap 50 dong khong mat ca lo vi 1 dong."""
        frappe = _frappe()
        sp = "ec_creator_insert"
        frappe.db.savepoint(sp)
        log = getattr(frappe.local, "message_log", None)
        keep = len(log) if isinstance(log, list) else None
        try:
            doc = frappe.get_doc(dict(values, doctype=DT))
            doc.insert(ignore_permissions=True, set_name=self._free_name(values.get("supplier_name")))
        except (frappe.ValidationError, frappe.DuplicateEntryError) as e:
            frappe.db.rollback(save_point=sp)
            if keep is not None:   # bo popup loi cua dong nay: da tra ve trong ket qua tung dong
                del frappe.local.message_log[keep:]
            raise InsertError(_clean_msg(e))
        return doc.name

    @staticmethod
    def _free_name(supplier_name):
        """Site dat ten Supplier THEO TEN NCC: hai creator khac nhau trung ten (da xac nhan trung
        mem) se dung khoa chinh -> them hau to '- 1' nhu ERPNext lam voi Customer."""
        frappe = _frappe()
        if frappe.defaults.get_global_default("supp_master_name") != "Supplier Name":
            return None
        if not supplier_name or not frappe.db.exists(DT, supplier_name):
            return None
        from frappe.model.naming import append_number_if_name_exists
        return append_number_if_name_exists(DT, supplier_name)

    def update(self, name, values):
        doc = _frappe().get_doc(DT, name)
        doc.update(values)
        doc.save(ignore_permissions=True)
        return doc.name

    def missing_misa(self):
        fields = ["name", "supplier_name", "ec_cr_type", "tax_id", "ec_cr_cccd", "ec_phone",
                  "ec_cr_email", "ec_cr_address", "owner", "creation"]
        return _frappe().get_all(DT, filters={"supplier_group": domain.CREATOR_GROUP,
                                              "ec_cr_misa_code": ["is", "not set"]},
                                 fields=fields, order_by="creation asc", limit_page_length=0)

    def misa_owner(self, code, exclude):
        return _frappe().db.get_value(DT, {"ec_cr_misa_code": code, "name": ["!=", exclude]},
                                      "name")

    def roles(self, user):
        return set(_frappe().get_roles(user))
