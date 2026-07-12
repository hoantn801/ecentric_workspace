# Copyright (c) 2026, eCentric and contributors
"""Background processing: submit worker, polling reconciler (authoritative - Phase 1
works with polling only), stale monitor, orphan-file scan.

Kill switch: site_config `ec_esign_scheduler_disabled: 1` (fail-safe: any config read
error => disabled; alerts precedent). POLL-FIRST rule: an uncertain previous attempt is
never blindly retried - the worker polls provider state and only submits when the
expected signer is provably unsigned.
"""
import frappe
from frappe.utils import add_to_date, now_datetime

from ecentric_workspace.approval_center.esign import binding
from ecentric_workspace.approval_center.esign import events
from ecentric_workspace.approval_center.esign import package as pkgsvc
from ecentric_workspace.approval_center.esign import service as svc
from ecentric_workspace.approval_center.esign.providers import get_adapter
from ecentric_workspace.approval_center.esign.providers.base import (
    ProviderError, SignatureProviderAdapter,
)
from ecentric_workspace.approval_center.esign.sanitize import safe_error

DSR = "EC Digital Signature Request"

# Server-derived provider action for bulk-process. The DSR.action -> provider
# transitionType mapping is authoritative here (never from frontend, never the numeric
# transition_id which is reserved for Workflow/transition reject/cancel operations).
_PROVIDER_TRANSITION = {"Sign": "approve"}


def _disabled():
    try:
        return bool(int(frappe.conf.get("ec_esign_scheduler_disabled") or 0))
    except Exception:
        return True  # fail-safe: broken config reads as DISABLED


def _settings_and_adapter(dsr):
    s = frappe.db.get_value("EC Digital Signature Provider Settings",
                            {"provider": dsr.provider, "environment": dsr.environment},
                            "*", as_dict=True)
    if not s:
        raise ProviderError("settings_missing", "provider settings row missing", retryable=False)
    return s, get_adapter(s)


def _ensure_provider_document(dsr, settings, adapter):
    """Creation trigger support: create the provider document lazily when the package
    has no scts_document_id yet ('Before First Signing Level' mode, and the reconciler
    backstop for 'On Business Submit' failures). Gated by allow_document_creation."""
    pkg = frappe.get_doc("EC Digital Signature Package", dsr.package)
    if pkg.scts_document_id:
        if pkg.status in ("Locked", "Provider Created"):
            # normalize forward to Active (idempotent)
            if pkg.status == "Locked":
                events.set_package_status(pkg.name, "Active", event_type="ProviderCreated")
            else:
                events.set_package_status(pkg.name, "Active")
        return pkg.scts_document_id
    if pkg.error_code == "create_outcome_unknown":
        # a prior AddDocument outcome is UNKNOWN (ambiguous write): the document may
        # already exist provider-side. NEVER auto-recreate. Retryable so the request
        # stays in-flight until an SM reconciles (sets scts_document_id or clears the
        # marker); the poll cap then escalates to Manual Review.
        raise ProviderError("scts_awaiting_create_reconciliation",
                            "AddDocument outcome unknown - awaiting manual reconciliation",
                            retryable=True)
    if not int(settings.get("allow_document_creation") or 0):
        raise ProviderError("document_creation_gated",
                            "allow_document_creation is OFF", retryable=True)
    # Lazy trigger ('Before First Signing Level'): the package is already Active
    # (signable) - provider-document creation is an ATTRIBUTE update, never a status
    # regression (Active has no backward edges by design). Only the submit-time path
    # (Locked / retry of a failed create) walks the Provider Creating chain.
    if pkg.status == "Locked":
        events.set_package_status(pkg.name, "Provider Creating", event_type="ProviderSubmitted")
    elif pkg.status == "Provider Create Failed":
        events.set_package_status(pkg.name, "Provider Creating", event_type="RetryScheduled")
    else:  # Active (lazy mode)
        events.emit("ProviderSubmitted", package=pkg.name)
    files = pkgsvc.package_files(pkg.name)
    prof = frappe.db.get_value(
        "EC Digital Signature Profile", pkg.profile,
        ["workflow_definition_id", "document_type_id", "company_id", "department_id",
         "document_template_id"], as_dict=True) or {}
    ctx = {
        "doc_code": pkg.doc_code_sent or pkg.business_name,
        "title": pkg.doc_title_sent or pkg.business_name,
        "amount": pkg.doc_amount_sent,
        "workflow_definition_id": prof.get("workflow_definition_id"),
        "document_type_id": prof.get("document_type_id"),
        "company_id": prof.get("company_id"),
        "department_id": prof.get("department_id"),
        "document_template_id": prof.get("document_template_id"),
        "files": [{"order": i, "name": f.file_name, "file_dsf": f.name,
                   "can_be_signed": f.requires_signature,
                   "is_supporting_document": f.is_supporting_document,
                   "share_with_partner": f.share_with_partner,
                   "content": pkgsvc.file_bytes(f.name)}  # private bytes; never logged
                  for i, f in enumerate(files)],
        "placements": [dict(p) for p in pkgsvc.package_placements(pkg.name)],
    }
    try:
        res = adapter.create_document(ctx)
    except ProviderError as e:
        if getattr(e, "ambiguous", False):
            # AddDocument outcome UNKNOWN: mark the package so no run ever recreates,
            # emit a sanitized audit event, and propagate the ambiguity (the worker moves
            # the DSR to Verifying; reconciliation is required before any recreate).
            frappe.db.set_value("EC Digital Signature Package", pkg.name,
                                {"error_code": "create_outcome_unknown",
                                 "error_message": safe_error(e)})
            events.emit("CreateOutcomeUnknown", package=pkg.name, error_summary=safe_error(e))
            raise
        if frappe.db.get_value("EC Digital Signature Package", pkg.name,
                               "status") == "Provider Creating":
            events.set_package_status(pkg.name, "Provider Create Failed", event_type="Failed",
                                      error_summary=safe_error(e))
        else:  # Active stays Active; failure lives on the DSR + Event
            events.emit("Failed", package=pkg.name, error_summary=safe_error(e))
        raise
    frappe.db.set_value("EC Digital Signature Package", pkg.name,
                        {"scts_document_id": res["document_id"],
                         "created_at_provider": now_datetime(),
                         "error_code": None, "error_message": None})
    by_order = {f["order"]: f.get("file_id") for f in res.get("files") or []}
    for i, f in enumerate(files):
        if by_order.get(i):
            frappe.db.set_value("EC Digital Signature File", f.name,
                                "scts_document_file_id", by_order[i])
    if frappe.db.get_value("EC Digital Signature Package", pkg.name,
                           "status") == "Provider Creating":
        events.set_package_status(pkg.name, "Provider Created", event_type="ProviderCreated",
                                  provider_txn_id=res["document_id"])
        events.set_package_status(pkg.name, "Active")
    else:  # Active (lazy mode): attribute update only
        events.emit("ProviderCreated", package=pkg.name, provider_txn_id=res["document_id"])
    return res["document_id"]


def process_signing_request(dsr_name):
    """State-aware worker. Safe to re-run at any time (reconciler re-entry)."""
    frappe.db.get_value(DSR, dsr_name, "name", for_update=True)
    dsr = frappe.db.get_value(DSR, dsr_name, "*", as_dict=True)
    if not dsr or dsr.status not in ("Queued", "Provider Accepted", "Verifying"):
        return
    try:
        settings, adapter = _settings_and_adapter(dsr)
        if dsr.status == "Queued":
            # PRE-WRITE GATE (S2B-A): the FULL ERP-side signer binding must hold BEFORE
            # any SCTS write on this run - document assembly (AddDocument) AND bulk-process.
            # Active approver == verified mapping == outbound userId == live owner of the
            # signatureId. Fails closed; NO role bypass (runs as the background user but is
            # bound to the persisted approver, never the session). Re-entry poll ticks are
            # reads only and are not gated here.
            binding.assert_outbound_binding(dsr_name, adapter)
        doc_id = _ensure_provider_document(dsr, settings, adapter)

        # POLL-FIRST: did a previous (uncertain) attempt already succeed?
        doc_state = adapter.poll_status(doc_id)
        expected = svc._expected_for(dsr)
        expected["document_id"] = doc_id
        vr = SignatureProviderAdapter.verify_signed_result(doc_state, expected)
        if vr.ok:
            if dsr.status != "Signed":
                events.set_dsr_status(dsr_name, "Signed",
                                      extra_fields={"verified_at": now_datetime()},
                                      event_type="Verified", verification_result=vr.reason)
            out = svc.verify_and_complete(dsr_name)
            _enqueue_signed_retrieval(dsr.package, out)
            return

        signer = doc_state.signer(dsr.effective_scts_user_id)
        if signer and signer.get("status") == "rejected":
            events.set_dsr_status(dsr_name, "Verification Mismatch",
                                  event_type="VerificationMismatch",
                                  verification_result="signer_rejected_at_provider")
            events.set_dsr_status(dsr_name, "Manual Review", event_type="ManualReview")
            return

        if dsr.status == "Queued":
            # Binding was asserted at the top of this run (before any write); the DSR is
            # locked for_update so state cannot drift within this transaction.
            # Submit exactly once from Queued; acceptance != success (async).
            tt = _PROVIDER_TRANSITION.get(dsr.action)
            if not tt:
                raise ProviderError("scts_no_provider_transition",
                                    "no provider transitionType mapped for action %r"
                                    % dsr.action, retryable=False)
            res = adapter.approve_and_sign([doc_id], dsr.effective_scts_user_id,
                                           dsr.effective_signature_id,
                                           transition_type=tt)  # 'approve' (never numeric)
            events.set_dsr_status(
                dsr_name, "Provider Accepted",
                extra_fields={"accepted_at": now_datetime(),
                              "bulk_job_transaction_id": res.get("bulk_job_transaction_id")},
                event_type="ProviderAccepted",
                provider_txn_id=res.get("bulk_job_transaction_id"),
                scts_effective_user=dsr.effective_scts_user_id)
            dsr.status = "Provider Accepted"

        # Single immediate re-poll; further ticks belong to the reconciler.
        doc_state = adapter.poll_status(doc_id)
        vr = SignatureProviderAdapter.verify_signed_result(doc_state, expected)
        if vr.ok:
            events.set_dsr_status(dsr_name, "Signed",
                                  extra_fields={"verified_at": now_datetime()},
                                  event_type="Verified", verification_result=vr.reason)
            out = svc.verify_and_complete(dsr_name)
            _enqueue_signed_retrieval(dsr.package, out)
            return
        if dsr.status == "Provider Accepted":
            events.set_dsr_status(dsr_name, "Verifying", event_type="PollTick",
                                  verification_result=vr.reason)
    except binding.BindingError as e:
        # SECURITY/VALIDATION refusal (wrong approver, mapping/signature mismatch,
        # inactive signature, allowlist, package/hash, non-UAT provider). This is NOT a
        # transient provider failure: NO provider write occurred, and it MUST NOT be
        # auto-retried. Terminal Permanent Failure + a governed dead-letter ToDo for
        # manual review (the binding layer already emitted BindingRejected).
        try:
            events.set_dsr_status(dsr_name, "Permanent Failure", event_type="Failed",
                                  extra_fields={"error_code": "binding_refused",
                                                "error_message": safe_error(e), "retryable": 0},
                                  error_summary=safe_error(e))
            _dead_letter_todo(dsr_name)
        except Exception:
            frappe.log_error(frappe.get_traceback(), "esign.tasks.binding_refused")
        return
    except ProviderError as e:
        if getattr(e, "ambiguous", False):
            # NON-IDEMPOTENT write outcome unknown (bulk-process lost/timeout/5xx): the
            # provider may already have accepted, so NEVER resend. Move to Verifying and
            # let the reconciler poll Document/{id}; append a sanitized immutable event.
            try:
                events.set_dsr_status(dsr_name, "Verifying", event_type="BulkOutcomeUnknown",
                                      extra_fields={"error_code": e.code},
                                      verification_result="scts_bulk_outcome_unknown",
                                      error_summary=safe_error(e))
            except Exception:
                frappe.log_error(frappe.get_traceback(), "esign.tasks.bulk_outcome_unknown")
            return
        target = "Retryable Failure" if e.retryable else "Permanent Failure"
        try:
            events.set_dsr_status(dsr_name, target, event_type="Failed",
                                  extra_fields={"error_code": e.code,
                                                "error_message": safe_error(e),
                                                "retryable": 1 if e.retryable else 0},
                                  error_summary=safe_error(e))
            if not e.retryable:
                pass  # Permanent Failure is terminal; sweep_stale raises the ops ToDo
        except Exception:
            frappe.log_error(frappe.get_traceback(), "esign.tasks.process_signing_request.state")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "esign.tasks.process_signing_request")


def poll_pending():
    """Cron */5: reconcile every non-terminal in-flight DSR. Bounded by
    max_poll_attempts (per settings) -> Manual Review."""
    if _disabled():
        return
    rows = frappe.get_all(DSR, filters={"status": ["in", ["Queued", "Provider Accepted",
                                                          "Verifying", "Retryable Failure",
                                                          "Signed"]]},
                          fields=["name", "status", "provider", "environment",
                                  "request_attempt"], limit_page_length=200)
    for r in rows:
        try:
            if r.status == "Signed":
                out = svc.verify_and_complete(r.name)
                _enqueue_signed_retrieval(frappe.db.get_value(DSR, r.name, "package"), out)
                continue
            if r.status == "Retryable Failure":
                cap = frappe.db.get_value("EC Digital Signature Provider Settings",
                                          {"provider": r.provider, "environment": r.environment},
                                          "max_poll_attempts") or 30
                polls = frappe.db.count("EC Digital Signature Event",
                                        {"signature_request": r.name,
                                         "event_type": ["in", ["PollTick", "Failed",
                                                               "RetryScheduled"]]})
                if polls >= int(cap):
                    events.set_dsr_status(r.name, "Manual Review", event_type="ManualReview",
                                          extra_fields={"manual_review_reason":
                                                        "max_poll_attempts_exceeded"})
                    continue
                events.set_dsr_status(r.name, "Queued", event_type="RetryScheduled",
                                      retry_no=polls + 1)
            process_signing_request(r.name)
        except Exception:
            frappe.log_error(frappe.get_traceback(), "esign.tasks.poll_pending %s" % r.name)


def sweep_stale():
    """Hourly: non-terminal DSRs untouched beyond stale_after_hours -> Manual Review +
    ONE deduped ops ToDo (order_retry dead-letter pattern) + sanitized Error Log."""
    if _disabled():
        return
    rows = frappe.get_all(DSR, filters={"status": ["in", ["Queued", "Provider Accepted",
                                                          "Verifying", "Retryable Failure",
                                                          "Signed"]]},
                          fields=["name", "status", "provider", "environment", "modified"],
                          limit_page_length=500)
    now = now_datetime()
    for r in rows:
        try:
            hours = frappe.db.get_value("EC Digital Signature Provider Settings",
                                        {"provider": r.provider, "environment": r.environment},
                                        "stale_after_hours") or 24
            if r.modified and r.modified > add_to_date(now, hours=-int(hours)):
                continue
            events.set_dsr_status(r.name, "Manual Review", event_type="ManualReview",
                                  extra_fields={"manual_review_reason": "stale_request"})
            _dead_letter_todo(r.name)
            frappe.log_error("esign stale request -> Manual Review: %s (was %s)"
                             % (r.name, r.status), "esign.tasks.sweep_stale")
        except Exception:
            frappe.log_error(frappe.get_traceback(), "esign.tasks.sweep_stale %s" % r.name)


def _dead_letter_todo(dsr_name):
    """Exactly one Open ToDo per Manual Review DSR, assigned to a System Manager
    (Administrator fallback)."""
    if frappe.db.exists("ToDo", {"reference_type": DSR, "reference_name": dsr_name,
                                 "status": "Open"}):
        return
    owner = None
    for u in frappe.get_all("Has Role", filters={"role": "System Manager",
                                                 "parenttype": "User"},
                            fields=["parent"], distinct=True, limit_page_length=20):
        r = frappe.db.get_value("User", u.parent, ["enabled", "user_type"], as_dict=True)
        if r and r.enabled and r.user_type == "System User" and u.parent != "Administrator":
            owner = u.parent
            break
    frappe.get_doc({"doctype": "ToDo", "allocated_to": owner or "Administrator",
                    "reference_type": DSR, "reference_name": dsr_name,
                    "description": "esign: signing request needs manual review",
                    "assigned_by": "Administrator"}).insert(ignore_permissions=True)


def _enqueue_signed_retrieval(package_name, complete_result):
    """After a VERIFIED completion, queue signed-PDF retrieval. It is a separate job:
    a download failure never reverses the already-verified signature or downgrades the
    terminal DSR - it only leaves signed_bundle_complete=0 for a safe read retry."""
    if not package_name or not (complete_result or {}).get("completed"):
        return
    try:
        frappe.enqueue(
            "ecentric_workspace.approval_center.esign.signed_files.retrieve_and_store_for_package",
            package_name=package_name, queue="default", timeout=600,
            job_name="esign_signed_%s" % package_name, enqueue_after_commit=True)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "esign.tasks._enqueue_signed_retrieval")


def retrieve_signed_bundles():
    """Cron (kill-switched): retry signed-file retrieval for packages whose approval is
    terminal-completed but whose signed bundle is not yet complete. Safe read only; never
    resends AddDocument or bulk-process."""
    if _disabled():
        return
    rows = frappe.get_all(
        "EC Digital Signature Package",
        filters={"scts_document_id": ["is", "set"], "signed_bundle_complete": 0},
        fields=["name"], limit_page_length=200)
    from ecentric_workspace.approval_center.esign import signed_files
    for r in rows:
        # only retry for packages with a terminal-completed approval DSR
        done = frappe.db.exists(DSR, {"package": r.name, "status": "Approval Completed"})
        if not done:
            continue
        try:
            signed_files.retrieve_and_store_for_package(r.name)
        except Exception:
            frappe.log_error(frappe.get_traceback(),
                             "esign.tasks.retrieve_signed_bundles %s" % r.name)


def orphan_file_scan():
    """Daily, FLAG-ONLY (no auto-delete): Files attached to signing-profiled business
    docs with no EC Digital Signature File row and age > 24h."""
    if _disabled():
        return
    doctypes = frappe.get_all("EC Digital Signature Profile", filters={"enabled": 1},
                              pluck="business_doctype", distinct=True)
    cutoff = add_to_date(now_datetime(), hours=-24)
    for dt in set(doctypes):
        try:
            tracked = set(frappe.get_all("EC Digital Signature File", pluck="file"))
            files = frappe.get_all("File", filters={"attached_to_doctype": dt,
                                                    "creation": ["<", cutoff]},
                                   fields=["name", "attached_to_name"],
                                   limit_page_length=500)
            orphans = [f.name for f in files if f.name not in tracked]
            if orphans:
                frappe.log_error("esign orphan-file scan (%s): %s untracked file(s): %s"
                                 % (dt, len(orphans), ", ".join(orphans[:20])),
                                 "esign.tasks.orphan_file_scan")
        except Exception:
            frappe.log_error(frappe.get_traceback(), "esign.tasks.orphan_file_scan %s" % dt)
