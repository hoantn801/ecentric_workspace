# Copyright (c) 2026, eCentric and contributors
"""Signed-file hash-mismatch review resolution (Phase 5).

When a re-retrieved signed file returns a DIFFERENT SHA than the accepted one,
signed_files._store_hash_mismatch stores ONE private review candidate, keeps the accepted
signed_file pointer unchanged, marks provider_status=SignedHashMismatch, and opens one
deduplicated review ToDo. This module lets a privileged reviewer resolve that condition.

Every resolution: requires System Manager; is idempotent (a row with no pending candidate
is a no-op); appends an immutable sanitized event; preserves BOTH File records; updates
pointers atomically under a row lock; and never alters the original package hash or the
original approved (unsigned) attachment.
"""
import frappe
from frappe import _
from frappe.utils import now_datetime

from ecentric_workspace.approval_center.esign import events
from ecentric_workspace.approval_center.esign import permissions as perms

DSF = "EC Digital Signature File"
PKG = "EC Digital Signature Package"


def pending_reviews(package_name):
    """List DSF rows in this package awaiting signed-file review (read, SM only)."""
    perms.assert_system_manager()
    rows = frappe.get_all(DSF, filters={"package": package_name,
                                        "provider_status": "SignedHashMismatch"},
                          fields=["name", "file_name", "signed_file", "signed_file_sha256",
                                  "signed_review_candidate", "signed_review_sha256"])
    return {"package": package_name, "rows": rows}


def _load_locked(dsf_name):
    frappe.db.get_value(DSF, dsf_name, "name", for_update=True)  # row lock
    row = frappe.db.get_value(DSF, dsf_name,
                              ["name", "package", "file_name", "provider_status",
                               "signed_file", "signed_file_sha256",
                               "signed_review_candidate", "signed_review_sha256"],
                              as_dict=True)
    if not row:
        frappe.throw(_("Không tìm thấy dòng tệp ký."))
    return row


def _recompute_bundle_complete(package_name):
    files = frappe.get_all(DSF, filters={"package": package_name, "requires_signature": 1},
                           fields=["signed_file", "provider_status"])
    complete = bool(files) and all(
        f.signed_file and f.provider_status != "SignedHashMismatch" for f in files)
    frappe.db.set_value(PKG, package_name, "signed_bundle_complete", 1 if complete else 0)
    return complete


def _close_review_todo(package_name):
    for t in frappe.get_all("ToDo", filters={"reference_type": PKG,
                                             "reference_name": package_name,
                                             "status": "Open"}, pluck="name"):
        frappe.db.set_value("ToDo", t, "status", "Closed")


def _resolve(dsf_name, action, reason=None):
    perms.assert_system_manager()
    actor = frappe.session.user
    row = _load_locked(dsf_name)
    if row.provider_status != "SignedHashMismatch" or not row.signed_review_candidate:
        return {"resolved": False, "reason": "no_pending_review", "file": dsf_name}
    candidate = row.signed_review_candidate
    cand_sha = row.signed_review_sha256
    prior = row.signed_file

    if action == "accept":
        # promote candidate to the accepted signed file (new version). Both File records
        # are preserved; the original approved attachment (row.file) is untouched.
        frappe.db.set_value(DSF, dsf_name, {
            "signed_file": candidate, "signed_file_sha256": cand_sha,
            "provider_status": "Signed", "signed_retrieved_at": now_datetime(),
            "signed_review_candidate": None, "signed_review_sha256": None})
        evt = "SignedFileReviewAccepted"
    elif action == "reject":
        # discard the candidate (File record preserved); keep the accepted signed file.
        frappe.db.set_value(DSF, dsf_name, {
            "provider_status": "Signed",
            "signed_review_candidate": None, "signed_review_sha256": None})
        evt = "SignedFileReviewRejected"
    elif action == "keep":
        # explicitly keep existing accepted file; clear the pending marker.
        frappe.db.set_value(DSF, dsf_name, {
            "provider_status": "Signed",
            "signed_review_candidate": None, "signed_review_sha256": None})
        evt = "SignedFileReviewKept"
    else:
        frappe.throw(_("Hành động xử lý không hợp lệ."))

    events.emit(evt, package=row.package, erp_actor=actor,
                verification_result=(reason or action)[:130],
                request_meta={"file": row.file_name, "prior_signed_file": prior,
                              "candidate_file": candidate, "candidate_sha256": cand_sha,
                              "accepted": action == "accept"})
    complete = _recompute_bundle_complete(row.package)
    if complete:
        _close_review_todo(row.package)
    return {"resolved": True, "action": action, "file": dsf_name,
            "signed_bundle_complete": complete}


def accept_candidate(dsf_name, reason=None):
    return _resolve(dsf_name, "accept", reason)


def reject_candidate(dsf_name, reason=None):
    return _resolve(dsf_name, "reject", reason)


def keep_existing(dsf_name, reason=None):
    return _resolve(dsf_name, "keep", reason)
