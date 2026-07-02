# Copyright (c) 2026, eCentric and contributors
"""B1 seed idempotency + non-destructiveness tests for Approval Center.

Run on a Frappe site:
  bench --site <site> run-tests --module \
    ecentric_workspace.approval_center.tests.test_seed_idempotency
"""
import json
import os

import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.approval_center.patches import (
    p001_seed_approval_categories as p001,
    p002_seed_approval_types as p002,
)

CAT = "EC Approval Category"
TYP = "EC Approval Type"


def _seed_codes():
    base = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "seed")
    cats = json.load(open(os.path.join(base, "approval_categories_seed.json"), encoding="utf-8"))
    typs = json.load(open(os.path.join(base, "approval_types_seed.json"), encoding="utf-8"))
    return ([c["category_code"] for c in cats], [t["approval_code"] for t in typs])


class TestApprovalCenterSeed(FrappeTestCase):
    def test_seed_and_idempotency(self):
        cat_codes, typ_codes = _seed_codes()

        # I1 / I2: run seed once
        p001.execute()
        p002.execute()
        self.assertEqual(len(typ_codes), 19)
        for c in cat_codes:
            self.assertTrue(frappe.db.exists(CAT, c), c)
        for t in typ_codes:
            self.assertTrue(frappe.db.exists(TYP, t), t)

        # I2: seed defaults on every seeded type
        for t in typ_codes:
            row = frappe.db.get_value(
                TYP, t, ["card_status", "process_status", "visibility_mode", "route"], as_dict=True)
            self.assertEqual(row.card_status, "Coming Soon", t)
            self.assertEqual(row.process_status, "Discovery", t)
            self.assertEqual(row.visibility_mode, "All Internal Users", t)
            self.assertIn(row.route or "", ("", None), t)

        # I3: every type.category resolves
        for t in typ_codes:
            cat = frappe.db.get_value(TYP, t, "category")
            self.assertTrue(frappe.db.exists(CAT, cat), "%s -> %s" % (t, cat))

        # I4: none active
        active = frappe.get_all(TYP, filters={"name": ["in", typ_codes], "card_status": "Active"})
        self.assertEqual(active, [])

        # I5: re-run -> no growth
        before_c = frappe.db.count(CAT)
        before_t = frappe.db.count(TYP)
        p001.execute()
        p002.execute()
        self.assertEqual(frappe.db.count(CAT), before_c)
        self.assertEqual(frappe.db.count(TYP), before_t)

        # I6: admin edit preserved on re-run
        sample = typ_codes[0]
        frappe.db.set_value(TYP, sample, "card_status", "Migrating")
        p002.execute()
        self.assertEqual(frappe.db.get_value(TYP, sample, "card_status"), "Migrating")

        # I7: exact code set present
        got = set(frappe.get_all(TYP, filters={"name": ["in", typ_codes]}, pluck="name"))
        self.assertEqual(got, set(typ_codes))
