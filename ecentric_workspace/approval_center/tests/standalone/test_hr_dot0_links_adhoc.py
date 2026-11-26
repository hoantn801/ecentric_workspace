# Copyright (c) 2026, eCentric and contributors
"""Dot 0 HR (23/11/2026): Gan phieu duyet (EC Approval Link + quyen doc phieu rieng tu) va form
Phe duyet dot xuat gui CEO. Chay CODE THAT tren frappe gia (_hr_dot0_world).
    python -m pytest ecentric_workspace/approval_center/tests/standalone/test_hr_dot0_links_adhoc.py
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _hr_dot0_world as W  # noqa: E402

WORLD, FR = W.install()

from ecentric_workspace.approval_center.shared.workflow import transitions as tr  # noqa: E402
from ecentric_workspace.approval_center.shared.workflow import privacy  # noqa: E402
from ecentric_workspace.approval_center.shared.requests import approval_links as al  # noqa: E402
from ecentric_workspace.approval_center.shared.registry import get_definition  # noqa: E402
from ecentric_workspace.approval_center.features.adhoc_approval.application import service as adhoc  # noqa: E402

AR, AP, ACT = "EC Approval Request", "EC Approval Request Approver", "EC Approval Action"
HOST_DT, TGT_DT = "EC Payment Request", "EC Adhoc Approval Request"


def _reset():
    WORLD.reset()
    FR.local = type(FR.local)(message_log=[])
    FR.session.user = "Administrator"
    tr._sla = lambda: tr._SLA_OFF
    WORLD.metas["EC Approval Type"] = W.Meta(["private"])
    WORLD.metas[HOST_DT] = W.Meta(["requested_by", "approval_request", "request_title"])
    WORLD.metas[TGT_DT] = W.Meta(["requested_by", "approval_request", "request_title", "urgency"])
    WORLD.add("EC Approval Type", {"name": "ADHOC_APPROVAL", "private": 1,
                                   "approval_title": "Phê duyệt đột xuất",
                                   "route": "/approvals/adhoc-approval"})
    WORLD.add("EC Approval Type", {"name": "PAYMENT_REQUEST", "private": 0,
                                   "approval_title": "Đề nghị thanh toán"})
    for u in ("req@x", "fin@x", "ceo@x", "other@x"):
        WORLD.user(u)
    # phieu gan (rieng tu) cua req@x, CEO da duyet
    WORLD.add(TGT_DT, {"name": "EC-ADHOC-1", "requested_by": "req@x", "request_title": "Mua PC",
                       "approval_request": "APR-T"})
    WORLD.add(AR, {"name": "APR-T", "approval_type": "ADHOC_APPROVAL", "approval_status": "Approved",
                   "requested_by": "req@x", "reference_doctype": TGT_DT,
                   "reference_name": "EC-ADHOC-1"})
    WORLD.add(AP, {"approval_request": "APR-T", "approver": "ceo@x", "level_no": 1,
                   "status": "Approved"})
    # phieu chu: nhap cua req@x
    WORLD.add(HOST_DT, {"name": "PAYR-1", "requested_by": "req@x", "approval_request": None})


class LinkRules(unittest.TestCase):
    def setUp(self):
        _reset()
        FR.session.user = "req@x"

    def test_private_requires_explicit_choice(self):
        with self.assertRaises(W.Err):
            al.link(HOST_DT, "PAYR-1", "APR-T", share=None)
        out = al.link(HOST_DT, "PAYR-1", "APR-T", share="1")
        self.assertFalse(out["duplicate"])
        self.assertEqual(len(WORLD.rows(al.LINK_DT, active=1)), 1)

    def test_only_target_requester_may_link_private(self):
        WORLD.store[HOST_DT]["PAYR-1"]["requested_by"] = "other@x"
        FR.session.user = "other@x"
        WORLD.add(privacy.GRANT_DT, {"target_request": "APR-T", "user": "other@x", "active": 1})
        with self.assertRaises(W.PermErr):
            al.link(HOST_DT, "PAYR-1", "APR-T", share="1")

    def test_stranger_cannot_link_invisible_target(self):
        WORLD.add(HOST_DT, {"name": "PAYR-2", "requested_by": "other@x"})
        FR.session.user = "other@x"
        with self.assertRaises(W.PermErr):
            al.link(HOST_DT, "PAYR-2", "APR-T", share="0")

    def test_non_holder_cannot_link(self):
        FR.session.user = "fin@x"
        with self.assertRaises(W.PermErr):
            al.link(HOST_DT, "PAYR-1", "APR-T", share="1")

    def test_duplicate_is_idempotent_and_max(self):
        al.link(HOST_DT, "PAYR-1", "APR-T", share="0")
        self.assertTrue(al.link(HOST_DT, "PAYR-1", "APR-T", share="0")["duplicate"])
        orig = al.MAX_LINKS
        al.MAX_LINKS = 1
        try:
            WORLD.add(AR, {"name": "APR-X", "approval_type": "PAYMENT_REQUEST",
                           "approval_status": "Approved", "requested_by": "req@x",
                           "reference_doctype": HOST_DT, "reference_name": "PAYR-9"})
            WORLD.add(HOST_DT, {"name": "PAYR-9", "requested_by": "req@x"})
            with self.assertRaises(W.Err):
                al.link(HOST_DT, "PAYR-1", "APR-X")
        finally:
            al.MAX_LINKS = orig

    def test_label_hides_private_title_from_non_viewer(self):
        al.link(HOST_DT, "PAYR-1", "APR-T", share="0")
        chips = al.links_for_host(HOST_DT, "PAYR-1", "fin@x")
        self.assertIsNone(chips[0]["title"])
        self.assertFalse(chips[0]["can_open"])
        self.assertIsNone(chips[0]["detail_url"])
        mine = al.links_for_host(HOST_DT, "PAYR-1", "req@x")
        self.assertEqual(mine[0]["title"], "Mua PC")

    def test_used_elsewhere_counts_only(self):
        al.link(HOST_DT, "PAYR-1", "APR-T", share="0")
        WORLD.add(HOST_DT, {"name": "PAYR-3", "requested_by": "req@x"})
        al.link(HOST_DT, "PAYR-3", "APR-T", share="0")
        chip = al.links_for_host(HOST_DT, "PAYR-1", "req@x")[0]
        self.assertEqual(chip["used_elsewhere"], 1)


class Grants(unittest.TestCase):
    def setUp(self):
        _reset()
        FR.session.user = "req@x"
        al.link(HOST_DT, "PAYR-1", "APR-T", share="1")
        # phieu chu duoc gui: snapshot co fin@x la nguoi duyet
        WORLD.add(AR, {"name": "APR-H", "approval_type": "PAYMENT_REQUEST",
                       "approval_status": "Pending", "requested_by": "req@x",
                       "reference_doctype": HOST_DT, "reference_name": "PAYR-1", "current_level": 1})
        WORLD.store[HOST_DT]["PAYR-1"]["approval_request"] = "APR-H"
        WORLD.add(AP, {"approval_request": "APR-H", "approver": "fin@x", "level_no": 1,
                       "status": "Pending", "source": "Configured User"})
        # pre@x da co DocShare TU TRUOC (vd la nguoi duyet cua chinh phieu gan) - thu hoi khong
        # duoc xoa no.
        WORLD.user("pre@x")
        WORLD.add(AP, {"approval_request": "APR-H", "approver": "pre@x", "level_no": 1,
                       "status": "Pending", "source": "Configured User"})
        WORLD.add("DocShare", {"share_doctype": TGT_DT, "share_name": "EC-ADHOC-1", "user": "pre@x"})
        al.on_host_snapshot(W.D(WORLD.store[AR]["APR-H"]))

    def test_host_approver_gets_read_and_share(self):
        from ecentric_workspace.approval_center.shared.workflow.permissions import can_view_request
        self.assertTrue(can_view_request("APR-T", "fin@x"))
        self.assertIn((TGT_DT, "EC-ADHOC-1", "fin@x"), WORLD.shares)
        self.assertFalse(can_view_request("APR-T", "other@x"))

    def test_unlink_revokes_only_created_share(self):
        # req@x da co DocShare tu truoc? Khong - ta tao. fin@x: tao boi grant.
        WORLD.add("DocShare", {"share_doctype": TGT_DT, "share_name": "EC-ADHOC-1",
                               "user": "keep@x"})
        link = WORLD.rows(al.LINK_DT, active=1)[0]["name"]
        FR.session.user = "req@x"
        WORLD.store[AR]["APR-H"]["approval_status"] = "Information Required"
        al.unlink(link)
        from ecentric_workspace.approval_center.shared.workflow.permissions import can_view_request
        self.assertFalse(can_view_request("APR-T", "fin@x"))
        users = [r["user"] for r in WORLD.rows("DocShare")]
        self.assertNotIn("fin@x", users)
        self.assertIn("keep@x", users)
        self.assertIn("pre@x", users)
        self.assertFalse(can_view_request("APR-T", "pre@x"))   # grant thu hoi, DocShare giu
        self.assertTrue(any(a.get("action") == "Approval Unlinked" for a in WORLD.rows(ACT)))

    def test_access_by_grant_logged(self):
        privacy.note_access("fin@x", "APR-T", "ADHOC_APPROVAL", "req@x")
        self.assertEqual(WORLD.rows(privacy.ACCESS_DT)[0]["via"], "Gắn phiếu")


class SubmitGuard(unittest.TestCase):
    def setUp(self):
        _reset()
        FR.session.user = "req@x"

    def test_rejected_target_blocks_until_reason(self):
        al.link(HOST_DT, "PAYR-1", "APR-T", share="0")
        WORLD.store[AR]["APR-T"]["approval_status"] = "Rejected"
        with self.assertRaises(W.Err) as cm:
            al.assert_host_submittable(HOST_DT, "PAYR-1")
        # 26/11: mo dau "Vui long" de bo loc loi cua cac trang form giu nguyen thong diep (khong thay bang
        # "Khong the gui lai yeu cau..."), va KHONG chua chu "quyen" (mapErr doi thanh "khong con quyen").
        self.assertTrue(str(cm.exception).startswith("Vui lòng"), str(cm.exception))
        self.assertNotIn("quyền", str(cm.exception))
        link = WORLD.rows(al.LINK_DT, active=1)[0]["name"]
        al.set_override_reason(link, "Đã trao đổi trực tiếp với CEO")
        al.assert_host_submittable(HOST_DT, "PAYR-1")   # khong nem


class Adhoc(unittest.TestCase):
    def setUp(self):
        _reset()

    def test_definition_is_private_with_urgency(self):
        d = get_definition("ADHOC_APPROVAL")
        self.assertTrue(d.private)
        self.assertIn("urgency", d.editable_fields)
        self.assertIn("ADHOC_APPROVAL", privacy._code_private_types())

    def test_urgent_needs_reason_and_sla_override(self):
        doc = W.D({"request_title": "T", "content": "C", "urgency": "Gấp", "urgency_reason": ""})
        with self.assertRaises(W.Err):
            adhoc.validate_business(doc)
        doc["urgency_reason"] = "brand chốt"
        adhoc.validate_business(doc)
        self.assertEqual(adhoc.sla_overrides_for(doc), {1: adhoc.URGENT_SLA_POLICY})
        self.assertIsNone(adhoc.sla_overrides_for(W.D({"urgency": "Bình thường"})))

    def test_past_desired_date_rejected(self):
        with self.assertRaises(W.Err):
            adhoc.validate_business(W.D({"request_title": "T", "content": "C",
                                         "urgency": "Bình thường", "desired_by": "2026-01-01"}))

    def test_cc_validated_and_requester_dropped(self):
        WORLD.user("off@x", enabled=0)
        doc = W.D({"request_title": "T", "content": "C", "urgency": "Bình thường",
                   "requested_by": "req@x", "cc_users": "fin@x, req@x\nfin@x"})
        adhoc.validate_business(doc)
        self.assertEqual(doc["cc_users"], "fin@x")
        for bad in ("off@x", "khong.co@x", "Administrator"):
            with self.assertRaises(W.Err):
                adhoc.validate_business(W.D({"request_title": "T", "content": "C", "urgency": "Bình thường",
                                             "requested_by": "req@x", "cc_users": "fin@x, " + bad}))
        many = ", ".join("u%d@x" % i for i in range(16))
        for i in range(16):
            WORLD.user("u%d@x" % i)
        with self.assertRaises(W.Err):
            adhoc.validate_business(W.D({"request_title": "T", "content": "C", "urgency": "Bình thường",
                                         "requested_by": "req@x", "cc_users": many}))

    def test_cc_definition_editable(self):
        self.assertIn("cc_users", get_definition("ADHOC_APPROVAL").editable_fields)

    def test_engine_urgency_convention_matches_form(self):
        from ecentric_workspace.approval_center.features.adhoc_approval.domain.definition import URGENCY_LEVELS
        self.assertIn(adhoc.URGENT, tr.URGENT_VALUES)
        self.assertIn(adhoc.URGENT, URGENCY_LEVELS)


class WatcherRedaction(unittest.TestCase):
    def setUp(self):
        _reset()
        WORLD.user("ceo@x")
        WORLD.add(AR, {"name": "APR-1", "requested_by": "req@x"})
        WORLD.add(privacy.WATCHER_DT, {"approval_request": "APR-1", "watcher": "ceo@x"})

    def test_hidden_for_watcher_only(self):
        d = W.D({"watcher_hidden_fields": ("compensation",)})
        biz = {"requested_by": "req@x", "compensation": 100}
        privacy.redact_for_watcher(biz, d, "ceo@x", "APR-1")
        self.assertIsNone(biz["compensation"])
        biz2 = {"requested_by": "req@x", "compensation": 100}
        privacy.redact_for_watcher(biz2, d, "req@x", "APR-1")
        self.assertEqual(biz2["compensation"], 100)
        WORLD.add(AP, {"approval_request": "APR-1", "approver": "ceo@x"})
        biz3 = {"requested_by": "req@x", "compensation": 100}
        privacy.redact_for_watcher(biz3, d, "ceo@x", "APR-1")
        self.assertEqual(biz3["compensation"], 100)


if __name__ == "__main__":
    unittest.main()


class SearchWithoutHost(unittest.TestCase):
    """26/11/2026: form TAO MOI chua co ma -> search_linkable khong host. Chi de xuat phieu NGUOI
    XEM duoc (lop chan thu hai can_view_target, khong tin ham liet ke); phieu rieng tu chi nguoi gui
    phieu do moi `can_attach`. Gan that van qua link() sau khi luu."""
    def setUp(self):
        _reset()
        from ecentric_workspace.approval_center.reporting import scope as sc, queries as qq
        self._orig = (sc.resolve_scope, qq.fetch_requests_page)
        self.calls = []
        sc.resolve_scope = lambda user: {"user": user}

        def fake_page(scope, filters, start, page_len, search=None):
            self.calls.append((scope, dict(filters), search))
            # liet ke "ro ri" ca phieu nguoi xem khong duoc mo -> search phai tu loc
            return [{"name": "APR-T"}, {"name": "APR-P"}, {"name": "APR-MISSING"}]
        qq.fetch_requests_page = fake_page
        WORLD.add(HOST_DT, {"name": "PAYR-P", "requested_by": "other@x", "request_title": "Mua giấy"})
        WORLD.add(AR, {"name": "APR-P", "approval_type": "PAYMENT_REQUEST", "approval_status": "Approved",
                       "requested_by": "other@x", "reference_doctype": HOST_DT,
                       "reference_name": "PAYR-P"})

    def tearDown(self):
        from ecentric_workspace.approval_center.reporting import scope as sc, queries as qq
        sc.resolve_scope, qq.fetch_requests_page = self._orig

    def _codes(self, out):
        return [r["code"] for r in out["rows"]]

    def test_requester_sees_own_private_and_can_attach(self):
        FR.session.user = "req@x"
        out = al.search(None, None, q=" PC ", box="mine")
        self.assertIn("EC-ADHOC-1", self._codes(out))
        row = [r for r in out["rows"] if r["code"] == "EC-ADHOC-1"][0]
        self.assertTrue(row["private"] and row["can_attach"] and row["needs_share_choice"])
        self.assertFalse(row["already_linked"])
        self.assertEqual(self.calls[-1][0], {"user": "req@x"})
        self.assertEqual(self.calls[-1][1], {"box": "sent", "_me": "req@x"})
        self.assertEqual(self.calls[-1][2], "PC")

    def test_stranger_never_gets_invisible_private(self):
        FR.session.user = "other@x"
        codes = self._codes(al.search(None, None))
        self.assertNotIn("EC-ADHOC-1", codes)          # liet ke ro ri van bi chan
        self.assertIn("PAYR-P", codes)                 # phieu cua chinh minh

    def test_viewer_not_requester_cannot_attach_private(self):
        FR.session.user = "fin@x"
        WORLD.add(privacy.GRANT_DT, {"target_request": "APR-T", "user": "fin@x", "active": 1})
        rows = al.search(None, None)["rows"]
        row = [r for r in rows if r["code"] == "EC-ADHOC-1"]
        self.assertTrue(row and row[0]["can_open"])
        self.assertFalse(row[0]["can_attach"])

    def test_guest_and_half_host_rejected(self):
        FR.session.user = "Guest"
        with self.assertRaises(W.PermErr):
            al.search(None, None)
        FR.session.user = "req@x"
        with self.assertRaises(W.Err):
            al.search(HOST_DT, None)
        with self.assertRaises(W.Err):
            al.search(None, "PAYR-1")

    def test_host_mode_still_requires_holder(self):
        FR.session.user = "fin@x"
        with self.assertRaises(W.PermErr):
            al.search(HOST_DT, "PAYR-1")
        FR.session.user = "req@x"
        al.link(HOST_DT, "PAYR-1", "APR-T", share="0")
        rows = al.search(HOST_DT, "PAYR-1")["rows"]
        self.assertTrue([r for r in rows if r["code"] == "EC-ADHOC-1"][0]["already_linked"])

    def test_endpoint_accepts_no_host_and_takes_no_user(self):
        import inspect
        src = open(os.path.join(os.path.dirname(__file__), "..", "..", "reporting", "actions.py"),
                   encoding="utf-8").read()
        i = src.index("def search_linkable(")
        head = src[src.rindex("@frappe.whitelist", 0, i):src.index(")", i) + 1]
        self.assertIn('methods=["GET"]', head)
        self.assertIn("host_doctype=None, host_name=None", head)
        self.assertNotIn("user", head.split("def search_linkable(")[1])
        self.assertIsNone(inspect.signature(al.search).parameters["host_doctype"].default)
