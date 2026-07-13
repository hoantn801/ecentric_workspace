# Copyright (c) 2026, eCentric and contributors
"""Governed MULTI-SELECT SEQUENTIAL signing across business requests.

This is NOT provider "bulk" signing. SCTS multi-instance bulk-process (one provider call
carrying instanceIds[]) is NOT used here because that contract is UAT-unconfirmed. Instead
the operator selects several business requests and the system signs each ONE independently
through the existing, fully-verified single-item path (svc.approve_and_sign) - one provider
document + one single-instance provider write per request. It is fail-closed as a batch
(every selected item is validated before ANY item is enqueued; any failure refuses the whole
selection) but the provider interaction is strictly per-item and sequential.

The operation stays behind the `allow_bulk_signing` gate, which is OFF by default, and no UI
action currently exposes it. When (and only when) the exact UAT multi-instance bulk contract
is confirmed, a real batch path with a persisted EC Digital Signature Bulk Batch model and a
single instanceIds[] provider call may be introduced separately. Administrator / System
Manager role is never a bypass; per-item idempotency is preserved.
"""
import frappe
from frappe import _
from frappe.utils import now_datetime

from ecentric_workspace.approval_center.esign import events
from ecentric_workspace.approval_center.esign import guard
from ecentric_workspace.approval_center.esign import package as pkgsvc
from ecentric_workspace.approval_center.esign import permissions as perms
from ecentric_workspace.approval_center.esign import ratelimit
from ecentric_workspace.approval_center.esign import service as svc


def _norm_items(items):
    items = frappe.parse_json(items) if isinstance(items, str) else (items or [])
    out, seen = [], set()
    for it in items:
        bd, bn = it.get("business_doctype"), it.get("business_name")
        if not bd or not bn:
            frappe.throw(_("Mỗi mục cần business_doctype và business_name."))
        if (bd, bn) in seen:
            continue
        seen.add((bd, bn))
        out.append({"business_doctype": bd, "business_name": bn})
    if not out:
        frappe.throw(_("Không có mục nào để ký."))
    return out


def _item_eligibility(bd, bn, caller):
    """Per-item eligibility WITHOUT any write. Returns (ok, reason, ctx)."""
    if not frappe.db.exists(bd, bn):
        return False, "not_found", {}
    if not frappe.db.has_column(bd, "approval_request"):
        return False, "not_approval_form", {}
    ar = frappe.db.get_value(bd, bn, "approval_request")
    if not ar:
        return False, "not_submitted", {}
    readiness = svc.signing_readiness(bd, bn)
    if not readiness.get("ready"):
        return False, "not_ready:%s" % ",".join(readiness.get("reasons") or []), {}
    req = frappe.db.get_value("EC Approval Request", ar,
                              ["approval_type", "current_level"], as_dict=True)
    profile_name = guard.get_active_profile(bd, req.approval_type)
    profile = frappe.db.get_value("EC Digital Signature Profile", profile_name,
                                  ["provider", "environment"], as_dict=True)
    mapping = perms.verified_mapping(caller, profile.environment)
    if not mapping:
        return False, "no_verified_mapping", {}
    pkg_name = pkgsvc.active_package_for_request(ar)
    if frappe.db.get_value("EC Digital Signature Package", pkg_name, "error_code") \
            == "create_outcome_unknown":
        return False, "ambiguous_create_state", {}
    return True, "ok", {"environment": profile.environment,
                        "scts_user_id": mapping.scts_user_id, "package": pkg_name}


def preview_multi_select(items):
    """Read-only eligibility preview - NO writes, NO provider calls."""
    caller = frappe.session.user
    rows = []
    for it in _norm_items(items):
        ok, reason, ctx = _item_eligibility(it["business_doctype"], it["business_name"], caller)
        rows.append({"business_doctype": it["business_doctype"],
                     "business_name": it["business_name"], "eligible": ok, "reason": reason,
                     "environment": ctx.get("environment"), "scts_user_id": ctx.get("scts_user_id")})
    return {"caller": caller, "items": rows,
            "all_eligible": bool(rows) and all(r["eligible"] for r in rows),
            "mode": "multi_select_sequential"}


def multi_select_sequential_sign(items, comment=None):
    """Fail-closed governed multi-select SEQUENTIAL sign. Validates EVERY item first; refuses
    the whole selection on any failure; then signs each item independently through the
    verified single-item path. No provider batch call is made or implied."""
    caller = frappe.session.user
    ratelimit.hit("multi_select_sign", user=caller, limit=6, window_s=60)
    norm = _norm_items(items)

    validated, env, scts_user = [], None, None
    for it in norm:
        ok, reason, ctx = _item_eligibility(it["business_doctype"], it["business_name"], caller)
        if not ok:
            frappe.throw(_("Ký nhiều mục bị từ chối: mục {0} không hợp lệ ({1}).")
                         .format(it["business_name"], reason), frappe.ValidationError)
        if env is None:
            env, scts_user = ctx["environment"], ctx["scts_user_id"]
        else:
            if ctx["environment"] != env:
                frappe.throw(_("Tất cả mục phải cùng môi trường nhà cung cấp."),
                             frappe.ValidationError)
            if ctx["scts_user_id"] != scts_user:
                frappe.throw(_("Tất cả mục phải cùng người ký SCTS đã ánh xạ."),
                             frappe.ValidationError)
        validated.append(it)

    settings = frappe.db.get_value("EC Digital Signature Provider Settings",
                                   {"environment": env, "integration_enabled": 1},
                                   ["name", "allow_bulk_signing", "allow_production_signing"],
                                   as_dict=True)
    if not settings or not settings.allow_bulk_signing:
        frappe.throw(_("Cổng ký nhiều mục chưa được bật."), frappe.PermissionError)
    if settings.allow_production_signing:
        frappe.throw(_("Ký nhiều mục bị chặn khi bật ký Production."), frappe.PermissionError)

    # one correlation key for audit trace; NOT a provider batch id.
    selection_key = "MSEQ-%s-%s" % (now_datetime().strftime("%Y%m%d%H%M%S"),
                                    frappe.generate_hash(length=8))
    events.emit("MultiSelectSequentialSubmitted", erp_actor=caller,
                request_meta={"selection_key": selection_key, "count": len(validated),
                              "environment": env, "provider_batch": False})
    results = []
    for it in validated:
        r = svc.approve_and_sign(it["business_doctype"], it["business_name"],
                                 comment=comment, bulk_batch_key=selection_key)
        results.append({"business_doctype": it["business_doctype"],
                        "business_name": it["business_name"],
                        "signature_request": r.get("signature_request"),
                        "status": r.get("status"), "duplicate": r.get("duplicate")})
    return {"selection_key": selection_key, "count": len(results), "items": results,
            "mode": "multi_select_sequential"}
