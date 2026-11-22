# Copyright (c) 2026, eCentric and contributors
"""Ky luat - khoa tinh: khong co truong tien (D127), DocType hop le, hook / route / job da khai,
ghi chu phap ly co tren form, trang khong co khoi <script>/<style> inline (A65), definition
engine dang ky dung (rieng tu + khong duyet hang loat).

    python3 -m unittest ecentric_workspace.hr.tests.test_ky_luat_schema
"""
import glob
import io
import json
import os
import re
import unittest

from ecentric_workspace.hr.tests import ky_luat_fake  # noqa: F401
from ecentric_workspace.hr.ky_luat import constants as C

APP = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DT_DIR = os.path.join(APP, "ecentric_workspace", "doctype")
OWN = ("ec_hr_notice", "ec_discipline_case", "ec_discipline_rule", "ec_discipline_settings",
       "ec_discipline_log")
DECISION_JSON = os.path.join(APP, "approval_center", "doctype", "ec_discipline_decision_request",
                             "ec_discipline_decision_request.json")
MONEY = re.compile(r"(tien|phat|fine|amount|salary|luong|deduct|penalty_amount|money)", re.I)


def _read(rel):
    with io.open(os.path.join(APP, rel), encoding="utf-8") as fh:
        return fh.read()


def _doctypes():
    out = {}
    for s in OWN:
        out[s] = json.loads(_read(os.path.join(DT_DIR, s, s + ".json")))
    out["decision"] = json.loads(_read(DECISION_JSON))
    return out


class TestNoMoney(unittest.TestCase):
    def test_no_currency_or_money_named_fields(self):
        for key, d in _doctypes().items():
            for f in d["fields"]:
                with self.subTest(doctype=d["name"], field=f["fieldname"]):
                    self.assertNotIn(f["fieldtype"], ("Currency", "Float", "Percent"))
                    self.assertFalse(MONEY.search(f["fieldname"]), "truong nghi la tien: %s" % f["fieldname"])

    def test_service_never_writes_money_keys(self):
        from ecentric_workspace.hr.ky_luat.application import case_service
        for k in case_service.EDITABLE:
            self.assertFalse(MONEY.search(k), k)


class TestDocTypes(unittest.TestCase):
    def test_field_order_matches_fields_and_options_valid(self):
        for key, d in _doctypes().items():
            names = [f["fieldname"] for f in d["fields"]]
            self.assertEqual(d["field_order"], names, d["name"])
            self.assertEqual(len(names), len(set(names)), d["name"])
            for f in d["fields"]:
                if f["fieldtype"] in ("Link", "Table"):
                    self.assertTrue(f.get("options"), "%s.%s" % (d["name"], f["fieldname"]))

    def test_status_options_match_constants(self):
        d = _doctypes()
        case_status = next(f for f in d["ec_discipline_case"]["fields"] if f["fieldname"] == "status")
        self.assertEqual(tuple(case_status["options"].split("\n")), C.CASE_STATUSES)
        n_status = next(f for f in d["ec_hr_notice"]["fields"] if f["fieldname"] == "status")
        self.assertEqual(tuple(n_status["options"].split("\n")), C.NOTICE_STATUSES)
        pen = next(f for f in d["ec_discipline_case"]["fields"] if f["fieldname"] == "penalty")
        self.assertEqual(tuple(pen["options"].split("\n")[1:]), C.PENALTIES)

    def test_write_perm_only_system_manager_on_records(self):
        d = _doctypes()
        for key in ("ec_hr_notice", "ec_discipline_case", "decision"):
            writers = [p["role"] for p in d[key]["permissions"] if p.get("write")]
            self.assertEqual(writers, ["System Manager"], key)


class TestWiring(unittest.TestCase):
    def test_hooks(self):
        h = _read("hooks.py")
        for s in ('"/ky-luat"', '"/ky-luat/quyet-dinh"', "hr.ky_luat.permissions.notice_query",
                  "hr.ky_luat.permissions.case_has_permission", "hr.ky_luat.controllers.api.daily_job"):
            self.assertIn(s, h)

    def test_patches_declared(self):
        p = _read("patches.txt")
        for s in ("hr.patches.p060_ky_luat_danh_muc_mau", "approval_center.patches.p460_ky_luat_quyet_dinh",
                  "approval_center.patches.p461_resync_tong_quan_tab_ky_luat"):
            self.assertIn(s, p)

    def test_engine_handler_and_registry(self):
        self.assertIn('"EC Discipline Decision Request": "ecentric_workspace.approval_center.features.'
                      'discipline_decision.application.service.on_final_approval"',
                      _read("approval_center/shared/workflow/transitions.py"))
        self.assertIn("DISCIPLINE_DECISION_DEFINITION", _read("approval_center/shared/registry.py"))

    def test_definition(self):
        from ecentric_workspace.approval_center.features.discipline_decision.domain.definition import (
            DISCIPLINE_DECISION_DEFINITION as D)
        from ecentric_workspace.approval_center.shared.requests.contracts import validate_definition
        validate_definition(D)
        self.assertEqual(D.editable_fields, ())
        self.assertTrue(D.quick_comment_required)
        if hasattr(D, "private"):
            self.assertTrue(D.private)

    def test_nav_item_and_rail(self):
        self.assertIn('"key": "hr.ky_luat"', _read("hr/nav.py"))
        self.assertIn('{"key": "hr.ky_luat"}', _read("shell/nav.py"))


class TestPages(unittest.TestCase):
    TEMPLATES = ("www/ky_luat/index.html", "www/ky_luat/quyet_dinh.html",
                 "templates/includes/ky_luat/layout.html", "templates/includes/ky_luat/macros.html")

    def test_no_inline_script_or_style(self):
        for rel in self.TEMPLATES:
            src = _read(rel)
            self.assertNotRegex(src, r"<style", rel)
            for m in re.finditer(r"<script([^>]*)>", src):
                self.assertTrue("src=" in m.group(1) or "application/json" in m.group(1), rel)

    def test_legal_note_on_every_page(self):
        self.assertIn("{{ legal_note|e }}", _read("templates/includes/ky_luat/layout.html"))
        self.assertIn("NĐ 145/2020", C.LEGAL_NOTE)

    def test_no_money_input_on_forms(self):
        src = _read("www/ky_luat/index.html")
        for name in re.findall(r'name="([a-z_]+)"', src):
            self.assertFalse(MONEY.search(name), name)

    def test_tong_quan_has_discipline_tab(self):
        src = _read("hr/pages/tong_quan/main_section.html")
        self.assertIn('tabs.push(["discipline", "Kỷ luật"])', src)
        self.assertIn("employee_discipline", src)

    def test_decision_page_renders(self):
        try:
            import jinja2
        except ImportError:
            self.skipTest("khong co jinja2")
        import datetime as dt
        base = "{% block content %}{% endblock %}{% block script %}{% endblock %}"
        env = jinja2.Environment(loader=jinja2.ChoiceLoader([
            jinja2.DictLoader({"base.html": base}), jinja2.FileSystemLoader(APP)]), autoescape=False)
        html = env.get_template("www/ky_luat/quyet_dinh.html").render(
            base_template_path="base.html", title="QD", legal_note=C.LEGAL_NOTE, ekl_css="", ekl_js="",
            ekl_shell_mount="", ekl_topbar="", boot_json="{}", case_route="/ky-luat?tab=ho-so&ma=KL-1",
            d={"request_title": "Quyết định kỷ luật - Sa thải - A", "name": "QD-1", "discipline_case": "KL-1",
               "employee_name": "A", "employee": "EMP-1", "card": C.CARD_BLACK, "penalty": C.P_DISMISS,
               "dismissal_ground": "(4) Tu y bo viec", "rule_title": "R", "violation_date": dt.date(2026, 11, 10),
               "meeting_date": dt.date(2026, 11, 30), "effective_date": None, "termination_date": dt.date(2026, 12, 15),
               "limitation_effective_end": dt.date(2027, 5, 10), "summary": "s", "meeting_summary": "m",
               "decision_draft": "/private/files/qd.pdf"},
            approval={"approval_status": "Pending", "status_label": "Đang phê duyệt"}, caps={"can_approve": True},
            timeline=[{"action": "Submitted", "actor": "hr", "action_time": dt.datetime(2026, 11, 30, 9), "comment": ""}])
        self.assertIn("15/12/2026", html)
        self.assertIn('data-ekl-decide-act="approve"', html)
        self.assertIn("NĐ 145/2020", html)

    def test_assets_exist(self):
        for rel in ("public/js/ec_ky_luat.js", "public/css/ec_ky_luat.css"):
            self.assertTrue(os.path.exists(os.path.join(APP, rel)), rel)


if __name__ == "__main__":
    unittest.main()
