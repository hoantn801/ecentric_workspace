# Copyright (c) 2026, eCentric and contributors
"""Ghi loi tu may: idempotent, nang muc, khong ghi de ket qua duyet; duyet tren ERP cham lai diem."""
import unittest

from ecentric_workspace.host_qc.exceptions import ForbiddenError, InvalidInput, NotFoundError
from ecentric_workspace.host_qc.services.build_rules_config_service import BuildRulesConfigService
from ecentric_workspace.host_qc.services.list_reviews_service import ListReviewsService
from ecentric_workspace.host_qc.services.record_violation_service import RecordViolationService, mark
from ecentric_workspace.host_qc.services.rescore_session_service import RescoreSessionService
from ecentric_workspace.host_qc.services.review_violation_service import ReviewViolationService
from ecentric_workspace.host_qc.tests import fakes as F

M1 = {"name": "M1", "machine_id": "M1"}


class Base(unittest.TestCase):
    def setUp(self):
        self.sessions, self.viol = F.FakeSessions(), F.FakeViolations()
        self.sessions.add("s1", started_at=F.NOW, hosts=[{"host_id": "h1", "host_name": "Lan"}])
        self.cfg = BuildRulesConfigService(F.FakeSettings(), F.FakeRules())
        self.rescore = RescoreSessionService(self.sessions, self.viol, self.cfg)
        self.svc = RecordViolationService(self.sessions, self.viol, self.cfg, self.rescore)

    def send(self, **kw):
        v = dict({"id": "v1", "session_id": "s1", "code": "ENG-01", "group": "C", "severity": "Minor",
                  "host_id": "h1", "start": 1795948860000, "end": 1795948900000}, **kw)
        return self.svc.execute(M1, v)


class TestRecordViolation(Base):
    def test_tao_moi_roi_gui_lai_khong_nhan_doi(self):
        self.send()
        self.send()
        self.assertEqual(len(self.viol.v), 1)
        v = self.viol.v["v1"]
        self.assertEqual((v["review"], v["host_name"], v["needs_verification"]), ("Pending", "Lan", 0))
        self.assertEqual(self.sessions.s["s1"]["total_score"], 97)

    def test_nang_minor_len_critical_thi_cho_xac_minh(self):
        self.send()
        self.send(severity="Critical")
        v = self.viol.v["v1"]
        self.assertEqual((v["severity"], v["review"], v["needs_verification"]), ("Critical", "Need Review", 1))
        self.assertEqual(self.sessions.s["s1"]["status_color"], "RED")

    def test_app_gui_lai_khong_ghi_de_ket_qua_duyet(self):
        self.send(severity="Major")
        ReviewViolationService(self.viol, self.rescore, F.clock).execute("qc@x", ["Host QC Manager"], "v1",
                                                                         "False Positive", "nham")
        self.assertEqual(self.sessions.s["s1"]["total_score"], 100)
        self.send(severity="Major", review="Pending")
        self.assertEqual(self.viol.v["v1"]["review"], "False Positive")
        self.assertEqual(self.sessions.s["s1"]["total_score"], 100)

    def test_ma_co_default_review_bat_dau_need_review(self):
        self.send(id="v2", code="VOI-02", group="A", severity="Major")
        self.assertEqual(self.viol.v["v2"]["review"], "Need Review")
        self.assertEqual(self.sessions.s["s1"]["total_score"], 100)     # VOI-02 chua Valid -> chua tru

    def test_loi(self):
        with self.assertRaises(InvalidInput):
            self.send(id="bad id!")
        with self.assertRaises(NotFoundError):
            self.send(session_id="khong-co")
        with self.assertRaises(ForbiddenError):
            self.svc.execute({"name": "M2"}, {"id": "v9", "session_id": "s1", "code": "ENG-01", "severity": "Minor"})

    def test_mark(self):
        self.assertEqual(mark("abc def", [[4, 7]]), "abc «def»")
        self.assertEqual(mark("«x»", [[0, 1]]), "«x»")


class TestReview(Base):
    def test_can_manager(self):
        self.send()
        with self.assertRaises(ForbiddenError):
            ReviewViolationService(self.viol, self.rescore).execute("u", ["Host QC Viewer"], "v1", "Valid Violation")
        with self.assertRaises(InvalidInput):
            ReviewViolationService(self.viol, self.rescore).execute("u", ["Host QC Manager"], "v1", "Pending")

    def test_duyet_tra_diem_va_log_va_reviews_cho_app(self):
        self.send(severity="Critical")
        out = ReviewViolationService(self.viol, self.rescore, F.clock).execute(
            "qc@x", ["Host QC Manager"], "v1", "Valid Violation", "dung")
        self.assertEqual(out, {"review": "Valid Violation", "total_score": 82, "status_color": "RED"})
        self.assertEqual(self.viol.v["v1"]["needs_verification"], 0)
        self.assertEqual(self.viol.logs[0][1]["from_review"], "Need Review")
        rows = ListReviewsService(self.sessions, self.viol).execute(M1, "s1")
        self.assertEqual(rows, [{"violation_id": "v1", "review": "Valid Violation", "reviewer": "qc@x",
                                 "note": "dung", "at": "2026-11-24T20:00:00+07:00"}])
        with self.assertRaises(ForbiddenError):
            ListReviewsService(self.sessions, self.viol).execute({"name": "M2"}, "s1")


if __name__ == "__main__":
    unittest.main()
