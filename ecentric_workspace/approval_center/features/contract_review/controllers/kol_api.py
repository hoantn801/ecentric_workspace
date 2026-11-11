# Copyright (c) 2026, eCentric and contributors
"""HTTP cho hop dong KOL/KOC tren form 27. Chi parse tham so + lay nguoi dung tu phien.

Duong dan: ecentric_workspace.approval_center.api.contract_review.kol_* (api/contract_review.py
re-export controllers/api.py, file do `import *` tu day).
KHONG ham nao nhan `user`/`actor` (test_no_whitelisted_actor_param).
"""
import json
from importlib import import_module

import frappe
from frappe import _

from ecentric_workspace.approval_center.features.contract_review.domain import kol
from ecentric_workspace.approval_center.shared.creators.service import (
    CreatorError, CreatorPermissionError, CreatorService)

__all__ = ["kol_me", "kol_search_sales_orders", "kol_list_templates", "kol_placeholder_help",
           "kol_preview_amounts", "kol_generate_contract", "kol_mark_signed",
           "kol_add_acceptance", "kol_send_acceptance", "kol_delete_acceptance", "kol_complete_acceptance",
           "kol_ai_extract", "kol_ai_qc", "kol_search_creators", "kol_get_creator",
           "kol_create_creator", "kol_update_creator", "kol_missing_misa", "kol_set_misa_code",
           "kol_verify_signed", "kol_verify_acceptance", "kol_pending_checks"]


def _app(module):
    """Nap tang application khi goi (khong luc import): controllers/api.py `import *` file nay,
    va cac test chi gia lap `frappe` (khong co frappe.utils) van nap duoc controllers/api.py."""
    return import_module("ecentric_workspace.approval_center.features.contract_review.application."
                         + module)


def _me():
    user = frappe.session.user
    if user == "Guest":
        frappe.throw(_("Vui lòng đăng nhập."), frappe.PermissionError)
    return user


def _creator(fn, *args):
    try:
        return fn(_me(), *args)
    except CreatorPermissionError as e:
        frappe.throw(_(str(e)), frappe.PermissionError)
    except CreatorError as e:
        frappe.throw(_(str(e)))


def _json(data):
    return json.loads(data or "{}") if isinstance(data, str) else (data or {})


@frappe.whitelist()
def kol_me():
    return {"is_finance": _app("kol_lookup").is_finance(_me())}


@frappe.whitelist()
def kol_search_sales_orders(query=None):
    user = _me()
    return {"rows": _app("kol_lookup").search_sales_orders(user, query),
            "missing": _app("kol_lookup").gbs_without_counterpart(user, query)}


@frappe.whitelist()
def kol_list_templates(kind=None):
    _me()
    return {"rows": _app("kol_lookup").list_templates(kind)}


@frappe.whitelist()
def kol_placeholder_help():
    _me()
    return {"placeholders": list(kol.PLACEHOLDER_HELP)}


@frappe.whitelist()
def kol_preview_amounts(creator_type=None, amount_type=None, amount_input=None, pit_rate=None,
                        vat_rate=None, payment_schedule=None, advance_percent=None):
    """So tren form tinh bang DUNG ham server dung luc luu - khong co cong thuc thu hai o JS."""
    _me()
    try:
        out = kol.compute_amounts(creator_type, amount_type, amount_input, pit_rate, vat_rate)
        out["advance"] = kol.advance_amount(out["payable"], payment_schedule, advance_percent)
        out["payable_words"] = kol.amount_in_words(out["payable"])
        return {"ok": True, "amounts": out}
    except ValueError as e:
        return {"ok": False, "error": str(e)}


@frappe.whitelist(methods=["POST"])
def kol_generate_contract(name):
    return _app("kol_files").generate_contract(name, _me())


@frappe.whitelist(methods=["POST"])
def kol_mark_signed(name, signed_file):
    return _app("kol_service").mark_signed(name, signed_file, _me())


@frappe.whitelist(methods=["POST"])
def kol_add_acceptance(name, description=None, acceptance_date=None, amount=None):
    return _app("kol_acceptance").add_acceptance(name, _me(), description, acceptance_date, amount)


@frappe.whitelist(methods=["POST"])
def kol_delete_acceptance(name, row):
    return _app("kol_acceptance").delete_acceptance(name, _me(), row)


@frappe.whitelist(methods=["POST"])
def kol_send_acceptance(name, row):
    return _app("kol_acceptance").send_acceptance(name, _me(), row)


@frappe.whitelist(methods=["POST"])
def kol_complete_acceptance(name, row, signed_file):
    return _app("kol_acceptance").complete_acceptance(name, _me(), row, signed_file)


@frappe.whitelist(methods=["POST"])
def kol_ai_extract(name):
    return _app("kol_ai").extract_fields(name, _me())


@frappe.whitelist(methods=["POST"])
def kol_ai_qc(name):
    return _app("kol_ai").run_qc(name, _me())


@frappe.whitelist()
def kol_search_creators(query=None):
    return {"rows": _creator(CreatorService().search, query, None)}


@frappe.whitelist()
def kol_get_creator(name):
    return _creator(CreatorService().get, name)


@frappe.whitelist(methods=["POST"])
def kol_create_creator(data, confirm_soft=0):
    return _creator(CreatorService().create, _json(data), str(confirm_soft) in ("1", "true"))


@frappe.whitelist(methods=["POST"])
def kol_update_creator(name, data):
    return _creator(CreatorService().update, name, _json(data))


@frappe.whitelist()
def kol_missing_misa():
    return {"rows": _creator(CreatorService().missing_misa)}


@frappe.whitelist(methods=["POST"])
def kol_set_misa_code(name, code):
    return _creator(CreatorService().set_misa_code, name, code)


def _flag(v):
    return str(v).strip().lower() in ("1", "true", "yes")


@frappe.whitelist(methods=["POST"])
def kol_verify_signed(name, ok, note=None):
    return _app("kol_verify").verify_contract(name, _me(), _flag(ok), note)


@frappe.whitelist(methods=["POST"])
def kol_verify_acceptance(name, row, ok, note=None):
    return _app("kol_verify").verify_acceptance(name, _me(), row, _flag(ok), note)


@frappe.whitelist()
def kol_pending_checks():
    return {"rows": _app("kol_verify").pending_checks(_me())}
