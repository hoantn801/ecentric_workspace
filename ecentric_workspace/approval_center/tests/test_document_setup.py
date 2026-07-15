# Copyright (c) 2026, eCentric and contributors
"""Phase A1 - Document Setup read model + classification persistence.

READ creates nothing; classification WRITE lazily materializes exactly one local Draft package
+ one DSF per physical document (idempotent), writes requires_signature canonically and mirrors
is_supporting_document server-side, is requester-scoped and package-Draft-only, and produces no
provider/DSR/SCTS/Approval Request/ToDo side effects.

Runs on the bench:
  bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_document_setup
"""
import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.approval_center.api import payment_request as papi
from ecentric_workspace.approval_center.esign import document_setup as ds
from ecentric_workspace.approval_center.esign import package as pkgsvc
from ecentric_workspace.approval_center.tests import esign_fixtures as fx

BD, AT = "EC Payment Request", "PAYMENT_REQUEST"
PROFILE = "ZZESN_PAYR"
PKG, DSF = "EC Digital Signature Package", "EC Digital Signature File"

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64          # non-PDF bytes


def _profile(requester=1):
    fx.ensure_process(); fx.ensure_settings(allowed_users=None); fx.ensure_profile()
    frappe.db.set_value("EC Digital Signature Profile", PROFILE,
                        {"approver_signature_policy": "All Approval Levels",
                         "requester_signature_required": requester})


def _pending(tag):
    _profile()
    h = fx.full_stack(fx.PFX + tag + "@example.com", fx.PFX + tag + "m@example.com")
    biz = fx.draft_payment_request(h["requester"])
    frappe.set_user(h["requester"]); papi.submit_request(biz); frappe.set_user("Administrator")
    return h["requester"], biz


def _attach(biz, user, name="doc.pdf", content=None, content_hash=None):
    frappe.set_user(user)
    doc = frappe.get_doc({"doctype": "File", "file_name": name, "is_private": 1,
                          "attached_to_doctype": BD, "attached_to_name": biz,
                          "content": content if content is not None else fx.PDF}
                         ).insert(ignore_permissions=True)
    if content_hash is not None:
        frappe.db.set_value("File", doc.name, "content_hash", content_hash)
    frappe.set_user("Administrator")
    return doc.name


def _state(user, biz):
    frappe.set_user(user)
    try:
        return ds.get_document_setup_state(BD, biz)
    finally:
        frappe.set_user("Administrator")


def _write(user, biz, ref, req_sig, confirm=0):
    frappe.set_user(user)
    try:
        return ds.set_document_requires_signature(BD, biz, ref, req_sig, confirm=confirm)
    finally:
        frappe.set_user("Administrator")


class TestDocumentSetupRead(FrappeTestCase):
    def tearDown(self):
        frappe.set_user("Administrator")

    def test_one_file_one_document(self):
        req, biz = _pending("d1"); _attach(biz, req, "a.pdf", fx.PDF, "H1")
        st = _state(req, biz)
        self.assertEqual(st["summary"]["documents"], 1)

    def test_duplicate_content_hash_one_document(self):
        req, biz = _pending("d2")
        _attach(biz, req, "a.pdf", fx.PDF, "HDUP"); _attach(biz, req, "a (1).pdf", fx.PDF, "HDUP")
        st = _state(req, biz)
        self.assertEqual(st["summary"]["documents"], 1)
        self.assertEqual(st["documents"][0]["duplicate_count"], 2)

    def test_fallback_dedupe_by_file_url(self):
        req, biz = _pending("d3")
        a = _attach(biz, req, "n.pdf", fx.PDF, None)
        url = frappe.db.get_value("File", a, "file_url")
        b = _attach(biz, req, "n.pdf", fx.PDF, None)
        frappe.db.set_value("File", b, "file_url", url)          # same url, no content_hash
        frappe.db.set_value("File", a, "content_hash", None)
        frappe.db.set_value("File", b, "content_hash", None)
        st = _state(req, biz)
        self.assertEqual(st["summary"]["documents"], 1)

    def test_same_name_different_content_separate(self):
        req, biz = _pending("d4")
        _attach(biz, req, "a.pdf", fx.PDF, "HX"); _attach(biz, req, "a.pdf", PNG, "HY")
        st = _state(req, biz)
        self.assertEqual(st["summary"]["documents"], 2)

    def test_no_dsf_default_classification(self):
        req, biz = _pending("d5"); _attach(biz, req, "a.pdf", fx.PDF, "H5")
        d = _state(req, biz)["documents"][0]
        self.assertTrue(d["requires_signature"])
        self.assertEqual(d["classification_source"], "default")
        self.assertIsNone(d["signature_file"])
        self.assertEqual(d["setup_state"], "not_configured")

    def test_existing_dsf_canonical_classification(self):
        req, biz = _pending("d6"); ref = _attach(biz, req, "a.pdf", fx.PDF, "H6")
        _write(req, biz, ref, False)                            # -> supporting
        d = next(x for x in _state(req, biz)["documents"] if x["document_ref"] == ref)
        self.assertFalse(d["requires_signature"])
        self.assertEqual(d["classification_source"], "digital_signature_file")
        self.assertEqual(d["setup_state"], "supporting_document")

    def test_required_count_from_signer_plan(self):
        req, biz = _pending("d8"); _attach(biz, req, "a.pdf", fx.PDF, "H8")
        st = _state(req, biz)
        self.assertEqual(st["signer_plan"]["summary"]["required_slots"],
                         st["documents"][0]["required_signer_slots"])

    def test_missing_mapping_does_not_fail(self):
        req, biz = _pending("d9"); _attach(biz, req, "a.pdf", fx.PDF, "H9")
        frappe.db.delete("EC SCTS User Mapping", {"frappe_user": req})
        st = _state(req, biz)
        self.assertIn("documents", st)                         # still resolves

    def test_legacy_placements_not_fake_progress(self):
        req, biz = _pending("d10"); ref = _attach(biz, req, "a.pdf", fx.PDF, "H10")
        _write(req, biz, ref, True)                            # materialize DSF (signable)
        draft = pkgsvc.draft_package_for_business(BD, biz)
        dsf = frappe.get_all(DSF, filters={"package": draft, "requires_signature": 1}, pluck="name")[0]
        pkgsvc.save_placements(draft, [{"signature_file": dsf, "page_index": 1, "x": 10, "y": 10,
                                        "width": 50, "height": 20, "level_no": 1,
                                        "signature_type": "mock"}])
        d = next(x for x in _state(req, biz)["documents"] if x["signature_file"] == dsf)
        self.assertEqual(d["setup_state"], "legacy_unmapped")
        self.assertEqual(d["legacy_placement_count"], 1)

    def test_unsupported_signable_format_state(self):
        req, biz = _pending("d11"); _attach(biz, req, "pic.png", PNG, "H11")
        d = _state(req, biz)["documents"][0]
        self.assertTrue(d["requires_signature"])               # default signable
        self.assertFalse(d["direct_signing_supported"])
        self.assertEqual(d["setup_state"], "unsupported")

    def test_read_creates_zero_records(self):
        req, biz = _pending("d12"); _attach(biz, req, "a.pdf", fx.PDF, "H12")
        counts = {dt: frappe.db.count(dt) for dt in
                  (PKG, DSF, "EC Digital Signature Placement", "EC Digital Signature Request",
                   "ToDo")}
        _state(req, biz); _state(req, biz)
        for dt, before in counts.items():
            self.assertEqual(frappe.db.count(dt), before, "read mutated %s" % dt)


class TestDocumentSetupWrite(FrappeTestCase):
    def tearDown(self):
        frappe.set_user("Administrator")

    def test_first_write_creates_one_draft_and_one_dsf(self):
        req, biz = _pending("w13"); ref = _attach(biz, req, "a.pdf", fx.PDF, "HW13")
        self.assertFalse(pkgsvc.draft_package_for_business(BD, biz))
        _write(req, biz, ref, False)
        self.assertTrue(pkgsvc.draft_package_for_business(BD, biz))
        draft = pkgsvc.draft_package_for_business(BD, biz)
        self.assertEqual(frappe.db.count(DSF, {"package": draft}), 1)

    def test_duplicate_files_resolve_to_one_dsf(self):
        req, biz = _pending("w15")
        r1 = _attach(biz, req, "a.pdf", fx.PDF, "HW15"); _attach(biz, req, "a (1).pdf", fx.PDF, "HW15")
        _write(req, biz, r1, False); _write(req, biz, r1, False)
        draft = pkgsvc.draft_package_for_business(BD, biz)
        self.assertEqual(frappe.db.count(DSF, {"package": draft}), 1)

    def test_repeated_write_idempotent(self):
        req, biz = _pending("w16"); ref = _attach(biz, req, "a.pdf", fx.PDF, "HW16")
        _write(req, biz, ref, False); _write(req, biz, ref, False)
        draft = pkgsvc.draft_package_for_business(BD, biz)
        self.assertEqual(frappe.db.count(PKG, {"business_doctype": BD, "business_name": biz}), 1)
        self.assertEqual(frappe.db.count(DSF, {"package": draft}), 1)

    def test_canonical_and_mirror_synced(self):
        req, biz = _pending("w17"); ref = _attach(biz, req, "a.pdf", fx.PDF, "HW17")
        _write(req, biz, ref, False)
        draft = pkgsvc.draft_package_for_business(BD, biz)
        row = frappe.db.get_value(DSF, {"package": draft}, ["requires_signature",
                                                            "is_supporting_document"], as_dict=True)
        self.assertEqual((row.requires_signature, row.is_supporting_document), (0, 1))
        _write(req, biz, ref, True)
        row = frappe.db.get_value(DSF, {"package": draft}, ["requires_signature",
                                                            "is_supporting_document"], as_dict=True)
        self.assertEqual((row.requires_signature, row.is_supporting_document), (1, 0))

    def test_locked_package_denied(self):
        req, biz = _pending("w18"); ref = _attach(biz, req, "a.pdf", fx.PDF, "HW18")
        _write(req, biz, ref, True)
        draft = pkgsvc.draft_package_for_business(BD, biz)
        dsf = frappe.get_all(DSF, filters={"package": draft, "requires_signature": 1}, pluck="name")[0]
        frappe.set_user(req)
        pkgsvc.save_placements(draft, [{"signature_file": dsf, "page_index": 1, "x": 10, "y": 10,
                                        "width": 50, "height": 20, "level_no": 1,
                                        "signature_type": "mock"}])
        from ecentric_workspace.approval_center.esign import requester
        requester.requester_lock_signing_package(BD, biz)      # -> Locked
        frappe.set_user("Administrator")
        out = _write(req, biz, ref, False)
        self.assertFalse(out["ok"]); self.assertEqual(out["reason"], "package_locked")

    def test_unauthorized_user_denied(self):
        req, biz = _pending("w19"); ref = _attach(biz, req, "a.pdf", fx.PDF, "HW19")
        stranger = fx.user(fx.PFX + "w19x@example.com")
        frappe.set_user(stranger)
        with self.assertRaises(frappe.PermissionError):
            ds.set_document_requires_signature(BD, biz, ref, False)
        frappe.set_user("Administrator")

    def test_no_admin_or_sm_bypass(self):
        req, biz = _pending("w20"); ref = _attach(biz, req, "a.pdf", fx.PDF, "HW20")
        sm = fx.user(fx.PFX + "w20sm@example.com", roles=("Employee", "System Manager"))
        frappe.set_user(sm)
        with self.assertRaises(frappe.PermissionError):
            ds.set_document_requires_signature(BD, biz, ref, False)
        frappe.set_user("Administrator")                       # Administrator != requester
        with self.assertRaises(frappe.PermissionError):
            ds.set_document_requires_signature(BD, biz, ref, False)

    def test_no_provider_dsr_approval_todo_side_effects(self):
        req, biz = _pending("w21"); ref = _attach(biz, req, "a.pdf", fx.PDF, "HW21")
        before = {dt: frappe.db.count(dt) for dt in
                  ("EC Digital Signature Request", "EC Approval Request")}
        todo_before = frappe.db.count("ToDo")
        _write(req, biz, ref, False)
        self.assertEqual(frappe.db.count("EC Digital Signature Request"),
                         before["EC Digital Signature Request"])
        self.assertEqual(frappe.db.count("EC Approval Request"), before["EC Approval Request"])
        self.assertEqual(frappe.db.count("ToDo"), todo_before)

    def test_existing_placements_require_confirmation(self):
        req, biz = _pending("w22"); ref = _attach(biz, req, "a.pdf", fx.PDF, "HW22")
        _write(req, biz, ref, True)
        draft = pkgsvc.draft_package_for_business(BD, biz)
        dsf = frappe.get_all(DSF, filters={"package": draft, "requires_signature": 1}, pluck="name")[0]
        frappe.set_user(req)
        pkgsvc.save_placements(draft, [{"signature_file": dsf, "page_index": 1, "x": 10, "y": 10,
                                        "width": 50, "height": 20, "level_no": 1,
                                        "signature_type": "mock"}])
        frappe.set_user("Administrator")
        out = _write(req, biz, ref, False)                     # no confirm
        self.assertTrue(out.get("confirmation_required"))
        self.assertEqual(out["reason"], "existing_placements")
        self.assertEqual(_placement_count(dsf), 1)             # unchanged

    def test_confirmed_supporting_conversion_resets_placements(self):
        req, biz = _pending("w23"); ref = _attach(biz, req, "a.pdf", fx.PDF, "HW23")
        _write(req, biz, ref, True)
        draft = pkgsvc.draft_package_for_business(BD, biz)
        dsf = frappe.get_all(DSF, filters={"package": draft, "requires_signature": 1}, pluck="name")[0]
        frappe.set_user(req)
        pkgsvc.save_placements(draft, [{"signature_file": dsf, "page_index": 1, "x": 10, "y": 10,
                                        "width": 50, "height": 20, "level_no": 1,
                                        "signature_type": "mock"}])
        frappe.set_user("Administrator")
        out = _write(req, biz, ref, False, confirm=1)          # confirmed
        self.assertTrue(out["ok"])
        self.assertEqual(_placement_count(dsf), 0)             # governed reset (save_placements)
        row = frappe.db.get_value(DSF, dsf, ["requires_signature", "is_supporting_document"],
                                  as_dict=True)
        self.assertEqual((row.requires_signature, row.is_supporting_document), (0, 1))

    def test_stale_dsf_not_shown_as_current_attachment(self):
        req, biz = _pending("w24"); ref = _attach(biz, req, "a.pdf", fx.PDF, "HW24")
        _write(req, biz, ref, True)                            # DSF for this content
        # remove the native attachment (its content is now stale relative to the DSF)
        frappe.delete_doc("File", ref, ignore_permissions=True, force=True)
        st = _state(req, biz)
        refs = [d["document_ref"] for d in st["documents"]]
        self.assertNotIn(ref, refs)                            # not a current attachment
        self.assertTrue(len(st["stale_signing_files"]) >= 1)   # reported, not deleted

    def test_supporting_non_pdf_document(self):
        req, biz = _pending("w25"); ref = _attach(biz, req, "sheet.xlsx", PNG, "HW25")
        out = _write(req, biz, ref, False)                     # mark supporting
        self.assertTrue(out["ok"])
        draft = pkgsvc.draft_package_for_business(BD, biz)
        row = frappe.db.get_value(DSF, {"package": draft}, ["requires_signature", "is_pdf",
                                                            "is_supporting_document"], as_dict=True)
        self.assertEqual((row.requires_signature, row.is_pdf, row.is_supporting_document), (0, 0, 1))

    def test_unsupported_signable_write_refused(self):
        req, biz = _pending("w25b"); ref = _attach(biz, req, "pic.png", PNG, "HW25b")
        out = _write(req, biz, ref, True)                      # signable non-PDF
        self.assertFalse(out["ok"])
        self.assertEqual(out["reason"], "unsupported_signable_format")


def _placement_count(dsf_name):
    return len([p for p in frappe.get_all("EC Digital Signature Placement",
                                          filters={"signature_file": dsf_name}, fields=["status"])
                if (p.status or "") != "Invalid"])


PDF2 = fx.PDF[:-5] + b"XZ%%EOF"                      # distinct content -> distinct SHA


class TestDocumentSetupCorrections(FrappeTestCase):
    def tearDown(self):
        frappe.set_user("Administrator")

    # ---- 1. implicit default true is a true no-op ----
    def test_set_true_on_no_dsf_is_noop_zero_writes(self):
        req, biz = _pending("c1"); ref = _attach(biz, req, "a.pdf", fx.PDF, "HC1")
        counts = {dt: frappe.db.count(dt) for dt in (PKG, DSF, "EC Digital Signature Event")}
        out = _write(req, biz, ref, True)                       # default already true
        self.assertTrue(out["ok"]); self.assertTrue(out.get("no_op"))
        for dt, before in counts.items():
            self.assertEqual(frappe.db.count(dt), before, "no-op mutated %s" % dt)

    def test_existing_classification_repeat_is_noop(self):
        req, biz = _pending("c2"); ref = _attach(biz, req, "a.pdf", fx.PDF, "HC2")
        _write(req, biz, ref, False)                            # -> supporting (materialize)
        ev0 = frappe.db.count("EC Digital Signature Event",
                              {"event_type": "DocumentClassificationChanged"})
        out = _write(req, biz, ref, False)                      # repeat false -> no-op
        self.assertTrue(out.get("no_op"))
        self.assertEqual(frappe.db.count("EC Digital Signature Event",
                                         {"event_type": "DocumentClassificationChanged"}), ev0)

    # ---- 2. document-scoped placement reset preserves siblings ----
    def test_clear_file_placements_preserves_sibling_ids(self):
        req, biz = _pending("c3"); _attach(biz, req, "seed.pdf", fx.PDF, "HC3")
        frappe.set_user(req)
        draft = pkgsvc.get_or_create_draft(BD, biz, PROFILE, allow_submitted=True).name
        a = pkgsvc.add_file(draft, "A.pdf", fx.PDF, requires_signature=1).name
        b = pkgsvc.add_file(draft, "B.pdf", PDF2, requires_signature=1).name
        pkgsvc.save_placements(draft, [
            {"signature_file": a, "page_index": 1, "x": 10, "y": 10, "width": 50, "height": 20,
             "level_no": 1, "signature_type": "mock"},
            {"signature_file": b, "page_index": 1, "x": 20, "y": 20, "width": 50, "height": 20,
             "level_no": 1, "signature_type": "mock"}])
        b_before = sorted(frappe.get_all("EC Digital Signature Placement",
                                         filters={"signature_file": b}, pluck="name"))
        removed = pkgsvc.clear_file_placements(a)               # document-scoped
        frappe.set_user("Administrator")
        self.assertEqual(removed, 1)
        self.assertEqual(_placement_count(a), 0)               # A cleared
        b_after = sorted(frappe.get_all("EC Digital Signature Placement",
                                        filters={"signature_file": b}, pluck="name"))
        self.assertEqual(b_before, b_after)                    # B row IDs UNCHANGED (no churn)

    def test_clear_file_placements_idempotent(self):
        req, biz = _pending("c3b"); _attach(biz, req, "s.pdf", fx.PDF, "HC3b")
        frappe.set_user(req)
        draft = pkgsvc.get_or_create_draft(BD, biz, PROFILE, allow_submitted=True).name
        a = pkgsvc.add_file(draft, "A.pdf", fx.PDF, requires_signature=1).name
        self.assertEqual(pkgsvc.clear_file_placements(a), 0)   # none -> idempotent no-op
        frappe.set_user("Administrator")

    # ---- 3. classification audit ----
    def test_initial_true_to_false_is_audited(self):
        req, biz = _pending("c4"); ref = _attach(biz, req, "a.pdf", fx.PDF, "HC4")
        _write(req, biz, ref, False)
        draft = pkgsvc.draft_package_for_business(BD, biz)
        evs = frappe.get_all("EC Digital Signature Event",
                             filters={"package": draft, "event_type": "DocumentClassificationChanged"},
                             fields=["name", "request_meta", "erp_actor"])
        self.assertEqual(len(evs), 1)
        meta = frappe.parse_json(evs[0].request_meta)
        self.assertEqual(meta["requires_signature_before"], True)
        self.assertEqual(meta["requires_signature_after"], False)
        self.assertEqual(evs[0].erp_actor, req)

    def test_noop_emits_no_event(self):
        req, biz = _pending("c5"); ref = _attach(biz, req, "a.pdf", fx.PDF, "HC5")
        _write(req, biz, ref, True)                            # no-op (default true)
        self.assertEqual(frappe.db.count("EC Digital Signature Event",
                                         {"event_type": "DocumentClassificationChanged"}), 0)

    def test_subsequent_change_audited(self):
        req, biz = _pending("c6"); ref = _attach(biz, req, "a.pdf", fx.PDF, "HC6")
        _write(req, biz, ref, False)                           # true->false
        _write(req, biz, ref, True)                            # false->true (subsequent)
        draft = pkgsvc.draft_package_for_business(BD, biz)
        evs = frappe.get_all("EC Digital Signature Event",
                             filters={"package": draft, "event_type": "DocumentClassificationChanged"},
                             fields=["request_meta"], order_by="creation asc")
        self.assertEqual(len(evs), 2)
        m2 = frappe.parse_json(evs[1].request_meta)
        self.assertEqual((m2["requires_signature_before"], m2["requires_signature_after"]),
                         (False, True))

    # ---- 4. DSF precedence ----
    def test_cancelled_dsf_not_authoritative(self):
        req, biz = _pending("c7"); ref = _attach(biz, req, "a.pdf", fx.PDF, "HC7")
        _write(req, biz, ref, False)                           # DSF in a Draft package
        draft = pkgsvc.draft_package_for_business(BD, biz)
        frappe.db.set_value(PKG, draft, "status", "Cancelled")  # simulate historical cancelled
        d = next(x for x in _state(req, biz)["documents"] if x["document_ref"] == ref)
        # Cancelled package is NOT authoritative -> falls back to the default (signable)
        self.assertTrue(d["requires_signature"])
        self.assertEqual(d["classification_source"], "default")

    def test_needs_review_on_ambiguous_coexistence(self):
        req, biz = _pending("c8"); ref = _attach(biz, req, "a.pdf", fx.PDF, "HC8")
        _write(req, biz, ref, False)                           # Draft package
        draft = pkgsvc.draft_package_for_business(BD, biz)
        # a second immutable-live package coexisting -> ambiguous
        frappe.get_doc({"doctype": PKG, "business_doctype": BD, "business_name": biz,
                        "profile": PROFILE, "provider": "Mock", "environment": "UAT",
                        "package_version": 2, "status": "Locked", "package_hash": "x"}
                       ).insert(ignore_permissions=True)
        st = _state(req, biz)
        self.assertTrue(st["needs_review"])
        self.assertFalse(st["editable"])
        out = _write(req, biz, ref, True)
        self.assertFalse(out["ok"]); self.assertEqual(out["reason"], "needs_review")
