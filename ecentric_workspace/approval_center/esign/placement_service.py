# Copyright (c) 2026, eCentric and contributors
"""Phase C - functional, governed signer-slot PLACEMENT service. Turns the A2 drawer into a
real placement workspace on top of the B1 signer plan and the existing package/placement model.

Guarantees: document-SCOPED mutation (File A never churns File B); requester-scoped writes only
(no Administrator/System Manager/role/ignore_permissions bypass); editable signing-setup stage
only (absent or Draft package; Locked/Active/Provider/Completed => denied); signer_slot_key must
exist in the CURRENT authoritative B1 plan (never trusts the browser); progress is unique
covered required slots / total required slots (never raw box count); legacy placements without a
current slot key are surfaced honestly, never counted. No Phase D/E: no freeze, no submit
gating, no provider/runtime/SCTS change.
"""
import frappe
from frappe import _

from ecentric_workspace.approval_center.esign import document_setup as ds
from ecentric_workspace.approval_center.esign import package as pkgsvc
from ecentric_workspace.approval_center.esign import permissions as perms
from ecentric_workspace.approval_center.esign import signer_plan as sp

PL = "EC Digital Signature Placement"


# --------------------------------------------------------------------------- #
# read model
# --------------------------------------------------------------------------- #
def _slot_label(slot):
    if slot.get("kind") == "requester":
        return "Người đề nghị"
    mode = slot.get("approval_mode")
    suffix = " (một trong)" if mode == "Any One" else (" (tối thiểu)" if mode == "Minimum Count" else "")
    return (slot.get("level_name") or ("Cấp %s" % slot.get("level_no"))) + suffix


def _required_slots(bd, bn):
    plan = sp.resolve_signer_plan(bd, bn)
    if not plan.get("resolved"):
        return [], {}, plan
    req = [s for s in (plan.get("slots") or []) if s.get("required")]
    return req, {s["slot_key"] for s in req}, plan


def _resolve_file(bd, bn, document_ref):
    f = frappe.db.get_value("File", document_ref,
                            ["name", "attached_to_doctype", "attached_to_name", "file_name",
                             "file_url"], as_dict=True)
    if not f or f.attached_to_doctype != bd or f.attached_to_name != bn:
        return None
    return f


def _is_pdf(f, dsf):
    if dsf:
        return bool(dsf.get("is_pdf"))
    return ds._is_pdf_name(f.get("file_name"), f.get("file_url"))


def _dsf_for(bd, bn, f, pkg_name):
    if not pkg_name:
        return None
    return ds._dsf_by_sha(pkg_name, ds._rep_sha({"name": f["name"]}))


def _placement_rows(pkg_name, dsf_name):
    return frappe.get_all(PL, filters={"package": pkg_name, "signature_file": dsf_name,
                                       "status": ["!=", "Invalid"]},
                          fields=["name", "page_index", "x", "y", "width", "height",
                                  "signer_slot_key", "signer_slot_version"],
                          order_by="creation asc")


def placement_state(business_doctype, business_name, document_ref):
    """Read-only placement + progress state for one physical document. Permission-checked."""
    perms.assert_can_view_business(business_doctype, business_name)
    cur_name, cur_status, is_draft, needs_review = ds._current_package(business_doctype, business_name)
    is_requester = frappe.session.user == ds._requester_of(business_doctype, business_name)
    _editable, _edit_reason = ds._setup_editable(business_doctype, business_name)
    editable = _editable and is_requester            # sent (AR exists) => immutable, view-only

    required, required_keys, plan = _required_slots(business_doctype, business_name)
    f = _resolve_file(business_doctype, business_name, document_ref)
    if not f:
        return {"business_doctype": business_doctype, "business_name": business_name,
                "document_ref": document_ref, "ok": False, "reason": "stale_or_foreign_attachment"}
    dsf = _dsf_for(business_doctype, business_name, f, cur_name)
    is_pdf = _is_pdf(f, dsf)
    requires_signature = bool(dsf.get("requires_signature")) if dsf else True

    rows, covered, legacy = [], set(), 0
    if dsf:
        for p in _placement_rows(cur_name, dsf["name"]):
            k = p.get("signer_slot_key")
            rows.append({"name": p["name"], "page_index": p["page_index"], "x": p["x"], "y": p["y"],
                         "width": p["width"], "height": p["height"], "signer_slot_key": k})
            if k and k in required_keys:
                covered.add(k)
            else:
                legacy += 1

    labels = {s["slot_key"]: _slot_label(s) for s in required}
    return {
        "business_doctype": business_doctype, "business_name": business_name,
        "document_ref": document_ref, "display_name": f.get("file_name"),
        "file_url": f.get("file_url"), "ok": True,
        "editable": editable, "setup_editable_reason": _edit_reason, "needs_review": needs_review,
        "is_pdf": is_pdf, "requires_signature": requires_signature,
        "supporting_document": (dsf is not None and not requires_signature),
        "slot_key_version": plan.get("slot_key_version"),
        "signer_plan_resolved": plan.get("resolved"),
        "required_slots": [{"slot_key": s["slot_key"], "label": labels[s["slot_key"]],
                            "kind": s.get("kind"), "approval_mode": s.get("approval_mode"),
                            "candidates": s.get("candidates", [])} for s in required],
        "placements": rows,
        "covered_slot_count": len(covered),
        "required_slot_count": len(required) if requires_signature else 0,
        "progress": {"covered": len(covered),
                     "required": len(required) if requires_signature else 0},
        "legacy_unmapped_count": legacy,
    }


# --------------------------------------------------------------------------- #
# governed writes
# --------------------------------------------------------------------------- #
def _assert_write_ok(business_doctype, business_name):
    """SINGLE shared gate (ecentric_workspace...document_setup._assert_setup_editable): requester
    only (no Admin/SM/role/ignore_permissions bypass) AND pre-submit editable stage. Once the
    request has been sent ('Gửi yêu cầu' => EC Approval Request exists) placement is IMMUTABLE:
    add/move/resize/delete are all rejected here, not just disabled in the UI."""
    ds._assert_setup_editable(business_doctype, business_name)   # raises if not requester / sent / locked
    cur_name, cur_status, is_draft, needs_review = ds._current_package(business_doctype, business_name)
    return cur_name


def _ensure_signable_dsf(business_doctype, business_name, f, cur_name):
    """Resolve/materialize the local Draft package + one signable DSF for this physical PDF
    (governed, purely local - no provider/DSR/SCTS/lock). Returns (draft_name, dsf_name)."""
    content = frappe.get_doc("File", f["name"]).get_content()
    sha = pkgsvc.hashing.sha256_bytes(content)
    draft = cur_name
    if not draft:
        at, profile, err = sp._resolve_type_and_profile(
            business_doctype, business_name,
            perms.business_approval_request(business_doctype, business_name))
        if err or not profile:
            frappe.throw(_("Chưa cấu hình hồ sơ ký cho loại yêu cầu này."))
        draft = pkgsvc.get_or_create_draft(business_doctype, business_name, profile,
                                           allow_submitted=True).name
    dsf = ds._dsf_by_sha(draft, sha)
    if not dsf:
        display = f.get("file_name") or (f.get("file_url") or "").rsplit("/", 1)[-1] or "document.pdf"
        dsf_name = pkgsvc.add_file(draft, display, content, requires_signature=1,
                                   is_supporting_document=0).name
    else:
        dsf_name = dsf["name"]
    return draft, dsf_name


def save_placement(business_doctype, business_name, document_ref, box):
    """Create/update ONE signature box for a signable PDF document. Governed + slot-validated +
    document-scoped + idempotent. Materializes the local Draft package/DSF on first placement."""
    box = frappe.parse_json(box) if isinstance(box, str) else (box or {})
    cur_name = _assert_write_ok(business_doctype, business_name)
    f = _resolve_file(business_doctype, business_name, document_ref)
    if not f:
        return {"ok": False, "reason": "stale_or_foreign_attachment"}
    dsf_probe = _dsf_for(business_doctype, business_name, f, cur_name)
    if dsf_probe is not None and not dsf_probe.get("requires_signature"):
        return {"ok": False, "reason": "supporting_document"}
    if not _is_pdf(f, dsf_probe):
        return {"ok": False, "reason": "not_pdf"}
    # slot key must be in the CURRENT authoritative B1 plan (never trust the browser)
    required, required_keys, plan = _required_slots(business_doctype, business_name)
    slot = box.get("signer_slot_key")
    if not slot or slot not in required_keys:
        return {"ok": False, "reason": "invalid_slot_key"}
    # LEGACY RUNTIME COMPAT: the deployed provider payload / preflight still key off level_no.
    # Resolve it from the AUTHORITATIVE B1 plan slot (which itself came from the frozen
    # EC Approval Request Level), NOT from parsing the slot-key string. Requester slot => 0.
    # signer_slot_key remains the unique identity; level_no may be shared across Any One / All /
    # Minimum slots at the same level. scts_role_title is left blank so the existing governed
    # runtime derivation (tasks._enrich_signer_context) fills it - level_no is not re-authored
    # as the identity.
    slot_obj = next((so for so in required if so["slot_key"] == slot), None)
    compat_level_no = 0 if (slot_obj and slot_obj.get("kind") == "requester") \
        else int((slot_obj or {}).get("level_no") or 0)
    draft, dsf_name = _ensure_signable_dsf(business_doctype, business_name, f, cur_name)
    name = pkgsvc.upsert_placement(draft, dsf_name, {
        "name": box.get("name"), "page_index": box.get("page_index"),
        "x": box.get("x"), "y": box.get("y"), "width": box.get("width"), "height": box.get("height"),
        "level_no": compat_level_no,
        "signer_slot_key": slot, "signer_slot_version": plan.get("slot_key_version")})
    st = placement_state(business_doctype, business_name, document_ref)
    return {"ok": True, "placement_name": name, "state": st}


def delete_placement(business_doctype, business_name, document_ref, placement_name):
    """Delete ONE signature box (governed; document-scoped; siblings untouched)."""
    _assert_write_ok(business_doctype, business_name)
    row = frappe.db.get_value(PL, placement_name, ["signature_file"], as_dict=True) \
        if frappe.db.exists(PL, placement_name) else None
    if row:
        # the placement's file must belong to THIS business document (scope check)
        pkg = frappe.db.get_value("EC Digital Signature File", row.signature_file, "package")
        biz = frappe.db.get_value("EC Digital Signature Package", pkg,
                                  ["business_doctype", "business_name"], as_dict=True) or {}
        if biz.get("business_doctype") != business_doctype or biz.get("business_name") != business_name:
            return {"ok": False, "reason": "foreign_placement"}
        pkgsvc.delete_placement_row(placement_name)
    st = placement_state(business_doctype, business_name, document_ref)
    return {"ok": True, "state": st}
