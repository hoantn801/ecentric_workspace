# Copyright (c) 2026, eCentric and contributors
"""Controlled SCTS UAT pilot: read-only readiness checklist + an opt-in, heavily gated
manual probe (S2B-C1). Backend-authoritative; returns SAFE identifiers only - never
tokens, passwords, or PDF/base64 content. Nothing here runs automatically.
"""
import frappe
from frappe import _
from frappe.utils import now_datetime
from frappe.utils.password import get_decrypted_password

from ecentric_workspace.approval_center.esign import guard
from ecentric_workspace.approval_center.esign import package as pkgsvc
from ecentric_workspace.approval_center.esign import permissions as perms

SETTINGS_DT = "EC Digital Signature Provider Settings"
PKG = "EC Digital Signature Package"
DSF = "EC Digital Signature File"
DSR = "EC Digital Signature Request"


def _has_secret(name, field):
    try:
        return bool((get_decrypted_password(SETTINGS_DT, name, field, raise_exception=False) or "").strip())
    except Exception:
        return False


def uat_pilot_readiness(payment_request_name=None):
    """SM/Administrator-only, READ-ONLY structured readiness checklist. Returns
    {ready, blocking_items[], warnings[], checks{}} with safe identifiers only."""
    perms.assert_system_manager()
    user = frappe.session.user
    checks = {}
    blocking = []
    warnings = []

    def chk(key, ok, blocking_flag=True, detail=None):
        checks[key] = {"ok": bool(ok), "detail": detail}
        if not ok:
            (blocking if blocking_flag else warnings).append(key)
        return ok

    # ---- provider ----
    s = frappe.db.get_value(SETTINGS_DT, {"provider": "SCTS", "environment": "UAT"},
                            "*", as_dict=True)
    chk("provider_scts_uat_settings_exist", bool(s))
    if s:
        chk("environment_is_uat", s.environment == "UAT")
        chk("base_url_configured", bool((s.base_url or "").strip()))
        chk("credentials_configured",
            bool((s.username or "").strip()) and _has_secret(s.name, "password"))
        chk("integration_enabled", bool(s.integration_enabled))
        chk("document_creation_enabled", bool(s.allow_document_creation))
        chk("signing_enabled", bool(s.allow_signing))
        chk("production_signing_disabled", not bool(s.allow_production_signing))
        chk("callback_disabled", not bool(s.allow_callback))
        chk("bulk_signing_disabled", not bool(s.allow_bulk_signing))
        raw = (s.allowed_signing_users or "").replace(",", "\n")
        allowed = {u.strip().lower() for u in raw.splitlines() if u.strip()}
        chk("user_in_uat_allowlist", user.lower() in allowed)

    # ---- profile (best-effort; resolved from the PR when provided) ----
    profile = None
    approval_type = None
    if payment_request_name and frappe.db.exists("EC Payment Request", payment_request_name):
        approval_type = frappe.db.get_value("EC Payment Request", payment_request_name,
                                            "approval_type")
    prof_row = None
    if approval_type:
        prof_name = guard.get_active_profile("EC Payment Request", approval_type)
        prof_row = frappe.db.get_value("EC Digital Signature Profile", prof_name, "*",
                                       as_dict=True) if prof_name else None
    if not prof_row:
        cand = frappe.get_all("EC Digital Signature Profile",
                              filters={"business_doctype": "EC Payment Request",
                                       "provider": "SCTS", "enabled": 1},
                              fields=["*"], limit_page_length=1)
        prof_row = cand[0] if cand else None
    chk("active_profile_exists", bool(prof_row))
    if prof_row:
        profile = prof_row
        chk("workflow_definition_id_present", bool(prof_row.get("workflow_definition_id")))
        chk("document_type_id_present", bool(prof_row.get("document_type_id")))
        chk("company_id_present", bool(prof_row.get("company_id")))
        chk("department_id_present", bool(prof_row.get("department_id")))
        chk("document_template_id_present", bool(prof_row.get("document_template_id")),
            blocking_flag=False)  # optional -> warning only

    # ---- mapping (current user) ----
    maps = frappe.get_all("EC SCTS User Mapping",
                          filters={"frappe_user": user, "environment": "UAT", "active": 1},
                          fields=["name", "scts_user_id", "signature_id", "mapping_status"])
    chk("exactly_one_active_mapping", len(maps) == 1)
    if len(maps) == 1:
        m = maps[0]
        chk("mapped_scts_user_id_present", bool(m.scts_user_id))
        chk("signature_id_present", bool(m.signature_id))
        chk("mapping_verified", m.mapping_status == "Verified")

    # ---- payment request (only when a specific PR is given) ----
    if payment_request_name:
        chk("payment_request_exists", frappe.db.exists("EC Payment Request", payment_request_name))
        ar = perms.business_approval_request("EC Payment Request", payment_request_name) \
            if frappe.db.exists("EC Payment Request", payment_request_name) else None
        chk("approval_request_active", bool(ar))
        if ar:
            req = frappe.db.get_value("EC Approval Request", ar,
                                      ["approval_status", "current_level"], as_dict=True)
            chk("level_resolved", bool(req and req.current_level))
            if req and req.current_level and approval_type:
                chk("level_requires_signature",
                    guard.level_requires_signature("EC Payment Request", approval_type,
                                                   req.current_level))
                chk("current_user_is_active_approver",
                    req.approval_status == "Pending"
                    and bool(perms.pending_approver_row(ar, req.current_level, user)))
            pkg_name = pkgsvc.active_package_for_request(ar)
            pkg = frappe.db.get_value(PKG, pkg_name,
                                      ["name", "status", "package_hash", "error_code"],
                                      as_dict=True) if pkg_name else None
            chk("package_locked", bool(pkg and pkg.status in ("Locked", "Active")))
            chk("package_hash_valid",
                bool(pkg and pkg.package_hash and pkgsvc.compute_hash(pkg_name) == pkg.package_hash))
            if pkg_name:
                sfiles = frappe.get_all(DSF, filters={"package": pkg_name, "requires_signature": 1},
                                        fields=["name", "file", "file_name", "is_pdf", "sha256"])
                chk("all_signable_files_private_pdf",
                    all(f.is_pdf for f in sfiles) and all(
                        frappe.db.get_value("File", f.file, "is_private") for f in sfiles if f.file))
                chk("file_hashes_match",
                    all(f.sha256 == pkgsvc.hashing.sha256_bytes(pkgsvc.file_bytes(f.name))
                        for f in sfiles) if sfiles else False)
                chk("placements_complete", not pkgsvc.preflight_for_lock(pkg_name))
                chk("no_active_duplicate_dsr",
                    frappe.db.count(DSR, {"package": pkg_name,
                                          "status": ["in", ["Queued", "Provider Accepted",
                                                            "Verifying", "Signed"]]}) <= 1,
                    blocking_flag=False)
                chk("no_unresolved_ambiguous_create",
                    (pkg.error_code != "create_outcome_unknown") if pkg else True)

    ready = len(blocking) == 0
    return {"ready": ready, "blocking_items": blocking, "warnings": warnings,
            "checks": checks, "user": user,
            "payment_request": payment_request_name}


# --------------------------------------------------------------------------- #
# opt-in manual probe (NEVER runs automatically / in CI / via scheduler)
# --------------------------------------------------------------------------- #
def _is_uat_void_named(payment_request_name):
    row = frappe.db.get_value("EC Payment Request", payment_request_name,
                              ["name", "request_title", "reason"], as_dict=True) or {}
    blob = " ".join(str(row.get(k) or "") for k in ("name", "request_title", "reason")).upper()
    return ("VOID" in blob) or ("UAT" in blob) or ("TEST" in blob)


def run_scts_uat_pilot_probe(payment_request_name, apply=0):
    """Manual, opt-in UAT probe. apply=0 (default) does readiness + a REDACTED payload
    preview with NO external calls. apply=1 may drive the real UAT sequence ONLY when every
    readiness item passes, the environment is UAT, the user is allowlisted, and the PR is
    explicitly UAT/VOID-named. Production is always rejected. Never touches secrets."""
    perms.assert_system_manager()
    apply = int(apply or 0)

    if not frappe.db.exists("EC Payment Request", payment_request_name):
        frappe.throw(_("Không tìm thấy Payment Request."))
    # Production is ALWAYS rejected for the probe.
    prod = frappe.db.exists(SETTINGS_DT, {"provider": "SCTS", "environment": "Production",
                                          "allow_signing": 1})
    readiness = uat_pilot_readiness(payment_request_name)

    preview = {
        "route_add_document": "POST /api/AddDocument",
        "route_bulk_process": "POST /api/Workflow/bulk-process (transitionType=approve)",
        "route_document_poll": "GET /api/Document/{id}",
        "route_signed_pdf": "GET /api/Document/pdf  [UAT contract UNCONFIRMED]",
        "documents": "<redacted: file names + base64 omitted>",
        "signatures": "<redacted: placement geometry only, no identity>",
        "credentials": "<never included>",
    }

    if apply != 1:
        return {"applied": False, "mode": "preview", "ready": readiness["ready"],
                "readiness": readiness, "payload_preview": preview,
                "note": "apply=0: no external SCTS calls were made."}

    # ---- apply=1 hard gates ----
    if not _is_uat_void_named(payment_request_name):
        frappe.throw(_("Probe apply=1 chỉ chạy trên Payment Request đánh dấu UAT/VOID/TEST."),
                     frappe.PermissionError)
    s = frappe.db.get_value(SETTINGS_DT, {"provider": "SCTS", "environment": "UAT"},
                            ["environment", "allow_production_signing"], as_dict=True)
    if not s or s.environment != "UAT":
        frappe.throw(_("Probe apply=1 chỉ chạy trên môi trường UAT."), frappe.PermissionError)
    if not readiness["ready"]:
        return {"applied": False, "mode": "blocked",
                "reason": "readiness_incomplete", "readiness": readiness}

    # Governed real submit reuses the entire verified path (binding, AddDocument,
    # bulk-process transitionType=approve, poll, completion, signed-file retrieval); the
    # sanitized immutable events ARE the captured evidence. No scheduler is invoked here.
    from ecentric_workspace.approval_center.esign import service as svc
    res = svc.approve_and_sign("EC Payment Request", payment_request_name,
                               comment="[UAT PILOT PROBE]")
    dsr = res.get("signature_request")
    evidence = frappe.get_all("EC Digital Signature Event",
                              filters={"signature_request": dsr},
                              fields=["event_type", "event_time", "verification_result",
                                      "error_summary"], order_by="creation asc") if dsr else []
    return {"applied": True, "mode": "submitted", "signature_request": dsr,
            "readiness_ready": readiness["ready"], "evidence_events": evidence,
            "note": "Provider writes + signed-file retrieval proceed via the governed "
                    "worker/reconciler; review the sanitized events for evidence."}
