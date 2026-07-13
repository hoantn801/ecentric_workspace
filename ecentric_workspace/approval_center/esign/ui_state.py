# Copyright (c) 2026, eCentric and contributors
"""Backend-computed signing UI state (Phase 2).

The frontend renders ONLY what this returns; it never computes authorization, progress, or
which actions are permitted. Everything sensitive (token / password / Authorization / raw
provider payload / Base64 / private file path / exception trace) is excluded here. The
actual approve_and_sign / bulk / retrieval paths re-validate authoritatively under lock, so
a stale or forged UI can never cause a signature.
"""
import frappe

from ecentric_workspace.approval_center.esign import guard
from ecentric_workspace.approval_center.esign import package as pkgsvc
from ecentric_workspace.approval_center.esign import permissions as perms
from ecentric_workspace.approval_center.esign import service as svc

DSR = "EC Digital Signature Request"
PKG = "EC Digital Signature Package"

# Canonical human progress stages (Phase 2 contract). Ordered for display.
STAGES = ("Package Preparing", "Ready to Sign", "Creating Provider Document",
          "Provider Document Created", "Signing Submitted", "Verifying", "Signed",
          "Signed File Pending", "Signed File Stored", "Provider Rejected",
          "Retryable Failure", "Permanent Failure", "Manual Review")

# Map a DSR status to a display stage (package/ signed-bundle context refines it below).
_DSR_STAGE = {
    "Draft": "Ready to Sign", "Prepared": "Ready to Sign", "Queued": "Signing Submitted",
    "Provider Accepted": "Signing Submitted", "Verifying": "Verifying", "Signed": "Signed",
    "Approval Completed": "Signed File Pending", "Rejected": "Provider Rejected",
    "Retryable Failure": "Retryable Failure", "Permanent Failure": "Permanent Failure",
    "Verification Mismatch": "Manual Review", "Manual Review": "Manual Review",
    "Mapping Required": "Ready to Sign", "Placement Required": "Package Preparing",
    "Cancelled": "Ready to Sign", "Superseded": "Ready to Sign",
}

_SAFE_ERROR = {  # provider error_code -> safe, actionable Vietnamese message
    "create_outcome_unknown": "Kết quả tạo tài liệu chưa xác định - chờ đối soát (không gửi lại).",
    "scts_bulk_outcome_unknown": "Kết quả ký chưa xác định - hệ thống sẽ dò trạng thái, không gửi lại.",
    "binding_refused": "Ràng buộc chữ ký bị từ chối - cần kiểm tra ánh xạ người ký.",
    "package_hash_drift": "Gói tài liệu đã thay đổi - cần tạo phiên bản mới.",
}


def _primary_dsr(ar):
    """The most relevant DSR for display: the newest non-cancelled/superseded row."""
    rows = frappe.get_all(
        DSR, filters={"approval_request": ar}, order_by="creation desc",
        fields=["name", "status", "action", "request_attempt", "error_code",
                "manual_review_reason", "queued_at", "verified_at", "completed_at"])
    for r in rows:
        if r.status not in ("Cancelled", "Superseded"):
            return r
    return rows[0] if rows else None


def _stage(pkg, dsr, signed_complete):
    if not pkg or pkg.get("status") == "Draft":
        return "Package Preparing"
    if not dsr:
        return "Ready to Sign"
    stage = _DSR_STAGE.get(dsr.status, "Ready to Sign")
    if dsr.status == "Queued" and not pkg.get("scts_document_id"):
        stage = "Creating Provider Document"
    if dsr.status == "Provider Accepted" and pkg.get("scts_document_id"):
        stage = "Provider Document Created"
    if dsr.status == "Approval Completed":
        stage = "Signed File Stored" if signed_complete else "Signed File Pending"
    return stage


def signing_ui_state(business_doctype, business_name):
    """Read-only, sanitized signing state for the detail panel. Permission-checked."""
    perms.assert_can_view_business(business_doctype, business_name)
    status = svc.get_signing_status(business_doctype, business_name)
    readiness = svc.signing_readiness(business_doctype, business_name)
    ar = perms.business_approval_request(business_doctype, business_name)
    pkg = status.get("package")
    dsr = _primary_dsr(ar) if ar else None
    signed_complete = bool(pkg and pkg.get("signed_bundle_complete"))
    stage = _stage(pkg, dsr, signed_complete)

    safe_error = None
    review = False
    if dsr and dsr.error_code:
        safe_error = _SAFE_ERROR.get(dsr.error_code, "Có lỗi cần xử lý - xem nhật ký duyệt.")
    if dsr and dsr.status in ("Manual Review", "Verification Mismatch"):
        review = True
    if pkg:
        # a stored signed file whose provider_status flagged a hash mismatch => review
        mism = frappe.db.count("EC Digital Signature File",
                               {"package": pkg["name"], "provider_status": "SignedHashMismatch"})
        review = review or bool(mism)

    actions = _available_actions(readiness, stage, dsr, review)
    return {
        "enabled": status.get("enabled"),
        "stage": stage, "stages": list(STAGES),
        "package": _sanitized_package(pkg),
        "readiness": readiness,
        "can_sign": bool(readiness.get("ready")),
        "primary_request": _sanitized_dsr(dsr),
        "signed_bundle_complete": signed_complete,
        "manual_review": review,
        "safe_error": safe_error,
        "actions": actions,
    }


def _sanitized_package(pkg):
    if not pkg:
        return None
    keep = ("name", "status", "package_version", "package_hash", "scts_document_id",
            "provider", "environment", "signed_bundle_complete")
    out = {k: pkg.get(k) for k in keep}
    out["files"] = [{"name": f.get("name"), "file_name": f.get("file_name"),
                     "requires_signature": f.get("requires_signature"),
                     "is_supporting_document": f.get("is_supporting_document"),
                     "share_with_partner": f.get("share_with_partner"),
                     "is_pdf": f.get("is_pdf"), "sha256": f.get("sha256"),
                     "signed_file": bool(f.get("signed_file")),
                     "signed_file_sha256": f.get("signed_file_sha256"),
                     "provider_status": f.get("provider_status")}
                    for f in (pkg.get("files") or [])]
    out["placement_count"] = len(pkg.get("placements") or [])
    return out


def _sanitized_dsr(dsr):
    if not dsr:
        return None
    return {"name": dsr.name, "status": dsr.status, "action": dsr.action,
            "request_attempt": dsr.request_attempt, "queued_at": str(dsr.queued_at or ""),
            "verified_at": str(dsr.verified_at or ""),
            "completed_at": str(dsr.completed_at or ""),
            "manual_review_reason": dsr.manual_review_reason}


def _available_actions(readiness, stage, dsr, review):
    """Governed action hints (the backend still re-authorizes each). NEVER offers an action
    that resends AddDocument or bulk-process after an ambiguous write."""
    acts = ["refresh_readiness", "view_audit"]
    if readiness.get("ready"):
        acts.append("approve_and_sign")
    if stage in ("Signing Submitted", "Verifying", "Provider Document Created",
                 "Creating Provider Document", "Signed"):
        acts.append("poll_status")
    if stage == "Signed File Pending":
        acts.append("retry_signed_read")
    if stage == "Signed File Stored":
        acts.append("open_signed_file")
    if review:
        acts.append("open_review")
    return acts
