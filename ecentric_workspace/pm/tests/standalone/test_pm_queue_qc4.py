# -*- coding: utf-8 -*-
"""QC round 4 (15/11/2026, nghiệm thu "một ngày dùng") - Việc cần làm backend.

  D1 "Xin dời hạn" khép vòng trên một màn:
     * người nhận: dòng tab=me mang deadline_ask {due} khi mình đã xin dời hạn việc đó (Pending);
     * người giao: tab=give `proposals` có thêm yêu cầu xin dời hạn gửi MÌNH (kind Deadline,
       recipient = mình) với counter.kind = "deadline" (trả lời bằng pm_inbox.answer_deadline),
       hạn cũ = hạn hiện tại của việc, giữ giờ; không vào counts.
  D2 Giới hạn 500 do server nói (`limit`), frontend không ghi cứng.
  D3 Tin Teams 8h30: 3 việc đầu có "Làm trước:" + ghi chú hạn, tên dài bị cắt; người chỉ có việc chờ nhận
     thấy ĐÚNG các việc chờ nhận (không phải việc tuần sau không liên quan).
Fake 'now' = Fri 2026-10-16 10:00 (_pm_fake)."""
import os
import sys
import types
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _pm_fake as F  # noqa: E402


class Base(unittest.TestCase):
    def setUp(self):
        self.fk = F.install()
        F.seed_users(self.fk)
        self.q = self.fk.load("ecentric_workspace.pm.api.queue")

    def me(self, u=F.ALICE):
        self.fk.set_user(u)

    def dl(self, name, task, by, to, end, status="Pending", msg="Chờ hàng về"):
        self.fk.add("PM Assignment Request", name=name, task=task, recipient=to, requested_by=by,
                    status=status, kind="Deadline", proposed_end=end + " 00:00:00", message=msg)

    def hook_digest(self, sent):
        m = types.ModuleType("ecentric_workspace.notification_center.events")
        m.publish_notification_event = lambda et, u, title, msg, **k: sent.append((u, title, msg))
        sys.modules["ecentric_workspace.notification_center.events"] = m
        nc = sys.modules.get("ecentric_workspace.notification_center") or types.ModuleType("ecentric_workspace.notification_center")
        nc.events = m
        sys.modules["ecentric_workspace.notification_center"] = nc


class TestDeadlineAskLoop(Base):
    def seed(self):
        F.task(self.fk, "T1", owner=F.GIVER, assign=[F.ALICE], end="2026-10-16", pm_end_time="15:00:00", subject="Bao cao")
        F.task(self.fk, "T2", owner=F.GIVER, assign=[F.ALICE], end="2026-10-17")
        self.dl("DL1", "T1", F.ALICE, F.GIVER, "2026-10-20")
        self.dl("DL0", "T2", F.ALICE, F.GIVER, "2026-10-25", status="Rejected")   # answered -> not pending

    def test_assignee_row_carries_deadline_ask(self):
        self.seed()
        self.me()
        rows = {r["name"]: r for r in self.q.list()["rows"]}
        self.assertEqual(rows["T1"]["deadline_ask"], {"due": "2026-10-20"})
        self.assertIsNone(rows["T2"]["deadline_ask"])

    def test_giver_sees_it_in_proposals_kind_deadline(self):
        self.seed()
        self.me(F.GIVER)
        out = self.q.list(tab="give")
        props = [p for p in out["proposals"] if p["counter"]["kind"] == "deadline"]
        self.assertEqual([p["name"] for p in props], ["T1"])
        c = props[0]["counter"]
        self.assertEqual((c["request"], c["recipient"], c["recipient_name"], c["due"], c["time"], c["old_due"], c["reason"]),
                         ("DL1", F.ALICE, "Alice", "2026-10-20", "15:00", "2026-10-16", "Chờ hàng về"))
        self.assertEqual(props[0]["rank"], 0)
        # the task itself stays in the list once (counts unchanged by the proposal)
        self.assertEqual(sorted(r["name"] for r in out["rows"]), ["T1", "T2"])
        self.assertEqual(sum(out["counts"].values()), 2)

    def test_not_for_someone_else(self):
        self.seed()
        self.me(F.BOB)
        self.assertEqual(self.q.list(tab="give")["proposals"], [])

    def test_counter_proposals_keep_kind_counter(self):
        F.task(self.fk, "REQ", owner=F.GIVER, assign=[], state="Backlog")
        self.fk.add("PM Assignment Request", name="AR1", task="REQ", recipient=F.ALICE, requested_by=F.GIVER,
                    status="Reschedule Proposed", kind="Assignment", counter_end="2026-10-22 17:00:00",
                    proposed_end="2026-10-18 18:00:00", response_reason="Ban")
        self.me(F.GIVER)
        p = self.q.list(tab="give")["proposals"]
        self.assertEqual([(x["name"], x["counter"]["kind"]) for x in p], [("REQ", "counter")])


class TestLimit(Base):
    def test_limit_comes_from_server(self):
        self.me()
        self.assertEqual(self.q.list()["limit"], 500)
        self.assertEqual(self.q.list(tab="give")["limit"], 500)


class TestDigestText(Base):
    def test_top3_lead_in_due_hint_and_cut(self):
        self.fk.module.get_conf = lambda: {"ec_pm_morning_digest": 1}
        F.task(self.fk, "A1", owner=F.GIVER, assign=[F.ALICE], end="2026-10-14", priority="Urgent",
               subject="Gui bao gia cho khach hang Unilever ban cuoi cung co chu ky giam doc va dong dau do")
        F.task(self.fk, "A2", owner=F.GIVER, assign=[F.ALICE], end="2026-10-16", pm_end_time="15:00:00", subject="Chot GMV")
        F.task(self.fk, "A3", owner=F.GIVER, assign=[F.ALICE], end="2026-10-17", subject="Ke hoach")
        sent = []
        self.hook_digest(sent)
        self.q.morning_digest()
        u, title, msg = sent[0]
        self.assertEqual(title, "Hôm nay có 2 việc cần xử lý")
        self.assertIn("1 việc quá hạn, 1 việc hạn hôm nay. Làm trước: 1. ", msg)
        self.assertIn("… (trễ 2 ngày)", msg)
        self.assertIn("2. Chot GMV (hạn 15:00)", msg)
        self.assertIn("3. Ke hoach (hạn mai)", msg)
        self.assertNotIn("dong dau do", msg)

    def test_only_asks_lists_the_asks_not_other_tasks(self):
        self.fk.module.get_conf = lambda: {"ec_pm_morning_digest": 1}
        F.task(self.fk, "REQ", owner=F.GIVER, assign=[], state="Backlog", subject="Setup kho")
        self.fk.add("PM Assignment Request", name="AR1", task="REQ", recipient=F.BOB, requested_by=F.GIVER,
                    status="Pending", kind="Assignment")
        F.task(self.fk, "LATER", owner=F.GIVER, assign=[F.BOB], end="2026-10-30", subject="Viec tuan sau")
        sent = []
        self.hook_digest(sent)
        self.q.morning_digest()
        u, title, msg = sent[0]
        self.assertEqual((u, title), (F.BOB, "1 việc chờ bạn nhận"))
        self.assertTrue(msg.startswith("Setup kho (Gia Ver giao). Mở Việc cần làm để nhận việc"), msg)
        self.assertNotIn("Viec tuan sau", msg)

    def test_digest_text_pure_more_than_three_asks(self):
        asks = [{"subject": "Viec %d" % i, "from_name": "An"} for i in range(5)]
        head, msg = self.q._digest_text([], asks, "2026-10-16")
        self.assertEqual(head, "5 việc chờ bạn nhận")
        self.assertIn("Viec 2 (An giao) · và 2 việc khác.", msg)


if __name__ == "__main__":
    unittest.main()
