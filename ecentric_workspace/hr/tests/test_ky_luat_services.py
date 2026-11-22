# Copyright (c) 2026, eCentric and contributors
"""Ky luat - service chay ngoai Frappe (FakeRepo): the vang, ho so 4 buoc, hoan / keo dai thoi
hieu, CEO, sa thai -> Clearance, xoa ky luat, job, quyen xem.

    python3 -m unittest ecentric_workspace.hr.tests.test_ky_luat_services
"""
import datetime as dt
import unittest

from ecentric_workspace.hr.tests.ky_luat_fake import CEO, HR, LM, NV, OUT, UNION, FakeRepo
from ecentric_workspace.hr.ky_luat import constants as C
from ecentric_workspace.hr.ky_luat.application import (
    access as A, case_service as CS, decision_service as DS, jobs, notice_service as NS,
    procedure_service as PS, views as V)
from ecentric_workspace.hr.ky_luat.domain.errors import FieldErrors, KyLuatError, KyLuatForbidden

d = dt.date


def ctx(repo, user):
    return V.make_ctx(repo, user)


def case_payload(**kw):
    p = {"employee": "EMP-NV", "card": C.CARD_RED, "penalty": C.P_REPRIMAND, "rule": "R1",
         "violation_date": "2026-11-10", "description": "Vang 2 ngay khong phep",
         "violation_record": "/private/files/bb.pdf"}
    p.update(kw)
    return p


class Base(unittest.TestCase):
    def setUp(self):
        self.r = FakeRepo()

    def at(self, day):
        self.r._today = day

    def make_case(self, **kw):
        return CS.create(self.r, ctx(self.r, HR), case_payload(**kw))["name"]

    def to_met(self, name, meeting=d(2026, 11, 30)):
        PS.notify_meeting(self.r, ctx(self.r, HR), name, str(meeting))
        self.at(meeting)
        PS.record_meeting(self.r, ctx(self.r, HR), name, {"employee_present": C.PRESENT_YES,
                                                          "employee_statement": "Toi xin loi",
                                                          "meeting_minutes": "/private/files/hop.pdf"})


class TestNotice(Base):
    def issue(self, user=LM, **kw):
        p = {"employee": "EMP-NV", "behavior": "Di muon", "content": "Nhac lan 1", "incident_date": "2026-11-20"}
        p.update(kw)
        return NS.issue(self.r, ctx(self.r, user), p)

    def test_lm_issue_and_due_three_workdays(self):
        out = self.issue()
        n = self.r.get_notice(out["name"])
        self.assertEqual(n["status"], C.NOTICE_PENDING)
        self.assertEqual(n["reply_due"], d(2026, 11, 26))
        self.assertEqual(n["issuer_role"], C.ISSUER_LM)
        self.assertTrue(self.r.to(NV))

    def test_outsider_cannot_issue_and_nobody_to_self(self):
        with self.assertRaises(KyLuatForbidden):
            self.issue(user=OUT)
        with self.assertRaises(KyLuatForbidden):
            NS.issue(self.r, ctx(self.r, LM), {"employee": "EMP-LM", "behavior": "x", "content": "y",
                                               "incident_date": "2026-11-20"})

    def test_hr_can_issue_validation(self):
        with self.assertRaises(FieldErrors) as e:
            self.issue(user=HR, behavior="", incident_date="2026-12-30")
        self.assertIn("behavior", e.exception.errors)
        self.assertIn("incident_date", e.exception.errors)

    def test_evidence_must_be_own_private_file(self):
        self.r.bad_files.add("/files/x.png")
        with self.assertRaises(FieldErrors) as e:
            self.issue(evidence="/files/x.png")
        self.assertIn("evidence", e.exception.errors)

    def test_read_reply_only_owner(self):
        name = self.issue()["name"]
        with self.assertRaises(KyLuatForbidden):
            NS.mark_read(self.r, ctx(self.r, LM), name)
        NS.mark_read(self.r, ctx(self.r, NV), name)
        self.assertEqual(self.r.get_notice(name)["status"], C.NOTICE_READ)
        NS.reply(self.r, ctx(self.r, NV), name, "Em se rut kinh nghiem")
        self.assertEqual(self.r.get_notice(name)["status"], C.NOTICE_REPLIED)
        self.assertTrue(self.r.to(LM))

    def test_read_after_reply_keeps_replied(self):
        name = self.issue()["name"]
        NS.reply(self.r, ctx(self.r, NV), name, "Da hieu")
        NS.mark_read(self.r, ctx(self.r, NV), name)
        self.assertEqual(self.r.get_notice(name)["status"], C.NOTICE_REPLIED)

    def test_auto_close_after_three_workdays(self):
        name = self.issue()["name"]
        self.at(d(2026, 11, 26))
        self.assertEqual(NS.auto_close_overdue(self.r), 0)          # hom nay van con han
        self.at(d(2026, 11, 27))
        self.assertEqual(NS.auto_close_overdue(self.r), 1)
        n = self.r.get_notice(name)
        self.assertEqual(n["status"], C.NOTICE_NO_REPLY)
        self.assertEqual(n["response"], C.NOTICE_AUTO_TEXT)
        self.assertEqual(n["logs"][-1]["action"], C.NOTICE_AUTO_TEXT)
        self.assertEqual(NS.auto_close_overdue(self.r), 0)          # idempotent

    def test_read_notice_not_auto_closed(self):
        name = self.issue()["name"]
        NS.mark_read(self.r, ctx(self.r, NV), name)
        self.at(d(2026, 12, 10))
        self.assertEqual(NS.auto_close_overdue(self.r), 0)

    def test_hint_after_three_in_90_days_no_auto_red(self):
        self.issue(incident_date="2026-10-01")
        self.issue(incident_date="2026-11-01")
        out = self.issue(incident_date="2026-11-20")
        self.assertTrue(out["hint"])
        self.assertEqual(self.r.cases_, {})                         # khong tu lap the do
        self.assertTrue(self.r.to(HR))

    def test_visibility(self):
        name = self.issue()["name"]
        n = self.r.get_notice(name)
        self.assertTrue(A.can_view_notice(ctx(self.r, NV), n))
        self.assertTrue(A.can_view_notice(ctx(self.r, LM), n))
        self.assertTrue(A.can_view_notice(ctx(self.r, HR), n))
        self.assertTrue(A.can_view_notice(ctx(self.r, CEO), n))
        self.assertFalse(A.can_view_notice(ctx(self.r, OUT), n))
        with self.assertRaises(KyLuatForbidden):
            V.notice_detail(self.r, ctx(self.r, OUT), name)
        self.assertEqual(V.visible_notices(self.r, ctx(self.r, OUT)), [])


class TestCaseFlow(Base):
    def test_lm_propose_hr_accept(self):
        name = CS.propose(self.r, ctx(self.r, LM), case_payload(rule=None, violation_record=None))["name"]
        c = self.r.get_case(name)
        self.assertEqual(c["status"], C.S_PROPOSED)
        self.assertEqual(c["hr_review_due"], d(2026, 11, 26))
        self.assertTrue(self.r.to(HR))
        with self.assertRaises(KyLuatForbidden):
            CS.update(self.r, ctx(self.r, LM), name, {"accept": 1})
        with self.assertRaises(FieldErrors):                      # HR phai chon dieu khoan
            CS.update(self.r, ctx(self.r, HR), name, {"accept": 1})
        CS.update(self.r, ctx(self.r, HR), name, {"accept": 1, "rule": "R1"})
        self.assertEqual(self.r.get_case(name)["status"], C.S_DRAFT)

    def test_outsider_cannot_propose(self):
        with self.assertRaises(KyLuatForbidden):
            CS.propose(self.r, ctx(self.r, OUT), case_payload())

    def test_only_hr_creates(self):
        with self.assertRaises(KyLuatForbidden):
            CS.create(self.r, ctx(self.r, LM), case_payload())

    def test_limitation_and_finance_rule(self):
        c = self.r.get_case(self.make_case())
        self.assertEqual(c["limitation_end"], "2027-05-10")
        c2 = self.r.get_case(self.make_case(rule="RF"))
        self.assertEqual(c2["limitation_end"], "2027-11-10")
        self.assertEqual(c2["finance_related"], 1)

    def test_expired_cannot_create(self):
        with self.assertRaises(KyLuatError):
            self.make_case(violation_date="2026-05-01")             # 6 thang -> 01/11 < hom nay

    def test_no_money_field_accepted(self):
        name = self.make_case(fine_amount=500000, salary_deduction=1)
        c = self.r.get_case(name)
        self.assertNotIn("fine_amount", c)
        self.assertNotIn("salary_deduction", c)

    def test_full_flow_red(self):
        name = self.make_case(is_union_member=1)
        with self.assertRaises(FieldErrors) as e:
            PS.notify_meeting(self.r, ctx(self.r, HR), name, "2026-11-27")    # < 5 ngay LV
        self.assertIn("meeting_date", e.exception.errors)
        with self.assertRaises(FieldErrors):
            PS.notify_meeting(self.r, ctx(self.r, HR), name, "2026-12-05")    # thu Bay
        PS.notify_meeting(self.r, ctx(self.r, HR), name, "2026-11-30")
        c = self.r.get_case(name)
        self.assertEqual(c["status"], C.S_NOTIFIED)
        self.assertEqual(c["union_rep_user"], UNION)
        self.assertTrue(any(s[2] for s in self.r.to(NV)))                 # email cho NV
        self.assertTrue(any(s[2] for s in self.r.to(UNION)))              # email cho cong doan
        PS.confirm_attendance(self.r, ctx(self.r, NV), name, 0, "Toi ban")
        self.assertEqual(self.r.get_case(name)["attendance_reply"], C.ATTEND_NO)
        with self.assertRaises(KyLuatError):
            PS.record_meeting(self.r, ctx(self.r, HR), name, {})              # chua toi ngay
        self.at(d(2026, 11, 30))
        with self.assertRaises(FieldErrors) as e:
            PS.record_meeting(self.r, ctx(self.r, HR), name, {"employee_present": C.PRESENT_NO})
        self.assertIn("meeting_minutes", e.exception.errors)
        PS.record_meeting(self.r, ctx(self.r, HR), name, {"employee_present": C.PRESENT_NO,
                                                          "meeting_minutes": "/private/files/hop.pdf"})
        c = self.r.get_case(name)
        self.assertEqual(c["status"], C.S_MET)
        self.assertIn("không có nghĩa là đồng ý", c["employee_statement"])
        self.assertEqual(c["ceo_due"], d(2026, 12, 2))
        with self.assertRaises(FieldErrors):
            PS.submit_to_ceo(self.r, ctx(self.r, HR), name, {})              # thieu du thao
        out = PS.submit_to_ceo(self.r, ctx(self.r, HR), name, {"decision_draft": "/private/files/qd.pdf"})
        self.assertEqual(self.r.get_case(name)["status"], C.S_AT_CEO)
        self.r.decisions[out["decision_request"]] = "Approved"
        DS.on_ceo_approved(self.r, name)
        c = self.r.get_case(name)
        self.assertEqual(c["status"], C.S_ISSUED)
        self.assertEqual(c["expunge_due"], d(2027, 2, 28))                # 30/11 + 3 thang
        self.assertTrue(self.r.to(NV) and self.r.to(UNION))
        self.assertEqual(DS.on_ceo_approved(self.r, name)["status"], C.S_ISSUED)   # idempotent

    def test_meeting_one_workday_short_rejected(self):
        self.at(d(2026, 11, 24))                                   # thu Ba -> som nhat thu Ba 01/12
        name = self.make_case()
        with self.assertRaises(FieldErrors):
            PS.notify_meeting(self.r, ctx(self.r, HR), name, "2026-11-30")
        self.assertEqual(PS.notify_meeting(self.r, ctx(self.r, HR), name, "2026-12-01")["earliest"], "2026-12-01")

    def test_meeting_respects_holiday(self):
        self.r.hols = {d(2026, 11, 26)}
        name = self.make_case()
        with self.assertRaises(FieldErrors):
            PS.notify_meeting(self.r, ctx(self.r, HR), name, "2026-11-30")
        PS.notify_meeting(self.r, ctx(self.r, HR), name, "2026-12-01")

    def test_meeting_on_holiday_rejected(self):
        self.r.hols = {d(2026, 12, 1)}
        name = self.make_case()
        with self.assertRaises(FieldErrors) as e:
            PS.notify_meeting(self.r, ctx(self.r, HR), name, "2026-12-01")
        self.assertIn("ngày nghỉ", e.exception.errors["meeting_date"])

    def test_union_member_without_rep_config(self):
        self.r.settings_["union_rep_user"] = None
        name = self.make_case(is_union_member=1)
        with self.assertRaises(KyLuatError):
            PS.notify_meeting(self.r, ctx(self.r, HR), name, "2026-11-30")

    def test_notify_requires_violation_record(self):
        name = self.make_case(violation_record=None)
        with self.assertRaises(FieldErrors) as e:
            PS.notify_meeting(self.r, ctx(self.r, HR), name, "2026-11-30")
        self.assertIn("violation_record", e.exception.errors)

    def test_employee_visibility_only_after_notice(self):
        name = self.make_case()
        c = self.r.get_case(name)
        self.assertFalse(A.can_view_case(ctx(self.r, NV), c))
        self.assertTrue(A.can_view_case(ctx(self.r, LM), c))
        self.assertFalse(A.can_view_case(ctx(self.r, OUT), c))
        self.assertFalse(A.can_view_case(ctx(self.r, UNION), c))
        PS.notify_meeting(self.r, ctx(self.r, HR), name, "2026-11-30")
        c = self.r.get_case(name)
        self.assertTrue(A.can_view_case(ctx(self.r, NV), c))
        self.assertFalse(A.can_view_case(ctx(self.r, UNION), c))          # khong phai doan vien
        detail = V.case_detail(self.r, ctx(self.r, NV), name)
        self.assertNotIn("hr_note", detail)
        self.assertTrue(detail["actions"]["attend"])
        self.assertFalse(detail["actions"]["record"])
        self.assertEqual(V.visible_cases(self.r, ctx(self.r, OUT)), [])

    def test_recidivism_detected_on_new_case(self):
        first = self.make_case()
        self.to_met(first)
        out = PS.submit_to_ceo(self.r, ctx(self.r, HR), first, {"decision_draft": "/private/files/qd.pdf"})
        self.r.decisions[out["decision_request"]] = "Approved"
        DS.on_ceo_approved(self.r, first)
        second = self.make_case(violation_date="2026-11-28")
        c = self.r.get_case(second)
        self.assertEqual(c["recidivism"], 1)
        self.assertIn(first, c["recidivism_note"])

    def test_ceo_reject_reconciles_to_no_discipline(self):
        name = self.make_case()
        self.to_met(name)
        out = PS.submit_to_ceo(self.r, ctx(self.r, HR), name, {"decision_draft": "/private/files/qd.pdf"})
        self.r.decisions[out["decision_request"]] = "Information Required"
        self.assertEqual(DS.reconcile(self.r, name), C.S_AT_CEO)
        self.assertEqual(V.case_detail(self.r, ctx(self.r, HR), name)["display_status"], "CEO yêu cầu bổ sung")
        PS.resubmit_to_ceo(self.r, ctx(self.r, HR), name, {"effective_date": "2026-12-01"})
        self.assertEqual(self.r.decision_calls[-1][0], "resubmit")
        self.r.decisions[out["decision_request"]] = "Rejected"
        self.assertEqual(DS.reconcile(self.r, name), C.S_NO_DISCIPLINE)
        self.assertTrue(self.r.to(NV))


class TestDismissal(Base):
    def run_to_issue(self, clearance):
        self.r.clearance_result = clearance
        name = self.make_case(card=C.CARD_BLACK, penalty=C.P_DISMISS, dismissal_ground="4")
        self.to_met(name)
        with self.assertRaises(FieldErrors):
            PS.submit_to_ceo(self.r, ctx(self.r, HR), name, {"decision_draft": "/private/files/qd.pdf"})
        out = PS.submit_to_ceo(self.r, ctx(self.r, HR), name, {"decision_draft": "/private/files/qd.pdf",
                                                               "termination_date": "2026-12-15"})
        self.r.decisions[out["decision_request"]] = "Approved"
        DS.on_ceo_approved(self.r, name)
        return self.r.get_case(name)

    def test_dismissal_sets_relieving_and_clearance(self):
        c = self.run_to_issue("EC-CLR-1")
        self.assertEqual(self.r.relieving["EMP-NV"], d(2026, 12, 15))
        self.assertEqual(self.r.clearance_calls[0][0], "EMP-NV")
        self.assertEqual(self.r.clearance_calls[0][2], d(2026, 12, 15))
        self.assertIn("EC-CLR-1", c["offboarding_note"])
        self.assertIsNone(c["expunge_due"])

    def test_dismissal_clearance_missing_falls_back(self):
        c = self.run_to_issue(None)
        self.assertIn("HR tạo tay", c["offboarding_note"])
        self.assertEqual(c["status"], C.S_ISSUED)
        self.assertTrue(self.r.to(HR))


class TestPostpone(Base):
    def test_leave_on_meeting_day_rejected_then_auto_postpone_when_meeting(self):
        name = self.make_case()
        self.r.leaves["EMP-NV"] = [(d(2026, 11, 30), d(2026, 12, 4))]
        with self.assertRaises(FieldErrors):
            PS.notify_meeting(self.r, ctx(self.r, HR), name, "2026-11-30")
        PS.notify_meeting(self.r, ctx(self.r, HR), name, "2026-12-07")
        self.r.leaves["EMP-NV"].append((d(2026, 12, 7), d(2026, 12, 9)))      # nghi om dot xuat
        self.at(d(2026, 12, 7))
        out = PS.record_meeting(self.r, ctx(self.r, HR), name, {"employee_present": C.PRESENT_NO,
                                                                "meeting_minutes": "/private/files/hop.pdf"})
        self.assertEqual(out["status"], C.S_POSTPONED)
        c = self.r.get_case(name)
        self.assertEqual(c["block_reason"], C.BLOCK_LEAVE)
        with self.assertRaises(KyLuatError):                                  # van trong thoi gian cam
            CS.resume(self.r, ctx(self.r, HR), name)
        self.at(d(2026, 12, 10))
        self.assertEqual(CS.resume(self.r, ctx(self.r, HR), name)["status"], C.S_DRAFT)

    def test_manual_postpone_extends_limitation(self):
        name = self.make_case(violation_date="2026-06-01")                   # het han goc 01/12
        out = CS.postpone(self.r, ctx(self.r, HR), name, C.BLOCK_MATERNITY, "2026-11-25", "2027-03-31")
        self.assertEqual(out["status"], C.S_POSTPONED)
        c = self.r.get_case(name)
        self.assertEqual(c["limitation_effective_end"], "2027-05-30")         # 31/03 + 60
        self.at(d(2027, 4, 1))
        self.assertEqual(CS.resume(self.r, ctx(self.r, HR), name)["status"], C.S_DRAFT)

    def test_postpone_requires_valid_reason(self):
        name = self.make_case()
        with self.assertRaises(FieldErrors):
            CS.postpone(self.r, ctx(self.r, HR), name, "Ly do khac", "2026-11-25", "2026-11-30")


class TestJobs(Base):
    def test_daily_skips_weekend(self):
        self.at(d(2026, 11, 28))
        self.assertEqual(jobs.daily(self.r), {"skipped": "ngay nghi"})

    def test_warn_once_and_expire(self):
        name = self.make_case(violation_date="2026-06-01")                   # het 01/12
        out = jobs.scan_open_cases(self.r)
        self.assertEqual(out["warned"], 1)
        self.assertEqual(jobs.scan_open_cases(self.r)["warned"], 0)           # chi mot lan
        self.at(d(2026, 12, 2))
        self.assertEqual(jobs.scan_open_cases(self.r)["expired"], 1)
        self.assertEqual(self.r.get_case(name)["status"], C.S_EXPIRED)

    def test_expired_at_ceo_never_issued(self):
        name = self.make_case(violation_date="2026-06-01")
        PS.notify_meeting(self.r, ctx(self.r, HR), name, "2026-11-30")
        self.at(d(2026, 11, 30))
        PS.record_meeting(self.r, ctx(self.r, HR), name, {"employee_present": C.PRESENT_YES, "employee_statement": "x",
                                                          "meeting_minutes": "/private/files/h.pdf"})
        out = PS.submit_to_ceo(self.r, ctx(self.r, HR), name, {"decision_draft": "/private/files/qd.pdf"})
        self.at(d(2026, 12, 3))
        self.r.decisions[out["decision_request"]] = "Approved"
        self.assertEqual(DS.on_ceo_approved(self.r, name)["status"], C.S_EXPIRED)

    def test_expunge_and_hold_on_recidivism(self):
        a = self.make_case()
        self.to_met(a)
        o = PS.submit_to_ceo(self.r, ctx(self.r, HR), a, {"decision_draft": "/private/files/qd.pdf"})
        self.r.decisions[o["decision_request"]] = "Approved"
        DS.on_ceo_approved(self.r, a)                                            # QD 30/11, xoa 28/02
        self.at(d(2027, 3, 1))
        self.assertEqual(DS.expunge_due_cases(self.r), (1, 0))
        self.assertEqual(self.r.get_case(a)["status"], C.S_EXPUNGED)

        self.at(d(2026, 11, 23))
        b = self.make_case(employee="EMP-NV", violation_date="2026-11-11")
        self.to_met(b)
        o = PS.submit_to_ceo(self.r, ctx(self.r, HR), b, {"decision_draft": "/private/files/qd.pdf"})
        self.r.decisions[o["decision_request"]] = "Approved"
        DS.on_ceo_approved(self.r, b)
        self.r.cases_[b]["decision_date"] = d(2026, 12, 1)
        self.r.cases_[b]["expunge_due"] = d(2027, 3, 1)
        self.r.cases_[a].update(status=C.S_ISSUED, decision_date=d(2026, 11, 30), expunge_due=d(2027, 2, 28))
        self.at(d(2027, 3, 1))
        done, held = DS.expunge_due_cases(self.r)
        self.assertEqual(self.r.get_case(a)["status"], C.S_ISSUED)              # bi giu vi tai pham
        self.assertTrue(self.r.get_case(a)["expunge_hold_note"])
        self.assertGreaterEqual(held, 1)
        DS.expunge_manual(self.r, ctx(self.r, HR), a, "HR xem: khong cung hanh vi")
        self.assertEqual(self.r.get_case(a)["status"], C.S_EXPUNGED)


class TestEmployeeTab(Base):
    def test_profile_tab_permissions(self):
        NS.issue(self.r, ctx(self.r, LM), {"employee": "EMP-NV", "behavior": "x", "content": "y",
                                           "incident_date": "2026-11-20"})
        self.make_case()
        hr_view = V.employee_discipline(self.r, ctx(self.r, HR), "EMP-NV")
        self.assertEqual(len(hr_view["notices"]), 1)
        self.assertEqual(len(hr_view["cases"]), 1)
        nv_view = V.employee_discipline(self.r, ctx(self.r, NV), "EMP-NV")
        self.assertEqual(len(nv_view["cases"]), 0)                              # chua thong bao hop
        with self.assertRaises(KyLuatForbidden):
            V.employee_discipline(self.r, ctx(self.r, OUT), "EMP-NV")


if __name__ == "__main__":
    unittest.main()
