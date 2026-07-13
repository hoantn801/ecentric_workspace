# Copyright (c) 2026, eCentric and contributors
"""Controlled SCTS UAT pilot: read-only readiness checklist + an opt-in, heavily gated
manual probe (S2B-C1). Backend-authoritative; returns SAFE identifiers only - never
tokens, passwords, or PDF/base64 content. Nothing here runs automatically.

ACTOR SEMANTICS (release fix): the OPERATOR (caller / frappe.session.user, a System
Manager) is separated from the TARGET APPROVER (the persisted active approver resolved
from the Approval Request + runtime level). Mapping / signature / allowlist / profile
checks apply to the ACTIVE APPROVER, never blindly to the SM caller. apply=1 additionally
requires the caller to BE the active approver (System-Manager role alone is never a bypass).
"""
import frappe
from frappe import _
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


def _resolve_active_approver(ar, level, caller):
    """The persisted active approver for (Approval Request, runtime level). Prefer the
    caller when the caller themselves holds a pending row (self readiness check); otherwise
    the first pending approver row. Resolved entirely from Approval Engine state."""
    if caller and perms.pending_approver_row(ar, level, caller):
        return caller
    rows = frappe.get_all("EC Approval Request Approver",
                          filters={"approval_request": ar, "level_no": level,
                                   "status": "Pending"},
                          pluck="approver", order_by="idx asc, creation asc",
                          limit_page_length=1)
    return rows[0] if rows else None


def uat_pilot_readiness(payment_request_name=None):
    """Administrator/System Manager-only READ-ONLY readiness checklist. Mapping / signature
    / allowlist / profile checks evaluate the ACTIVE APPROVER (persisted), not the caller.
    Returns {ready, blocking_items[], warnings[], checks{}, caller_user, active_approver}
    with safe identifiers only."""
    perms.assert_system_manager()
    caller = frappe.session.user
    checks = {}
    blocking = []
    warnings = []

    def chk(key, ok, blocking_flag=True, detail=None):
        checks[key] = {"ok": bool(ok), "detail": detail}
        if not ok:
            (blocking if blocking_flag else warnings).append(key)
        return ok

    # ---- resolve target approver from persisted Approval Engine state (if a PR given) ----
    ar = None
    req = None
    approval_type = None
    active_approver = None
    if payment_request_name and frappe.db.exists("EC Payment Request", payment_request_name):
        approval_type = frappe.db.get_value("EC Payment Request", payment_request_name,
                                            "approval_type")
        ar = perms.business_approval_request("EC Payment Request", payment_request_name)
        if ar:
            req = frappe.db.get_value("EC Approval Request", ar,
                                      ["approval_status", "current_level"], as_dict=True)
            if req and req.current_level:
                active_approver = _resolve_active_approver(ar, req.current_level, caller)
    # the SIGNER subject of mapping/allowlist/signature checks: the active approver when a
    # PR is targeted, otherwise the caller (a general provider-side self diagnostic).
    signer = active_approver or (caller if not payment_request_name else None)

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
        # allowlist is evaluated for the ACTIVE APPROVER (the signer), not the SM caller.
        chk("active_approver_in_uat_allowlist",
            bool(signer) and signer.lower() in allowed)

    # ---- profile: for a TARGETED PR use ONLY the exact active profile resolved for its
    # approval_type (no fallback to an arbitrary enabled SCTS profile); a general enabled
    # profile is used only for the no-PR provider diagnostic. ----
    prof_row = None
    if payment_request_name:
        if approval_type:
            prof_name = guard.get_active_profile("EC Payment Request", approval_type)
            prof_row = frappe.db.get_value("EC Digital Signature Profile", prof_name, "*",
                                           as_dict=True) if prof_name else None
        chk("exact_active_profile_for_approval_type", bool(prof_row))
    else:
        cand = frappe.get_all("EC Digital Signature Profile",
                              filters={"business_doctype": "EC Payment Request",
                                       "provider": "SCTS", "enabled": 1},
                              fields=["*"], limit_page_length=1)
        prof_row = cand[0] if cand else None
        chk("active_profile_exists", bool(prof_row))
    if prof_row:
        chk("workflow_definition_id_present", bool(prof_row.get("workflow_definition_id")))
        chk("document_type_id_present", bool(prof_row.get("document_type_id")))
        chk("company_id_present", bool(prof_row.get("company_id")))
        chk("department_id_present", bool(prof_row.get("department_id")))
        chk("document_template_id_present", bool(prof_row.get("document_template_id")),
            blocking_flag=False)

    # ---- mapping (of the ACTIVE APPROVER, never the SM caller) ----
    if signer:
        maps = frappe.get_all("EC SCTS User Mapping",
                              filters={"frappe_user": signer, "environment": "UAT",
                                       "active": 1},
                              fields=["name", "scts_user_id", "signature_id", "mapping_status"])
        chk("approver_exactly_one_active_mapping", len(maps) == 1)
        if len(maps) == 1:
            m = maps[0]
            chk("approver_mapped_scts_user_id_present", bool(m.scts_user_id))
            chk("approver_signature_id_present", bool(m.signature_id))
            chk("approver_mapping_verified", m.mapping_status == "Verified")
    else:
        chk("active_approver_resolved", False)

    # ---- payment request ----
    if payment_request_name:
        chk("payment_request_exists", frappe.db.exists("EC Payment Request", payment_request_name))
        chk("approval_request_active", bool(ar))
        if ar:
            chk("level_resolved", bool(req and req.current_level))
            chk("active_approver_resolved", bool(active_approver))
            if req and req.current_level and approval_type:
                chk("level_requires_signature",
                    guard.level_requires_signature("EC Payment Request", approval_type,
                                                   req.current_level))
            # operator (caller) vs signer: a WARNING for readiness (SM may inspect another
            # approver's readiness); apply=1 turns this into a hard block downstream.
            chk("caller_is_active_approver", caller == active_approver, blocking_flag=False)
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
                # fail-closed structured file readiness (no traceback escapes).
                chk("has_signable_files", bool(sfiles))
                chk("all_signable_files_have_file_link", bool(sfiles) and all(f.file for f in sfiles))
                priv_ok = bool(sfiles)
                for ff in sfiles:
                    if not ff.file or not frappe.db.exists("File", ff.file) \
                            or not frappe.db.get_value("File", ff.file, "is_private"):
                        priv_ok = False
                chk("all_signable_files_exist_and_private", priv_ok)
                chk("all_signable_files_are_pdf", bool(sfiles) and all(f.is_pdf for f in sfiles))
                try:
                    hashes_ok = bool(sfiles) and all(
                        f.sha256 == pkgsvc.hashing.sha256_bytes(pkgsvc.file_bytes(f.name))
                        for f in sfiles)
                except Exception as _e:
                    hashes_ok = False  # missing/unreadable File -> blocking item, not a crash
                chk("file_hashes_match", hashes_ok, detail=None)
                try:
                    placements_ok = not pkgsvc.preflight_for_lock(pkg_name)
                except Exception:
                    placements_ok = False
                chk("placements_complete", placements_ok)
                chk("no_active_duplicate_dsr",
                    frappe.db.count(DSR, {"package": pkg_name,
                                          "status": ["in", ["Queued", "Provider Accepted",
                                                            "Verifying", "Signed"]]}) <= 1)
                chk("no_unresolved_ambiguous_create",
                    (pkg.error_code != "create_outcome_unknown") if pkg else True)

    ready = len(blocking) == 0
    return {"ready": ready, "blocking_items": blocking, "warnings": warnings,
            "checks": checks, "caller_user": caller, "active_approver": active_approver,
            "signer_evaluated": signer, "payment_request": payment_request_name}


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
    preview with NO external calls and NO approval mutation. apply=1 may drive the real UAT
    sequence ONLY when: every readiness item passes; the environment is UAT; the caller IS
    the active approver; the caller is UAT-allowlisted; the PR is explicitly UAT/VOID-named.
    System-Manager role alone is NEVER a bypass; all strict signer-binding invariants remain
    mandatory. Production is always rejected. Never touches secrets."""
    perms.assert_system_manager()
    apply = int(apply or 0)

    if not frappe.db.exists("EC Payment Request", payment_request_name):
        frappe.throw(_("Không tìm thấy Payment Request."))
    readiness = uat_pilot_readiness(payment_request_name)
    caller = readiness["caller_user"]
    active_approver = readiness["active_approver"]

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
        # readiness + redacted preview ONLY: no external call, no approval mutation.
        return {"applied": False, "mode": "preview", "ready": readiness["ready"],
                "caller_user": caller, "active_approver": active_approver,
                "readiness": readiness, "payload_preview": preview,
                "note": "apply=0: no external SCTS calls, no approval mutation."}

    # ---- apply=1 hard gates (role alone is never enough) ----
    if not _is_uat_void_named(payment_request_name):
        frappe.throw(_("Probe apply=1 chỉ chạy trên Payment Request đánh dấu UAT/VOID/TEST."),
                     frappe.PermissionError)
    env = frappe.db.get_value(SETTINGS_DT, {"provider": "SCTS", "environment": "UAT"},
                              "environment")
    if env != "UAT":
        frappe.throw(_("Probe apply=1 chỉ chạy trên môi trường UAT."), frappe.PermissionError)
    # the CALLER must be the persisted active approver - System Manager is not a signer.
    if not active_approver or caller != active_approver:
        return {"applied": False, "mode": "blocked", "reason": "caller_not_active_approver",
                "caller_user": caller, "active_approver": active_approver,
                "readiness": readiness}
    if not readiness["ready"]:
        return {"applied": False, "mode": "blocked", "reason": "readiness_incomplete",
                "caller_user": caller, "active_approver": active_approver,
                "readiness": readiness}

    # Governed real submit reuses the entire verified path (strict signer binding,
    # AddDocument, bulk-process transitionType=approve, poll, completion, signed-file
    # retrieval). The sanitized immutable events ARE the captured evidence. No scheduler
    # is invoked here. The caller == active approver, so approve_and_sign authorises as
    # the true signer under the same binding invariants.
    from ecentric_workspace.approval_center.esign import service as svc
    res = svc.approve_and_sign("EC Payment Request", payment_request_name,
                               comment="[UAT PILOT PROBE]")
    dsr = res.get("signature_request")
    evidence = frappe.get_all("EC Digital Signature Event",
                              filters={"signature_request": dsr},
                              fields=["event_type", "event_time", "verification_result",
                                      "error_summary"], order_by="creation asc") if dsr else []
    return {"applied": True, "mode": "submitted", "signature_request": dsr,
            "caller_user": caller, "active_approver": active_approver,
            "readiness_ready": readiness["ready"], "evidence_events": evidence,
            "note": "Provider writes + signed-file retrieval proceed via the governed "
                    "worker/reconciler; review the sanitized events for evidence."}
