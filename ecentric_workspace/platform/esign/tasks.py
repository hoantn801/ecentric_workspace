# Copyright (c) 2026, eCentric and contributors
"""Background processing: submit worker, polling reconciler (authoritative - Phase 1
works with polling only), stale monitor, orphan-file scan.

Kill switch: site_config `ec_esign_scheduler_disabled: 1` (fail-safe: any config read
error => disabled; alerts precedent). POLL-FIRST rule: an uncertain previous attempt is
never blindly retried - the worker polls provider state and only submits when the
expected signer is provably unsigned.
"""
import time

import frappe
from frappe.utils import add_to_date, now_datetime

from ecentric_workspace.platform.esign import binding
from ecentric_workspace.platform.esign import events
from ecentric_workspace.platform.esign import package as pkgsvc
from ecentric_workspace.platform.esign import service as svc
from ecentric_workspace.platform.esign import state as sm
from ecentric_workspace.platform.esign.providers import get_adapter
from ecentric_workspace.platform.esign.providers.base import (
    ProviderError, SignatureProviderAdapter, VerificationResult,
)
from ecentric_workspace.platform.esign.sanitize import safe_error

DSR = "EC Digital Signature Request"
EVT = "EC Digital Signature Event"

# Server-derived provider action for bulk-process. The DSR.action -> provider
# transitionType mapping is authoritative here (never from frontend, never the numeric
# transition_id which is reserved for Workflow/transition reject/cancel operations).
_PROVIDER_TRANSITION = {"Sign": "approve"}


def _disabled():
    try:
        return bool(int(frappe.conf.get("ec_esign_scheduler_disabled") or 0))
    except Exception:
        return True  # fail-safe: broken config reads as DISABLED


def _integration_open(provider, environment):
    """True only when the provider integration gate is enabled for this pair. A scheduler
    task must NOT build an adapter or make any SCTS network call while integration is OFF
    (defence in depth on top of the binding/guard gate at write time)."""
    return bool(frappe.db.get_value(
        "EC Digital Signature Provider Settings",
        {"provider": provider, "environment": environment}, "integration_enabled"))


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
         "document_template_id", "doc_code_source", "title_source", "amount_source"],
        as_dict=True) or {}
    _resolve_doc_meta(pkg, prof)                              # fills doc_*_sent once (audited)
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
        "placements": _with_page_heights(pkg.name,
                                         [dict(p) for p in pkgsvc.package_placements(pkg.name)]),
    }
    _enrich_signer_context(ctx["placements"], dsr)  # item 5: derive roleTitle/signatureType
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


def _resolve_doc_meta(pkg, prof):
    """Fill the package's doc_code_sent / doc_title_sent / doc_amount_sent ONCE from the
    profile's source-field config (doc_code_source/title_source/amount_source name business-doc
    fieldnames). These profile fields existed in the schema but were never read (S2B gap) - the
    provider payload fell back to the business name and amount 0."""
    updates = {}
    biz_fields = [f for f in (prof.get("doc_code_source"), prof.get("title_source"),
                              prof.get("amount_source")) if f]
    biz = frappe.db.get_value(pkg.business_doctype, pkg.business_name, biz_fields,
                              as_dict=True) if biz_fields else {}
    if not pkg.doc_code_sent and prof.get("doc_code_source") and biz.get(prof["doc_code_source"]):
        updates["doc_code_sent"] = str(biz[prof["doc_code_source"]])[:140]
    if not pkg.doc_title_sent and prof.get("title_source") and biz.get(prof["title_source"]):
        updates["doc_title_sent"] = str(biz[prof["title_source"]])[:140]
    if pkg.doc_amount_sent in (None, 0) and prof.get("amount_source")             and biz.get(prof["amount_source"]) is not None:
        try:
            updates["doc_amount_sent"] = float(biz[prof["amount_source"]])
        except (TypeError, ValueError):
            pass
    if updates:
        frappe.db.set_value("EC Digital Signature Package", pkg.name, updates)
        for k, v in updates.items():
            setattr(pkg, k, v)


def _with_page_heights(pkg_name, placements):
    """Attach the PDF page height (points) of each placement's page so the provider adapter can
    convert our canonical TOP-LEFT-origin geometry into the provider's coordinate system (SCTS
    expects PDF coordinates = BOTTOM-left origin; live evidence 2026-08-23: the requester's
    signature rendered vertically mirrored). Fail-soft: unknown height -> omitted (adapter
    falls back to 792/Letter)."""
    sizes_by_file = {}
    for pl in placements:
        f = pl.get("signature_file")
        if f not in sizes_by_file:
            try:
                sizes_by_file[f] = pkgsvc._page_sizes(pkgsvc.file_bytes(f)) or []
            except Exception:
                sizes_by_file[f] = []
        sizes = sizes_by_file[f]
        idx = int(pl.get("page_index") or 1) - 1
        if 0 <= idx < len(sizes):
            pl["page_height"] = float(sizes[idx][1])
    return placements


def _enrich_signer_context(placements, dsr):
    """Fill blank per-placement signatureType/roleTitle from GOVERNED derivation (item 5) so
    admins never type them per level. signatureType <- the signer's Verified SCTS mapping
    metadata; roleTitle <- requester role title (profile/default) for a Requester DSR, else a
    level-derived title. Explicit placement values (overrides) are preserved; geometry is
    untouched. `dsr` is the as_dict signing request being assembled."""
    if not placements:
        return placements
    from ecentric_workspace.platform.esign import guard as _g
    from ecentric_workspace.platform.esign import permissions as _perms
    is_req = (dsr or {}).get("actor_type") == "Requester"
    signer = dsr.get("actor_user") if is_req else dsr.get("approver")
    mapping = _perms.verified_mapping(signer, dsr.get("environment")) if signer else None
    sig_type = _g.derive_signature_type(mapping)
    profile = frappe.db.get_value("EC Digital Signature Package", dsr.get("package"), "profile")
    # Per-LEVEL title overrides from the profile's levels table (matched by level_no). The old
    # code passed the DSR-actor is_requester for EVERY placement, so a Requester DSR titled ALL
    # boxes with the requester role - wrong for multi-slot documents (Phase C) and fatal for
    # eContract, where the title selects the sign-template AREA (signatureId) per box.
    level_titles = {int(r.level_no): r.scts_role_title
                    for r in frappe.get_all("EC Digital Signature Profile Level",
                                            filters={"parent": profile},
                                            fields=["level_no", "scts_role_title"])
                    if r.level_no is not None and r.scts_role_title} if profile else {}
    for p in placements:
        if not p.get("signature_type") and sig_type:
            p["signature_type"] = sig_type
        if not p.get("scts_role_title"):
            lvl = p.get("level_no")
            p_is_requester = not lvl                # Phase C: requester slot carries level_no=0
            p["scts_role_title"] = _g.derive_role_title(
                profile, level_no=lvl, is_requester=p_is_requester,
                override=(None if p_is_requester else level_titles.get(int(lvl or 0))))
    return placements


def _complete_dsr(dsr_name, dsr):
    """Route completion by actor_type. Requester DSRs complete through the requester path
    (activation, never engine.approve()); Approval-Level DSRs use the unchanged approver
    completion."""
    if (dsr or {}).get("actor_type") == "Requester":
        from ecentric_workspace.platform.esign import requester
        return requester.reconcile_and_complete_requester(dsr_name)
    return svc.verify_and_complete(dsr_name)


def _profile_of(dsr):
    """Profile name behind this DSR (via its package). Returns None when absent - the
    caller then treats the handover as unconfigured and falls back, loudly."""
    if not dsr.get("package"):
        return None
    return frappe.db.get_value("EC Digital Signature Package", dsr["package"], "profile")


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

        # POLL-FIRST chi danh cho chan ky CO THE da gui roi.
        #
        # 28/08 23:54, EC-DSR-2026-00023: chan duyet Cap 1 vua tao xong, chua gui gi, POLL
        # -FIRST chay ngay va thay tren tai lieu DA CO chu ky cua dung nguoi do - chu ky ma
        # chinh ho vua dat o chan NGUOI TRINH 40 giay truoc. Ket qua: Verified ->
        # ApprovalCompleted trong 1,4 giay, khong mot lenh nao toi SCTS, va cap duyet dong
        # lai voi mot chu ky khong ton tai. Dung lop loi UAT VOID 5.
        #
        # Cau hoi ma POLL-FIRST tra loi ("lan gui truoc co thanh cong khong?") chi co nghia
        # khi DA TUNG GUI. Chan ky chua gui bao gio thi khong the hoan tat bang cach nhin -
        # no phai gui truoc da.
        may_have_sent = sm.may_have_sent(dsr)
        doc_state = adapter.poll_status(doc_id)
        expected = svc._expected_for(dsr)
        expected["document_id"] = doc_id
        vr = (SignatureProviderAdapter.verify_signed_result(doc_state, expected)
              if may_have_sent else VerificationResult(False, "not_sent_yet"))
        if vr.ok:
            if dsr.status != "Signed":
                events.set_dsr_status(dsr_name, "Signed",
                                      extra_fields={"verified_at": now_datetime()},
                                      event_type="Verified", verification_result=vr.reason)
            out = _complete_dsr(dsr_name, dsr)
            _enqueue_signed_retrieval(dsr.package, out)
            return

        signer = doc_state.signer(dsr.effective_scts_user_id,
                                  dsr.actor_user or dsr.approver)
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
            #
            # CHOT MOT CHIEU: neu chan ky nay CO THE DA TUNG gui thi KHONG gui lai. Duong
            # nguy hiem: Provider Accepted -> loi poll -> Retryable Failure -> quay ve Queued
            # -> nhanh nay gui LAN HAI. Lenh ky khong idempotent - lan hai co the tao chu ky
            # thu hai tren cung tai lieu. POLL-FIRST o tren chi cuu duoc khi chu ky da kip
            # xuat hien; cua so con lai phai co nguoi nhin.
            #
            # Dinh nghia cua `may_have_sent` nam o `state.may_have_sent` - MOT cho duy nhat,
            # dung chung voi trang ops de nhan nut noi dung viec se xay ra.
            # Fail-closed: Manual Review de "Doi soat" (chi DOC) quyet dinh, khong bao gio doan.
            if may_have_sent:
                # GHI LY DO VERIFY TU CHOI. Truoc day `vr.reason` bi vut o day, nen su kien
                # ManualReview trong ron: 02/09 23:40 phai suy luan ra "cua so thoi gian bi
                # Thu lai day len sau chu ky" thay vi doc mot dong. Mot cho roi vao Manual
                # Review ma khong noi vi sao la mot cho nguoi truc phai doan.
                events.set_dsr_status(dsr_name, "Manual Review", event_type="ManualReview",
                                      verification_result=vr.reason,
                                      extra_fields={"manual_review_reason":
                                                    "prior_bulk_submit_uncertain"})
                return
            tt = _PROVIDER_TRANSITION.get(dsr.action)
            if not tt:
                raise ProviderError("scts_no_provider_transition",
                                    "no provider transitionType mapped for action %r"
                                    % dsr.action, retryable=False)
            # GOVERNED HANDOVER (2026-08-27). eContract broadcasts to the whole role pool
            # unless the caller names the next handler - which is how somebody outside the
            # chain signed EC-PAYR-2026-00026. Prefer the portal's own `transition` path
            # with an explicit `toUsers`; fall back to the pool-wide call only when the next
            # handler genuinely cannot be named, and RECORD why (never silently).
            from ecentric_workspace.platform.esign import next_handler
            stage = "requester" if dsr.actor_type == "Requester" else "approval"
            # Naming the next handler is an IMPROVEMENT on top of a path that already works.
            # It must never be able to break signing: the first version raised on a child
            # table query and killed the whole leg, leaving the DSR stuck at Queued with no
            # provider call at all. Any failure here degrades to the previous behaviour and
            # is recorded - never propagated.
            # INSTANCE id, khong phai DOCUMENT id. Truyen document id vao
            # `/api/Workflow/{instanceId}` tra 404 voi moi nguoi - do bang tay 02/09, ke ca
            # nguoi da ky that tren chinh tai lieu do - nen kham pha canh chuyen chua bao gio
            # chay duoc va moi lenh ky deu roi ve pool.
            from ecentric_workspace.platform.esign.package import workflow_instance_id
            inst_id = workflow_instance_id(dsr.package) or doc_id
            try:
                plan = next_handler.plan_handover(dsr, _profile_of(dsr),
                                                  settings.get("environment"), stage=stage,
                                                  adapter=adapter, instance_id=inst_id)
            except Exception as exc:
                plan = {"mode": "pool", "reason": "handover_planning_failed:%s"
                                                  % type(exc).__name__}
                frappe.log_error(frappe.get_traceback(), "esign handover planning failed")
            res = None
            if plan["mode"] == "transition" and hasattr(adapter, "transition_with_recipients"):
                events.emit("HandoverTargeted", signature_request=dsr_name, package=dsr.package,
                            request_meta={"to_users": plan.get("to_users"),
                                          "erp_users": plan.get("erp_users"),
                                          # Ai bi eContract tu choi nhan, va co hoi duoc
                                          # khong. Thieu hai truong nay thi dsr_trace chi
                                          # thay danh sach cuoi cung, khong thay vi sao no
                                          # ngan di - dung khoang toi da ton hai ngay.
                                          "dropped_not_eligible":
                                              plan.get("dropped_not_eligible"),
                                          "recipients_unverified":
                                              plan.get("recipients_unverified"),
                                          "stage": stage})
                try:
                    res = adapter.transition_with_recipients(
                        inst_id, dsr.effective_scts_user_id, plan["to_users"], plan["config"],
                        dsr.effective_signature_id)
                except ProviderError as exc:
                    # A DEFINITE rejection (4xx) means the provider did NOT act, so re-sending
                    # through the older proven path is safe and is not a double-sign. An
                    # AMBIGUOUS outcome (timeout/5xx) may already have been applied - never
                    # resend that one. Naming the next handler is an improvement layered on a
                    # path that already worked; it must never stop signing altogether.
                    if getattr(exc, "ambiguous", False):
                        raise
                    events.emit("HandoverPoolFallback", signature_request=dsr_name,
                                package=dsr.package, error_summary=safe_error(exc),
                                request_meta={"stage": stage,
                                              "reason": "transition_rejected_falling_back"})
            if res is None:
                if plan["mode"] != "transition":
                    events.emit("HandoverPoolFallback", signature_request=dsr_name,
                                package=dsr.package,
                                error_summary="next handler not named: %s" % plan.get("reason"),
                                request_meta={"stage": stage, "reason": plan.get("reason")})
                # `bulk-process` nhan `instanceIds`. Gui document id vao day chinh la hinh
                # dang that bai kho chan doan nhat cua ca vu: SCTS tra 2xx kem
                # bulkJobTransactionId roi khong ky gi ca, vi cong viec khong tro vao instance
                # nao. Loi 400 cua duong `transition` con bao ngay; duong nay im lang.
                res = adapter.approve_and_sign([inst_id], dsr.effective_scts_user_id,
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
            out = _complete_dsr(dsr_name, dsr)
            _enqueue_signed_retrieval(dsr.package, out)
            return
        if dsr.status == "Provider Accepted":
            events.set_dsr_status(dsr_name, "Verifying", event_type="PollTick",
                                  verification_result=vr.reason)
            # Lan poll ngay lap tuc o tren gan nhu luon truot: no chay khoang mot giay sau
            # khi nha cung cap NHAN lenh, con chu ky thuong xuat hien sau 20-40 giay. Sau do
            # thi khong con ai hoi lai cho toi vong cron - va nguoi vua bam "Duyet & Ky"
            # ngoi nhin man hinh khong doi gi trong nhieu phut. Bao cao 28/08: "phai 2-5 phut
            # sau no moi bao da xu ly. Delay nhu nay kha khong tot cho UI UX".
            #
            # Nen bam mot cong viec doi soat NHANH ngay sau day. No CHI DOC va xac minh,
            # khong bao gio gui lenh ky - nen chay them vai lan la vo hai.
            _enqueue_fast_verify(dsr_name)
        elif dsr.status == "Verifying":
            # EVERY poll must leave a trace, not just the first one. Previously only the
            # Provider Accepted -> Verifying transition emitted PollTick, so a leg that kept
            # failing verification went completely silent: the reconciler was retrying every
            # five minutes but the event log stopped dead, which reads exactly like a stalled
            # job. That cost real time to chase during the 2026-08-27 pilot.
            events.emit("PollTick", signature_request=dsr_name, package=dsr.package,
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
    """Cron */1 (doi tu */5 ngay 27/08): doi soat moi chan ky con dang bay. Chan tren la
    max_poll_attempts trong settings -> Manual Review."""
    if _disabled():
        return
    rows = frappe.get_all(DSR, filters={"status": ["in", ["Queued", "Provider Accepted",
                                                          "Verifying", "Retryable Failure",
                                                          "Signed"]]},
                          fields=["name", "status", "provider", "environment",
                                  "request_attempt"], limit_page_length=200)
    for r in rows:
        if not _integration_open(r.provider, r.environment):
            continue  # gate OFF -> no adapter, no SCTS network call
        try:
            if r.status == "Signed":
                # Re nhanh theo actor_type qua _complete_dsr, KHONG goi thang
                # svc.verify_and_complete. Duong verify_and_complete la duong APPROVER: no
                # goi engine.approve, ma nguoi de nghi khong phai approver nen engine tu
                # choi -> chan ky bi dong dau Manual Review. Nut "Doi soat" tren trang ops
                # (reconcile_signature_request) truoc day cung goi y het, nen bam cuu ho
                # chi lap lai dung loi do: ket vinh vien, requester_signature_status ket
                # 'Processing', Cap 1 khong bao gio kich hoat. 31/08: 4 chan "Manual Review
                # Requester" tren trang ops la dung lop loi nay.
                #
                # Doc actor_type/package tu DB chu khong tu hang get_all: hang do la ban
                # chieu hep, va mot ban chieu thieu truong thi dict.get tra None - tuc la
                # lai re nham sang duong approver trong IM LANG, dung loi vua sua.
                full = frappe.db.get_value(DSR, r.name, ["name", "actor_type", "package"],
                                           as_dict=True) or {}
                out = _complete_dsr(r.name, full)
                _enqueue_signed_retrieval(full.get("package"), out)
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


#: Doi soat nhanh ngay sau khi nha cung cap nhan lenh. Cac moc do bang giay ke tu luc bam.
#:
#: "20-40 giay" la so do thoi con di duong pool (eContract tu gan nguoi roi moi ky). Tu 02/09
#: chan duyet di targeted, do lai tren ba chan that: chu ky xuat hien sau 2-5 giay ke tu
#: ProviderAccepted (00032: 8,7s ke ca cho; 00033: 4,3s; 00031 thu lai: 2s). Voi nhip cu, lan
#: hoi dau +0,8s luon truot (SCTS chua kip ghi) roi phai doi 8s nua - tuc nguoi dung nhin man
#: hinh them ~5 giay vi mot con so cu.
#:
#: Nhip moi: 2, 3, 4, 6, 10 (tong 25s giu worker, thay vi 80s). Van chi la tang tang toc -
#: vong cron la luoi an toan. `short` worker giu toi da 25s nen lenh ky ke tiep (cung hang
#: `short` tu 03/09) khong bao gio phai doi qua lau.
FAST_VERIFY_DELAYS = (2, 3, 4, 6, 10)
#: Cac trang thai con dang bay - ra khoi tap nay thi dung ngay, khong doi tiep.
_FAST_VERIFY_LIVE = ("Provider Accepted", "Verifying")


def _enqueue_fast_verify(dsr_name):
    """Bam mot vong doi soat ngan, chay nen. Nuot moi loi: day la tang tang toc, khong
    phai duong bao dam - vong cron van la luoi an toan."""
    try:
        frappe.enqueue("ecentric_workspace.platform.esign.tasks.fast_verify",
                       queue="short", timeout=180, dsr_name=dsr_name,
                       job_name="esign_fastverify_%s" % dsr_name,
                       enqueue_after_commit=True)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "esign.tasks._enqueue_fast_verify")


def fast_verify(dsr_name):
    """Hoi nha cung cap vai lan trong khoang 80 giay dau, roi nhuong lai cho vong cron.

    CHI DOC + xac minh. Khong gui lenh ky, khong retry lenh ky - mot lenh ky khong
    idempotent thi khong bao gio duoc phat lai tu dong. Cai nay chi rut ngan khoang thoi
    gian nguoi dung ngoi nhin man hinh khong doi gi.
    """
    if _disabled():
        return
    for wait in FAST_VERIFY_DELAYS:
        time.sleep(wait)
        status = frappe.db.get_value(DSR, dsr_name, "status")
        if status not in _FAST_VERIFY_LIVE:
            return                      # da xong (hoac da hong) - khong hoi nua
        try:
            process_signing_request(dsr_name)
        except Exception:
            frappe.log_error(frappe.get_traceback(), "esign.tasks.fast_verify %s" % dsr_name)
            return
        if frappe.db.get_value(DSR, dsr_name, "status") not in _FAST_VERIFY_LIVE:
            return


#: A leg the provider accepted normally produces a signature within SECONDS - measured on
#: this system: 2s, 2s, 1s. Past this many minutes with nothing happening, waiting longer is
#: not going to help; somebody has to look.
PROVIDER_SILENCE_MINUTES = 20


def flag_silent_legs():
    """Every 5 minutes: a leg the provider ACCEPTED but never acted on -> Manual Review.

    On 2026-08-27 a leg sat in `Verifying` while the provider had accepted the job, returned
    a transaction id, and then done nothing at all: no signature, not even a row in its own
    workflow log. The only backstop was sweep_stale at 24 hours. On a live system carrying
    real payment approvals, a whole day of looking-busy-while-stuck is not an acceptable
    failure mode - and the person waiting has no way to tell it apart from "the provider is
    slow today".

    Deliberately conservative: only legs the provider has already ACCEPTED (so we know the
    request left us), only after twenty minutes, and it moves them to Manual Review rather
    than retrying - a non-idempotent signing write must never be replayed automatically.
    """
    if _disabled():
        return
    rows = frappe.get_all(DSR, filters={"status": ["in", ["Provider Accepted", "Verifying"]]},
                          fields=["name", "status", "accepted_at", "modified", "package"],
                          limit_page_length=200)
    now = now_datetime()
    cutoff = add_to_date(now, minutes=-PROVIDER_SILENCE_MINUTES)
    for r in rows:
        try:
            since = r.accepted_at or r.modified
            if not since or since > cutoff:
                continue
            events.set_dsr_status(
                r.name, "Manual Review", event_type="ManualReview",
                extra_fields={"manual_review_reason": "provider_accepted_but_silent"},
                error_summary=("nha cung cap da nhan lenh luc %s nhung khong tao chu ky sau %s phut"
                               % (since, PROVIDER_SILENCE_MINUTES)))
            _dead_letter_todo(r.name)
        except Exception:
            frappe.log_error(frappe.get_traceback(), "esign.tasks.flag_silent_legs %s" % r.name)


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
    (Administrator fallback), plus a notification to that owner AND to the person whose
    signature is stuck."""
    if frappe.db.exists("ToDo", {"reference_type": DSR, "reference_name": dsr_name,
                                 "status": "Open"}):
        return
    owner = None
    # `order_by` KHONG phai trang tri: khong co no thi nguoi nhan viec phu thuoc thu tu
    # tra ve cua DB - cung mot loai su co, hai lan chay co the roi vao hai nguoi khac
    # nhau, va khong ai la nguoi chiu trach nhiem co dinh. Sap theo `parent` cho ket qua
    # on dinh va tai lap duoc khi di truy nguyen mot su co.
    for u in frappe.get_all("Has Role", filters={"role": "System Manager",
                                                 "parenttype": "User"},
                            fields=["parent"], distinct=True, order_by="parent asc",
                            limit_page_length=20):
        r = frappe.db.get_value("User", u.parent, ["enabled", "user_type"], as_dict=True)
        if r and r.enabled and r.user_type == "System User" and u.parent != "Administrator":
            owner = u.parent
            break
    frappe.get_doc({"doctype": "ToDo", "allocated_to": owner or "Administrator",
                    "reference_type": DSR, "reference_name": dsr_name,
                    "description": "esign: signing request needs manual review",
                    "assigned_by": "Administrator"}).insert(ignore_permissions=True)
    # Mot dong trong `tabToDo` khong phai mot lan cham toi nguoi that: nguoi truc chi
    # thay no neu tu mo Action Center, con NGUOI DANG CHO KY (nguoi duyet / nguoi de
    # nghi) thi khong co gi bao ca - phieu cua ho dung im o mot trang thai khong tu
    # thoat ra duoc. Thong bao di qua dung pipeline chung nen the chuong tro ve
    # /ec-esign/ops (nhanh esign trong action_center.resolvers), noi sua duoc chan ky.
    # Nuot loi: mot thong bao hong khong duoc lam mat viec dead-letter vua tao.
    try:
        from ecentric_workspace.approval_center.shared.workflow import transitions as engine
        d = frappe.db.get_value(DSR, dsr_name, ["actor_user", "requested_by"],
                                as_dict=True) or {}
        who = [owner or "Administrator", d.get("actor_user"), d.get("requested_by")]
        engine.notify([w for w in who if w],
                      "Chữ ký số cần can thiệp thủ công: %s" % dsr_name, DSR, dsr_name)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "esign.tasks._dead_letter_todo notify")


def _enqueue_signed_retrieval(package_name, complete_result):
    """After a VERIFIED completion, queue signed-PDF retrieval. It is a separate job:
    a download failure never reverses the already-verified signature or downgrades the
    terminal DSR - it only leaves signed_bundle_complete=0 for a safe read retry."""
    if not package_name or not (complete_result or {}).get("completed"):
        return
    try:
        frappe.enqueue(
            "ecentric_workspace.platform.esign.signed_files.retrieve_and_store_for_package",
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
        # `retrieval_abandoned` la co NGUOI bat, sau khi ket luan tai lieu ben nha cung cap
        # khong con lay ve duoc nua. Khong loc no o day thi nut "Ngung thu lai" chi la trang
        # tri: cron van goi mang moi 30 phut cho mot goi da co nguoi tuyen bo la bo.
        filters={"scts_document_id": ["is", "set"], "signed_bundle_complete": 0,
                 "retrieval_abandoned": 0},
        fields=["name", "provider", "environment"], limit_page_length=200)
    from ecentric_workspace.platform.esign import signed_files
    for r in rows:
        if not _integration_open(r.provider, r.environment):
            continue  # gate OFF -> no adapter, no SCTS network call
        # only retry for packages with a terminal-completed approval DSR
        done = frappe.db.exists(DSR, {"package": r.name, "status": "Approval Completed"})
        if not done:
            continue
        try:
            out = signed_files.retrieve_and_store_for_package(r.name)
        except Exception:
            frappe.log_error(frappe.get_traceback(),
                             "esign.tasks.retrieve_signed_bundles %s" % r.name)
            out = None
        if not (out or {}).get("ok"):
            _flag_stalled_retrieval(r.name)


#: Cron chay moi 30 phut. 10 lan ~ 5 tieng khong lay duoc PDF thi khong con la "cham" nua.
RETRIEVAL_ALERT_AFTER = 10


def _flag_stalled_retrieval(package_name):
    """Bao dong MOT LAN khi mot goi thu lai qua nhieu ma van chua co PDF da ky.

    Vong lap tren khong dem gi ca: no thu lai VO HAN, khong leo thang, khong tao nhac viec.
    Chu thich trong hooks.py viet "bounded retry" nhung trong code khong co gioi han nao.
    Nen mot goi hong quay mai trong im lang, va tren man hinh no trong y het mot goi dang
    cho binh thuong. 29/08: hai goi da quay hon ba muoi lan voi loi 404 ma khong ai biet.

    Bao dong DUNG MOT LAN cho moi goi (su kien tu no la co chan trung): keu moi 30 phut thi
    chi ba ngay la khong ai doc nua.
    """
    try:
        # Dem qua signed_files.retrieval_rounds, KHONG dem `SignedFileRetrievalStarted`.
        # Su kien do chi ton tai tren duong di thuan loi, nen bao dong nay tung khong the keu
        # cho dung loai goi ma no sinh ra de canh - xem chu thich o retrieval_rounds.
        from ecentric_workspace.platform.esign import signed_files
        tries = signed_files.retrieval_rounds(package_name)
        if tries < RETRIEVAL_ALERT_AFTER:
            return
        if frappe.db.exists(EVT, {"package": package_name,
                                  "event_type": "SignedRetrievalStalled"}):
            return
        events.emit("SignedRetrievalStalled", package=package_name,
                    request_meta={"attempts": tries, "threshold": RETRIEVAL_ALERT_AFTER})
    except Exception:
        # Bao dong hong thi KHONG duoc lam gay vong lap tai file - viec chinh quan trong hon.
        frappe.log_error(frappe.get_traceback(),
                         "esign.tasks._flag_stalled_retrieval %s" % package_name)


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
