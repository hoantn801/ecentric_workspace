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

from ecentric_workspace.approval_center.esign import guard
from ecentric_workspace.approval_center.esign import hashing
from ecentric_workspace.approval_center.esign import package as pkgsvc
from ecentric_workspace.approval_center.esign import permissions as perms
from ecentric_workspace.approval_center.esign import signer_plan as sp

AR = "EC Approval Request"
PKG = "EC Digital Signature Package"
DSF = "EC Digital Signature File"
_IMMUTABLE_PKG = ("Locked", "Active", "Provider Creating", "Provider Created",
                  "Provider Create Failed", "Completed")


# --------------------------------------------------------------------------- #
# pure helpers (no side effects)
# --------------------------------------------------------------------------- #
def _is_pdf_name(name, url):
    n = (name or "").lower()
    u = (url or "").lower()
    return n.endswith(".pdf") or u.endswith(".pdf")


def _setup_state(requires_signature, is_pdf_like, placement_count):
    """Honest state (no fake n/n before Phase C signer_slot_key):
      supporting_document | unsupported | legacy_unmapped | not_configured.
    'complete' is intentionally NOT produced in A1."""
    if not requires_signature:
        return "supporting_document"
    if not is_pdf_like:
        return "unsupported"
    if placement_count > 0:
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
def _draft_pkg(bd, bn):
    return pkgsvc.draft_package_for_business(bd, bn)


def _immutable_pkg(bd, bn):
    return frappe.db.get_value(
        PKG, {"business_doctype": bd, "business_name": bn, "status": ["in", _IMMUTABLE_PKG]},
        "name", order_by="creation desc")


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


# --------------------------------------------------------------------------- #
# READ MODEL  (zero writes / zero side effects)
# --------------------------------------------------------------------------- #
def get_document_setup_state(business_doctype, business_name):
    perms.assert_can_view_business(business_doctype, business_name)
    draft = _draft_pkg(business_doctype, business_name)
    locked = _immutable_pkg(business_doctype, business_name)
    editable = bool(draft) or not bool(locked)     # no Locked-only package blocks editing
    can_classify = editable and (frappe.session.user == _requester_of(business_doctype,
                                                                      business_name))
    plan = sp.resolve_signer_plan(business_doctype, business_name)
    required_slots = (plan.get("summary") or {}).get("required_slots", 0) if plan.get("resolved") else 0

    groups = _dedupe(_current_files(business_doctype, business_name))
    pkg_for_dsf = draft or locked
    docs, n_sign, n_support = [], 0, 0
    for g in groups:
        rep = g["rep"]
        is_pdf_like = _is_pdf_name(rep.get("file_name"), rep.get("file_url"))
        dsf = None
        # DSF linkage needs SHA-256 (DSF.file is a copy, not the original attachment) - only
        # compute when a package with files could exist, keeping fresh requests read-cheap.
        if pkg_for_dsf and frappe.db.count(DSF, {"package": pkg_for_dsf}):
            dsf = _dsf_by_sha(pkg_for_dsf, _rep_sha(rep))
        if dsf:
            req_sig = bool(dsf.requires_signature)
            classification_source = "digital_signature_file"
            signature_file = dsf.name
            is_pdf_like = bool(dsf.is_pdf)
            placement_count = _placement_count(dsf.name)
        else:
            req_sig = True                          # implicit default; NO DSF created to store it
            classification_source = "default"
            signature_file = None
            placement_count = 0
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
            "setup_state": _setup_state(req_sig, is_pdf_like, placement_count),
            "legacy_placement_count": placement_count,
        })
        n_sign += 1 if req_sig else 0
        n_support += 0 if req_sig else 1

    return {
        "business_doctype": business_doctype, "business_name": business_name,
        "editable": editable, "can_classify": can_classify,
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
    requires_signature = bool(int(requires_signature)) if not isinstance(requires_signature, bool) \
        else requires_signature
    confirm = bool(int(confirm)) if not isinstance(confirm, bool) else confirm
    _assert_can_classify(business_doctype, business_name)

    # 1) resolve document_ref back to a CURRENT private-or-public attachment of THIS record
    f = frappe.db.get_value("File", document_ref,
                            ["name", "attached_to_doctype", "attached_to_name", "file_name",
                             "file_url"], as_dict=True)
    if not f or f.attached_to_doctype != business_doctype or f.attached_to_name != business_name:
        return {"ok": False, "reason": "stale_or_foreign_attachment"}

    # 2) immutability: reuse a Draft; NEVER create a parallel Draft to bypass a Locked package
    draft = _draft_pkg(business_doctype, business_name)
    if not draft and _immutable_pkg(business_doctype, business_name):
        return {"ok": False, "reason": "package_locked"}

    content = frappe.get_doc("File", f.name).get_content()
    sha = hashing.sha256_bytes(content)

    # 3) materialize/reuse the local Draft package (governed, purely local)
    if not draft:
        at, profile, err = sp._resolve_type_and_profile(
            business_doctype, business_name,
            perms.business_approval_request(business_doctype, business_name))
        if err or not profile:
            return {"ok": False, "reason": err or "profile_not_configured"}
        draft = pkgsvc.get_or_create_draft(business_doctype, business_name, profile,
                                           allow_submitted=True).name

    # 4) materialize/reuse exactly ONE DSF for this physical document (idempotent by SHA)
    dsf = _dsf_by_sha(draft, sha)
    try:
        if not dsf:
            display = f.file_name or (f.file_url or "").rsplit("/", 1)[-1] or "document"
            row = pkgsvc.add_file(draft, display, content,
                                  requires_signature=1 if requires_signature else 0,
                                  is_supporting_document=0 if requires_signature else 1)
            dsf_name = row.name
        else:
            dsf_name = dsf.name
            # 5) confirmation gate: turning OFF signing on a document that already has placements
            if not requires_signature:
                plc = _placement_count(dsf_name)
                if plc and not confirm:
                    return {"ok": False, "confirmation_required": True,
                            "reason": "existing_placements", "placement_count": plc}
                if plc and confirm:
                    remaining = [dict(p) for p in pkgsvc.package_placements(draft)
                                 if p.signature_file != dsf_name]
                    pkgsvc.save_placements(draft, remaining)   # governed reset (reuse)
            # 6) canonical write + server-owned mirror (single service owns both fields)
            pkgsvc.set_file_flags(dsf_name,
                                  requires_signature=1 if requires_signature else 0,
                                  is_supporting_document=0 if requires_signature else 1)
    except frappe.ValidationError as e:
        # non-PDF marked as signing-required is refused by _validate_content -> structured state
        if "PDF" in str(e):
            return {"ok": False, "reason": "unsupported_signable_format"}
        raise

    state = get_document_setup_state(business_doctype, business_name)
    doc = next((d for d in state["documents"] if d["document_ref"] == document_ref), None)
    return {"ok": True, "document": doc, "editable": state["editable"]}
