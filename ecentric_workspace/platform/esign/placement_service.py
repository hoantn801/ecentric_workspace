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

from ecentric_workspace.platform.esign import document_setup as ds
from ecentric_workspace.platform.esign import package as pkgsvc
from ecentric_workspace.platform.esign import permissions as perms
from ecentric_workspace.platform.esign import signer_plan as sp
from ecentric_workspace.platform.esign import signing_files

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
        # `level_ref` MUST travel with every slot.
        #
        # The drawer draws a real signature into a box by comparing the box's `level_ref`
        # against the `level_ref` the overlay endpoint reports for each signature. This
        # projection used to drop the field, so in the browser `sl.level_ref` was
        # `undefined`, every approval_level comparison was false, and only the requester
        # slot (matched on `kind` alone) ever rendered. Both endpoints were individually
        # correct; the field was lost in transit between them. 29/08: diagnosed against
        # `signer_plan` -- which DOES carry level_ref -- and wrongly declared the data
        # matching, because that is not the endpoint the screen reads.
        "required_slots": [{"slot_key": s["slot_key"], "label": labels[s["slot_key"]],
                            "kind": s.get("kind"), "approval_mode": s.get("approval_mode"),
                            "level_ref": s.get("level_ref"),
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
    content = pkgsvc.raw_file_bytes(f["name"])
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
        if signing_files.is_signing_file(business_doctype, business_name,
                                         f.get("file_url"), sha=sha) is False:
            frappe.throw(_("Tệp này không phải tài liệu ký của phiếu."))
        display = f.get("file_name") or (f.get("file_url") or "").rsplit("/", 1)[-1] or "document.pdf"
        dsf_name = pkgsvc.add_file(draft, display, content, requires_signature=1,
                                   is_supporting_document=0,
                                   source_file=f["name"]).name   # lien ket, khong sao chep (05/09)
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
    # Ban PDF cu khong con khai trong goi Draft -> go truoc khi dat o (PR-G vong 2 B-1).
    signing_files.reconcile_draft(cur_name, business_doctype, business_name)
    # Loai phieu khai tep ky (ec_esign_signing_files, PR-G): chi dat o ky tren tep do (khop URL
    # hoac noi dung - cung luat voi man thiet lap).
    if signing_files.hook_path(business_doctype) and signing_files.is_signing_file(
            business_doctype, business_name, f.get("file_url"),
            sha=pkgsvc.hashing.sha256_bytes(pkgsvc.raw_file_bytes(f["name"]))) is False:
        return {"ok": False, "reason": "not_signing_file"}
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
    if name is None:                                   # update raced a delete - do NOT resurrect
        return {"ok": False, "reason": "placement_deleted", "state": st}
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


# --------------------------------------------------------------------------- #
# Tu dat o ky theo MOC trong PDF (hop dong / BBNT KOL - THIETKE_ky_so_hop_dong muc 2e, 18/11)
# --------------------------------------------------------------------------- #
MARKER_SLOT_HOOK = "ec_esign_marker_slots"


def _marker_slots(business_doctype, business_name, required):
    """{ten moc: slot_key}. Hook nghiep vu (ec_esign_marker_slots[doctype] -> ham(bd, bn,
    required_slots) -> dict) neu co; khong thi mac dinh: KY_BEN_A -> slot ky DUY NHAT khong phai
    nguoi de nghi (vd CEO "Don vi ky" WF09). Nhieu slot -> khong doan. KY_BEN_B (doi tac) chua co
    slot trong ke hoach ky (cho buoc doi tac - PR-D) -> chi hook moi gan duoc."""
    try:
        hooks = frappe.get_hooks(MARKER_SLOT_HOOK) or {}
        path = hooks.get(business_doctype) if isinstance(hooks, dict) else None
        if isinstance(path, (list, tuple)):
            path = path[-1] if path else None
    except Exception:
        path = None
    if path:
        try:
            res = frappe.get_attr(path)(business_doctype, business_name, required) or {}
        except Exception:
            frappe.log_error(frappe.get_traceback(), "esign marker slot hook %s" % path)
            return {}
        return {k: v for k, v in res.items() if v} if isinstance(res, dict) else {}
    signers = [s for s in required if s.get("kind") != "requester"]
    return {"KY_BEN_A": signers[0]["slot_key"]} if len(signers) == 1 else {}


def auto_place(business_doctype, business_name, document_ref):
    """Tu tao o ky tu moc [[KY_BEN_A]] / [[KY_BEN_B]] trong lop chu cua PDF.

    Di qua DUNG save_placement (cung chot: chi nguoi lap, goi Draft, slot thuoc ke hoach hien tai).
    Khong ghi de: slot da co o tren tep nay -> bo qua. Thu tu:
      1. loai phieu co ham doi chieu: PDF khong lop chu -> CHAN (khong lui ve keo tay - bo qua buoc
         kiem so lieu); khong khop -> CHAN;
      2. khong co moc -> de nguoi lap keo tay (bao ro);
      3. moc -> slot (hook / mac dinh) -> o 180x60pt ngay tren moc.
    """
    from ecentric_workspace.platform.esign import document_verification as dv
    from ecentric_workspace.platform.esign import pdf_markers as pm
    # Khoa hang phieu TRUOC moi lan doc: hai lan bam lien tiep khong tao trung o / trung tep cho
    # cung slot. Bo snapshot cu truoc (REPEATABLE READ: lan doc dau cua transaction lap snapshot;
    # chua ghi gi nen rollback an toan) de moi lan doc SAU khoa thay du lieu lan truoc da commit.
    from ecentric_workspace.platform.esign import lifecycle
    # QUYEN TRUOC MOI THU (QC PR-G vong 2 M-1, vong 3 minor 1): chi nguoi lap - khong thi ket qua
    # doi chieu (so hop dong / so tien lech) lo ra, va nguoi la khong giu duoc khoa hang phieu.
    ds._assert_can_classify(business_doctype, business_name)
    # Doc cong (HTTP) TRUOC khi khoa hang - khong goi mang khi dang giu khoa (QC PR-G vong 3 M1).
    # Chi doc khi co the mo lai (phieu "Can bo sung" + goi da khoa + loai phieu khai tep ky).
    portal = lifecycle.portal_for_possible_reopen(business_doctype, business_name)
    frappe.db.rollback()
    frappe.db.get_value(business_doctype, business_name, "name", for_update=True)
    # Kiem lai quyen SAU khoa (trang thai co the doi trong luc cho khoa).
    ds._assert_can_classify(business_doctype, business_name)
    # Moi phep kiem tep TRUOC (QC PR-G M2): tep sai / khong khop / khong lop chu KHONG BAO GIO mo
    # lai thiet lap ky (mo lai = huy tai lieu cu tren cong, khong lay lai duoc).
    f = _resolve_file(business_doctype, business_name, document_ref)
    if not f:
        return {"ok": False, "reason": "stale_or_foreign_attachment"}
    if not ds._is_pdf_name(f.get("file_name"), f.get("file_url")):
        return {"ok": False, "reason": "not_pdf"}
    content = pkgsvc.raw_file_bytes(f["name"])
    sha = pkgsvc.hashing.sha256_bytes(content)
    if signing_files.is_signing_file(business_doctype, business_name, f.get("file_url"),
                                     sha=sha) is False:
        return {"ok": False, "reason": "not_signing_file",
                "message": "Tệp này không phải tài liệu ký của phiếu."}
    analysis = pm.analyze(content)
    out = {"ok": True, "placed": [], "skipped": list(analysis.get("skipped") or []),
           "verify": None, "reopened": None}
    manual = False
    if dv.verifier_path(business_doctype):
        v = dv.verify(business_doctype, business_name, f.get("file_name"), content, analysis,
                      sha=sha)
        out["verify"] = v
        if v["status"] not in dv.PASS_STATUSES:
            return dict(out, ok=False, reason="verify_%s" % v["status"], message=v.get("reason"))
        manual = v["status"] == "not_applicable"
    # Phieu "Can bo sung" + goi da khoa (nguoi lap khong ky): tep MOI (khac ban da khoa) da qua
    # moi phep kiem -> mo lai thiet lap ky (goi Draft moi) roi moi dat o (PR-G muc 2).
    locked = lifecycle.locked_signable_shas(business_doctype, business_name)
    if locked is not None:
        if sha in locked:
            return dict(out, ok=False, reason="unchanged_in_locked_package",
                        message="Tệp này trùng bản đã khoá trong gói ký - không cần đặt lại ô ký.")
        reopened = lifecycle.maybe_reopen_for_edit(business_doctype, business_name,
                                                   portal=portal)
        out["reopened"] = (reopened or {}).get("new_package")
    cur = _assert_write_ok(business_doctype, business_name)
    # Ban PDF cu con lai trong goi Draft (mo lai TRUOC, tai ban moi SAU) -> go (PR-G vong 2 B-1).
    signing_files.reconcile_draft(cur, business_doctype, business_name)
    if manual:
        # Nghiep vu: phieu nay khong doi chieu theo moc (vd ban scan doi tac da ky) -> nguoi lap
        # keo o ky tay. ok False de ben goi KHONG hieu nham la "o ky da co san" (QC PR-G).
        return dict(out, ok=False, reason="manual_placement",
                    message="Tệp không dùng mốc ký tự động - kéo ô ký bằng tay.")
    if not analysis.get("markers"):
        return dict(out, ok=False, reason="no_markers",
                    message="Không tìm thấy mốc ký trong tệp - kéo ô ký bằng tay.")
    required, _keys, plan = _required_slots(business_doctype, business_name)
    slots = _marker_slots(business_doctype, business_name, required)
    st = placement_state(business_doctype, business_name, document_ref)
    have = {p.get("signer_slot_key") for p in (st.get("placements") or [])}
    seen = set()
    for m in analysis["markers"]:
        name = m["name"]
        slot = slots.get(name)
        if not slot:
            out["skipped"].append({"name": name, "page_index": m["page_index"],
                                   "reason": "no_slot_for_marker"})
            continue
        if name in seen or slot in have:
            out["skipped"].append({"name": name, "page_index": m["page_index"],
                                   "reason": "already_placed"})
            continue
        box = dict(pm.box_for(m), signer_slot_key=slot)
        res = save_placement(business_doctype, business_name, document_ref, box)
        if res.get("ok") is False:
            out["skipped"].append({"name": name, "page_index": m["page_index"],
                                   "reason": res.get("reason")})
            continue
        seen.add(name)
        have.add(slot)
        out["placed"].append({"name": name, "slot": slot, "box": box})
    out["state"] = placement_state(business_doctype, business_name, document_ref)
    return out
