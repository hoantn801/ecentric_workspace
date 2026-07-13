# Copyright (c) 2026, eCentric and contributors
"""Governed retrieval + storage of the final signed PDF (S2B-C1, hardened).

Retrieval runs ONLY after BOTH gates hold (fail-closed):
  1. the package has exactly one DSR in 'Approval Completed';
  2. GET /api/Document/{id} proves a terminal-signed document - an explicitly recognized
     terminal status, OR a signer-based fallback in which EVERY expected internal signer
     is present and signed, NO signer is pending/rejected/unknown, and signer identities
     match the persisted expectations. "Any signer signed" is NOT accepted; a partially
     signed document is blocked.

Storage is concurrency-safe and idempotent (row lock + reload; one accepted File per
signable row), never overwrites the original approved PDF, never touches DSR/approval
terminal state, and appends only sanitized events (no binary/base64 ever logged).
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

_TERMINAL_SIGNED = ("signed", "completed", "complete", "done", "finished", "success")


def _settings_and_adapter(pkg):
    s = frappe.db.get_value("EC Digital Signature Provider Settings",
                            {"provider": pkg.provider, "environment": pkg.environment},
                            "*", as_dict=True)
    if not s:
        raise ProviderError("settings_missing", "provider settings row missing", retryable=False)
    return s, get_adapter(s)


def _expected_signers(package_name):
    """The internal SCTS signer identities ERP submitted for this package (one per Sign
    DSR). Used to prove document identity in the signer-based fallback."""
    ids = frappe.get_all(DSR, filters={"package": package_name, "action": "Sign"},
                         pluck="effective_scts_user_id")
    return {str(i) for i in ids if i}


def _terminal_signed_ok(adapter, pkg):
    """(ok, reason). Fail-closed: requires exactly one Approval Completed DSR AND a
    provider-verified terminal-signed document."""
    completed = frappe.get_all(DSR, filters={"package": pkg.name,
                                             "status": "Approval Completed"}, pluck="name")
    if len(completed) != 1:
        return False, "not_exactly_one_completed_dsr:%d" % len(completed)

    doc = adapter.poll_status(pkg.scts_document_id)
    if not doc:
        return False, "no_document_state"
    status = str(getattr(doc, "status", "") or "").strip().lower()
    signers = getattr(doc, "signers", []) or []

    # any signer explicitly pending/rejected/unknown -> partial -> BLOCK (even if the
    # top-level status claims terminal).
    for s in signers:
        st = str(s.get("status") or "").strip().lower()
        if st != "signed":
            return False, "non_signed_signer_present:%s" % (st or "unknown")

    if status in _TERMINAL_SIGNED:
        return True, "terminal_status"

    # signer-based fallback: EVERY expected signer present + signed; identities match.
    expected = _expected_signers(pkg.name)
    if not expected:
        return False, "no_expected_signers"
    if not signers:
        return False, "no_signers"
    present = {str(s.get("user_id")) for s in signers}
    for e in expected:
        if e not in present:
            return False, "expected_signer_absent:%s" % e
    for s in signers:
        if str(s.get("user_id")) not in expected:
            return False, "unexpected_signer_identity"
    return True, "all_expected_signers_signed"


def retrieve_and_store_for_package(package_name, force=False):
    """Retrieve + store the signed PDF for every signable file. Gated fail-closed
    (Approval Completed + terminal-signed provider)."""
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
        events.emit("SignedFileRetrievalFailed", package=package_name, error_summary=safe_error(e))
        return {"ok": False, "reason": "settings_missing"}

    try:
        ok, reason = _terminal_signed_ok(adapter, pkg)
    except ProviderError as e:
        events.emit("SignedFileRetrievalFailed", package=package_name, error_summary=safe_error(e))
        return {"ok": False, "reason": "poll_failed", "retryable": e.retryable}
    if not ok:
        return {"ok": False, "reason": "not_terminal_signed", "detail": reason}

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
    """One signable file. Concurrency-safe + idempotent: after download+SHA the DSF row is
    locked and reloaded; a matching stored SHA is a no-op (even with force); a different
    SHA stores a deduplicated review candidate and keeps the accepted pointer unchanged."""
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

    # concurrency-safe commit: lock the row, reload under the lock.
    frappe.db.get_value(DSF, f.name, "name", for_update=True)
    cur = frappe.db.get_value(DSF, f.name, ["signed_file", "signed_file_sha256"], as_dict=True)

    if cur.signed_file and cur.signed_file_sha256 and cur.signed_file_sha256 == sha:
        events.emit("SignedFileDuplicateSkipped", package=pkg.name,
                    request_meta={"file": f.file_name, "sha256": sha})
        return {"file": f.name, "duplicate": True, "sha256": sha}

    if cur.signed_file and cur.signed_file_sha256 and cur.signed_file_sha256 != sha:
        return _store_hash_mismatch(pkg, f, sha, res["content"], res["size"])

    fdoc = frappe.get_doc({
        "doctype": "File", "file_name": "SIGNED-%s" % f.file_name, "is_private": 1,
        "attached_to_doctype": pkg.business_doctype, "attached_to_name": pkg.business_name,
        "content": res["content"],
    }).insert(ignore_permissions=True)
    frappe.db.set_value(DSF, f.name, {
        "signed_file": fdoc.name, "signed_file_sha256": sha,
        "signed_retrieved_at": now_datetime(), "provider_status": "Signed"})
    events.emit("SignedFileStored", package=pkg.name,
                request_meta={"file": "SIGNED-%s" % f.file_name, "sha256": sha, "size": res["size"]})
    return {"file": f.name, "stored": True, "sha256": sha, "signed_file": fdoc.name}


def _store_hash_mismatch(pkg, f, sha, content, size):
    """A different signed-file SHA: store ONE deduplicated private review candidate, keep
    the previously accepted signed_file pointer, mark SignedHashMismatch, leave
    signed_bundle_complete=0, and open one deduped review ToDo. Never overwrites."""
    review_name = "REVIEW-%s-%s" % (sha[:8], f.file_name)
    existing = frappe.db.exists("File", {"attached_to_doctype": pkg.business_doctype,
                                         "attached_to_name": pkg.business_name,
                                         "file_name": review_name})
    candidate = existing
    if not existing:
        candidate = frappe.get_doc({
            "doctype": "File", "file_name": review_name, "is_private": 1,
            "attached_to_doctype": pkg.business_doctype, "attached_to_name": pkg.business_name,
            "content": content,
        }).insert(ignore_permissions=True).name
    frappe.db.set_value(PKG, pkg.name, "signed_bundle_complete", 0)
    frappe.db.set_value(DSF, f.name, {"provider_status": "SignedHashMismatch",
                                      "signed_review_candidate": candidate,
                                      "signed_review_sha256": sha})
    events.emit("SignedFileHashMismatch", package=pkg.name,
                verification_result="signed_hash_changed",
                request_meta={"file": f.file_name, "sha256": sha,
                              "candidate_file": candidate, "size": size,
                              "duplicate_candidate": bool(existing)})
    _dead_letter_review(pkg, "signed_file_hash_mismatch:%s" % f.file_name)
    return {"file": f.name, "hash_mismatch": True, "sha256": sha, "candidate_file": candidate}


# Stable category marker so ONLY the signed-file-review ToDo is deduped/closed - never an
# unrelated reconciliation / manual-review / approval ToDo on the same package.
REVIEW_TODO_MARKER = "[EC-ESIGN-SIGNED-FILE-REVIEW]"


def _dead_letter_review(pkg, reason):
    """One Open signed-file-review ToDo per package (deduped by the stable marker; no DSR
    downgrade). Other ToDos on the same package are untouched."""
    if frappe.db.exists("ToDo", {"reference_type": PKG, "reference_name": pkg.name,
                                 "status": "Open",
                                 "description": ["like", "%" + REVIEW_TODO_MARKER + "%"]}):
        return
    frappe.get_doc({"doctype": "ToDo", "allocated_to": "Administrator",
                    "reference_type": PKG, "reference_name": pkg.name,
                    "description": "%s esign signed-file review: %s" % (REVIEW_TODO_MARKER, reason),
                    "assigned_by": "Administrator"}).insert(ignore_permissions=True)
