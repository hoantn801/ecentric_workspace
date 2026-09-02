# Copyright (c) 2026, eCentric and contributors
"""Document-package service: upload hardening (orphan-file prevention), flags, order,
placements, hashing, locking and versioning.

ORPHAN-FILE PREVENTION (pilot blocker, directive 2026-07-11): there is NO docname-less
upload path here. `add_file` requires an existing business draft owned by the caller;
the native File doc and the EC Digital Signature File row are created in the SAME
transaction (any failure rolls both back). The esign UI never calls the native
/api/method/upload_file.
"""
import io
import mimetypes
import os

import frappe
from frappe import _
from frappe.utils import now_datetime

from ecentric_workspace.platform.esign import events, hashing
from ecentric_workspace.platform.esign import permissions as perms

EXT_DENYLIST = (".crdownload", ".tmp", ".part", ".partial", ".download", ".exe",
                ".bat", ".cmd", ".sh", ".js", ".vbs", ".msi", ".dll")
PDF_MAGIC = b"%PDF-"


# --------------------------------------------------------------------------- #
# lookups
# --------------------------------------------------------------------------- #
def get_package(name):
    return frappe.get_doc("EC Digital Signature Package", name)


def active_package_for_request(approval_request):
    n = frappe.db.get_value("EC Digital Signature Package",
                            {"approval_request": approval_request, "status": "Active"}, "name")
    return n


def signable_package_for_request(approval_request):
    """The live signable package for a request: Locked (pre-provider) OR Active. Per
    flow/payment_request.py the requester_sign step runs at package_entry ("Locked",
    "Active") and ONLY the provider worker promotes Locked -> Active (nested inside the
    first signing). A lookup that requires "Active" therefore deadlocks the requester
    stage (bug found in the 2026-08-22 UAT pilot: lock -> Locked, submit_and_sign asked
    for Active -> 'Khong co goi tai lieu san sang ky'). Post-provider invariants that
    genuinely need Active (binding/guard completion checks) keep using their own
    status assertions."""
    # "Provider Create Failed" is the declared PARK state of provider_create (flow docs); the
    # state machine allows it back into "Provider Creating", and the worker re-enters it nested
    # inside the next signing attempt - so a new signing MUST be startable from it.
    return frappe.db.get_value("EC Digital Signature Package",
                               {"approval_request": approval_request,
                                "status": ["in", ("Locked", "Active", "Provider Create Failed")]},
                               "name")


def draft_package_for_business(business_doctype, business_name):
    return frappe.db.get_value("EC Digital Signature Package",
                               {"business_doctype": business_doctype,
                                "business_name": business_name, "status": "Draft"}, "name")


def package_files(pkg_name):
    return frappe.get_all("EC Digital Signature File", filters={"package": pkg_name},
                          fields=["name", "file", "file_name", "idx_order", "file_kind",
                                  "requires_signature", "is_supporting_document",
                                  "share_with_partner", "sha256", "size_bytes", "mime_type",
                                  "is_pdf", "scts_document_file_id"],
                          order_by="idx_order asc, creation asc")


def package_placements(pkg_name):
    return frappe.get_all("EC Digital Signature Placement", filters={"package": pkg_name},
                          fields=["name", "signature_file", "page_index", "x", "y", "llx", "lly",
                                  "width", "height", "level_no", "signature_type", "status"],
                          order_by="creation asc")


def requester_placements_complete(pkg_name):
    """Requester completeness: at least one signable file carries at least one non-Invalid
    placement. The requester is a SINGLE signer, so approver-level preflight (per profile level)
    does NOT apply - a package with zero requester placements is never complete and must never
    be lockable."""
    signable = {f.name for f in package_files(pkg_name) if f.requires_signature}
    if not signable:
        return False
    for pl in package_placements(pkg_name):
        if pl.signature_file in signable and (pl.status or "") != "Invalid":
            return True
    return False


# --------------------------------------------------------------------------- #
# create / upload
# --------------------------------------------------------------------------- #
def get_or_create_draft(business_doctype, business_name, profile_name, allow_submitted=False):
    """One Draft package per business doc. Requires the business draft to EXIST and be owned
    by the caller (orphan prevention). Normally the doc must not be submitted yet; the
    REQUESTER pre-approval prep path passes allow_submitted=True to prepare the package during
    the governed Pending Requester Signature stage (the caller is still authorized upstream)."""
    if not frappe.db.exists(business_doctype, business_name):
        frappe.throw(_("Vui lòng lưu nháp yêu cầu trước khi tải tệp."))
    existing = draft_package_for_business(business_doctype, business_name)
    if existing:
        return get_package(existing)
    if not allow_submitted and perms.business_approval_request(business_doctype, business_name):
        frappe.throw(_("Yêu cầu đã gửi duyệt - gói tài liệu không thể tạo mới ở trạng thái này."))
    prof = frappe.db.get_value("EC Digital Signature Profile", profile_name,
                               ["provider", "environment"], as_dict=True)
    pkg = frappe.get_doc({
        "doctype": "EC Digital Signature Package",
        "business_doctype": business_doctype, "business_name": business_name,
        "profile": profile_name, "provider": prof.provider, "environment": prof.environment,
        "package_version": 1, "status": "Draft",
    }).insert(ignore_permissions=True)  # post-authorization; SM-only DocPerm by design
    events.emit("Created", package=pkg.name)
    return pkg


def _validate_content(pkg, profile, file_name, content, requires_signature):
    ext = os.path.splitext(file_name or "")[1].lower()
    if ext in EXT_DENYLIST:
        frappe.throw(_("Loại tệp không được phép: {0}").format(ext))
    if not content or len(content) == 0:
        frappe.throw(_("Tệp rỗng - vui lòng kiểm tra lại."))
    max_mb = int(profile.get("max_file_mb") or 25)
    if len(content) > max_mb * 1024 * 1024:
        frappe.throw(_("Tệp vượt quá dung lượng cho phép ({0} MB).").format(max_mb))
    count = frappe.db.count("EC Digital Signature File", {"package": pkg.name})
    if count >= int(profile.get("max_files") or 20):
        frappe.throw(_("Gói tài liệu đã đạt số tệp tối đa ({0}).").format(profile.get("max_files")))
    is_pdf = content[:5] == PDF_MAGIC
    if is_pdf and b"%%EOF" not in content[-2048:]:
        frappe.throw(_("Tệp PDF không hợp lệ (thiếu EOF) - có thể tải lên chưa hoàn tất."))
    if requires_signature and int(profile.get("require_signable_pdf") or 0) and not is_pdf:
        frappe.throw(_("Tệp cần ký phải là PDF hợp lệ."))
    return is_pdf


def _guess_mime(file_name, is_pdf):
    if is_pdf:
        return "application/pdf"
    return mimetypes.guess_type(file_name or "")[0] or "application/octet-stream"


def add_file(pkg_name, file_name, content, requires_signature=0, is_supporting_document=0,
             share_with_partner=0, file_kind="Other"):
    """Validated upload. File doc + DSF row in ONE transaction (rollback together)."""
    pkg = get_package(pkg_name)
    perms.assert_requester_draft_package(pkg)
    profile = frappe.db.get_value("EC Digital Signature Profile", pkg.profile,
                                  ["max_files", "max_file_mb", "require_signable_pdf"],
                                  as_dict=True)
    is_pdf = _validate_content(pkg, profile, file_name, content, requires_signature)
    fdoc = frappe.get_doc({
        "doctype": "File", "file_name": file_name, "is_private": 1,
        "attached_to_doctype": pkg.business_doctype, "attached_to_name": pkg.business_name,
        "content": content,
    }).insert(ignore_permissions=True)  # attach to the caller-owned business draft only
    nxt = frappe.db.count("EC Digital Signature File", {"package": pkg.name})
    row = frappe.get_doc({
        "doctype": "EC Digital Signature File", "package": pkg.name, "file": fdoc.name,
        "file_name": file_name, "idx_order": nxt, "file_kind": file_kind or "Other",
        "requires_signature": 1 if requires_signature else 0,
        "is_supporting_document": 1 if is_supporting_document else 0,
        "share_with_partner": 1 if share_with_partner else 0,
        "sha256": hashing.sha256_bytes(content), "size_bytes": len(content),
        "mime_type": _guess_mime(file_name, is_pdf), "is_pdf": 1 if is_pdf else 0,
    }).insert(ignore_permissions=True)
    events.emit("Created", package=pkg.name,
                request_meta={"file": file_name, "size": len(content),
                              "flags": [requires_signature, is_supporting_document,
                                        share_with_partner]})
    return row


def set_file_flags(dsf_name, requires_signature=None, is_supporting_document=None,
                   share_with_partner=None, file_kind=None):
    row = frappe.get_doc("EC Digital Signature File", dsf_name)
    pkg = get_package(row.package)
    perms.assert_requester_draft_package(pkg)
    vals = {}
    if requires_signature is not None:
        if int(requires_signature) and not row.is_pdf and frappe.db.get_value(
                "EC Digital Signature Profile", pkg.profile, "require_signable_pdf"):
            frappe.throw(_("Tệp cần ký phải là PDF hợp lệ."))
        vals["requires_signature"] = 1 if int(requires_signature) else 0
    if is_supporting_document is not None:
        vals["is_supporting_document"] = 1 if int(is_supporting_document) else 0
    if share_with_partner is not None:
        vals["share_with_partner"] = 1 if int(share_with_partner) else 0
    if file_kind:
        vals["file_kind"] = file_kind
    if vals:
        frappe.db.set_value("EC Digital Signature File", dsf_name, vals)
    return vals


def reorder_files(pkg_name, ordered_dsf_names):
    pkg = get_package(pkg_name)
    perms.assert_requester_draft_package(pkg)
    rows = {r.name for r in package_files(pkg_name)}
    if set(ordered_dsf_names) != rows:
        frappe.throw(_("Danh sách sắp xếp không khớp với gói tài liệu."))
    for i, n in enumerate(ordered_dsf_names):
        frappe.db.set_value("EC Digital Signature File", n, "idx_order", i)


def remove_file(dsf_name):
    row = frappe.get_doc("EC Digital Signature File", dsf_name)
    pkg = get_package(row.package)
    perms.assert_requester_draft_package(pkg)
    for pl in frappe.get_all("EC Digital Signature Placement",
                             filters={"signature_file": dsf_name}, pluck="name"):
        frappe.delete_doc("EC Digital Signature Placement", pl, ignore_permissions=True)
    fdoc = row.file
    frappe.delete_doc("EC Digital Signature File", dsf_name, ignore_permissions=True)
    if fdoc and frappe.db.exists("File", fdoc):
        frappe.delete_doc("File", fdoc, ignore_permissions=True)


def upsert_placement(pkg_name, dsf_name, box):
    """Phase C: create OR update ONE placement box for a single signable file on an editable
    Draft package. Document-scoped (only this signature_file); never replace-all; sibling files
    untouched; stable row identity preserved on update. Governed (requester/Draft). Geometry is
    re-validated authoritatively. `box`: {name?, page_index, x, y, width, height,
    signer_slot_key, signer_slot_version, signature_type?}."""
    pkg = get_package(pkg_name)
    perms.assert_requester_draft_package(pkg)
    if frappe.db.get_value("EC Digital Signature File", dsf_name, "package") != pkg.name:
        frappe.throw(_("Tệp không thuộc gói này."))
    validate_placement_geometry(pkg_name, [dict(box, signature_file=dsf_name)])
    vals = {"page_index": int(box.get("page_index") or 1),
            "x": float(box.get("x") or 0), "y": float(box.get("y") or 0),
            "width": float(box.get("width") or 0), "height": float(box.get("height") or 0),
            "level_no": int(box.get("level_no") or 0),   # legacy runtime compat (from frozen plan slot)
            "signer_slot_key": box.get("signer_slot_key"),
            "signer_slot_version": int(box.get("signer_slot_version") or 0) or None,
            "signature_type": box.get("signature_type") or "mock"}
    name = box.get("name")
    if name:
        if not frappe.db.exists("EC Digital Signature Placement", name):
            # UPDATE for a row that no longer exists (deleted while the request was in flight).
            # NEVER silently resurrect it as a new row - signal the caller instead.
            return None
        row = frappe.get_doc("EC Digital Signature Placement", name)
        if row.package != pkg.name or row.signature_file != dsf_name:
            frappe.throw(_("Vị trí ký không thuộc tài liệu này."))
        row.update(vals); row.save(ignore_permissions=True)     # save() -> Version audit
        return row.name
    doc = frappe.get_doc(dict({"doctype": "EC Digital Signature Placement", "package": pkg.name,
                               "signature_file": dsf_name, "status": "Draft",
                               "placed_by": frappe.session.user, "placed_at": now_datetime()}, **vals)
                         ).insert(ignore_permissions=True)
    return doc.name


def delete_placement_row(placement_name):
    """Phase C: delete ONE placement box (governed; editable Draft only; document-scoped -
    sibling placements untouched). Archived to Deleted Document (audit preserved). Idempotent."""
    if not frappe.db.exists("EC Digital Signature Placement", placement_name):
        return 0
    row = frappe.db.get_value("EC Digital Signature Placement", placement_name,
                              ["package", "signature_file"], as_dict=True)
    perms.assert_requester_draft_package(get_package(row.package))
    frappe.delete_doc("EC Digital Signature Placement", placement_name, ignore_permissions=True)
    return 1


def clear_file_placements(dsf_name):
    """Document-SCOPED placement reset: remove placements for ONE EC Digital Signature File on
    an editable Draft package, with NO effect on sibling files (no replace-all, no sibling row
    churn / timestamp / audit noise). Governed ORM delete only (archived to Deleted Document;
    Placement track_changes preserved); idempotent (returns count removed). Requester/Draft
    authorization is enforced here (assert_requester_draft_package) and again at the public
    write boundary."""
    row = frappe.get_doc("EC Digital Signature File", dsf_name)
    pkg = get_package(row.package)
    perms.assert_requester_draft_package(pkg)
    if row.package != pkg.name:
        frappe.throw(_("Tệp không thuộc gói này."))
    n = 0
    for pl in frappe.get_all("EC Digital Signature Placement",
                             filters={"signature_file": dsf_name}, pluck="name"):
        frappe.delete_doc("EC Digital Signature Placement", pl, ignore_permissions=True)
        n += 1
    return n


def save_placements(pkg_name, placements):
    """Replace-all placement save for a Draft package (editor batch save). Each row:
    {signature_file, page_index, x, y, llx, lly, width, height, level_no,
     signature_type, scts_role_title, keyword}."""
    pkg = get_package(pkg_name)
    perms.assert_requester_draft_package(pkg)
    valid_files = {r.name: r for r in package_files(pkg_name)}
    for p in placements:
        sf = p.get("signature_file")
        if sf not in valid_files:
            frappe.throw(_("Vị trí ký tham chiếu tệp không thuộc gói."))
        if not valid_files[sf].requires_signature:
            frappe.throw(_("Chỉ đặt vị trí ký trên tệp được đánh dấu 'Cần ký'."))
    validate_placement_geometry(pkg_name, placements, valid_files)
    for old in frappe.get_all("EC Digital Signature Placement",
                              filters={"package": pkg_name}, pluck="name"):
        frappe.delete_doc("EC Digital Signature Placement", old, ignore_permissions=True)
    for p in placements:
        frappe.get_doc({
            "doctype": "EC Digital Signature Placement", "package": pkg_name,
            "signature_file": p.get("signature_file"), "page_index": p.get("page_index"),
            "x": p.get("x"), "y": p.get("y"), "llx": p.get("llx"), "lly": p.get("lly"),
            "width": p.get("width"), "height": p.get("height"),
            "level_no": p.get("level_no"), "signature_type": p.get("signature_type"),
            "scts_role_title": p.get("scts_role_title"), "keyword": p.get("keyword"),
            "status": "Draft", "placed_by": frappe.session.user, "placed_at": now_datetime(),
        }).insert(ignore_permissions=True)
    return len(placements)


# --------------------------------------------------------------------------- #
# hash / preflight / lock / revision
# --------------------------------------------------------------------------- #
def compute_hash(pkg_name):
    pkg = frappe.db.get_value("EC Digital Signature Package", pkg_name,
                              ["package_version", "profile"], as_dict=True)
    prof_mod = frappe.db.get_value("EC Digital Signature Profile", pkg.profile, "modified")
    files = package_files(pkg_name)
    order_of = {f.name: i for i, f in enumerate(files)}
    return hashing.package_hash(
        pkg.package_version, "%s@%s" % (pkg.profile, prof_mod),
        [{"order": i, "sha256": f.sha256, "requires_signature": f.requires_signature,
          "is_supporting_document": f.is_supporting_document,
          "share_with_partner": f.share_with_partner} for i, f in enumerate(files)],
        [{"file_order": order_of.get(p.signature_file, -1), "page_index": p.page_index,
          "x": p.x, "y": p.y, "width": p.width, "height": p.height,
          "level_no": p.level_no, "signature_type": p.signature_type}
         for p in package_placements(pkg_name) if p.status != "Invalid"])


def preflight_for_lock(pkg_name):
    """Blocking checks before lock/provider creation (§18 preflight, S2A backend part).
    Returns list of error strings (empty = OK)."""
    errs = []
    pkg = frappe.db.get_value("EC Digital Signature Package", pkg_name,
                              ["profile", "status"], as_dict=True)
    files = package_files(pkg_name)
    signable = [f for f in files if f.requires_signature]
    if not signable:
        errs.append("no_signable_file")
    for f in signable:
        if not f.is_pdf:
            errs.append("signable_not_pdf:%s" % f.file_name)
        if not f.sha256:
            errs.append("missing_hash:%s" % f.file_name)
    if any(not f.sha256 or not (f.size_bytes or 0) for f in files):
        errs.append("incomplete_upload")
    levels = frappe.get_all("EC Digital Signature Profile Level",
                            filters={"parent": pkg.profile, "requires_signature": 1},
                            fields=["level_no", "mandatory_placements_per_file"])
    pls = package_placements(pkg_name)
    for lvl in levels:
        for f in signable:
            n = len([p for p in pls if p.signature_file == f.name
                     and p.level_no == lvl.level_no and p.status != "Invalid"])
            if n < int(lvl.mandatory_placements_per_file or 1):
                errs.append("missing_placement:L%s:%s" % (lvl.level_no, f.file_name))
    return errs


def lock_package(pkg_name, approval_request):
    """Called by the business submit hook AFTER engine.submit succeeded, same transaction.
    Freezes the hash; from here the package is immutable (new version only)."""
    pkg = get_package(pkg_name)
    errs = preflight_for_lock(pkg_name)
    if errs:
        frappe.throw(_("Gói tài liệu chưa sẵn sàng: {0}").format(", ".join(errs[:6])))
    h = compute_hash(pkg_name)
    frappe.db.get_value("EC Digital Signature Package", pkg_name, "name", for_update=True)
    from ecentric_workspace.platform.esign import state as sm
    sm.assert_transition(sm.PACKAGE, pkg.status, "Locked")
    frappe.db.set_value("EC Digital Signature Package", pkg_name,
                        {"status": "Locked", "approval_request": approval_request,
                         "package_hash": h, "locked_at": now_datetime()})
    events.emit("Locked", package=pkg_name, request_meta={"hash": h,
                                                          "approval_request": approval_request})
    return h


def create_revision(old_pkg_name):
    """New Draft v(N+1): copies file rows (same underlying Files) + placements; old
    package Superseded; live DSRs Superseded (audited). Used by resubmit cycles."""
    old = get_package(old_pkg_name)
    if old.status not in ("Locked", "Active", "Provider Create Failed", "Provider Created"):
        frappe.throw(_("Chỉ tạo phiên bản mới từ gói đã khóa."))
    new = frappe.get_doc({
        "doctype": "EC Digital Signature Package",
        "business_doctype": old.business_doctype, "business_name": old.business_name,
        "approval_request": old.approval_request, "profile": old.profile,
        "provider": old.provider, "environment": old.environment,
        "package_version": int(old.package_version) + 1, "status": "Draft",
    }).insert(ignore_permissions=True)
    for f in package_files(old_pkg_name):
        frappe.get_doc({
            "doctype": "EC Digital Signature File", "package": new.name, "file": f.file,
            "file_name": f.file_name, "idx_order": f.idx_order, "file_kind": f.file_kind,
            "requires_signature": f.requires_signature,
            "is_supporting_document": f.is_supporting_document,
            "share_with_partner": f.share_with_partner, "sha256": f.sha256,
            "size_bytes": f.size_bytes, "mime_type": f.mime_type, "is_pdf": f.is_pdf,
        }).insert(ignore_permissions=True)
    old_files = {f.name: f for f in package_files(old_pkg_name)}
    new_by_file = {f.file: f.name for f in package_files(new.name)}
    for p in package_placements(old_pkg_name):
        src = old_files.get(p.signature_file)
        tgt = src and new_by_file.get(src.file)
        if not tgt:
            continue
        frappe.get_doc({
            "doctype": "EC Digital Signature Placement", "package": new.name,
            "signature_file": tgt, "page_index": p.page_index, "x": p.x, "y": p.y,
            "llx": p.llx, "lly": p.lly, "width": p.width, "height": p.height,
            "level_no": p.level_no, "signature_type": p.signature_type, "status": "Draft",
            "placed_by": frappe.session.user, "placed_at": now_datetime(),
        }).insert(ignore_permissions=True)
    for dsr in frappe.get_all("EC Digital Signature Request",
                              filters={"package": old_pkg_name,
                                       "status": ["in", ["Prepared", "Queued", "Provider Accepted",
                                                         "Verifying", "Retryable Failure",
                                                         "Mapping Required", "Placement Required",
                                                         "Manual Review"]]},
                              pluck="name"):
        events.set_dsr_status(dsr, "Superseded", event_type="Superseded",
                              request_meta={"superseded_by_package": new.name})
    events.set_package_status(old_pkg_name, "Superseded", event_type="Superseded",
                              request_meta={"new_package": new.name})
    frappe.db.set_value("EC Digital Signature Package", old_pkg_name, "superseded_by", new.name)
    return new


# --------------------------------------------------------------------------- #
# private bytes + placement geometry (S2B-B)
# --------------------------------------------------------------------------- #
def file_bytes(dsf_name):
    """Server-side read of a package file's PRIVATE bytes (post-authorization system
    read). Callers are already permission-gated (requester/SM for draft mutations, the
    governed worker for provider assembly). Bytes are never logged."""
    file_id = frappe.db.get_value("EC Digital Signature File", dsf_name, "file")
    if not file_id:
        frappe.throw(_("Không tìm thấy tệp đính kèm."))
    return raw_file_bytes(file_id)


def raw_file_bytes(file_id):
    """Bytes of a `File` record - ALWAYS bytes, whatever Frappe hands back.

    `File.get_content()` does NOT reliably return bytes. It reads the file in binary and
    then tries `.decode()`, returning a `str` whenever the bytes happen to be valid UTF-8:

        with open(file_path, mode="rb") as f:
            self._content = f.read()
            try:
                self._content = self._content.decode()   # <- plain text wins here
            except UnicodeDecodeError:
                pass                                     # <- .png/.jpg/most PDFs stay bytes

    Most real PDFs carry compressed streams, so they fail to decode and arrive as bytes -
    which is why every caller could pass the result straight into `sha256_bytes` and nothing
    broke for months. But an attachment that IS decodable - a plain-ASCII PDF, a .txt or .csv
    receipt, an .svg - comes back as `str`, `sha256_bytes` raises TypeError, and the person
    placing signature boxes gets "Không thể lưu vị trí chữ ký — thử lại" with no way forward.
    Found 02/09 by uploading a minimal ASCII PDF while running the E2E by hand.

    Re-encoding is exact, not a guess: Frappe decoded these very bytes with strict UTF-8, so
    `.encode("utf-8")` returns the identical bytes and the sha256 still describes the file on
    disk. Anything else that is not bytes is a real fault and must not be hashed silently.
    """
    content = frappe.get_doc("File", file_id).get_content()
    if isinstance(content, str):
        return content.encode("utf-8")
    if isinstance(content, (bytes, bytearray)):
        return bytes(content)
    frappe.throw(_("Không đọc được nội dung tệp đính kèm."))


def _page_sizes(content):
    """[(width_pt, height_pt), ...] per page via pypdf (bundled with frappe). Returns
    None if the bytes are not a parseable PDF."""
    try:
        from pypdf import PdfReader
    except Exception:
        from PyPDF2 import PdfReader  # older bench fallback
    try:
        reader = PdfReader(io.BytesIO(content))
        sizes = []
        for pg in reader.pages:
            # CROPBOX, khong phai mediabox: trinh xem (va khung dat vi tri ky cua minh) ve
            # theo cropbox. Khi hai cai lech nhau - rat thuong gap voi PDF xuat tu Word hay
            # tu may scan - thi toa do minh gui di lech dung bang phan chenh do, va chu ky
            # in ra khong nam trong o. Cropbox vang mat thi pypdf tra ve chinh mediabox.
            box = getattr(pg, "cropbox", None) or pg.mediabox
            w, h = float(box.width), float(box.height)
            # Trang XOAY 90/270 thi chieu rong va chieu cao doi cho nhau khi hien thi.
            # Bo qua chi tiet nay la lech han mot canh giay.
            try:
                rot = int(pg.get("/Rotate", 0) or 0) % 360
            except Exception:
                rot = 0
            if rot in (90, 270):
                w, h = h, w
            sizes.append((w, h))
        return sizes
    except Exception:
        return None


def pdf_page_geometry(dsf_name):
    """Page count + per-page point dimensions for a signable file (drives governed
    placement entry in the UI). Permission is enforced by the API wrapper."""
    row = frappe.db.get_value("EC Digital Signature File", dsf_name,
                              ["is_pdf", "requires_signature"], as_dict=True)
    if not row or not row.is_pdf:
        frappe.throw(_("Chỉ tệp PDF mới có thông tin trang để đặt vị trí ký."))
    sizes = _page_sizes(file_bytes(dsf_name)) or []
    return {"page_count": len(sizes),
            "pages": [{"page": i + 1, "width": w, "height": h}
                      for i, (w, h) in enumerate(sizes)]}


def validate_placement_geometry(pkg_name, placements, valid_files=None, tol=1.0):
    """Governed geometry validation for placements (fail-closed). Raises on the first
    violation. Rules: page_index integer > 0 and <= page count; width/height > 0; the
    box (top-left origin, points) stays inside the page media box. Coordinates are
    validated against the CURRENT package version's file bytes."""
    if valid_files is None:
        valid_files = {r.name: r for r in package_files(pkg_name)}
    size_cache = {}
    for p in placements:
        sf = p.get("signature_file")
        if sf not in valid_files:
            frappe.throw(_("Vị trí ký tham chiếu tệp không thuộc gói."))
        try:
            page = int(p.get("page_index"))
        except (TypeError, ValueError):
            frappe.throw(_("Số trang không hợp lệ."))
        if page < 1:
            frappe.throw(_("Số trang phải lớn hơn 0."))
        try:
            x = float(p.get("x") or 0); y = float(p.get("y") or 0)
            w = float(p.get("width") or 0); h = float(p.get("height") or 0)
        except (TypeError, ValueError):
            frappe.throw(_("Toạ độ vị trí ký không hợp lệ."))
        if w <= 0 or h <= 0:
            frappe.throw(_("Kích thước vị trí ký phải dương."))
        if x < 0 or y < 0:
            frappe.throw(_("Toạ độ vị trí ký không được âm."))
        if sf not in size_cache:
            size_cache[sf] = _page_sizes(file_bytes(sf))
        sizes = size_cache[sf]
        if sizes is None:
            frappe.throw(_("Không đọc được kích thước trang PDF để kiểm tra vị trí ký."))
        if page > len(sizes):
            frappe.throw(_("Trang {0} vượt quá số trang của tệp.").format(page))
        pw, ph = sizes[page - 1]
        if x + w > pw + tol or y + h > ph + tol:
            frappe.throw(_("Vị trí ký nằm ngoài khổ trang PDF."))
    return True


def workflow_instance_id(pkg, fallback_to_document=True):
    """Ma WORKFLOW INSTANCE cua goi - KHAC ma DOCUMENT, va day la cho da lam hong viec ky.

    `GET /api/Workflow/{instanceId}` va `POST /api/Workflow/transition` deu nhan INSTANCE id.
    Toan he dang truyen `scts_document_id` vao do. Do bang tay 02/09 tren tai lieu
    f3a2c0f7-...: goi bang document id tra 404 voi CA BA nguoi - ke ca nguoi da ky that tren
    chinh tai lieu do - nen day khong phai chuyen quyen, ma la sai ma.

    Hau qua day chuyen: `discover_transition` khong bao gio chay duoc -> khong biet
    transitionId dung cua canh hien tai -> gui id cau hinh cu -> SCTS tra 400 "Duong chuyen
    khong hop le" -> roi ve pool -> pool tra 2xx kem ma giao dich roi khong co gi xay ra.

    Tra `None` khi khong co va `fallback_to_document=False`: nguoi goi phai tu quyet dinh co
    dam gui bang document id nua khong, thay vi bi lang le tra ve dung cai gia tri sai cu.
    """
    if isinstance(pkg, str):
        pkg = frappe.db.get_value("EC Digital Signature Package", pkg,
                                  ["scts_workflow_instance_id", "scts_document_id"],
                                  as_dict=True) or {}
    get = pkg.get if hasattr(pkg, "get") else (lambda k: getattr(pkg, k, None))
    iid = (get("scts_workflow_instance_id") or "").strip() if get("scts_workflow_instance_id") else None
    if iid:
        return iid
    return (get("scts_document_id") or None) if fallback_to_document else None
