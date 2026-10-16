# -*- coding: utf-8 -*-
"""Hotfix 16/10: ghim binh luan trong viec (pm.api.comments.pin / list). Fake frappe, no bench."""
import json
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _pm_fake as F  # noqa: E402


class TestCommentPin(unittest.TestCase):
    def setUp(self):
        self.fk = F.install()
        F.seed_users(self.fk)
        self.fk.doctypes.add("Comment")
        self.fk.meta_fields["Task"] = {"ec_pinned_comments"}
        self.fk.module.utils.strip_html = lambda s: re.sub(r"<[^>]+>", "", s or "")
        self.cm = self.fk.load("ecentric_workspace.pm.api.comments")
        F.task(self.fk, "T", owner=F.GIVER, assign=[F.ALICE])
        F.task(self.fk, "T2", owner=F.GIVER, assign=[F.ALICE])
        for n, ref in (("C1", "T"), ("C2", "T"), ("CX", "T2")):
            self.fk.add("Comment", name=n, comment_type="Comment", reference_doctype="Task",
                        reference_name=ref, content="<p>Ghi chu %s</p>" % n, owner=F.GIVER)
        self.fk.set_user(F.ALICE)

    def pins(self):
        return json.loads(self.fk.row("Task", "T").get("ec_pinned_comments") or "[]")

    def test_pin_unpin_and_list_flags(self):
        r = self.cm.pin("Task", "T", "C2", 1)
        self.assertEqual(r["pinned"], ["C2"])
        self.assertEqual(self.pins(), ["C2"])
        out = self.cm.list("Task", "T")
        self.assertEqual(out["pinned"], ["C2"])
        self.assertEqual({x["name"]: x["pinned"] for x in out["rows"]}, {"C1": 0, "C2": 1})
        self.assertEqual(out["can_pin"], 1)
        self.cm.pin("Task", "T", "C2", 0)
        self.assertEqual(self.pins(), [])

    def test_pin_writes_audit_info_comment_and_not_in_chat(self):
        self.cm.pin("Task", "T", "C1", 1)
        info = [c for c in self.fk.db.t("Comment").values() if c.get("comment_type") == "Info"]
        self.assertEqual(len(info), 1)
        self.assertIn("Ghi chu C1", info[0]["content"])
        self.assertTrue(all(x["name"] != info[0]["name"] for x in self.cm.list("Task", "T")["rows"]))

    def test_comment_of_other_task_rejected(self):
        with self.assertRaises(F.PermissionError):
            self.cm.pin("Task", "T", "CX", 1)
        self.assertEqual(self.pins(), [])

    def test_outsider_cannot_pin(self):
        self.fk.set_user(F.OUTSIDER)
        with self.assertRaises(F.PermissionError):
            self.cm.pin("Task", "T", "C1", 1)

    def test_cap_five(self):
        for i in range(6):
            self.fk.add("Comment", name="K%d" % i, comment_type="Comment", reference_doctype="Task",
                        reference_name="T", content="k", owner=F.GIVER)
        for i in range(5):
            self.cm.pin("Task", "T", "K%d" % i, 1)
        with self.assertRaises(F.ValidationError):
            self.cm.pin("Task", "T", "K5", 1)
        self.assertEqual(len(self.pins()), 5)

    def test_field_missing_degrades(self):
        self.fk.meta_fields["Task"] = set()
        self.assertEqual(self.cm.list("Task", "T")["can_pin"], 0)
        with self.assertRaises(F.ValidationError):
            self.cm.pin("Task", "T", "C1", 1)


if __name__ == "__main__":
    unittest.main()
