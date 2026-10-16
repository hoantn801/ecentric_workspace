# -*- coding: utf-8 -*-
"""Hotfix 16/10: mo /pm#project/<id> phai to sang muc "Du an" o menu trai, khong roi ve
"Viec cua toi". Chuoi: pm/nav.py khai hash_segments -> shell/api.py::_ser giu truong ->
ec_shell.js hashActiveKey doc truong. Thieu mot mat xich la loi quay lai."""
import os
import re
import unittest

APP = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


def _rd(*p):
    with open(os.path.join(APP, *p), encoding="utf-8") as f:
        return f.read()


class TestNavHashSegments(unittest.TestCase):
    def test_pm_nav_declares_project_segment_on_projects_item(self):
        src = _rd("pm", "nav.py")
        self.assertRegex(src, r'\{"hash_segments": \["project"\]\} if key == "pm\.view\.projects"')

    def test_shell_serializer_keeps_hash_segments(self):
        src = _rd("shell", "api.py")
        m = re.search(r"def _ser\(.*?\n(?=def |\Z)", src, re.S)
        self.assertIsNotNone(m, "_ser not found")
        self.assertIn('"hash_segments"', m.group(0))

    def test_shell_js_matches_hash_segments(self):
        src = _rd("public", "js", "ec_shell.js")
        self.assertIn("(it.hash_segments || []).indexOf(curSeg) >= 0", src)


if __name__ == "__main__":
    unittest.main()
