# Copyright (c) 2026, eCentric and contributors
"""Digital Signature Orchestrator.

Owns: pre-flight authorization, idempotency + concurrency, DSR lifecycle, provider
handoff (via adapter), verification, and the ONLY completion path into the engine:
engine.service.approve() called with the in-process call marker set AND a persisted,
provider-verified DSR that esign.guard re-validates against the DB under lock.

Never: raw approval-state writes, provider payloads (adapter-only), frontend-supplied
identity (mapping-only), completion on 'accepted' (three-concept separation).
"""
from datetime import timedelta
import frappe
from frappe import _
from frappe.utils import now_datetime

from ecentric_workspace.platform.esign import binding, events, guard, hashing
from ecentric_workspace.platform.esign import package as pkgsvc
from ecentric_workspace.platform.esign import permissions as perms
from ecentric_workspace.platform.esign import state as sm
from ecentric_workspace.platform.esign.providers import get_adapter
from ecentric_workspace.platform.esign.sanitize import safe_error

DSR = "EC Digital Signature Request"
LIVE_OR_DONE = ("Prepared", "Queued", "Provider Accepted", "Verifying", "Signed",
                "Approval Completed")


# --------------------------------------------------------------------------- #
# resolution helpers
# --------------------------------------------------------------------------- #
def _settings_for(profile_row):
    s = frappe.db.get_value("EC Digital Signature Provider Settings",
                            {"provider": profile_row.provider,
                             "environment": profile_row.environment}, "*", as_dict=True)
    if not s:
        frappe.throw(_("Chưa cấu hình Provider Settings cho {0}/{1}.").format(
            profile_row.provider, profile_row.environment))
    return s


def _profile_doc(reference_doctype, approval_type):
    name = guard.get_active_profile(reference_doctype, approval_type)
    if not name:
        frappe.throw(_("Ký số chưa được bật cho loại yêu cầu này."))
    return frappe.db.get_value("EC Digital Signature Profile", name, "*", as_dict=True)


def _req_for_business(business_doctype, business_name):
    ar = perms.business_approval_request(business_doctype, business_name)
    if not ar:
        frappe.throw(_("Yêu cầu này chưa được gửi duyệt."))
    return frappe.get_doc("EC Approval Request", ar)


def _level_row(req):
    n = frappe.db.get_value("EC Approval Request Level",
                            {"approval_request": req.name, "level_no": req.current_level},
                            "name")
    if not n:
        frappe.throw(_("Không tìm thấy cấp duyệt hiện tại."))
    return n


def _profile_level(profile_name, level_no):
    return frappe.db.get_value("EC Digital Signature Profile Level",
                               {"parent": profile_name, "level_no": level_no},
                               ["requires_signature", "scts_role_title", "signature_type"],
                               as_dict=True)


def _transition_id(profile_name, action):
    return frappe.db.get_value("EC Digital Signature Profile Transition",
                               {"parent": profile_name, "action": action}, "transition_id")


def _lock_key(approval_request, level_no):
    return "esign:lock:%s:%s" % (approval_request, level_no)


def _acquire_lock(key):
    """Redis nx lock (alerts precedent). UX-independent server-side double-submit
    control; unique idempotency key remains the DB-level backstop."""
    try:
        ok = frappe.cache().set(key, "1", nx=True, ex=30)
    except Exception:
        ok = True  # cache down: unique idempotency key still guarantees single submission
    if not ok:
        frappe.throw(_("Yêu cầu ký đang được xử lý - vui lòng đợi."))


def _release_lock(key):
    try:
        frappe.cache().delete(key)
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# approve & sign (single request)
# --------------------------------------------------------------------------- #
def approve_and_sign(business_doctype, business_name, comment=None, bulk_batch_key=None):
    """Full server-side pre-flight, then create+enqueue a signing request. The client
    supplied ONLY (business doctype, name, comment) - identity, level, package and
    transition are all resolved server-side."""
    actor = frappe.session.user
    req = _req_for_business(business_doctype, business_name)
    profile = _profile_doc(business_doctype, req.approval_type)
    settings = _settings_for(profile)

    binding.assert_provider_environment(settings)  # fail fast: nhan la + Production chua bat
    perms.assert_allowed_signer(settings, actor)
    perms.assert_pending_approver(req, actor)
    approver_row = perms.pending_approver_row(req.name, req.current_level, actor)

    # Policy-driven (Approver Signature Policy) so admins need not recreate every level; the
    # final level is resolved dynamically from the request's frozen runtime approvers.
    if not guard.level_requires_signature(business_doctype, req.approval_type, req.current_level,
                                          final_level=guard.request_final_level(req.name)):
        frappe.throw(_("Cấp duyệt hiện tại không yêu cầu ký số - dùng nút Duyệt thường."))

    mapping = perms.verified_mapping(actor, profile.environment)
    if not mapping:
        events.emit("MappingRequired", erp_actor=actor,
                    request_meta={"business": business_name, "level": req.current_level})
        frappe.throw(_("Bạn chưa có ánh xạ chữ ký SCTS được xác minh - liên hệ quản trị."))

    pkg_name = pkgsvc.active_package_for_request(req.name)
    if not pkg_name:
        frappe.throw(_("Không có gói tài liệu sẵn sàng ký cho yêu cầu này."))
    pkg = frappe.db.get_value("EC Digital Signature Package", pkg_name,
                              ["name", "package_version", "package_hash", "scts_document_id"],
                              as_dict=True)
    recomputed = pkgsvc.compute_hash(pkg_name)
    if recomputed != pkg.package_hash:
        events.emit("VerificationMismatch", package=pkg_name, erp_actor=actor,
                    verification_result="package_hash_drift")
        frappe.throw(_("Gói tài liệu đã thay đổi so với phiên bản đã khóa - cần phiên bản mới."))

    request_level = _level_row(req)
    idem = hashing.idempotency_key(
        profile.provider, profile.environment, req.name, request_level, approver_row,
        "Sign", pkg.package_hash, "%s@%s" % (mapping.name, mapping.modified))

    existing = frappe.db.get_value(DSR, {"idempotency_key": idem},
                                   ["name", "status"], as_dict=True)
    if existing and existing.status in LIVE_OR_DONE:
        return {"signature_request": existing.name, "status": existing.status,
                "duplicate": True}

    lock = _lock_key(req.name, req.current_level)
    _acquire_lock(lock)
    try:
        # Backstop re-check inside the lock window.
        existing = frappe.db.get_value(DSR, {"idempotency_key": idem},
                                       ["name", "status"], as_dict=True)
        if existing and existing.status in LIVE_OR_DONE:
            return {"signature_request": existing.name, "status": existing.status,
                    "duplicate": True}
        if existing:  # prior terminal-failed attempt: reuse row, bump attempt
            dsr_name = existing.name
            frappe.db.set_value(DSR, dsr_name, {
                "request_attempt": (frappe.db.get_value(DSR, dsr_name, "request_attempt") or 0) + 1,
                "requested_by": actor})
            events.set_dsr_status(dsr_name, "Prepared", event_type="RetryScheduled",
                                  erp_actor=actor)
        else:
            dsr = frappe.get_doc({
                "doctype": DSR, "provider": profile.provider,
                "environment": profile.environment, "package": pkg_name,
                "approval_request": req.name, "request_level": request_level,
                "approver_row": approver_row, "action": "Sign",
                "requested_by": actor, "approver": actor,
                "effective_scts_user_id": mapping.scts_user_id,
                "effective_signature_id": mapping.signature_id,
                "idempotency_key": idem, "status": "Draft",
                "package_version": pkg.package_version, "package_hash": pkg.package_hash,
                "bulk_batch_key": bulk_batch_key,
            }).insert(ignore_permissions=True)  # post-authorization system row
            dsr_name = dsr.name
            events.emit("Created", signature_request=dsr_name, package=pkg_name,
                        erp_actor=actor, scts_effective_user=mapping.scts_user_id)
            events.set_dsr_status(dsr_name, "Prepared", erp_actor=actor,
                                  event_type="Prepared")
        events.set_dsr_status(dsr_name, "Queued",
                              extra_fields={"queued_at": now_datetime()}, erp_actor=actor)
        frappe.enqueue(
            "ecentric_workspace.platform.esign.tasks.process_signing_request",
            dsr_name=dsr_name, queue=sm.SIGNING_QUEUE, timeout=sm.SIGNING_JOB_TIMEOUT,
            job_name="esign_dsr_%s" % dsr_name, enqueue_after_commit=True)
        return {"signature_request": dsr_name, "status": "Queued", "duplicate": False}
    finally:
        _release_lock(lock)


# --------------------------------------------------------------------------- #
# verification + completion (worker side)
# --------------------------------------------------------------------------- #
def _completed_legs_of_same_signer(dsr):
    """SO chan ky da hoan tat cua CUNG NGUOI nay tren cung goi, khong ke chan dang xet.

    Day la thu tu cua chan nay trong cac chu ky cua nguoi do: N chan truoc da an N chu ky,
    chan nay phai la chu ky thu N+1. Thay cho `_last_completed_leg_time` - san THOI GIAN
    "chu ky phai moi hon luc chan truoc hoan tat" - vi eContract tra `signed_at` chi toi
    PHUT: 02/09 23:06 mot nguoi trinh ky roi duyet cap 1 trong cung mot phut, ca hai chu ky
    doc thanh 23:06:00, deu "cu hon" san 23:06:2x, chan duyet khong bao gio xac nhan duoc.

    Tra `None` khi khong dem duoc. Nguoi nhan PHAI phan biet None voi 0: 0 nghia la "chua
    co chan nao" (chu ky dau tien cua nguoi do la du), None nghia la "khong biet" (giu
    duong cu, khong ha yeu cau).
    """
    if not dsr.get("package") or not dsr.get("effective_scts_user_id"):
        return None
    try:
        return frappe.db.count(
            "EC Digital Signature Request",
            {"package": dsr.get("package"),
             "effective_scts_user_id": dsr.get("effective_scts_user_id"),
             "name": ["!=", dsr.get("name")],
             "status": ["in", ("Signed", "Approval Completed")]})
    except Exception:
        return None


def _expected_for(dsr):
    pkg = frappe.db.get_value("EC Digital Signature Package", dsr.package,
                              ["scts_document_id"], as_dict=True)
    # Chi dem tep DA SANG nha cung cap (phu luc Excel giu tren ERP khong tinh) - xem
    # package.provider_file_count. Dem ca goi la nguon cua file_count_mismatch 05/09.
    file_count = pkgsvc.provider_file_count(dsr.package)
    # FRESHNESS bound (2026-08-27): the signature that satisfies THIS leg must be newer
    # than the moment the leg was queued. Email-only matching used to accept a signature
    # the same person had made for a DIFFERENT leg earlier (see verify_signed_result).
    from ecentric_workspace.platform.esign.providers.base import SignatureProviderAdapter
    # MOC LA LUC NHA CUNG CAP NHAN LENH (`accepted_at`), KHONG PHAI LUC XEP HANG GAN NHAT.
    #
    # 02/09 23:40: "Thu lai" mot chan da duoc ky that luc 23:06. Thu lai dat `queued_at` =
    # 23:40:40, cua so thanh 23:38:40, va chu ky 23:06 - chu ky DUNG cua chan nay - bi coi
    # la "truoc khi hoi". Tuc tu truoc toi nay Thu lai chua bao gio xac nhan noi mot chu ky
    # da ton tai; no chi co the quay ve Manual Review.
    #
    # `accepted_at` la luc lenh ky thuc su den nha cung cap, khong doi qua cac lan thu lai.
    # Chan chua gui bao gio thi khong co no - khi do `queued_at` la moc dung, vi chua co lenh
    # nao de chu ky "moi hon".
    asked_at = dsr.get("accepted_at") or dsr.get("queued_at") or dsr.get("creation")
    signed_after = None
    if asked_at:
        parsed = SignatureProviderAdapter._parse_provider_time(asked_at)
        if parsed:
            signed_after = parsed - timedelta(
                seconds=SignatureProviderAdapter.SIGN_TIME_TOLERANCE_SECONDS)
    # Nhung dung sai do (120 giay, de bu lech dong ho voi nha cung cap) RONG hon khoang
    # cach giua hai chan ky lien tiep cua CUNG MOT NGUOI.
    #
    # 28/08: nguoi trinh ky luc 23:53; chan duyet Cap 1 cua chinh ho xep hang 23:54:01, moc
    # tuoi thanh 23:52:01, va chu ky 23:53 - cua chan TRUOC - dat yeu cau. Cap duyet dong
    # lai bang mot chu ky khong phai cua no.
    #
    # Lan dau sua bang SAN THOI GIAN (chu ky phai moi hon luc chan truoc hoan tat). San do
    # hong 02/09 vi eContract chi tra `signed_at` toi PHUT - hai chu ky cung phut thi khong
    # phan biet duoc bang thoi gian. Gio sua bang THU TU: chan thu N cua mot nguoi doi chu
    # ky thu N+1 cua nguoi do. Dem thi khong can phan biet hai chu ky cung phut, ma loi
    # 28/08 van bi chan (khi do chi co MOT chu ky, chan doi cai thu HAI).
    return {"document_id": pkg.scts_document_id, "user_id": dsr.effective_scts_user_id,
            "signature_id": dsr.effective_signature_id, "file_count": file_count,
            # eContract detail identifies internal signers by EMAIL only (no userIds);
            # the ERP user id IS the company email of the bound signer.
            "email": dsr.actor_user or dsr.approver,
            "signed_after": signed_after,
            "prior_signatures": _completed_legs_of_same_signer(dsr)}


def mark_verified(dsr_name, doc_state):
    """Provider state passed verify_signed_result -> DSR Signed + verified_at."""
    events.set_dsr_status(dsr_name, "Signed",
                          extra_fields={"verified_at": now_datetime()},
                          event_type="Verified", verification_result="verified")



def _guarded_dsr_transition(dsr_name, from_status, to_status, extra=None,
                            event_type=None, **event_kw):
    """R2 (2026-07-12): race-safe conditional state mutation - the CURRENT persisted
    status is part of the UPDATE condition, so a worker that lost a completion race
    can never overwrite another worker's terminal result (Approval Completed is
    never downgraded). Returns True only if THIS caller performed the transition;
    the audit event is emitted only in that case (no misleading failure events for
    idempotent losers)."""
    from ecentric_workspace.platform.esign import state as sm
    sm.assert_transition(sm.DSR, from_status, to_status)
    vals = {"status": to_status}
    vals.update(extra or {})
    set_clause = ", ".join("`%s`=%%s" % k for k in vals)
    frappe.db.sql("UPDATE `tabEC Digital Signature Request` SET " + set_clause
                  + " WHERE name=%s AND status=%s",
                  list(vals.values()) + [dsr_name, from_status])
    changed = frappe.db.sql("SELECT ROW_COUNT()")[0][0] == 1
    if changed:
        events.emit(event_type or to_status.replace(" ", ""),
                    signature_request=dsr_name, **event_kw)
    return changed


def reconcile_manual_review(dsr_name):
    """Re-verify a leg parked in Manual Review against the provider's CURRENT state.

    Reads only. If the signature the leg was waiting for is now really there - the signer
    went to the provider's own portal and signed by hand - the leg is marked Signed and the
    normal governed completion runs. If it is not there, nothing changes and the reason is
    returned.

    This never calls a signing endpoint. Re-sending a non-idempotent signing command to
    "unstick" a leg is how you end up with two signatures on one document.
    """
    dsr = frappe.db.get_value(DSR, dsr_name, "*", as_dict=True)
    if not dsr:
        frappe.throw(_("Không tìm thấy yêu cầu ký."))
    if dsr.status != "Manual Review":
        return {"ok": False, "reason": "not_in_manual_review:%s" % dsr.status}
    settings = _settings_for(dsr)      # nem to khi thieu cau hinh - khong im lang
    doc_id = frappe.db.get_value("EC Digital Signature Package", dsr.package, "scts_document_id")
    if not doc_id:
        return {"ok": False, "reason": "no_provider_document"}

    from ecentric_workspace.platform.esign.providers import get_adapter
    from ecentric_workspace.platform.esign.providers.base import SignatureProviderAdapter
    adapter = get_adapter(settings)
    doc_state = adapter.poll_status(doc_id)
    vr = SignatureProviderAdapter.verify_signed_result(doc_state, _expected_for(dsr))
    events.emit("PollTick", signature_request=dsr_name, package=dsr.package,
                verification_result=vr.reason,
                request_meta={"source": "manual_reconcile"})
    if not vr.ok:
        return {"ok": False, "reason": vr.reason}
    events.set_dsr_status(dsr_name, "Signed", event_type="Verified",
                          verification_result=vr.reason)
    # Re nhanh theo actor_type - CUNG loi voi poll_pending (tasks.py). verify_and_complete
    # la duong approver (engine.approve); chan NGUOI DE NGHI phai hoan tat qua duong
    # requester. Truoc day nut "Doi soat" goi thang duong approver, engine tu choi vi
    # requester khong phai pending approver, va chan ky quay lai Manual Review - tuc nut
    # cuu ho lap lai dung cai loi da day no vao do.
    if dsr.actor_type == "Requester":
        from ecentric_workspace.platform.esign import requester
        requester.reconcile_and_complete_requester(dsr_name)
    else:
        verify_and_complete(dsr_name)
    final = frappe.db.get_value(DSR, dsr_name, "status")
    if final == "Approval Completed":
        return {"ok": True, "reason": vr.reason, "status": final}
    # Xac minh duoc chu ky KHONG dong nghia cap duyet da hoan tat: engine co the tu choi vi
    # yeu cau da huy, cap da doi, hoac chan ky khac da dong cap nay. Bao ok=True o day la
    # noi doi - lan chay 28/08 tra ok=True trong khi yeu cau da bi huy va khong co gi thay
    # doi. Lay dung ly do engine ghi lai thay vi de nguoi doc tu suy.
    why = frappe.db.get_value(
        "EC Digital Signature Event",
        {"signature_request": dsr_name, "event_type": "ManualReview"},
        "error_summary", order_by="event_time desc")
    return {"ok": False, "reason": "verified_but_engine_refused",
            "verification": vr.reason, "engine": why, "status": final}


def verify_and_complete(dsr_name):
    """The governed completion path. Requires DSR already 'Signed' (verified). Sets the
    in-process call marker, then lets the ENGINE complete the level; the engine-side
    guard re-validates the persisted DSR under lock (frappe.flags is never trusted
    alone). On engine refusal (state drift) -> Manual Review ONLY if this attempt
    still owns the Signed state (R2: losers of a completion race exit as idempotent
    no-ops; terminal states are never downgraded)."""
    frappe.db.get_value(DSR, dsr_name, "name", for_update=True)
    dsr = frappe.db.get_value(DSR, dsr_name,
                              ["name", "status", "approval_request", "approver", "package"],
                              as_dict=True)
    if not dsr or dsr.status != "Signed":
        return {"completed": False, "reason": "not_in_signed_state"}
    prev = getattr(frappe.flags, guard.FLAG_KEY, None)
    setattr(frappe.flags, guard.FLAG_KEY, dsr.name)
    prev_mute = frappe.flags.mute_messages
    frappe.flags.mute_messages = True
    # ATOMICITY (verification-gate correction, 2026-07-12): savepoint before the
    # engine call. If engine.approve() fails AFTER partial mutations (e.g. approver
    # row set but level activation failed), the except path FIRST rolls back to the
    # savepoint so no partial approval state can ever commit alongside the Manual
    # Review marker. Happy path stays one atomic transaction: DSR lock -> guard DB
    # validation -> engine.approve -> DSR 'Approval Completed', no intermediate commit.
    frappe.db.savepoint("esign_verify_complete")
    try:
        from ecentric_workspace.approval_center.shared.workflow import transitions as engine
        engine.approve(dsr.approval_request, actor=dsr.approver,
                       comment=_("Duyệt & Ký (ký số đã xác minh: {0})").format(dsr.name))
    except Exception as e:
        # R2 (2026-07-12): rollback the savepoint FIRST, then let the CURRENT
        # persisted DB state decide. Manual Review is stamped only when this
        # failing attempt still owns the eligible 'Signed' processing state
        # (conditional UPDATE); a worker that merely lost a valid concurrency
        # race exits as an idempotent no-op with NO failure/manual-review event,
        # and a terminal result (Approval Completed) is never downgraded.
        frappe.db.rollback(save_point="esign_verify_complete")
        if _guarded_dsr_transition(dsr_name, "Signed", "Manual Review",
                                   extra={"manual_review_reason": safe_error(e)[:200]},
                                   event_type="ManualReview", error_summary=safe_error(e)):
            return {"completed": False, "reason": "engine_refused", "detail": safe_error(e)}
        return {"completed": False, "reason": "already_finalized_by_parallel_worker"}
    finally:
        setattr(frappe.flags, guard.FLAG_KEY, prev)
        frappe.flags.mute_messages = prev_mute
        frappe.local.message_log = []
    # Winner finalization - also state-guarded. If a racing loser stamped
    # Manual Review in the window after our engine.approve, repair it to the true
    # terminal outcome (the engine DID approve exactly once in this transaction).
    if _guarded_dsr_transition(dsr_name, "Signed", "Approval Completed",
                               extra={"completed_at": now_datetime()},
                               event_type="ApprovalCompleted", erp_actor=dsr.approver):
        return {"completed": True}
    if _guarded_dsr_transition(dsr_name, "Manual Review", "Approval Completed",
                               extra={"completed_at": now_datetime(),
                                      "manual_review_reason": None},
                               event_type="ApprovalCompleted", erp_actor=dsr.approver):
        return {"completed": True, "note": "repaired_racer_manual_review_label"}
    # Already Approval Completed (idempotent) - nothing to do.
    return {"completed": True, "note": "already_terminal"}


# --------------------------------------------------------------------------- #
# reject / cancel / retry
# --------------------------------------------------------------------------- #
def reject_with_transition(business_doctype, business_name, comment):
    """ERP is the system of record: engine.reject FIRST (engine authorizes + requires
    reason). Provider transition is best-effort afterwards; failure never un-rejects."""
    actor = frappe.session.user
    req = _req_for_business(business_doctype, business_name)
    profile = _profile_doc(business_doctype, req.approval_type)
    prev_mute = frappe.flags.mute_messages
    frappe.flags.mute_messages = True
    try:
        from ecentric_workspace.approval_center.shared.workflow import transitions as engine
        engine.reject(req.name, actor=actor, comment=comment)
    finally:
        frappe.flags.mute_messages = prev_mute
        frappe.local.message_log = []
    pkg_name = pkgsvc.active_package_for_request(req.name)
    sync_pending = 0
    if pkg_name:
        pkg = frappe.db.get_value("EC Digital Signature Package", pkg_name,
                                  ["scts_document_id"], as_dict=True)
        tid = _transition_id(profile.name, "Reject")
        if pkg.scts_document_id and tid is not None:
            try:
                adapter = get_adapter(_settings_for(profile))
                adapter.execute_transition(pkg.scts_document_id, tid, {"comment": comment})
                events.emit("Rejected", package=pkg_name, erp_actor=actor,
                            request_meta={"transition_id": tid})
            except Exception as e:
                sync_pending = 1
                events.emit("Failed", package=pkg_name, erp_actor=actor,
                            error_summary=safe_error(e),
                            request_meta={"phase": "reject_transition"})
    return {"rejected": True, "provider_sync_pending": sync_pending}


def cancel_signature_request(dsr_name, reason):
    """Ops action (SM): cancel a stuck signing request. Never touches approval state."""
    perms.assert_system_manager()
    if not (reason or "").strip():
        frappe.throw(_("Vui lòng nhập lý do hủy."))
    events.set_dsr_status(dsr_name, "Cancelled", event_type="Cancelled",
                          request_meta={"reason": reason})
    return {"cancelled": True}


def retry_signature_request(dsr_name):
    """Ops action (SM): re-drive from Manual Review / Retryable Failure. POLL-FIRST is
    enforced in the worker - a retry never blind-resubmits."""
    perms.assert_system_manager()
    cur = frappe.db.get_value(DSR, dsr_name, "status")
    if cur not in ("Manual Review", "Retryable Failure"):
        frappe.throw(_("Chỉ retry được yêu cầu ở trạng thái Manual Review / Retryable Failure."))
    frappe.db.set_value(DSR, dsr_name, "request_attempt",
                        (frappe.db.get_value(DSR, dsr_name, "request_attempt") or 0) + 1)
    events.set_dsr_status(dsr_name, "Queued", event_type="RetryScheduled",
                          extra_fields={"queued_at": now_datetime()})
    frappe.enqueue(
        "ecentric_workspace.platform.esign.tasks.process_signing_request",
        dsr_name=dsr_name, queue=sm.SIGNING_QUEUE, timeout=sm.SIGNING_JOB_TIMEOUT,
        job_name="esign_dsr_%s" % dsr_name, enqueue_after_commit=True)
    return {"queued": True}


# --------------------------------------------------------------------------- #
# status (read)
# --------------------------------------------------------------------------- #
def get_signing_status(business_doctype, business_name):
    perms.assert_can_view_business(business_doctype, business_name)
    ar = perms.business_approval_request(business_doctype, business_name)
    out = {"enabled": False, "package": None, "requests": []}
    profile = None
    at = frappe.db.get_value(business_doctype, business_name, "approval_type") \
        if frappe.db.has_column(business_doctype, "approval_type") else None
    if not at and ar:
        at = frappe.db.get_value("EC Approval Request", ar, "approval_type")
    if at:
        profile = guard.get_active_profile(business_doctype, at)
    else:
        # draft with empty approval_type field (per-form APIs don't populate it):
        # any enabled+gated profile for this DocType decides visibility
        for r in frappe.get_all("EC Digital Signature Profile",
                                 filters={"business_doctype": business_doctype, "enabled": 1},
                                 fields=["name", "approval_type"], limit_page_length=5):
            profile = guard.get_active_profile(business_doctype, r.approval_type)
            if profile:
                break
    out["enabled"] = bool(profile)
    pkg_name = None
    if ar:
        # Active or approval_request-linked package first; fall back to the requester's unlocked
        # Draft (which has neither, since approval_request is set only at lock) so the placement
        # editor / signing UI can resolve it pre-lock. For the approver flow a locked/active
        # package always exists, so the Draft fallback never fires.
        pkg_name = pkgsvc.active_package_for_request(ar) \
            or frappe.db.get_value("EC Digital Signature Package",
                                   {"approval_request": ar}, "name") \
            or pkgsvc.draft_package_for_business(business_doctype, business_name)
    else:
        pkg_name = pkgsvc.draft_package_for_business(business_doctype, business_name)
    if pkg_name:
        pkg = frappe.db.get_value("EC Digital Signature Package", pkg_name,
                                  ["name", "status", "package_version", "package_hash",
                                   "scts_document_id", "provider", "environment",
                                   "signed_bundle_complete"], as_dict=True)
        pkg["files"] = pkgsvc.package_files(pkg_name)
        pkg["placements"] = pkgsvc.package_placements(pkg_name)
        out["package"] = pkg
    if ar:
        out["requests"] = frappe.get_all(
            DSR, filters={"approval_request": ar},
            fields=["name", "status", "action", "approver", "request_attempt",
                    "queued_at", "verified_at", "completed_at", "error_code",
                    "manual_review_reason"],
            order_by="creation asc")
    return out


# --------------------------------------------------------------------------- #
# ambiguous-create reconciliation (S2B-B PR#146)
# --------------------------------------------------------------------------- #
def reconcile_document_creation(package_name, scts_document_id):
    """Governed reconciliation of an AMBIGUOUS AddDocument outcome. It NEVER trusts an
    arbitrary entered id: it first VERIFIES the provider document (GET /api/Document/{id})
    against the package (document identity + expected file count) and appends an immutable
    sanitized event, then continues the flow poll-first WITHOUT ever recreating:
      * document already signed by the effective signer -> the requeued worker verifies
        and completes (poll-first);
      * document exists but bulk-process was never submitted -> requeue and submit
        bulk-process exactly once (worker poll-first guarantees once);
      * bulk-process may already have occurred (a transaction id is recorded) -> remain in
        Verifying and poll only."""
    if not (scts_document_id or "").strip():
        frappe.throw(_("Cần cung cấp mã tài liệu SCTS để đối soát."))
    pkg = frappe.db.get_value(
        "EC Digital Signature Package", package_name,
        ["name", "error_code", "scts_document_id", "provider", "environment",
         "doc_code_sent", "business_name", "business_doctype", "profile"], as_dict=True)
    if not pkg:
        frappe.throw(_("Không tìm thấy gói tài liệu."))
    if pkg.error_code != "create_outcome_unknown":
        frappe.throw(_("Gói này không ở trạng thái cần đối soát tạo tài liệu."))

    settings = frappe.db.get_value("EC Digital Signature Provider Settings",
                                   {"provider": pkg.provider, "environment": pkg.environment},
                                   "*", as_dict=True)
    if not settings:
        frappe.throw(_("Chưa cấu hình Provider Settings."))
    adapter = get_adapter(settings)
    doc_state = adapter.poll_status(scts_document_id)  # GET /api/Document/{id}
    if not doc_state or str(doc_state.document_id) != str(scts_document_id):
        events.emit("CreateReconcileRejected", package=package_name,
                    verification_result="document_not_found")
        frappe.throw(_("Không xác minh được tài liệu SCTS theo mã đã nhập."))

    pkg_files = frappe.get_all("EC Digital Signature File", filters={"package": package_name},
                               fields=["name", "file_name"],
                               order_by="idx_order asc, creation asc")
    expected_files = pkgsvc.provider_file_count(package_name)   # tru phu luc giu tren ERP
    if len(doc_state.files) != expected_files:
        events.emit("CreateReconcileRejected", package=package_name,
                    verification_result="file_count_mismatch:%s!=%s"
                    % (len(doc_state.files), expected_files))
        frappe.throw(_("Số tệp của tài liệu SCTS không khớp với gói."))

    # --- FAIL-CLOSED IDENTITY: prove the SCTS document belongs to THIS package ---
    ident = doc_state.identity or {}
    expected_code = (pkg.doc_code_sent or pkg.business_name or "").strip()
    provider_code = ident.get("doc_code")
    provider_code = str(provider_code).strip() if provider_code is not None else ""
    if not provider_code:
        # no code/reference from SCTS -> identity UNPROVABLE -> do NOT bind an arbitrary
        # id; keep the package in the reconciliation-required (create_outcome_unknown) state.
        events.emit("CreateReconcileRejected", package=package_name,
                    verification_result="insufficient_provider_identity_evidence")
        return {"reconciled": False, "reason": "insufficient_provider_identity_evidence",
                "package": package_name}
    if provider_code != expected_code:
        events.emit("CreateReconcileRejected", package=package_name,
                    verification_result="document_code_mismatch")
        frappe.throw(_("Mã tài liệu SCTS không khớp với gói - từ chối đối soát."))
    # file names / order when the provider returns them
    prov_names = [f.get("name") for f in doc_state.files]
    if any(prov_names):
        if prov_names != [f.file_name for f in pkg_files]:
            events.emit("CreateReconcileRejected", package=package_name,
                        verification_result="file_names_mismatch")
            frappe.throw(_("Tên/thứ tự tệp của tài liệu SCTS không khớp với gói."))
    # workflow / document type / company / department identifiers when returned
    prof = frappe.db.get_value(
        "EC Digital Signature Profile", pkg.profile,
        ["workflow_definition_id", "document_type_id", "company_id", "department_id"],
        as_dict=True) or {}
    for key in ("workflow_definition_id", "document_type_id", "company_id", "department_id"):
        pv, ev = ident.get(key), prof.get(key)
        if pv not in (None, "") and ev and str(pv) != str(ev):
            events.emit("CreateReconcileRejected", package=package_name,
                        verification_result="identity_mismatch:%s" % key)
            frappe.throw(_("Định danh tài liệu SCTS không khớp hồ sơ - từ chối đối soát."))

    # identity VERIFIED -> bind id, clear the unknown marker, immutable sanitized event
    frappe.db.set_value("EC Digital Signature Package", package_name,
                        {"scts_document_id": scts_document_id, "error_code": None,
                         "error_message": None})
    for i, f in enumerate(pkg_files):
        if i < len(doc_state.files) and doc_state.files[i].get("file_id"):
            frappe.db.set_value("EC Digital Signature File", f.name,
                                "scts_document_file_id", doc_state.files[i]["file_id"])
    events.emit("CreateReconciled", package=package_name,
                request_meta={"scts_document_id": scts_document_id, "doc_code": provider_code,
                              "file_count": len(doc_state.files),
                              "provider_status": doc_state.status})
    cont = _continue_after_reconcile(package_name)
    return {"reconciled": True, "scts_document_id": scts_document_id,
            "file_count": len(doc_state.files), "continuation": cont}


def _continue_after_reconcile(package_name):
    """Poll-first continuation for the affected DSR(s). Never recreates AddDocument."""
    rows = frappe.get_all(
        DSR, filters={"package": package_name,
                      "status": ["in", ["Queued", "Provider Accepted", "Verifying",
                                        "Retryable Failure", "Manual Review"]]},
        fields=["name", "status", "bulk_job_transaction_id"])
    out = []
    for r in rows:
        frappe.db.get_value(DSR, r.name, "name", for_update=True)
        if r.bulk_job_transaction_id:
            # bulk-process may already have occurred -> poll only, never resubmit.
            if r.status != "Verifying" and r.status in ("Retryable Failure",):
                events.set_dsr_status(r.name, "Queued", event_type="RetryScheduled",
                                      extra_fields={"queued_at": now_datetime()})
            out.append({"dsr": r.name, "action": "poll_only"})
            continue
        # no bulk submitted -> requeue to Queued via a legal path; the worker poll-first
        # completes if already signed, otherwise submits bulk-process exactly once.
        cur = frappe.db.get_value(DSR, r.name, "status")
        if cur == "Verifying":
            events.set_dsr_status(r.name, "Retryable Failure", event_type="RetryScheduled",
                                  extra_fields={"retryable": 1})
            cur = "Retryable Failure"
        if cur in ("Retryable Failure", "Manual Review", "Provider Accepted"):
            if cur == "Provider Accepted":
                out.append({"dsr": r.name, "action": "poll_only"})
                continue
            events.set_dsr_status(r.name, "Queued", event_type="RetryScheduled",
                                  extra_fields={"queued_at": now_datetime()})
        frappe.enqueue(
            "ecentric_workspace.platform.esign.tasks.process_signing_request",
            dsr_name=r.name, queue=sm.SIGNING_QUEUE, timeout=sm.SIGNING_JOB_TIMEOUT,
            job_name="esign_dsr_%s" % r.name, enqueue_after_commit=True)
        out.append({"dsr": r.name, "action": "requeued"})
    return out


# --------------------------------------------------------------------------- #
# backend-computed signing readiness (S2B-B PR#146 - UI gate; backend authoritative)
# --------------------------------------------------------------------------- #
def signing_readiness(business_doctype, business_name):
    """Backend-computed readiness for the Duyệt & Ký button. The UI only reflects this;
    the actual approve_and_sign path re-validates everything under lock, so a stale or
    forged UI can never sign. Read-only."""
    perms.assert_can_view_business(business_doctype, business_name)
    user = frappe.session.user
    checks = {}
    ar = perms.business_approval_request(business_doctype, business_name)
    if not ar:
        return {"ready": False, "reasons": ["not_submitted"], "checks": {}}
    req = frappe.get_doc("EC Approval Request", ar)
    profile_name = guard.get_active_profile(business_doctype, req.approval_type)
    checks["signing_enabled"] = bool(profile_name)
    if not profile_name:
        return {"ready": False, "reasons": ["signing_not_enabled"], "checks": checks}
    profile = frappe.db.get_value("EC Digital Signature Profile", profile_name,
                                  ["provider", "environment"], as_dict=True)
    settings = frappe.db.get_value("EC Digital Signature Provider Settings",
                                   {"provider": profile.provider,
                                    "environment": profile.environment}, "*", as_dict=True) or {}
    is_approver = bool(req.approval_status == "Pending" and req.current_level
                       and perms.pending_approver_row(ar, req.current_level, user))
    checks["active_approver"] = is_approver
    checks["level_requires_signature"] = bool(
        req.current_level and guard.level_requires_signature(
            business_doctype, req.approval_type, req.current_level,
            final_level=guard.request_final_level(ar)))
    pkg_name = pkgsvc.active_package_for_request(ar)
    pkg = frappe.db.get_value("EC Digital Signature Package", pkg_name,
                              ["status", "package_hash"], as_dict=True) if pkg_name else None
    checks["package_active_hash_valid"] = bool(
        pkg and pkg.status == "Active" and pkg.package_hash
        and pkgsvc.compute_hash(pkg_name) == pkg.package_hash)
    checks["mandatory_placements_complete"] = bool(
        pkg_name and not pkgsvc.preflight_for_lock(pkg_name))
    checks["verified_mapping"] = bool(perms.verified_mapping(user, profile.environment))
    checks["provider_environment_ok"] = bool(
        profile.environment in binding.ALLOWED_ENVIRONMENTS
        and (profile.environment != "Production" or settings.get("allow_production_signing")))
    raw = (settings.get("allowed_signing_users") or "").replace(",", "\n")
    allowed = {u.strip().lower() for u in raw.splitlines() if u.strip()}
    checks["allowlisted"] = user.lower() in allowed
    checks["gates_enabled"] = bool(settings.get("integration_enabled")
                                   and settings.get("allow_document_creation")
                                   and settings.get("allow_signing"))
    checks["production_signing_on"] = bool(settings.get("allow_production_signing"))
    required = ["active_approver", "level_requires_signature", "package_active_hash_valid",
                "mandatory_placements_complete", "verified_mapping", "provider_environment_ok",
                "allowlisted", "gates_enabled"]
    ready = all(checks.get(k) for k in required)
    reasons = [k for k in required if not checks.get(k)]
    return {"ready": ready, "reasons": reasons, "checks": checks}
