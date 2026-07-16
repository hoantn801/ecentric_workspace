# Copyright (c) 2026, eCentric and contributors
"""Phase A1 - Document Setup read model + classification persistence (backend/service layer).
Shared, business-doctype-agnostic. Reuses native Frappe File (source attachment), the governed
EC Digital Signature File/Package model (local signing representation), the deployed signer_plan
resolver, and the existing package services. NO UI, NO schema change, NO submit/lock lifecycle
change, NO provider/DSR/SCTS call, NO approval transition.

READS create nothing. A local Draft package + DSF are materialized ONLY on an explicit
classification WRITE, and only when no editable package already blocks it (never a parallel
Draft to bypass an immutable/Locked package).

Canonical classification field: EC Digital Signature File.requires_signature.
  Bộ chứng từ  <=>  requires_signature = 0.
is_supporting_document is a server-owned MIRROR (= not requires_signature), never written
independently by the client. file_kind semantics are preserved, not used as a second gate.
"""
import os

import frappe
from frappe import _

from ecentric_workspace.approval_center.esign import events
from ecentric_workspace.approval_center.esign import guard
from ecentric_workspace.approval_center.esign import hashing
from ecentric_workspace.approval_center.esign import package as pkgsvc
from ecentric_workspace.approval_center.esign import permissions as perms
from ecentric_workspace.approval_center.esign import signer_plan as sp

AR = "EC Approval Request"
PKG = "EC Digital Signature Package"
DSF = "EC Digital Signature File"
# Live package statuses (authoritative). Cancelled/Superseded are NEVER authoritative and can
# never override the current package or a native attachment's default classification.
_LIVE_STATES = ("Draft", "Locked", "Active", "Provider Creating", "Provider Created",
                "Provider Create Failed", "Completed")


# --------------------------------------------------------------------------- #
# pure helpers (no side effects)
# --------------------------------------------------------------------------- #
_TRUE = ("true", "1")
_FALSE = ("false", "0")


def _to_bool(v):
    """Canonical boolean normalizer for the public API/service boundary. Frappe serializes
    browser boolean args as STRINGS on the Website call path, so accept bool / 0 / 1 /
    "true" / "false" / "1" / "0" (case-insensitive, trimmed). Reject anything else with a
    ValidationError - NEVER Python bool("false") (which is True)."""
    if isinstance(v, bool):
        return v
    if isinstance(v, int) and v in (0, 1):
        return bool(v)
    sv = str(v).strip().lower()
    if sv in _TRUE:
        return True
    if sv in _FALSE:
        return False
    frappe.throw(_("Giá trị boolean không hợp lệ: {0}").format(v), frappe.ValidationError)


def _is_pdf_name(name, url):
    n = (name or "").lower()
    u = (url or "").lower()
    return n.endswith(".pdf") or u.endswith(".pdf")


def _setup_state(requires_signature, is_pdf_like, covered, required, legacy_unmapped):
    """Phase C real state from covered signer slots:
      supporting_document | unsupported | complete | in_progress | legacy_unmapped | not_configured."""
    if not requires_signature:
        return "supporting_document"
    if not is_pdf_like:
        return "unsupported"
    if required and covered >= required:
        return "complete"
    if covered > 0:
        return "in_progress"
    if legacy_unmapped > 0:
        return "legacy_unmapped"
    return "not_configured"


# --------------------------------------------------------------------------- #
# attachment resolution + physical-document dedupe
# --------------------------------------------------------------------------- #
def _current_files(bd, bn):
    return frappe.get_all(
        "File", filters={"attached_to_doctype": bd, "attached_to_name": bn},
        fields=["name", "file_name", "file_url", "content_hash", "is_private", "creation"],
        order_by="creation asc, name asc")


def _physical_key(f):
    # 1) native content hash; 2) canonical file_url; 3) record identity (never display name)
    return (f.get("content_hash") and "sha:" + f["content_hash"]) \
        or (f.get("file_url") and "url:" + f["file_url"]) \
        or ("file:" + f["name"])


def _dedupe(files):
    """One group per physical document; deterministic representative = earliest creation then
    lowest name (files already ordered so). Returns ordered list of groups."""
    groups, order = {}, []
    for f in files:
        k = _physical_key(f)
        if k not in groups:
            groups[k] = {"key": k, "rep": f, "members": [f]}
            order.append(k)
        else:
            groups[k]["members"].append(f)
    return [groups[k] for k in order]


# --------------------------------------------------------------------------- #
# package / DSF resolution
# --------------------------------------------------------------------------- #
def _current_package(bd, bn):
    """Deterministic CURRENT package + needs_review, by governed precedence:
      1) the editable Draft package (authoritative for editable setup), else
      2) the newest immutable-LIVE package (Locked/Active/Provider*/Completed) for read-only.
    Cancelled/Superseded/orphan packages are excluded and never override. Returns
    (name, status, is_draft, needs_review). needs_review = an ambiguous coexistence
    (>1 Draft, or a Draft AND an immutable-live package at once) - the caller must NOT guess."""
    rows = frappe.get_all(PKG, filters={"business_doctype": bd, "business_name": bn,
                                        "status": ["in", _LIVE_STATES]},
                          fields=["name", "status"], order_by="creation desc")
    drafts = [r for r in rows if r.status == "Draft"]
    immut = [r for r in rows if r.status != "Draft"]
    needs_review = len(drafts) > 1 or (bool(drafts) and bool(immut))
    if drafts:
        return drafts[0].name, drafts[0].status, True, needs_review
    if immut:
        return immut[0].name, immut[0].status, False, needs_review
    return None, None, False, needs_review


def _rep_sha(rep):
    return hashing.sha256_bytes(frappe.get_doc("File", rep["name"]).get_content())


def _dsf_by_sha(pkg_name, sha):
    if not pkg_name:
        return None
    return frappe.db.get_value(DSF, {"package": pkg_name, "sha256": sha},
                               ["name", "requires_signature", "is_pdf"], as_dict=True)


def _placement_count(dsf_name):
    if not dsf_name:
        return 0
    return len([p for p in frappe.get_all("EC Digital Signature Placement",
                                          filters={"signature_file": dsf_name},
                                          fields=["status"]) if (p.status or "") != "Invalid"])


def _requester_of(bd, bn):
    ar = perms.business_approval_request(bd, bn)
    if ar:
        return frappe.db.get_value(AR, ar, "requested_by")
    return frappe.db.get_value(bd, bn, "owner")


def _assert_can_classify(bd, bn):
    """WRITE authorization: the actual requester / business editor ONLY - no Administrator /
    System Manager / generic-role / ignore_permissions bypass. (Package-Draft-only immutability
    is additionally enforced downstream by package.set_file_flags / add_file via
    assert_requester_draft_package.)"""
    perms.assert_can_view_business(bd, bn)
    actor = frappe.session.user
    if actor != _requester_of(bd, bn):
        frappe.throw(_("Chỉ người đề nghị mới được phân loại tài liệu."), frappe.PermissionError)


def _setup_editable(bd, bn):
    """SINGLE governed predicate: may document setup (classification + placement) be MUTATED?
    Editable ONLY during the pre-submit document-setup stage - the business request has NOT been
    sent for approval yet (no EC Approval Request). After 'Gửi yêu cầu' the request enters the
    approval lifecycle -> setup is IMMUTABLE (view-only). Belt-and-suspenders: an ambiguous or
    immutable/frozen signing package also closes the window. Authoritative BUSINESS lifecycle
    state, NOT Frappe docstatus (EC Payment Request is not submittable). Returns (bool, reason)."""
    if perms.business_approval_request(bd, bn):
        return False, "already_submitted"
    cur_name, cur_status, is_draft, needs_review = _current_package(bd, bn)
    if needs_review:
        return False, "needs_review"
    if cur_name and not is_draft:
        return False, "package_locked"
    return True, None


def _assert_setup_editable(bd, bn):
    """Shared gate for ANY document-setup mutation (classification + placement): requester-only
    AND pre-submit editable stage. Raises otherwise. One rule for every write path."""
    _assert_can_classify(bd, bn)                                  # requester-only (raises)
    ok, reason = _setup_editable(bd, bn)
    if not ok:
        msg = {"already_submitted": _("Yêu cầu đã được gửi - không thể thay đổi thiết lập tài liệu/chữ ký."),
               "needs_review": _("Cấu hình ký đang mơ hồ - cần rà soát."),
               "package_locked": _("Gói ký đã được chốt - không thể thay đổi.")}.get(
                   reason, _("Không thể chỉnh sửa thiết lập tài liệu."))
        frappe.throw(msg, frappe.ValidationError)
    return reason


# --------------------------------------------------------------------------- #
# READ MODEL  (zero writes / zero side effects)
# --------------------------------------------------------------------------- #
def get_document_setup_state(business_doctype, business_name):
    perms.assert_can_view_business(business_doctype, business_name)
    cur_name, cur_status, is_draft, needs_review = _current_package(business_doctype, business_name)
    # Classification is allowed during the document-SETUP stage: no signing package yet (a local
    # Draft is materialized on the first write) OR an editable Draft exists. An immutable/frozen
    # package (Locked/Active/Provider*/Completed) closes the window; ambiguity needs review.
    # This is stage-based, NOT business docstatus (EC Payment Request is not submittable).
    editable, editable_reason = _setup_editable(business_doctype, business_name)
    can_classify = editable and (frappe.session.user == _requester_of(business_doctype,
                                                                      business_name))
    plan = sp.resolve_signer_plan(business_doctype, business_name)
    required_slots = (plan.get("summary") or {}).get("required_slots", 0) if plan.get("resolved") else 0
    _req_keys = {sl["slot_key"] for sl in (plan.get("slots") or []) if sl.get("required")} \
        if plan.get("resolved") else set()

    groups = _dedupe(_current_files(business_doctype, business_name))
    pkg_for_dsf = cur_name                          # Draft (editable) or immutable-live; never Cancelled/Superseded
    docs, n_sign, n_support = [], 0, 0
    for g in groups:
        rep = g["rep"]
        is_pdf_like = _is_pdf_name(rep.get("file_name"), rep.get("file_url"))
        dsf = None
        # DSF linkage needs SHA-256 (DSF.file is a copy, not the original attachment) - only
        # compute when a package with files could exist, keeping fresh requests read-cheap.
        if pkg_for_dsf and frappe.db.count(DSF, {"package": pkg_for_dsf}):
            dsf = _dsf_by_sha(pkg_for_dsf, _rep_sha(rep))
        covered = 0
        legacy_unmapped = 0
        if dsf:
            req_sig = bool(dsf.requires_signature)
            classification_source = "digital_signature_file"
            signature_file = dsf.name
            is_pdf_like = bool(dsf.is_pdf)
            _rows = frappe.get_all("EC Digital Signature Placement",
                                   filters={"signature_file": dsf.name, "status": ["!=", "Invalid"]},
                                   fields=["signer_slot_key"])
            covered = len({r.signer_slot_key for r in _rows
                           if r.signer_slot_key and r.signer_slot_key in _req_keys})
            legacy_unmapped = len([r for r in _rows
                                   if not r.signer_slot_key or r.signer_slot_key not in _req_keys])
        else:
            req_sig = True                          # implicit default; NO DSF created to store it
            classification_source = "default"
            signature_file = None
        docs.append({
            "document_ref": rep["name"],            # deterministic representative File.name
            "display_name": rep.get("file_name"),
            "file_url": rep.get("file_url"),
            "duplicate_count": len(g["members"]),
            "requires_signature": req_sig,
            "classification_source": classification_source,
            "signature_file": signature_file,
            "direct_signing_supported": is_pdf_like,
            "required_signer_slots": required_slots if req_sig else 0,
            "covered_slot_count": covered if req_sig else 0,
            "setup_state": _setup_state(req_sig, is_pdf_like, covered,
                                        required_slots if req_sig else 0, legacy_unmapped),
            "legacy_placement_count": legacy_unmapped,
        })
        n_sign += 1 if req_sig else 0
        n_support += 0 if req_sig else 1

    return {
        "business_doctype": business_doctype, "business_name": business_name,
        "editable": editable, "can_classify": can_classify, "setup_editable_reason": editable_reason, "needs_review": needs_review,
        "current_package_status": cur_status,
        "signer_plan": {"resolved": plan.get("resolved"),
                        "slot_key_version": plan.get("slot_key_version"),
                        "summary": {"required_slots": required_slots},
                        "reason": plan.get("reason")},
        "summary": {"documents": len(docs), "requires_signature": n_sign,
                    "supporting_documents": n_support},
        "documents": docs,
        "stale_signing_files": _stale_dsf(business_doctype, business_name, pkg_for_dsf, groups),
    }


def _stale_dsf(bd, bn, pkg_for_dsf, groups):
    """Structured (non-destructive) report of Draft/immutable-package DSF rows whose content is
    no longer a current attachment. Kept for audit; NEVER hard-deleted here."""
    if not pkg_for_dsf:
        return []
    current_shas = set()
    for g in groups:
        try:
            current_shas.add(_rep_sha(g["rep"]))
        except Exception:
            pass
    out = []
    for d in frappe.get_all(DSF, filters={"package": pkg_for_dsf},
                            fields=["name", "file_name", "sha256"]):
        if d.sha256 and d.sha256 not in current_shas:
            out.append({"signature_file": d.name, "display_name": d.file_name})
    return out


# --------------------------------------------------------------------------- #
# CLASSIFICATION WRITE  (idempotent, requester-scoped, package-Draft-only)
# --------------------------------------------------------------------------- #
def set_document_requires_signature(business_doctype, business_name, document_ref,
                                    requires_signature, confirm=False):
    requested = _to_bool(requires_signature)      # canonical (accepts "true"/"false"/1/0/bool)
    confirm = _to_bool(confirm)
    _assert_can_classify(business_doctype, business_name)
    _ok_edit, _edit_reason = _setup_editable(business_doctype, business_name)
    if not _ok_edit:
        return {"ok": False, "reason": _edit_reason}      # sent/locked/needs_review -> immutable

    # 1) resolve document_ref back to a CURRENT attachment of THIS record (revalidated)
    f = frappe.db.get_value("File", document_ref,
                            ["name", "attached_to_doctype", "attached_to_name", "file_name",
                             "file_url"], as_dict=True)
    if not f or f.attached_to_doctype != business_doctype or f.attached_to_name != business_name:
        return {"ok": False, "reason": "stale_or_foreign_attachment"}

    # 2) governed precedence: ambiguous coexistence -> needs_review (never guess); an immutable
    #    current package is never bypassed with a parallel Draft.
    cur_name, cur_status, is_draft, needs_review = _current_package(business_doctype, business_name)
    if needs_review:
        return {"ok": False, "reason": "needs_review"}
    if cur_name and not is_draft:
        return {"ok": False, "reason": "package_locked"}

    content = frappe.get_doc("File", f.name).get_content()
    sha = hashing.sha256_bytes(content)

    # 3) current EFFECTIVE classification WITHOUT materializing anything (default = signable).
    dsf = _dsf_by_sha(cur_name, sha) if cur_name else None
    current_effective = bool(dsf.requires_signature) if dsf else True

    # 3a) TRUE NO-OP: requested == current effective -> zero writes, zero events, unchanged state.
    if requested == current_effective:
        state = get_document_setup_state(business_doctype, business_name)
        doc = next((d for d in state["documents"] if d["document_ref"] == document_ref), None)
        return {"ok": True, "no_op": True, "document": doc, "editable": state["editable"]}

    before = current_effective
    try:
        if not dsf:
            # 4) materialize the local Draft package + exactly ONE DSF (only on a real change,
            #    which - since default is True - is always a change TO supporting=false).
            draft = cur_name
            if not draft:
                at, profile, err = sp._resolve_type_and_profile(
                    business_doctype, business_name,
                    perms.business_approval_request(business_doctype, business_name))
                if err or not profile:
                    return {"ok": False, "reason": err or "profile_not_configured"}
                draft = pkgsvc.get_or_create_draft(business_doctype, business_name, profile,
                                                   allow_submitted=True).name
            display = f.file_name or (f.file_url or "").rsplit("/", 1)[-1] or "document"
            row = pkgsvc.add_file(draft, display, content,
                                  requires_signature=1 if requested else 0,
                                  is_supporting_document=0 if requested else 1)
            dsf_name = row.name
        else:
            draft = cur_name
            dsf_name = dsf.name
            # 5) confirmation gate: turning signing OFF on a document that already has placements
            if not requested:
                plc = _placement_count(dsf_name)
                if plc and not confirm:
                    return {"ok": False, "confirmation_required": True,
                            "reason": "existing_placements", "placement_count": plc}
                if plc and confirm:
                    pkgsvc.clear_file_placements(dsf_name)   # DOCUMENT-scoped (no sibling churn)
            # 6) canonical write + server-owned mirror (single owner: set_file_flags)
            pkgsvc.set_file_flags(dsf_name,
                                  requires_signature=1 if requested else 0,
                                  is_supporting_document=0 if requested else 1)
    except frappe.ValidationError as e:
        if "PDF" in str(e):
            return {"ok": False, "reason": "unsupported_signable_format"}
        raise

    # 7) governed classification audit (reuse the existing event model). track_changes is
    #    provably insufficient (DSF insert makes no Version; set_file_flags uses db.set_value
    #    which bypasses Version), so emit an explicit, focused classification event on the REAL
    #    change only (never for a no-op). Captures actor / time / physical doc / before / after.
    events.emit("DocumentClassificationChanged", package=draft,
                erp_actor=frappe.session.user,
                request_meta={"business_doctype": business_doctype, "business_name": business_name,
                              "signature_file": dsf_name, "sha256": sha,
                              "requires_signature_before": before,
                              "requires_signature_after": requested})

    state = get_document_setup_state(business_doctype, business_name)
    doc = next((d for d in state["documents"] if d["document_ref"] == document_ref), None)
    return {"ok": True, "document": doc, "editable": state["editable"]}


def set_representative_attachment(business_doctype, business_name, file_url):
    """Backward-compatible representative pointer: set the single `request_attachment` field to
    an uploaded File's url ONLY when it is currently empty. Native File rows remain the
    authoritative multi-document list - this pointer only satisfies the legacy required-field
    contract. Guarantees: requester-scoped (NO Administrator/System Manager/role/
    ignore_permissions bypass); the File must genuinely be a current attachment of THIS record;
    never overwrites a non-empty pointer; touches NO other field (atomic single-field write, no
    full save / no recompute of unrelated fields); idempotent."""
    _assert_can_classify(business_doctype, business_name)      # requester-only, no bypass
    if not file_url:
        return {"ok": False, "reason": "no_file_url"}
    if not frappe.db.has_column(business_doctype, "request_attachment"):
        return {"ok": False, "reason": "no_pointer_field"}
    if not frappe.db.exists("File", {"file_url": file_url,
                                     "attached_to_doctype": business_doctype,
                                     "attached_to_name": business_name}):
        return {"ok": False, "reason": "not_attached"}         # not a current attachment of this doc
    current = frappe.db.get_value(business_doctype, business_name, "request_attachment")
    if current:
        return {"ok": True, "changed": False, "request_attachment": current}   # preserve existing
    frappe.db.set_value(business_doctype, business_name, "request_attachment", file_url)
    return {"ok": True, "changed": True, "request_attachment": file_url}
