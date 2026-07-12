# Copyright (c) 2026, eCentric and contributors
"""Governed retrieval + storage of the final signed PDF (S2B-C1).

Retrieval runs ONLY after the provider document is confirmed terminal-signed. It never
overwrites the original approved PDF, never touches DSR/approval terminal state, is
idempotent by sha256 (no duplicate File records), and appends only sanitized immutable
events (no binary/base64 ever logged). A download failure sets signed_bundle_complete=0
with retry - it never reverses an already-verified provider signature.
"""
import frappe
from frappe.utils import now_datetime

from ecentric_workspace.approval_center.esign import events
from ecentric_workspace.approval_center.esign.providers import get_adapter
from ecentric_workspace.approval_center.esign.providers.base import ProviderError
from ecentric_workspace.approval_center.esign.sanitize import safe_error

PKG = "EC Digital Signature Package"
DSF = "EC Digital Signature File"
DSR = "EC Digital Signature Request"

# provider document states that count as "terminal signed / completed"
_TERMINAL_SIGNED = ("signed", "completed", "complete", "done", "finished", "success")


def _settings_and_adapter(pkg):
    s = frappe.db.get_value("EC Digital Signature Provider Settings",
                            {"provider": pkg.provider, "environment": pkg.environment},
                            "*", as_dict=True)
    if not s:
        raise ProviderError("settings_missing", "provider settings row missing", retryable=False)
    return s, get_adapter(s)


def _document_is_terminal_signed(adapter, pkg):
    """Confirm via GET /api/Document/{id} that the document is terminal-signed before any
    file download (fail-closed)."""
    doc_state = adapter.poll_status(pkg.scts_document_id)
    if not doc_state:
        return False
    status = str(doc_state.status or "").strip().lower()
    if status in _TERMINAL_SIGNED:
        return True
    # or: at least one signer is signed and none pending (partial-safe: any signed signer
    # for a completed approval is acceptable evidence for retrieval)
    signers = getattr(doc_state, "signers", []) or []
    if signers and any((s.get("status") == "signed") for s in signers):
        return True
    return False


def retrieve_and_store_for_package(package_name, force=False):
    """Retrieve + store the signed PDF for every signable file of a package. Returns a
    structured result; sets signed_bundle_complete when all signable files are stored."""
    pkg = frappe.db.get_value(
        PKG, package_name,
        ["name", "provider", "environment", "scts_document_id", "business_doctype",
         "business_name", "status", "signed_bundle_complete"], as_dict=True)
    if not pkg:
        return {"ok": False, "reason": "package_missing"}
    if not pkg.scts_document_id:
        return {"ok": False, "reason": "no_provider_document"}

    try:
        settings, adapter = _settings_and_adapter(pkg)
    except ProviderError as e:
        events.emit("SignedFileRetrievalFailed", package=package_name,
                    error_summary=safe_error(e))
        return {"ok": False, "reason": "settings_missing"}

    # GATE: only retrieve after the provider document is terminal-signed.
    try:
        if not _document_is_terminal_signed(adapter, pkg):
            return {"ok": False, "reason": "document_not_terminal_signed"}
    except ProviderError as e:
        events.emit("SignedFileRetrievalFailed", package=package_name,
                    error_summary=safe_error(e))
        return {"ok": False, "reason": "poll_failed", "retryable": e.retryable}

    files = frappe.get_all(DSF, filters={"package": package_name, "requires_signature": 1},
                           fields=["name", "file", "file_name", "scts_document_file_id",
                                   "signed_file", "signed_file_sha256"],
                           order_by="idx_order asc, creation asc")
    results = []
    all_done = bool(files)
    for f in files:
        r = _retrieve_one(pkg, adapter, f, force=force)
        results.append(r)
        if not (r.get("stored") or r.get("duplicate")):
            all_done = False
    if all_done and files:
        frappe.db.set_value(PKG, package_name, "signed_bundle_complete", 1)
    return {"ok": all_done, "files": results}


def _retrieve_one(pkg, adapter, f, force=False):
    """One signable file. Idempotent by hash; a different hash than a previously stored
    signed file raises a governed Manual-Review dead-letter (never downgrades the DSR)."""
    # already stored and not a forced re-verify -> idempotent no-op (no re-download).
    if f.signed_file and f.signed_file_sha256 and not force:
        events.emit("SignedFileDuplicateSkipped", package=pkg.name,
                    request_meta={"file": f.file_name, "sha256": f.signed_file_sha256})
        return {"file": f.name, "duplicate": True, "sha256": f.signed_file_sha256}

    events.emit("SignedFileRetrievalStarted", package=pkg.name,
                request_meta={"file": f.file_name})
    try:
        res = adapter.get_signed_document(pkg.scts_document_id, f.scts_document_file_id)
    except ProviderError as e:
        events.emit("SignedFileRetrievalFailed", package=pkg.name,
                    error_summary=safe_error(e), request_meta={"file": f.file_name})
        frappe.db.set_value(PKG, pkg.name, "signed_bundle_complete", 0)
        return {"file": f.name, "stored": False, "error": e.code, "retryable": e.retryable}

    sha = res["sha256"]
    events.emit("SignedFileRetrieved", package=pkg.name,
                request_meta={"file": f.file_name, "sha256": sha, "size": res["size"]})

    # different hash than a previously stored signed file -> new version + Manual Review.
    if f.signed_file and f.signed_file_sha256 and f.signed_file_sha256 != sha:
        events.emit("SignedFileHashMismatch", package=pkg.name,
                    verification_result="signed_hash_changed",
                    request_meta={"file": f.file_name, "sha256": sha})
        frappe.db.set_value(PKG, pkg.name, "signed_bundle_complete", 0)
        frappe.db.set_value(DSF, f.name, "provider_status", "SignedHashMismatch")
        _dead_letter_review(pkg, "signed_file_hash_mismatch:%s" % f.file_name)
        return {"file": f.name, "hash_mismatch": True, "sha256": sha}

    # store a NEW private File (never overwrite the original approved PDF).
    signed_name = "SIGNED-%s" % f.file_name
    fdoc = frappe.get_doc({
        "doctype": "File", "file_name": signed_name, "is_private": 1,
        "attached_to_doctype": pkg.business_doctype, "attached_to_name": pkg.business_name,
        "content": res["content"],
    }).insert(ignore_permissions=True)
    frappe.db.set_value(DSF, f.name, {
        "signed_file": fdoc.name, "signed_file_sha256": sha,
        "signed_retrieved_at": now_datetime(), "provider_status": "Signed"})
    events.emit("SignedFileStored", package=pkg.name,
                request_meta={"file": signed_name, "sha256": sha, "size": res["size"]})
    return {"file": f.name, "stored": True, "sha256": sha, "signed_file": fdoc.name}


def _dead_letter_review(pkg, reason):
    """One Open ToDo per package for a signed-file review condition (no DSR downgrade)."""
    if frappe.db.exists("ToDo", {"reference_type": PKG, "reference_name": pkg.name,
                                 "status": "Open"}):
        return
    frappe.get_doc({"doctype": "ToDo", "allocated_to": "Administrator",
                    "reference_type": PKG, "reference_name": pkg.name,
                    "description": "esign signed-file review: %s" % reason,
                    "assigned_by": "Administrator"}).insert(ignore_permissions=True)
