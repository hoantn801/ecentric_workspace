# Copyright (c) 2026, eCentric and contributors
"""Governed retrieval + storage of the final signed PDF (S2B-C1, hardened).

Retrieval runs ONLY after BOTH gates hold (fail-closed):
  1. every signing leg is finished: at least one DSR in 'Approval Completed' and none still
     in flight (one leg per signature - requester plus each signing approval level);
  2. GET /api/Document/{id} proves a terminal-signed document - an explicitly recognized
     terminal status, OR a signer-based fallback in which EVERY expected internal signer
     is present and signed, NO signer is pending/rejected/unknown, and signer identities
     match the persisted expectations. "Any signer signed" is NOT accepted; a partially
     signed document is blocked.

Storage is concurrency-safe and idempotent (row lock + reload; one accepted File per
signable row), never overwrites the original approved PDF, never touches DSR/approval
terminal state, and appends only sanitized events (no binary/base64 ever logged).
"""
from ecentric_workspace.platform.esign.state import DSR_TERMINAL
import frappe
from frappe.utils import now_datetime

from ecentric_workspace.platform.esign import events
from ecentric_workspace.platform.esign.providers import get_adapter
from ecentric_workspace.platform.esign.providers.base import ProviderError
from ecentric_workspace.platform.esign.sanitize import safe_error

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
    """The internal signer identities ERP submitted for this package (one per Sign DSR):
    provider user ids AND the bound ERP users' emails (eContract's Document detail exposes
    internal signers by email only). Used in the signer-based fallback."""
    rows = frappe.get_all(DSR, filters={"package": package_name, "action": "Sign"},
                          fields=["effective_scts_user_id", "actor_user", "approver"])
    ids = {str(r.effective_scts_user_id) for r in rows if r.effective_scts_user_id}
    emails = {str(r.actor_user or r.approver).strip().lower()
              for r in rows if (r.actor_user or r.approver)}
    return ids, emails


def _terminal_signed_ok(adapter, pkg):
    """(ok, reason). Fail-closed: every signing leg must be finished AND the provider
    document must be terminal-signed.

    A package has ONE leg per signature: the requester leg plus one per approval level that
    requires signing. The old rule demanded EXACTLY ONE completed leg, which is true only
    for a single-signature document - so in real operation (requester + N approvers) the
    signed file could never be fetched (pilot UAT VOID 5 hit `not_exactly_one_completed_dsr:2`
    the moment the second leg finished). The real invariant is: at least one leg completed,
    and NO leg still in flight - a leg still running means more signatures are coming and the
    file we would download is partial.
    """
    rows = frappe.get_all(DSR, filters={"package": pkg.name}, fields=["name", "status"])
    if not rows:
        return False, "no_signature_request"
    completed = [r for r in rows if r.status == "Approval Completed"]
    if not completed:
        return False, "no_completed_dsr:%d" % len(rows)
    in_flight = [r for r in rows if r.status not in DSR_TERMINAL]
    if in_flight:
        return False, "signing_still_in_flight:%s" % ",".join(
            sorted({r.status for r in in_flight}))

    doc = adapter.poll_status(pkg.scts_document_id)
    if not doc:
        return False, "no_document_state"
    status = str(getattr(doc, "status", "") or "").strip().lower()
    signers = getattr(doc, "signers", []) or []

    # KHONG CO NGUOI KY NAO thi khong the chung minh da ky. Vong lap ben duoi khong chan gi
    # tren danh sach rong, roi `status in _TERMINAL_SIGNED` tra True - tuc mot chung tu
    # provider goi la "Hoan thanh" voi 0 nguoi ky se duoc tai ve va dong dau hoan tat.
    #
    # Khong phai gia dinh: 28/08 chung tu do ERP tao ra tren eContract co DU 5 o ky va KHONG
    # AI trong o nao ("Tham gia: --- / Chua co"). Day dung la lop loi cua UAT VOID 5, noi
    # cap duyet duoc bao "da ky" trong khi PDF khong co chu ky nao.
    #
    # Duong tin cay duy nhat khi khong co signers la doi chieu theo chan ky ben duoi - va
    # duong do da tu chan bang "no_signers".
    if not signers:
        return False, "no_signers_on_document"

    # any signer explicitly pending/rejected/unknown -> partial -> BLOCK (even if the
    # top-level status claims terminal).
    for s in signers:
        st = str(s.get("status") or "").strip().lower()
        if st != "signed":
            return False, "non_signed_signer_present:%s" % (st or "unknown")

    if status in _TERMINAL_SIGNED:
        return True, "terminal_status"

    # signer-based fallback: EVERY expected signer present + signed; identities match.
    exp_ids, exp_emails = _expected_signers(pkg.name)
    if not (exp_ids or exp_emails):
        return False, "no_expected_signers"
    if not signers:
        return False, "no_signers"
    def _known(s):
        return (str(s.get("user_id")) in exp_ids
                or str(s.get("email") or "").strip().lower() in exp_emails)
    present_ids = {str(s.get("user_id")) for s in signers if s.get("user_id")}
    present_emails = {str(s.get("email") or "").strip().lower() for s in signers}
    for e in exp_ids:
        if e not in present_ids and not exp_emails & present_emails:
            return False, "expected_signer_absent:%s" % e
    for e in exp_emails:
        if e not in present_emails and not exp_ids & present_ids:
            return False, "expected_signer_absent:%s" % e
    for s in signers:
        if not _known(s):
            return False, "unexpected_signer_identity"
    return True, "all_expected_signers_signed"


#: Moi su kien mot LUOT cron tai PDF co the de lai. Dem luot phai nhin ca hai.
_RETRIEVAL_EVENTS = ("SignedFileRetrievalStarted", "SignedFileRetrievalFailed")


def retrieval_rounds(package_name):
    """So LUOT cron da cham vao goi nay - dem bang MOC THOI GIAN, khong bang so su kien.

    Dem `SignedFileRetrievalStarted` la sai, va sai theo huong nguy hiem nhat: su kien do chi
    phat ra khi da qua duoc buoc do trang thai ben nha cung cap (`_retrieve_one`). Goi nao
    hong NGAY O BUOC DO - dung kieu hong pho bien nhat, vi du 404 tai lieu khong ton tai -
    thi chi de lai `SignedFileRetrievalFailed` va khong bao gio co mot `Started` nao.

    Hau qua that (phat hien 31/08 khi mo trang tren du lieu that): EC-DSP-2026-00016 that bai
    moi 30 phut lien tuc tu 23/08, hon 50 su kien loi, va ca trang lan bao dong deu ghi "da
    thu 0 luot". Bao dong `SignedRetrievalStalled` khong the keu duoc, vi nguong dat tren mot
    con so vinh vien bang 0.

    Dem so MOC PHUT rieng biet co su kien tai: mot luot cron de lai nhieu su kien nhung cung
    mot thoi diem, nen so moc phut xap xi so luot - va khong phu thuoc vao viec luot do di
    duoc toi dau truoc khi hong.
    """
    rows = frappe.get_all("EC Digital Signature Event",
                          filters={"package": package_name,
                                   "event_type": ["in", _RETRIEVAL_EVENTS]},
                          fields=["creation"], limit_page_length=0)
    return len({str(r.creation)[:16] for r in rows if r.creation})


def abandon_retrieval(package_name, reason):
    """Ngung thu tai PDF da ky cho mot goi - bang GHI NHAN, khong bang xoa gi.

    Vi sao can. Vong lap tai lai VO HAN. Khi tai lieu ben nha cung cap khong con ton tai
    (404), thu lai lan thu mot nghin cung khong khac lan thu nhat - nhung cron van goi mang
    moi 30 phut, mai mai. Ngay 31/08 co hai goi da quay nhu vay tu 23/08.

    Ai dong: System Manager, BAT BUOC neu ly do. He thong khong tu quyet dinh bo mot chung tu
    da ky - no chi ghi lai quyet dinh cua nguoi, kem ten nguoi va thoi diem. Cung nguyen tac
    voi guard.settle_signature_debt.

    KHONG xoa, KHONG doi trang thai goi, KHONG dung toi tep nao. Chi bat mot co de cron bo
    qua. Mo lai duoc bat cu luc nao neu tai lieu ben SCTS song lai - xem resume_retrieval.
    """
    # Ten module la `permissions`, KHONG phai `perms`. Ban dau viet `import perms` theo
    # thoi quen tu guard.py - nhung guard.py viet `import permissions as perms`. Loi nay
    # lam ca hai nut chet bang ModuleNotFoundError ngay truoc dong kiem quyen, va toan bo
    # test tinh (grep/AST) deu xanh vi khong test nao THUC SU nap module nay len chay.
    from ecentric_workspace.platform.esign import permissions as perms
    from frappe import _

    perms.assert_system_manager()
    if not (reason or "").strip():
        frappe.throw(_("Bắt buộc nêu lý do: đây là hồ sơ đã ký, và việc ngừng tải bản PDF "
                       "đã ký chỉ dừng lại được kèm giải trình."), frappe.ValidationError)

    row = frappe.db.get_value(PKG, package_name,
                              ["name", "approval_request", "retrieval_abandoned",
                               "signed_bundle_complete"], as_dict=True)
    if not row:
        frappe.throw(_("Không tìm thấy gói ký này."))
    if row.signed_bundle_complete:
        frappe.throw(_("Gói này đã lấy đủ PDF đã ký — không có gì để ngừng."))
    if row.retrieval_abandoned:
        return {"ok": True, "already": True}          # idempotent

    frappe.db.set_value(PKG, row.name, {
        "retrieval_abandoned": 1,
        "retrieval_abandoned_at": now_datetime(),
        "retrieval_abandoned_by": frappe.session.user,
        "retrieval_abandoned_reason": reason.strip()[:500]})
    events.emit("SignedRetrievalAbandoned", package=row.name, request_meta={
        "abandoned_by": frappe.session.user, "reason": reason.strip()[:500]})
    if row.approval_request:
        from ecentric_workspace.approval_center.shared.workflow import transitions as engine
        engine.log_action(row.approval_request, "Commented", frappe.session.user,
                          comment=_("Ngừng tải bản PDF đã ký của gói {0}. Lý do: {1}"
                                    ).format(row.name, reason.strip()))
    return {"ok": True}


def resume_retrieval(package_name):
    """Mo lai mot goi da ngung - de quyet dinh ngung khong phai la mot canh cua mot chieu.

    Tai lieu ben SCTS co the song lai (khoi phuc du lieu, sua cau hinh, doi moi truong).
    Neu ngung la vinh vien thi khong ai dam bam nut ngung, va vong lap vo han cu chay tiep.
    """
    # Ten module la `permissions`, KHONG phai `perms`. Ban dau viet `import perms` theo
    # thoi quen tu guard.py - nhung guard.py viet `import permissions as perms`. Loi nay
    # lam ca hai nut chet bang ModuleNotFoundError ngay truoc dong kiem quyen, va toan bo
    # test tinh (grep/AST) deu xanh vi khong test nao THUC SU nap module nay len chay.
    from ecentric_workspace.platform.esign import permissions as perms
    from frappe import _

    perms.assert_system_manager()
    if not frappe.db.exists(PKG, package_name):
        frappe.throw(_("Không tìm thấy gói ký này."))
    frappe.db.set_value(PKG, package_name, "retrieval_abandoned", 0)
    events.emit("SignedRetrievalResumed", package=package_name,
                request_meta={"resumed_by": frappe.session.user})
    return {"ok": True}


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
    # eContract (2026-08): Document/Submit does NOT return per-file ids, so DSF rows may have an
    # empty scts_document_file_id. Backfill from the Document detail (poll) by exact fileName
    # match, then persist. Fail-closed: no match -> the per-file retrieval errors as before.
    if any(not f.scts_document_file_id for f in files):
        try:
            doc = adapter.poll_status(pkg.scts_document_id)
            by_name = {}
            for df in (getattr(doc, "files", None) or []):
                if df.get("name") and df.get("file_id"):
                    by_name.setdefault(df["name"], df["file_id"])
            for f in files:
                if not f.scts_document_file_id and by_name.get(f.file_name):
                    f.scts_document_file_id = by_name[f.file_name]
                    frappe.db.set_value(DSF, f.name, "scts_document_file_id",
                                        f.scts_document_file_id)
        except ProviderError:
            pass                                  # per-file path will surface the error
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
