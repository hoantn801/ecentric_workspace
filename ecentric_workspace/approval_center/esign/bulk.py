# Copyright (c) 2026, eCentric and contributors
"""Governed bulk signing across BUSINESS REQUESTS (Phase 4).

Selection unit = one business request (one Payment Request = one active Approval Request /
runtime level / DSR), even when it has multiple files. Bulk signing is gated by its own
`allow_bulk_signing` flag and is OFF by default.

Architecture: this is a fail-closed BATCH over the existing, already-verified single-item
signing path (svc.approve_and_sign), sharing one batch correlation key. Every selected item
is fully security-validated BEFORE any provider write; if ANY item fails validation the
whole batch is refused and nothing is enqueued. Each item then runs its own governed worker
which makes exactly ONE provider write attempt for its instance (single-instance
bulk-process, transitionType=approve), polls, verifies, and completes ITS OWN approval
level independently. One failed/unknown item never rolls back another's verified signature.

True multi-instance instanceIds[] batching (one provider call for N instances) is DEFERRED
pending a confirmed UAT multi-instance bulk-process contract; the per-item partition here is
the safe partition the design explicitly permits. Administrator / System Manager role is
never a bulk bypass - eligibility is the active-approver + verified-mapping predicate.
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
    out = []
    seen = set()
    for it in items:
        bd = it.get("business_doctype")
        bn = it.get("business_name")
        if not bd or not bn:
            frappe.throw(_("Mỗi mục cần business_doctype và business_name."))
        key = (bd, bn)
        if key in seen:
            continue  # de-duplicate selection
        seen.add(key)
        out.append({"business_doctype": bd, "business_name": bn})
    if not out:
        frappe.throw(_("Không có mục nào để ký hàng loạt."))
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
    # backend-computed readiness (active approver, package hash, placements, mapping,
    # UAT, allowlist, gates, production-off) - all re-checked under lock at sign time too.
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
    ambiguous = frappe.db.get_value("EC Digital Signature Package", pkg_name, "error_code")
    if ambiguous == "create_outcome_unknown":
        return False, "ambiguous_create_state", {}
    # a live/terminal DSR already exists for this level? treat as not-eligible for a new sign
    ctx = {"environment": profile.environment, "scts_user_id": mapping.scts_user_id,
           "action": "Sign", "package": pkg_name}
    return True, "ok", ctx


def preview_bulk(items):
    """Read-only eligibility preview - NO writes, NO provider calls. Gated only by the
    per-item view permission inside signing_readiness (caller must be able to view each)."""
    caller = frappe.session.user
    rows = []
    for it in _norm_items(items):
        ok, reason, ctx = _item_eligibility(it["business_doctype"], it["business_name"], caller)
        rows.append({"business_doctype": it["business_doctype"],
                     "business_name": it["business_name"], "eligible": ok,
                     "reason": reason, "environment": ctx.get("environment"),
                     "scts_user_id": ctx.get("scts_user_id")})
    return {"caller": caller, "items": rows,
            "all_eligible": bool(rows) and all(r["eligible"] for r in rows)}


def bulk_sign(items, comment=None):
    """Fail-closed governed bulk sign. Validates EVERY item first; refuses the whole batch
    on any failure; then enqueues each item's governed signing under one batch key."""
    caller = frappe.session.user
    ratelimit.hit("bulk_sign", user=caller, limit=6, window_s=60)
    norm = _norm_items(items)

    # 1) bulk gate must be enabled (OFF by default -> fail closed). Determine environment
    #    from the first item, require ALL items to share it, and require the bulk gate on
    #    the matching provider settings.
    validated = []
    env = None
    scts_user = None
    for it in norm:
        ok, reason, ctx = _item_eligibility(it["business_doctype"], it["business_name"], caller)
        if not ok:
            frappe.throw(_("Ký hàng loạt bị từ chối: mục {0} không hợp lệ ({1}).")
                         .format(it["business_name"], reason), frappe.ValidationError)
        if env is None:
            env = ctx["environment"]
            scts_user = ctx["scts_user_id"]
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
        frappe.throw(_("Cổng ký hàng loạt chưa được bật."), frappe.PermissionError)
    if settings.allow_production_signing:
        frappe.throw(_("Ký hàng loạt bị chặn khi bật ký Production."), frappe.PermissionError)

    # 2) one batch correlation key; each item enqueues its own governed signing.
    batch_key = "BULK-%s-%s" % (now_datetime().strftime("%Y%m%d%H%M%S"),
                                frappe.generate_hash(length=8))
    events.emit("BulkBatchSubmitted", erp_actor=caller,
                request_meta={"batch_key": batch_key, "count": len(validated),
                              "environment": env})
    results = []
    for it in validated:
        r = svc.approve_and_sign(it["business_doctype"], it["business_name"],
                                 comment=comment, bulk_batch_key=batch_key)
        results.append({"business_doctype": it["business_doctype"],
                        "business_name": it["business_name"],
                        "signature_request": r.get("signature_request"),
                        "status": r.get("status"), "duplicate": r.get("duplicate")})
    return {"batch_key": batch_key, "count": len(results), "items": results}
