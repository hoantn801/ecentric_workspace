# Copyright (c) 2026, eCentric and contributors
"""Cham diem: phan thuan tuy, khong can bench.

Test quan trong nhat o day la `test_late_penalty_applied_once`. Ban Server Script
truoc chay khoi tru diem tre HAI LAN lien tiep, nen moi bao cao nop tre mat 20
diem thay vi 10 -- va truong dung de truy vet (`overall_score_before_late`) bi
chinh khoi thu hai ghi de bang so da tru, nen nhin vao du lieu KHONG thay duoc.
143 ban ghi mang dau hieu do. Neu ai do "don dep" ham nay ma vo tinh goi hai
lan lan nua, test nay phai do.
"""

import unittest

from ecentric_workspace.weekly_report import scoring


class _Doc(object):
    def __init__(self, **kw):
        self.late_submission = 0
        self.full_name = "Nguoi A"
        self.week_label = "2026-W39"
        self.department = "Service - EC"
        self.overall_status = "On Track"
        self.mood = "OK"
        self.ai_tools_used = "Claude"
        self.what_done = "xong viec"
        self.pending_progress = ""
        self.plan_next_week = ""
        self.blockers_help = ""
        self.ai_use_case = ""
        self.slide_deck = ""
        for k, v in kw.items():
            setattr(self, k, v)


TIERS = [
    {"tier_name": "Outstanding", "min_score": 85, "max_score": 100},
    {"tier_name": "Good", "min_score": 70, "max_score": 84},
    {"tier_name": "Acceptable", "min_score": 50, "max_score": 69},
    {"tier_name": "Below", "min_score": 0, "max_score": 49},
]

CRITERIA = [
    {"criterion_name": "Slide", "field_key": "slide_deck_score", "max_points": 75,
     "is_penalty": 0, "description": "chat luong slide", "display_order": 1},
    {"criterion_name": "AI", "field_key": "ai_tools_score", "max_points": 10,
     "is_penalty": 0, "description": "", "display_order": 2},
    {"criterion_name": "Tru diem", "field_key": "penalty", "max_points": 20,
     "is_penalty": 1, "description": "", "display_order": 3},
]


class TestLatePenalty(unittest.TestCase):
    def test_late_penalty_applied_once(self):
        doc = _Doc(late_submission=1)
        out = scoring._apply_late_penalty({"overall_score": 80, "penalty": 0}, doc, TIERS)
        self.assertEqual(out["overall_score"], 70, "phai tru DUNG 10, khong phai 20")
        self.assertEqual(out["penalty"], 10)
        self.assertEqual(out["overall_score_before_late"], 80,
                         "phai giu diem GOC, khong phai diem da tru")
        self.assertEqual(out["late_penalty_applied"], 10)

    def test_late_penalty_recomputes_tier(self):
        doc = _Doc(late_submission=1)
        out = scoring._apply_late_penalty(
            {"overall_score": 72, "penalty": 0, "tier": "Good"}, doc, TIERS)
        self.assertEqual(out["overall_score"], 62)
        self.assertEqual(out["tier"], "Acceptable")

    def test_not_late_is_untouched(self):
        doc = _Doc(late_submission=0)
        out = scoring._apply_late_penalty(
            {"overall_score": 80, "penalty": 3, "tier": "Good"}, doc, TIERS)
        self.assertEqual(out["overall_score"], 80)
        self.assertEqual(out["penalty"], 3)
        self.assertNotIn("late_penalty_applied", out)

    def test_never_below_zero(self):
        doc = _Doc(late_submission=1)
        out = scoring._apply_late_penalty({"overall_score": 4, "penalty": 0}, doc, TIERS)
        self.assertEqual(out["overall_score"], 0)

    def test_ai_penalty_is_added_to_not_replaced(self):
        """AI tu tru 15, he thong tru them 10 -> 25. Khong duoc nuot diem phat cua AI."""
        doc = _Doc(late_submission=1)
        out = scoring._apply_late_penalty({"overall_score": 60, "penalty": 15}, doc, TIERS)
        self.assertEqual(out["penalty"], 25)


class TestSchema(unittest.TestCase):
    def test_schema_from_rubric_uses_field_keys_and_max_points(self):
        s = scoring.build_schema(CRITERIA, TIERS)
        p = s["properties"]
        self.assertEqual(p["slide_deck_score"]["maximum"], 75)
        self.assertEqual(p["ai_tools_score"]["maximum"], 10)
        self.assertEqual(p["penalty"]["maximum"], 20)
        self.assertEqual(p["tier"]["enum"],
                         ["Outstanding", "Good", "Acceptable", "Below"])
        for common in ("overall_score", "ai_usage_score", "structure_score",
                       "feedback", "highlights", "improvements"):
            self.assertIn(common, p, common + " thieu trong schema")
            self.assertIn(common, s["required"])

    def test_schema_falls_back_to_legacy_when_rubric_empty(self):
        s = scoring.build_schema([], [])
        p = s["properties"]
        self.assertEqual(p["slide_deck_score"]["maximum"], 40)
        self.assertEqual(p["optional_bonus"]["maximum"], 10)
        self.assertEqual(p["tier"]["enum"],
                         ["Outstanding", "Good", "Acceptable", "Below"])

    def test_criterion_without_field_key_is_skipped(self):
        s = scoring.build_schema(
            [{"criterion_name": "x", "field_key": "", "max_points": 5}], TIERS)
        self.assertNotIn("", s["properties"])


class TestPrompt(unittest.TestCase):
    def test_grading_stance_appears_exactly_once(self):
        """Ban goc lap doan nay 2 lan. Lap lai = ton token va lech trong so prompt."""
        text = scoring.build_instruction("RUBRIC", "REPORT")
        self.assertEqual(text.count("GRADING STANCE"), 1)

    def test_instruction_carries_rubric_and_report(self):
        text = scoring.build_instruction("RUBRIC-HERE", "REPORT-HERE")
        self.assertIn("RUBRIC-HERE", text)
        self.assertIn("REPORT-HERE", text)

    def test_report_text_lists_slide_files(self):
        doc = _Doc()
        t = scoring.build_report_text(doc, ["a.pdf", "b.pdf"])
        self.assertIn("Slide Deck: 2 files", t)
        self.assertIn("  - a.pdf", t)

    def test_slide_filenames_decodes_percent_escapes(self):
        doc = _Doc(slide_deck="https://x/sites/op/Bao%20cao%20tuan%2338.pdf")
        self.assertEqual(scoring.slide_filenames(doc), ["Bao cao tuan#38.pdf"])

    def test_slide_filenames_ignores_blank_lines(self):
        doc = _Doc(slide_deck="\n  \nhttps://x/y/a.pdf\n")
        self.assertEqual(scoring.slide_filenames(doc), ["a.pdf"])


class TestDeptClean(unittest.TestCase):
    def test_strips_suffix(self):
        self.assertEqual(scoring._dept_clean("Service - EC"), "Service")
        self.assertEqual(scoring._dept_clean("Management"), "Management")
        self.assertEqual(scoring._dept_clean(None), "")
