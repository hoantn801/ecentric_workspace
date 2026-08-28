# Copyright (c) 2026, eCentric and contributors
"""Only the requester's signature was drawn; Direct Manager and Finance stayed blank.

Reported 2026-08-29 with a screenshot: three signatures existed, all three carried an
image, and the two sides agreed on the level identity -- yet two boxes stayed empty.

The bug was NOT in either endpoint. It was in transit.

  * `document_signature_overlay` reports `level_ref` per signature.   correct
  * `signer_plan` gives every slot a `level_ref`.                     correct
  * `placement_service.setup_state` -- the endpoint the DRAWER actually reads -- built
    its own projection of those slots and silently dropped the field.

So in the browser `sl.level_ref` was `undefined`, every approval_level comparison in
`_signedFor` was false, and only the requester slot rendered, because that one matches on
`kind` alone. Half-working, therefore invisible.

Why the previous test suite passed anyway: `test_overlay_level_ref.py` proved the two ENDS
speak the same key. It never asked whether the key survives the journey between them. A
matching pair of endpoints joined by a lossy pipe reads exactly like a working feature.
Same family as [[test-asserting-call-exists-proves-nothing]].

The diagnostic made the same mistake in the other direction: it queried `signer_plan`,
saw level_ref on every slot, and reported "the data matches". `signer_plan` is not the
endpoint the screen reads.

These tests EXECUTE the projection instead of grepping for it, so deleting the field fails
them rather than merely changing the text they search.
"""
import ast
import io
import os
import re
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))


def _src(*parts):
    root = _HERE
    for _i in range(8):
        path = os.path.join(root, *parts)
        if os.path.exists(path):
            return io.open(path, encoding="utf-8").read()
        parent = os.path.dirname(root)
        if parent == root:
            break
        root = parent
    raise AssertionError("khong tim thay %s" % (parts[-1],))


_PLACEMENT = _src("platform", "esign", "placement_service.py")
_UI = _src("platform", "esign", "ui", "document_signing_section.html")

# A slot as signer_plan really emits one (see signer_plan._level_slots).
_SLOT = {"slot_key": "L1", "kind": "approval_level", "approval_mode": "Any One",
         "level_ref": "8e662bucnq", "candidates": ["a@x.vn"], "required": True}


def _project(slot):
    """Run the real `required_slots` comprehension from placement_service on one slot.

    Pulled out of the source by AST so the test exercises the shipped expression rather
    than a copy of it that could drift.
    """
    tree = ast.parse(_PLACEMENT)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        for key, value in zip(node.keys, node.values):
            if isinstance(key, ast.Constant) and key.value == "required_slots":
                expr = ast.Expression(body=value)
                ast.fix_missing_locations(expr)
                # Names go in GLOBALS, not locals: a comprehension body runs in its own
                # scope and cannot see the caller's locals mapping.
                env = {"required": [slot], "labels": {slot["slot_key"]: "Cap 1"},
                       "__builtins__": {}}
                return eval(compile(expr, "<placement_service>", "eval"), env)
    raise AssertionError("khong tim thay phep chieu required_slots trong placement_service")


class TestTheDrawerEndpointCarriesLevelRef(unittest.TestCase):
    def test_the_projection_keeps_level_ref(self):
        out = _project(_SLOT)[0]
        self.assertIn("level_ref", out,
                      "man hinh doc endpoint NAY; thieu level_ref o day thi moi o cap "
                      "duyet deu khong bao gio ve duoc chu ky")

    def test_it_keeps_the_value_not_just_the_key(self):
        # An empty-but-present key is the same failure wearing a disguise: `undefined`
        # and `""` both lose every comparison in _signedFor.
        self.assertEqual(_project(_SLOT)[0].get("level_ref"), "8e662bucnq")

    def test_a_slot_without_a_level_still_projects(self):
        # Requester slots and legacy frozen rows legitimately have no level. They must
        # come through as None, not blow up the whole drawer.
        out = _project(dict(_SLOT, kind="requester", level_ref=None))[0]
        self.assertIsNone(out.get("level_ref"))

    def test_the_fields_the_drawer_reads_are_all_present(self):
        out = _project(_SLOT)[0]
        for field in ("slot_key", "label", "kind", "level_ref"):
            self.assertIn(field, out, "drawer doc truong %s" % field)


class TestTheBrowserStillMatchesOnIt(unittest.TestCase):
    """Guards the other half of the pipe, so a later refactor cannot quietly reopen this."""

    def test_the_comparison_reads_the_slot_field(self):
        body = re.search(r"function _signedFor\(slotKey\).*?\n  \}", _UI, re.S)
        self.assertIsNotNone(body, "khong tim thay _signedFor - test nay da mu")
        self.assertIn("sl.level_ref", body.group(0))

    def test_the_slot_list_comes_from_the_placement_endpoint(self):
        # DRW.st is setup_state's payload. If _signedFor ever reads a different object,
        # this test must be revisited rather than left passing on a stale assumption.
        self.assertIn("DRW.st && DRW.st.required_slots", _UI)


if __name__ == "__main__":
    unittest.main()
