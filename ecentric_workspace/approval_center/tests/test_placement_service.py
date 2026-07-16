# Copyright (c) 2026, eCentric and contributors
"""Phase C - governed signer-slot placement service (backend test matrix 1-16).
  bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_placement_service
"""
import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.approval_center.api import payment_request as papi
from ecentric_workspace.approval_center.esign import package as pkgsvc
from ecentric_workspace.approval_center.esign import placement_service as ps
from ecentric_workspace.approval_center.esign import signer_plan as sp
from ecentric_workspace.approval_center.esign import document_setup as ds
from ecentric_workspace.approval_center.tests import esign_fixtures as fx

BD = "EC Payment Request"
PL = "EC Digital Signature Placement"
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


def _profile():
    fx.ensure_process(); fx.ensure_settings(allowed_users=None); fx.ensure_profile()
    frappe.db.set_value("EC Digital Signature Profile", "ZZESN_PAYR",
                        {"approver_signature_policy": "All Approval Levels",
                         "requester_signature_required": 1})


def _pending(tag):
    _profile()
    h = fx.full_stack(fx.PFX + tag + "@example.com", fx.PFX + tag + "m@example.com")
    biz = fx.draft_payment_request(h["requester"])
    frappe.set_user(h["requester"]); papi.submit_request(biz); frappe.set_user("Administrator")
    return h["requester"], biz


def _attach(biz, user, name="a.pdf", content=None):
    frappe.set_user(user)
    d = frappe.get_doc({"doctype": "File", "file_name": name, "is_private": 1,
                        "attached_to_doctype": BD, "attached_to_name": biz,
                        "content": content if content is not None else fx.PDF}
                       ).insert(ignore_permissions=True)
    frappe.set_user("Administrator")
    return d.name


def _box(slot, x=50, y=50, name=None):
    b = {"page_index": 1, "x": x, "y": y, "width": 120, "height": 40, "signer_slot_key": slot}
    if name:
        b["name"] = name
    return b


class TestPlacementService(FrappeTestCase):
    def tearDown(self):
        frappe.set_user("Administrator")

    def test_1_requester_saves_valid_slot(self):
        req, biz = _pending("p1"); ref = _attach(biz, req)
        frappe.set_user(req)
        out = ps.save_placement(BD, biz, ref, _box("requester"))
        frappe.set_user("Administrator")
        self.assertTrue(out["ok"])
        self.assertEqual(out["state"]["covered_slot_count"], 1)

    def test_2_invalid_slot_rejected(self):
        req, biz = _pending("p2"); ref = _attach(biz, req)
        frappe.set_user(req)
        out = ps.save_placement(BD, biz, ref, _box("level:BOGUS:any-one"))
        frappe.set_user("Administrator")
        self.assertFalse(out["ok"]); self.assertEqual(out["reason"], "invalid_slot_key")

    def test_3_non_requester_denied(self):
        req, biz = _pending("p3"); ref = _attach(biz, req)
        other = fx.user(fx.PFX + "p3o@example.com")
        frappe.set_user(other)
        with self.assertRaises(frappe.PermissionError):
            ps.save_placement(BD, biz, ref, _box("requester"))
        frappe.set_user("Administrator")

    def test_4_admin_and_sm_not_bypassed(self):
        req, biz = _pending("p4"); ref = _attach(biz, req)
        sm = fx.user(fx.PFX + "p4sm@example.com", roles=("Employee", "System Manager"))
        frappe.set_user(sm)
        with self.assertRaises(frappe.PermissionError):
            ps.save_placement(BD, biz, ref, _box("requester"))
        frappe.set_user("Administrator")
        with self.assertRaises(frappe.PermissionError):
            ps.save_placement(BD, biz, ref, _box("requester"))

    def test_5_frozen_package_denied(self):
        req, biz = _pending("p5"); ref = _attach(biz, req)
        frappe.set_user(req)
        ps.save_placement(BD, biz, ref, _box("requester"))     # materialize + one box
        draft = pkgsvc.draft_package_for_business(BD, biz)
        frappe.set_user("Administrator")
        frappe.db.set_value("EC Digital Signature Package", draft, "status", "Locked")
        frappe.set_user(req)
        with self.assertRaises(frappe.ValidationError):
            ps.save_placement(BD, biz, ref, _box("requester", x=80))
        frappe.set_user("Administrator")

    def test_6_supporting_document_denied(self):
        req, biz = _pending("p6"); ref = _attach(biz, req)
        frappe.set_user(req)
        ds.set_document_requires_signature(BD, biz, ref, False)  # -> supporting DSF
        out = ps.save_placement(BD, biz, ref, _box("requester"))
        frappe.set_user("Administrator")
        self.assertFalse(out["ok"]); self.assertEqual(out["reason"], "supporting_document")

    def test_7_non_pdf_denied(self):
        req, biz = _pending("p7"); ref = _attach(biz, req, "pic.png", PNG)
        frappe.set_user(req)
        out = ps.save_placement(BD, biz, ref, _box("requester"))
        frappe.set_user("Administrator")
        self.assertFalse(out["ok"]); self.assertEqual(out["reason"], "not_pdf")

    def test_8_document_scoped_preserves_sibling(self):
        req, biz = _pending("p8"); a = _attach(biz, req, "A.pdf", fx.PDF)
        b = _attach(biz, req, "B.pdf", fx.PDF[:-5] + b"XZ%%EOF")
        frappe.set_user(req)
        ps.save_placement(BD, biz, b, _box("requester"))
        draft = pkgsvc.draft_package_for_business(BD, biz)
        b_dsf = ds._dsf_by_sha(draft, pkgsvc.hashing.sha256_bytes(fx.PDF[:-5] + b"XZ%%EOF"))["name"]
        b_ids_before = sorted(frappe.get_all(PL, filters={"signature_file": b_dsf}, pluck="name"))
        ps.save_placement(BD, biz, a, _box("requester"))       # mutate File A
        frappe.set_user("Administrator")
        b_ids_after = sorted(frappe.get_all(PL, filters={"signature_file": b_dsf}, pluck="name"))
        self.assertEqual(b_ids_before, b_ids_after)            # File B placements untouched

    def test_9_10_progress_unique_covered_not_row_count(self):
        req, biz = _pending("p9"); ref = _attach(biz, req)
        frappe.set_user(req)
        ps.save_placement(BD, biz, ref, _box("requester", x=40))
        out = ps.save_placement(BD, biz, ref, _box("requester", x=200))  # 2nd box, SAME slot
        frappe.set_user("Administrator")
        self.assertEqual(len(out["state"]["placements"]), 2)   # 2 boxes
        self.assertEqual(out["state"]["covered_slot_count"], 1)  # count the slot ONCE

    def test_11_legacy_unmapped_not_counted(self):
        req, biz = _pending("p11"); ref = _attach(biz, req)
        frappe.set_user(req)
        ps.save_placement(BD, biz, ref, _box("requester"))
        draft = pkgsvc.draft_package_for_business(BD, biz)
        dsf = frappe.get_all("EC Digital Signature File",
                             filters={"package": draft, "requires_signature": 1}, pluck="name")[0]
        # inject a legacy placement with NO signer_slot_key
        frappe.get_doc({"doctype": PL, "package": draft, "signature_file": dsf, "page_index": 1,
                        "x": 10, "y": 10, "width": 30, "height": 15, "status": "Draft"}
                       ).insert(ignore_permissions=True)
        st = ps.placement_state(BD, biz, ref)
        frappe.set_user("Administrator")
        self.assertEqual(st["covered_slot_count"], 1)          # legacy row not counted
        self.assertEqual(st["legacy_unmapped_count"], 1)

    def test_12_delete_updates_progress(self):
        req, biz = _pending("p12"); ref = _attach(biz, req)
        frappe.set_user(req)
        out = ps.save_placement(BD, biz, ref, _box("requester"))
        name = out["placement_name"]
        d = ps.delete_placement(BD, biz, ref, name)
        frappe.set_user("Administrator")
        self.assertTrue(d["ok"]); self.assertEqual(d["state"]["covered_slot_count"], 0)

    def test_13_reload_restores_exact_placement(self):
        req, biz = _pending("p13"); ref = _attach(biz, req)
        frappe.set_user(req)
        ps.save_placement(BD, biz, ref, _box("requester", x=77, y=88))
        st = ps.placement_state(BD, biz, ref)
        frappe.set_user("Administrator")
        pl = st["placements"][0]
        self.assertEqual((pl["x"], pl["y"], pl["signer_slot_key"]), (77.0, 88.0, "requester"))

    def test_14_15_16_modes_reflected_in_required_slots(self):
        req, biz = _pending("p14"); ref = _attach(biz, req)
        plan = sp.resolve_signer_plan(BD, biz)
        st = ps.placement_state(BD, biz, ref)
        # required slot count matches the B1 plan's required slots (Any One=1, All=N, Min=N)
        self.assertEqual(st["required_slot_count"], plan["summary"]["required_slots"])
        keys = {s["slot_key"] for s in st["required_slots"]}
        self.assertIn("requester", keys)                       # requester slot present


    def test_17_placement_state_zero_writes(self):
        req, biz = _pending("z1"); ref = _attach(biz, req)          # fresh default-signable PDF, no pkg
        counts = {dt: frappe.db.count(dt) for dt in
                  ("EC Digital Signature Package", "EC Digital Signature File", PL,
                   "EC Digital Signature Event")}
        frappe.set_user(req)
        st = ps.placement_state(BD, biz, ref)
        ps.placement_state(BD, biz, ref)                            # repeated
        frappe.set_user("Administrator")
        for dt, before in counts.items():
            self.assertEqual(frappe.db.count(dt), before, "placement_state wrote %s" % dt)
        # still resolves everything without materializing
        self.assertTrue(st["ok"]); self.assertTrue(st["is_pdf"]); self.assertTrue(st["file_url"])
        self.assertEqual(st["progress"]["covered"], 0)
        self.assertGreaterEqual(st["required_slot_count"], 1)

    def test_18_first_save_materializes_one_pkg_one_dsf_then_reuses(self):
        req, biz = _pending("z2"); ref = _attach(biz, req)
        self.assertFalse(pkgsvc.draft_package_for_business(BD, biz))
        frappe.set_user(req)
        ps.save_placement(BD, biz, ref, _box("requester"))
        draft = pkgsvc.draft_package_for_business(BD, biz)
        self.assertEqual(frappe.db.count("EC Digital Signature Package",
                                         {"business_doctype": BD, "business_name": biz}), 1)
        self.assertEqual(frappe.db.count(DSF := "EC Digital Signature File", {"package": draft}), 1)
        ps.save_placement(BD, biz, ref, _box("requester", x=200))   # second save reuses
        frappe.set_user("Administrator")
        self.assertEqual(frappe.db.count("EC Digital Signature Package",
                                         {"business_doctype": BD, "business_name": biz}), 1)
        self.assertEqual(frappe.db.count(DSF, {"package": draft}), 1)

    def test_19_delete_never_creates_pkg_or_dsf(self):
        req, biz = _pending("z3"); ref = _attach(biz, req)
        before = frappe.db.count("EC Digital Signature Package")
        frappe.set_user(req)
        out = ps.delete_placement(BD, biz, ref, "nonexistent-placement")  # nothing to delete
        frappe.set_user("Administrator")
        self.assertTrue(out["ok"])
        self.assertEqual(frappe.db.count("EC Digital Signature Package"), before)  # no materialization

    def test_20_level_no_compat_from_frozen_plan_slot(self):
        req, biz = _pending("z4"); ref = _attach(biz, req)
        plan = sp.resolve_signer_plan(BD, biz)
        lvl = next((sl for sl in plan["slots"] if sl["kind"] == "approval_level"), None)
        frappe.set_user(req)
        # requester slot -> level_no 0
        ps.save_placement(BD, biz, ref, _box("requester"))
        draft = pkgsvc.draft_package_for_business(BD, biz)
        rq = frappe.get_all(PL, filters={"package": draft, "signer_slot_key": "requester"},
                            fields=["level_no"])[0]
        self.assertEqual(rq.level_no, 0)
        if lvl:                                                     # approval-level slot -> frozen level_no
            ps.save_placement(BD, biz, ref, _box(lvl["slot_key"], x=250))
            r2 = frappe.get_all(PL, filters={"package": draft, "signer_slot_key": lvl["slot_key"]},
                                fields=["level_no"])[0]
            self.assertEqual(r2.level_no, lvl["level_no"])         # authoritative frozen level_no, not key parse
        frappe.set_user("Administrator")
