# Copyright (c) 2026, eCentric and contributors
"""B3.1 read-API tests: permission scope + capability flags.

  bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_b3_api
"""
import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.approval_center.api import ai_topup as api

PFX = "ZZB3_"


def _user(email, roles=("Employee",), enabled=1, utype="System User"):
    if not frappe.db.exists("User", email):
        u = frappe.get_doc({"doctype": "User", "email": email, "first_name": email.split("@")[0],
                            "user_type": utype, "enabled": enabled, "send_welcome_email": 0})
        u.flags.no_welcome_mail = True
        u.insert(ignore_permissions=True)
        if utype == "System User":
            u.add_roles(*roles)
    return email


def _tool():
    if not frappe.db.exists("EC AI Tool", "ZZB3 Tool"):
        frappe.get_doc({"doctype": "EC AI Tool", "tool_name": "ZZB3 Tool"}).insert(ignore_permissions=True)
    return "ZZB3 Tool"


def _draft(owner):
    return frappe.get_doc({"doctype": "EC AI Topup Request", "account_mode": "New Account",
                           "ai_tool": _tool(), "proposed_account_email": "d@example.com",
                           "proposed_account_manager": _user("zzb3_pm@example.com"),
                           "requested_by": owner}).insert(ignore_permissions=True)


class TestB3ReadAPI(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.addClassCleanup(lambda: frappe.set_user("Administrator"))

    def tearDown(self):
        frappe.set_user("Administrator")

    def test_form_options(self):
        opt = api.get_form_options()
        self.assertEqual(opt["account_modes"], ["Existing Account", "New Account"])
        self.assertIn("Top-up", opt["request_types"])
        self.assertIn("Monthly", opt["billing_cycles"])

    def test_active_user_search_hides_admin_for_non_sm(self):
        _user("zzb3_plain@example.com")
        frappe.set_user("zzb3_plain@example.com")
        rows = api.search_active_users(query="Admin")
        self.assertFalse(any(r["value"] == "Administrator" for r in rows))

    def test_my_requests_scoped_to_owner(self):
        a = _user("zzb3_a@example.com"); b = _user("zzb3_b@example.com")
        da = _draft(a)
        frappe.set_user(b)
        names = [r["name"] for r in api.list_my_requests()["rows"]]
        self.assertNotIn(da.name, names)
        frappe.set_user(a)
        self.assertIn(da.name, [r["name"] for r in api.list_my_requests()["rows"]])

    def test_detail_scope_denies_unrelated(self):
        a = _user("zzb3_a@example.com"); b = _user("zzb3_b@example.com")
        da = _draft(a)
        frappe.set_user(b)
        with self.assertRaises(frappe.exceptions.PermissionError):
            api.get_request_detail(da.name)

    def test_capabilities_for_draft_owner(self):
        a = _user("zzb3_a@example.com")
        da = _draft(a)
        frappe.set_user(a)
        cap = api.get_request_detail(da.name)["capabilities"]
        self.assertTrue(cap["can_submit"] and cap["can_edit"])
        self.assertFalse(cap["can_approve"])

    def test_fulfillment_queue_requires_eligibility(self):
        p = _user("zzb3_plain2@example.com")
        frappe.set_user(p)
        with self.assertRaises(frappe.exceptions.PermissionError):
            api.list_fulfillment_queue(section="unclaimed")

    def test_bootstrap_tabs(self):
        a = _user("zzb3_a@example.com")
        frappe.set_user(a)
        boot = api.get_bootstrap()
        self.assertTrue(boot["tabs"]["create"] and boot["tabs"]["my_requests"])
        self.assertIn("manager_resolvable", boot["context"])


class TestB3WriteAndSafeguards(FrappeTestCase):
    def tearDown(self):
        frappe.set_user("Administrator")

    def test_save_draft_owner_and_capabilities(self):
        a = _user("zzb3_wa@example.com")
        frappe.set_user(a)
        res = api.save_draft(payload=frappe.as_json({
            "account_mode": "New Account", "ai_tool": _tool(),
            "proposed_account_email": "n@example.com",
            "proposed_account_manager": _user("zzb3_wpm@example.com")}))
        self.assertTrue(res["name"])
        self.assertTrue(res["capabilities"]["can_submit"] and res["capabilities"]["can_edit"])
        self.assertEqual(frappe.db.get_value(api.BIZ, res["name"], "requested_by"), a)

    def test_save_draft_denies_other_owner(self):
        a = _user("zzb3_wa@example.com"); b = _user("zzb3_wb@example.com")
        doc = _draft(a)
        frappe.set_user(b)
        with self.assertRaises(frappe.exceptions.PermissionError):
            api.save_draft(name=doc.name, payload="{}")

    def test_page_size_capped(self):
        self.assertEqual(api.MAX_PAGE, 50)
        a = _user("zzb3_wa@example.com"); frappe.set_user(a)
        res = api.list_my_requests(page_length=1000)   # must not error; capped internally
        self.assertLessEqual(len(res["rows"]), 50)

    def test_active_user_minimal_shape(self):
        frappe.set_user("Administrator")
        rows = api.search_active_users(query="a")
        if rows:
            self.assertEqual(set(rows[0].keys()), {"value", "email", "label"})


def _active_proc(l1_user, l2_users):
    for p in frappe.get_all("EC Approval Process",
                            filters={"approval_type": "AI_TOPUP", "status": "Active"}, pluck="name"):
        frappe.db.set_value("EC Approval Process", p, "status", "Retired")
    code = "ZZB3A_" + frappe.generate_hash(length=5)
    p = frappe.get_doc({"doctype": "EC Approval Process", "process_code": code, "title": code,
                        "approval_type": "AI_TOPUP", "status": "Draft"}).insert(ignore_permissions=True)
    l1 = frappe.get_doc({"doctype": "EC Approval Level", "approval_process": p.name, "level_no": 1,
                         "level_name": "Manager", "approval_mode": "Any One"})
    l1.append("participants", {"participant_purpose": "Approver", "source_type": "User", "user": l1_user})
    l1.insert(ignore_permissions=True)
    l2 = frappe.get_doc({"doctype": "EC Approval Level", "approval_process": p.name, "level_no": 2,
                         "level_name": "Finance Review", "approval_mode": "Any One"})
    for u in l2_users:
        l2.append("participants", {"participant_purpose": "Approver", "source_type": "User", "user": u})
    l2.insert(ignore_permissions=True)
    p.status = "Active"; p.save(ignore_permissions=True)
    return p.name


def _submit_as(requester, l1_user, l2_users):
    doc = frappe.get_doc({"doctype": "EC AI Topup Request", "account_mode": "New Account",
                          "ai_tool": _tool(), "proposed_account_email": "s@example.com",
                          "proposed_account_manager": _user("zzb3_spm@example.com"),
                          "requested_by": requester}).insert(ignore_permissions=True)
    frappe.set_user(requester)
    api.submit_request(doc.name)
    frappe.set_user("Administrator")
    return doc.name


class TestB3Actions(FrappeTestCase):
    def tearDown(self):
        frappe.set_user("Administrator")

    def test_my_approvals_scope_and_actions(self):
        a = _user("zzb3_apr@example.com"); other = _user("zzb3_oth@example.com")
        req = _user("zzb3_req@example.com")
        _active_proc(a, ["zzb3_fin@example.com"])
        name = _submit_as(req, a, ["zzb3_fin@example.com"])
        frappe.set_user(a)
        pend = api.list_my_approvals(section="pending")["rows"]
        self.assertTrue(any(r["name"] == name for r in pend))
        frappe.set_user(other)
        self.assertFalse(any(r["name"] == name for r in api.list_my_approvals(section="pending")["rows"]))

    def test_reject_reason_required_and_unrelated_denied(self):
        a = _user("zzb3_apr@example.com"); other = _user("zzb3_oth@example.com"); req = _user("zzb3_req@example.com")
        _active_proc(a, ["zzb3_fin@example.com"])
        name = _submit_as(req, a, ["zzb3_fin@example.com"])
        frappe.set_user(a)
        with self.assertRaises(frappe.exceptions.ValidationError):
            api.reject(name, comment="")             # reason required (engine)
        with self.assertRaises(frappe.exceptions.ValidationError):
            api.request_information(name, comment="")  # comment required (engine)
        frappe.set_user(other)
        with self.assertRaises(frappe.exceptions.ValidationError):
            api.approve(name)                          # not a pending approver

    def test_approve_then_duplicate_blocked(self):
        a = _user("zzb3_apr@example.com"); req = _user("zzb3_req@example.com")
        _active_proc(a, [a])   # a is approver at both levels (Any One)
        name = _submit_as(req, a, [a])
        frappe.set_user(a)
        api.approve(name)                              # L1 -> advances to L2
        api.approve(name)                              # L2 -> Approved
        with self.assertRaises(frappe.exceptions.ValidationError):
            api.approve(name)                          # terminal -> blocked

    def test_cancel_draft_and_capability(self):
        req = _user("zzb3_req@example.com"); other = _user("zzb3_oth@example.com")
        doc = _draft(req)
        frappe.set_user(other)
        with self.assertRaises(frappe.exceptions.PermissionError):
            api.cancel(doc.name, reason="x")
        frappe.set_user(req)
        res = api.cancel(doc.name, reason="không cần nữa")
        self.assertTrue(res.get("deleted"))
        self.assertFalse(frappe.db.exists(api.BIZ, doc.name))


def _proc_with_fulfiller(approver, fulfiller):
    for p in frappe.get_all("EC Approval Process",
                            filters={"approval_type": "AI_TOPUP", "status": "Active"}, pluck="name"):
        frappe.db.set_value("EC Approval Process", p, "status", "Retired")
    code = "ZZB3F_" + frappe.generate_hash(length=5)
    p = frappe.get_doc({"doctype": "EC Approval Process", "process_code": code, "title": code,
                        "approval_type": "AI_TOPUP", "status": "Draft"})
    p.append("participants", {"participant_purpose": "Fulfiller", "source_type": "User", "user": fulfiller})
    p.insert(ignore_permissions=True)
    for no, name, adj in [(1, "Manager", 0), (2, "Finance Review", 1)]:
        lv = frappe.get_doc({"doctype": "EC Approval Level", "approval_process": p.name, "level_no": no,
                             "level_name": name, "approval_mode": "Any One", "allows_amount_adjustment": adj})
        lv.append("participants", {"participant_purpose": "Approver", "source_type": "User", "user": approver})
        lv.insert(ignore_permissions=True)
    p.status = "Active"; p.save(ignore_permissions=True)
    return p.name


class TestB3Fulfillment(FrappeTestCase):
    def tearDown(self):
        frappe.set_user("Administrator")

    def test_can_adjust_amount_is_flag_based(self):
        a = _user("zzb3_fa@example.com"); f = _user("zzb3_ff@example.com"); req = _user("zzb3_fr@example.com")
        proc = _proc_with_fulfiller(a, f)
        name = _submit_as(req, a, [a])
        frappe.set_user(a)
        api.approve(name)   # L1 -> L2 (Finance, flag=1)
        det = api.get_request_detail(name)
        self.assertTrue(det["capabilities"]["can_adjust_approved_amount"])
        # rename the Finance level -> capability still true (flag, not name)
        arname = frappe.db.get_value(api.BIZ, name, "approval_request")
        rl = frappe.get_all("EC Approval Request Level",
                            filters={"approval_request": arname, "level_no": 2}, pluck="name")[0]
        frappe.db.set_value("EC Approval Request Level", rl, "level_name", "Kiểm tra ngân sách")
        self.assertTrue(api.get_request_detail(name)["capabilities"]["can_adjust_approved_amount"])

    def test_claim_and_complete_flow(self):
        a = _user("zzb3_fa@example.com"); f = _user("zzb3_ff@example.com"); other = _user("zzb3_fo@example.com")
        req = _user("zzb3_fr@example.com")
        proc = _proc_with_fulfiller(a, f)
        name = _submit_as(req, a, [a])
        frappe.set_user(a); api.approve(name); api.approve(name)   # -> Approved -> fulfillment Assigned
        self.assertEqual(frappe.db.get_value(api.BIZ, name, "fulfillment_status"), "Assigned")
        # non-fulfiller cannot claim
        frappe.set_user(other)
        with self.assertRaises(Exception):
            api.claim_fulfillment(name)
        # fulfiller claims
        frappe.set_user(f)
        api.claim_fulfillment(name)
        self.assertEqual(frappe.db.get_value(api.BIZ, name, "fulfillment_owner"), f)
        # complete without payment proof -> blocked
        with self.assertRaises(frappe.exceptions.ValidationError):
            api.complete_fulfillment(name, payload=frappe.as_json({"actual_amount": 10, "actual_currency": "VND",
                "topup_datetime": frappe.utils.now_datetime(), "transaction_reference": "T",
                "invoice_status": "No Invoice Issued", "no_invoice_reason": "r",
                "confirmed_account_manager": f, "actual_account_email": "x@example.com"}))
        # non-owner cannot complete
        frappe.set_user(other)
        with self.assertRaises(frappe.exceptions.PermissionError):
            api.complete_fulfillment(name, payload="{}")


class TestRequestTitle(FrappeTestCase):
    """UAT polish 2: request_title save/require/list/detail + New Account backend guard."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.addClassCleanup(lambda: frappe.set_user("Administrator"))

    def tearDown(self):
        frappe.set_user("Administrator")

    def test_save_draft_persists_title_and_shows_in_list_and_detail(self):
        u = _user("zzb3_title@example.com")
        frappe.set_user(u)
        res = api.save_draft(payload=frappe.as_json({
            "account_mode": "New Account", "ai_tool": _tool(),
            "proposed_account_email": "t@example.com",
            "proposed_account_manager": _user("zzb3_tpm@example.com"),
            "request_title": "Renewal - ZZB3 Tool - t@example.com"}))
        name = res["name"]
        self.assertEqual(frappe.db.get_value(api.BIZ, name, "request_title"),
                         "Renewal - ZZB3 Tool - t@example.com")
        rows = api.list_my_requests()["rows"]
        self.assertTrue(any(r.get("request_title") == "Renewal - ZZB3 Tool - t@example.com" for r in rows))
        self.assertEqual(api.get_request_detail(name)["business"]["request_title"],
                         "Renewal - ZZB3 Tool - t@example.com")

    def test_submit_requires_title(self):
        u = _user("zzb3_title2@example.com")
        frappe.set_user(u)
        res = api.save_draft(payload=frappe.as_json({
            "account_mode": "New Account", "ai_tool": _tool(),
            "proposed_account_email": "t2@example.com",
            "proposed_account_manager": _user("zzb3_tpm2@example.com")}))   # no request_title
        with self.assertRaises(frappe.exceptions.ValidationError):
            api.submit_request(res["name"])

    def test_new_account_missing_fields_rejected_backend(self):
        u = _user("zzb3_title3@example.com")
        frappe.set_user(u)
        with self.assertRaises(frappe.exceptions.ValidationError):
            api.save_draft(payload=frappe.as_json({
                "account_mode": "New Account", "request_title": "X"}))     # missing ai_tool/proposed_*


def _ai_account():
    email = "zzb3acc@example.com"
    existing = frappe.get_all("EC AI Account", filters={"account_email": email}, pluck="name")
    if existing:
        return existing[0]
    return frappe.get_doc({"doctype": "EC AI Account", "ai_tool": _tool(), "account_email": email,
                           "account_manager": _user("zzb3_accm@example.com"), "status": "Active"}
                          ).insert(ignore_permissions=True).name


def _submit_fin(requester, approver, amount=100):
    """New Account request with a requested_amount, submitted; L1/L2(Finance) approver = approver."""
    doc = frappe.get_doc({"doctype": "EC AI Topup Request", "account_mode": "New Account",
                          "ai_tool": _tool(), "proposed_account_email": "fc@example.com",
                          "proposed_account_manager": _user("zzb3_fcpm@example.com"),
                          "request_title": "FC - ZZB3 Tool - fc@example.com",
                          "requested_amount": amount, "requested_by": requester}).insert(ignore_permissions=True)
    frappe.set_user(requester)
    api.submit_request(doc.name)
    frappe.set_user("Administrator")
    return doc.name


class TestFinanceCommentValidation(FrappeTestCase):
    """Finance-comment mandatory rule must apply ONLY on a Finance amount adjustment,
    never on plain draft/save/submit (UAT: submit was wrongly blocked)."""

    def tearDown(self):
        frappe.set_user("Administrator")

    def test_new_account_save_draft_no_finance_comment(self):
        req = _user("zzb3_fcr@example.com")
        frappe.set_user(req)
        res = api.save_draft(payload=frappe.as_json({
            "account_mode": "New Account", "ai_tool": _tool(),
            "proposed_account_email": "fc1@example.com",
            "proposed_account_manager": _user("zzb3_fcpm@example.com"),
            "request_title": "T", "requested_amount": 100}))
        self.assertTrue(res["name"])   # no finance-comment error

    def test_new_account_submit_no_finance_comment(self):
        req = _user("zzb3_fcr2@example.com"); a = _user("zzb3_fca2@example.com")
        _proc_with_fulfiller(a, a)
        name = _submit_fin(req, a, 100)                       # must not raise
        self.assertEqual(float(frappe.db.get_value(api.BIZ, name, "approved_amount")), 100.0)  # controlled default

    def test_existing_account_submit_no_finance_comment(self):
        req = _user("zzb3_fcr3@example.com"); a = _user("zzb3_fca3@example.com")
        _proc_with_fulfiller(a, a); acc = _ai_account()
        frappe.set_user(req)
        res = api.save_draft(payload=frappe.as_json({
            "account_mode": "Existing Account", "ai_account": acc,
            "request_title": "T3", "requested_amount": 50}))
        api.submit_request(res["name"])                      # must not raise
        frappe.set_user("Administrator")

    def test_finance_equal_amount_no_comment_ok(self):
        req = _user("zzb3_fcr4@example.com"); a = _user("zzb3_fca4@example.com")
        _proc_with_fulfiller(a, a); name = _submit_fin(req, a, 100)
        frappe.set_user(a)
        api.approve(name)                                    # L1
        api.approve(name, approved_amount=100)               # L2 Finance, equal -> no comment required
        frappe.set_user("Administrator")
        ar = frappe.db.get_value(api.BIZ, name, "approval_request")
        self.assertEqual(frappe.db.get_value("EC Approval Request", ar, "approval_status"), "Approved")

    def test_finance_diff_amount_requires_comment(self):
        req = _user("zzb3_fcr5@example.com"); a = _user("zzb3_fca5@example.com")
        _proc_with_fulfiller(a, a); name = _submit_fin(req, a, 100)
        frappe.set_user(a)
        api.approve(name)                                    # L1
        with self.assertRaises(frappe.exceptions.ValidationError):
            api.approve(name, approved_amount=80)            # diff, no comment -> blocked in service

    def test_finance_diff_amount_with_comment_ok(self):
        req = _user("zzb3_fcr6@example.com"); a = _user("zzb3_fca6@example.com")
        _proc_with_fulfiller(a, a); name = _submit_fin(req, a, 100)
        frappe.set_user(a)
        api.approve(name)                                    # L1
        api.approve(name, approved_amount=80, comment="giảm theo ngân sách")
        frappe.set_user("Administrator")
        self.assertEqual(float(frappe.db.get_value(api.BIZ, name, "approved_amount")), 80.0)

    def test_non_finance_save_no_finance_validation(self):
        req = _user("zzb3_fcr7@example.com")
        d = frappe.get_doc({"doctype": "EC AI Topup Request", "account_mode": "New Account",
                            "ai_tool": _tool(), "proposed_account_email": "fc7@example.com",
                            "proposed_account_manager": _user("zzb3_fcpm7@example.com"),
                            "request_title": "T7", "requested_amount": 100, "approved_amount": 80,
                            "requested_by": req}).insert(ignore_permissions=True)   # differing amounts, no comment
        d.reload(); d.operation_note = "x"; d.save(ignore_permissions=True)          # plain re-save must not raise
        self.assertTrue(d.name)


class TestProcessPreview(FrappeTestCase):
    """Draft stepper preview: get_request_detail exposes configured levels only pre-submit."""

    def tearDown(self):
        frappe.set_user("Administrator")

    def test_draft_returns_process_preview_and_no_runtime_levels(self):
        a = _user("zzb3_pp_a@example.com"); req = _user("zzb3_pp_r@example.com")
        _proc_with_fulfiller(a, a)                 # active process with 2 configured levels
        doc = _draft(req)                          # draft, not submitted
        frappe.set_user(req)
        det = api.get_request_detail(doc.name)
        self.assertGreaterEqual(len(det["process_preview"]), 2)
        self.assertEqual(det["levels"], [])        # no runtime snapshot yet
        self.assertIsNone(det["approval"]["name"])

    def test_submitted_has_runtime_levels_and_empty_preview(self):
        a = _user("zzb3_pp_a2@example.com"); req = _user("zzb3_pp_r2@example.com")
        _proc_with_fulfiller(a, a)
        name = _submit_fin(req, a, 100)
        det = api.get_request_detail(name)
        self.assertEqual(det["process_preview"], [])
        self.assertGreaterEqual(len(det["levels"]), 2)
        self.assertTrue(det["approval"]["name"])


class TestSubmitDraftAPI(FrappeTestCase):
    """submit_request as the draft-detail primary action: owner-only, blocks non-Draft, clean payload."""

    def tearDown(self):
        frappe.set_user("Administrator")

    def test_owner_can_submit_own_draft(self):
        a = _user("zzb3_sd_a@example.com"); req = _user("zzb3_sd_r@example.com")
        _proc_with_fulfiller(a, a)
        frappe.set_user(req)
        res = api.save_draft(payload=frappe.as_json({
            "account_mode": "New Account", "ai_tool": _tool(),
            "proposed_account_email": "sd@example.com",
            "proposed_account_manager": _user("zzb3_sd_pm@example.com"),
            "request_title": "SD", "requested_amount": 100}))
        out = api.submit_request(res["name"])
        self.assertTrue(out.get("submitted"))
        self.assertTrue(out["detail"]["approval"]["name"])          # runtime request created
        frappe.set_user("Administrator")
        self.assertTrue(frappe.db.get_value(api.BIZ, res["name"], "approval_request"))

    def test_non_owner_cannot_submit_others_draft(self):
        a = _user("zzb3_sd_a2@example.com"); req = _user("zzb3_sd_r2@example.com"); other = _user("zzb3_sd_o2@example.com")
        _proc_with_fulfiller(a, a)
        doc = frappe.get_doc({"doctype": "EC AI Topup Request", "account_mode": "New Account",
                              "ai_tool": _tool(), "proposed_account_email": "sd2@example.com",
                              "proposed_account_manager": _user("zzb3_sd_pm2@example.com"),
                              "request_title": "SD2", "requested_by": req}).insert(ignore_permissions=True)
        frappe.set_user(other)
        with self.assertRaises(frappe.exceptions.ValidationError):
            api.submit_request(doc.name)

    def test_submitting_non_draft_is_blocked(self):
        a = _user("zzb3_sd_a3@example.com"); req = _user("zzb3_sd_r3@example.com")
        _proc_with_fulfiller(a, a)
        name = _submit_fin(req, a, 100)                              # already submitted
        frappe.set_user(req)
        with self.assertRaises(frappe.exceptions.ValidationError):
            api.submit_request(name)
        frappe.set_user("Administrator")

    def test_can_submit_capability_true_for_draft_owner(self):
        req = _user("zzb3_sd_r4@example.com")
        doc = _draft(req)
        frappe.set_user(req)
        cap = api.get_request_detail(doc.name)["capabilities"]
        self.assertTrue(cap["can_submit"])
        self.assertTrue(cap["can_cancel"])


class TestTimelineFields(FrappeTestCase):
    """get_request_detail timeline must query only real EC Approval Action columns (regression:
    it selected non-existent level_no/level_name/related_user -> SQL 1054 after submit)."""

    def tearDown(self):
        frappe.set_user("Administrator")

    def test_detail_after_submit_returns_timeline_no_sql_error(self):
        a = _user("zzb3_tl_a@example.com"); req = _user("zzb3_tl_r@example.com")
        _proc_with_fulfiller(a, a)
        name = _submit_fin(req, a, 100)                 # submit logs a Submitted action
        det = api.get_request_detail(name)              # would raise 1054 before the fix
        self.assertIsInstance(det["timeline"], list)
        self.assertTrue(any(t["action"] == "Submitted" for t in det["timeline"]))
        for t in det["timeline"]:
            self.assertIn("action", t); self.assertIn("actor", t); self.assertIn("action_time", t)

    def test_submit_request_returns_submitted_and_detail(self):
        a = _user("zzb3_tl_a2@example.com"); req = _user("zzb3_tl_r2@example.com")
        _proc_with_fulfiller(a, a)
        frappe.set_user(req)
        res = api.save_draft(payload=frappe.as_json({
            "account_mode": "New Account", "ai_tool": _tool(),
            "proposed_account_email": "tl@example.com",
            "proposed_account_manager": _user("zzb3_tl_pm@example.com"),
            "request_title": "TL", "requested_amount": 100}))
        out = api.submit_request(res["name"])
        self.assertTrue(out.get("submitted"))
        self.assertIsInstance(out["detail"]["timeline"], list)
        frappe.set_user("Administrator")

    def test_timeline_empty_for_draft(self):
        req = _user("zzb3_tl_r3@example.com")
        doc = _draft(req)                               # draft, no runtime request
        frappe.set_user(req)
        det = api.get_request_detail(doc.name)
        self.assertEqual(det["timeline"], [])           # empty, no SQL error
        frappe.set_user("Administrator")

    def test_timeline_after_approve_has_actions(self):
        a = _user("zzb3_tl_a4@example.com"); req = _user("zzb3_tl_r4@example.com")
        _proc_with_fulfiller(a, a); name = _submit_fin(req, a, 100)
        frappe.set_user(a); api.approve(name)           # logs an Approved action
        det = api.get_request_detail(name)
        frappe.set_user("Administrator")
        self.assertTrue(any(t["action"] in ("Approved", "Submitted") for t in det["timeline"]))


def _proc_3levels(approver, fulfiller):
    for p in frappe.get_all("EC Approval Process",
                            filters={"approval_type": "AI_TOPUP", "status": "Active"}, pluck="name"):
        frappe.db.set_value("EC Approval Process", p, "status", "Retired")
    code = "ZZB3T_" + frappe.generate_hash(length=5)
    p = frappe.get_doc({"doctype": "EC Approval Process", "process_code": code, "title": code,
                        "approval_type": "AI_TOPUP", "status": "Draft"})
    p.append("participants", {"participant_purpose": "Fulfiller", "source_type": "User", "user": fulfiller})
    p.insert(ignore_permissions=True)
    for no, name, adj in [(1, "Manager", 0), (2, "Operation Review", 0), (3, "Finance Review", 1)]:
        lv = frappe.get_doc({"doctype": "EC Approval Level", "approval_process": p.name, "level_no": no,
                             "level_name": name, "approval_mode": "Any One", "allows_amount_adjustment": adj})
        lv.append("participants", {"participant_purpose": "Approver", "source_type": "User", "user": approver})
        lv.insert(ignore_permissions=True)
    p.status = "Active"; p.save(ignore_permissions=True)
    return p.name


class TestAdminOverride(FrappeTestCase):
    """System Manager 'approve current level' override - service-layer, no impersonation."""

    def tearDown(self):
        frappe.set_user("Administrator")

    def _ar(self, name):
        return frappe.db.get_value(api.BIZ, name, "approval_request")

    def test_capability_sm_true_ordinary_false(self):
        sm = _user("zzb3_ao_sm@example.com", roles=("Employee", "System Manager"))
        a = _user("zzb3_ao_a@example.com"); req = _user("zzb3_ao_r@example.com")
        _proc_3levels(a, a); name = _submit_fin(req, a, 100)
        frappe.set_user(sm)
        self.assertTrue(api.get_request_detail(name)["capabilities"]["can_admin_approve_current_level"])
        frappe.set_user(a)
        self.assertFalse(api.get_request_detail(name)["capabilities"]["can_admin_approve_current_level"])

    def test_non_sm_cannot_override(self):
        a = _user("zzb3_ao_a2@example.com"); req = _user("zzb3_ao_r2@example.com"); other = _user("zzb3_ao_o2@example.com")
        _proc_3levels(a, a); name = _submit_fin(req, a, 100)
        frappe.set_user(other)
        with self.assertRaises(frappe.exceptions.PermissionError):
            api.admin_approve_current_level(name, reason="x")

    def test_override_requires_reason(self):
        sm = _user("zzb3_ao_sm3@example.com", roles=("Employee", "System Manager"))
        a = _user("zzb3_ao_a3@example.com"); req = _user("zzb3_ao_r3@example.com")
        _proc_3levels(a, a); name = _submit_fin(req, a, 100)
        frappe.set_user(sm)
        with self.assertRaises(frappe.exceptions.ValidationError):
            api.admin_approve_current_level(name, reason="   ")

    def test_override_blocked_for_draft(self):
        sm = _user("zzb3_ao_sm4@example.com", roles=("Employee", "System Manager"))
        req = _user("zzb3_ao_r4@example.com")
        doc = _draft(req)
        frappe.set_user(sm)
        with self.assertRaises(frappe.exceptions.ValidationError):
            api.admin_approve_current_level(doc.name, reason="x")

    def test_override_blocked_for_information_required(self):
        sm = _user("zzb3_ao_sm5@example.com", roles=("Employee", "System Manager"))
        a = _user("zzb3_ao_a5@example.com"); req = _user("zzb3_ao_r5@example.com")
        _proc_3levels(a, a); name = _submit_fin(req, a, 100)
        frappe.set_user(a); api.request_information(name, comment="need info")
        frappe.set_user(sm)
        self.assertFalse(api.get_request_detail(name)["capabilities"]["can_admin_approve_current_level"])
        with self.assertRaises(frappe.exceptions.ValidationError):
            api.admin_approve_current_level(name, reason="x")

    def test_override_full_chain_to_fulfillment_and_audit(self):
        sm = _user("zzb3_ao_sm6@example.com", roles=("Employee", "System Manager"))
        a = _user("zzb3_ao_a6@example.com"); f = _user("zzb3_ao_f6@example.com"); req = _user("zzb3_ao_r6@example.com")
        _proc_3levels(a, f); name = _submit_fin(req, a, 100); ar = self._ar(name)
        frappe.set_user(sm)
        api.admin_approve_current_level(name, reason="r1")          # L1 Manager -> L2 Operation
        self.assertEqual(frappe.db.get_value("EC Approval Request", ar, "current_level"), 2)
        api.admin_approve_current_level(name, reason="r2")          # L2 Operation -> L3 Finance
        self.assertEqual(frappe.db.get_value("EC Approval Request", ar, "current_level"), 3)
        api.admin_approve_current_level(name, reason="r3")          # L3 Finance -> final approval
        frappe.set_user("Administrator")
        self.assertEqual(frappe.db.get_value("EC Approval Request", ar, "approval_status"), "Approved")
        self.assertEqual(frappe.db.get_value(api.BIZ, name, "fulfillment_status"), "Assigned")
        # pending approver on L1 was Skipped (not impersonated / not left actionable)
        self.assertEqual(frappe.db.get_value("EC Approval Request Approver",
                         {"approval_request": ar, "level_no": 1, "approver": a}, "status"), "Skipped")
        # audit: an Approved action by the SM with an Admin override reason
        acts = frappe.get_all("EC Approval Action",
                              filters={"approval_request": ar, "action": "Approved", "actor": sm},
                              fields=["comment"])
        self.assertTrue(any("Admin override" in (x.comment or "") for x in acts))

    def test_override_blocked_after_completed(self):
        sm = _user("zzb3_ao_sm7@example.com", roles=("Employee", "System Manager"))
        a = _user("zzb3_ao_a7@example.com"); f = _user("zzb3_ao_f7@example.com"); req = _user("zzb3_ao_r7@example.com")
        _proc_3levels(a, f); name = _submit_fin(req, a, 100)
        frappe.set_user(sm)
        api.admin_approve_current_level(name, reason="1")
        api.admin_approve_current_level(name, reason="2")
        api.admin_approve_current_level(name, reason="3")          # -> Approved (terminal)
        with self.assertRaises(frappe.exceptions.ValidationError):
            api.admin_approve_current_level(name, reason="again")  # stale/duplicate -> blocked


class TestListStepData(FrappeTestCase):
    """Lists expose dynamic step data (total_levels + level names) for 'Bước X/N' labels."""

    def tearDown(self):
        frappe.set_user("Administrator")

    def test_my_requests_includes_total_levels_and_current_name(self):
        a = _user("zzb3_ls_a@example.com"); req = _user("zzb3_ls_r@example.com")
        _proc_3levels(a, a); name = _submit_fin(req, a, 100)     # submitted, pending L1
        frappe.set_user(req)
        row = [r for r in api.list_my_requests()["rows"] if r["name"] == name][0]
        self.assertEqual(row["total_levels"], 3)
        self.assertTrue(row["current_level_name"])

    def test_my_requests_draft_uses_active_process_level_count(self):
        a = _user("zzb3_ls_a2@example.com"); req = _user("zzb3_ls_r2@example.com")
        _proc_3levels(a, a)
        doc = _draft(req)                                        # draft (no runtime)
        frappe.set_user(req)
        row = [r for r in api.list_my_requests()["rows"] if r["name"] == doc.name][0]
        self.assertEqual(row["total_levels"], 3)

    def test_my_approvals_includes_level_name(self):
        a = _user("zzb3_ls_a3@example.com"); req = _user("zzb3_ls_r3@example.com")
        _proc_3levels(a, a); name = _submit_fin(req, a, 100)
        frappe.set_user(a)
        row = [r for r in api.list_my_approvals(section="pending")["rows"] if r["name"] == name][0]
        self.assertEqual(row["total_levels"], 3)
        self.assertTrue(row["level_name"])


def _proc_todo(m, o1, o2, fin, f):
    for p in frappe.get_all("EC Approval Process",
                            filters={"approval_type": "AI_TOPUP", "status": "Active"}, pluck="name"):
        frappe.db.set_value("EC Approval Process", p, "status", "Retired")
    code = "ZZB3TD_" + frappe.generate_hash(length=5)
    p = frappe.get_doc({"doctype": "EC Approval Process", "process_code": code, "title": code,
                        "approval_type": "AI_TOPUP", "status": "Draft"})
    p.append("participants", {"participant_purpose": "Fulfiller", "source_type": "User", "user": f})
    p.insert(ignore_permissions=True)
    for no, nm, apprs in [(1, "Manager", [m]), (2, "Operation Review", [o1, o2]), (3, "Finance Review", [fin])]:
        lv = frappe.get_doc({"doctype": "EC Approval Level", "approval_process": p.name, "level_no": no,
                             "level_name": nm, "approval_mode": "Any One"})
        for u in apprs:
            lv.append("participants", {"participant_purpose": "Approver", "source_type": "User", "user": u})
        lv.insert(ignore_permissions=True)
    p.status = "Active"; p.save(ignore_permissions=True)
    return p.name


class TestAssignmentToDos(FrappeTestCase):
    """ToDos follow the pending approver(s) and close as the request advances (idempotent)."""

    def tearDown(self):
        frappe.set_user("Administrator")

    def _open(self, name, user=None):
        flt = {"reference_type": api.BIZ, "reference_name": name, "status": "Open"}
        if user:
            flt["allocated_to"] = user
        return frappe.get_all("ToDo", filters=flt, pluck="allocated_to")

    def test_todo_follows_levels_then_fulfillment(self):
        m = _user("zzb3_td_m@example.com"); o1 = _user("zzb3_td_o1@example.com"); o2 = _user("zzb3_td_o2@example.com")
        fin = _user("zzb3_td_fin@example.com"); f = _user("zzb3_td_f@example.com"); req = _user("zzb3_td_r@example.com")
        _proc_todo(m, o1, o2, fin, f)
        name = _submit_fin(req, m, 100)
        # submit -> Manager has exactly one open ToDo (no duplicate), Operation not yet
        self.assertEqual([u for u in self._open(name) if u == m], [m])
        self.assertNotIn(o1, self._open(name))
        # Manager approves -> Manager ToDo closed, Operation ToDos opened
        frappe.set_user(m); api.approve(name); frappe.set_user("Administrator")
        self.assertNotIn(m, self._open(name))
        self.assertIn(o1, self._open(name)); self.assertIn(o2, self._open(name))
        # Operation Any One (o1) approves -> o1+o2(skipped) closed, Finance opened
        frappe.set_user(o1); api.approve(name); frappe.set_user("Administrator")
        self.assertNotIn(o1, self._open(name)); self.assertNotIn(o2, self._open(name))
        self.assertIn(fin, self._open(name))
        # Finance approves -> Finance closed, fulfiller assigned
        frappe.set_user(fin); api.approve(name); frappe.set_user("Administrator")
        self.assertNotIn(fin, self._open(name))
        self.assertIn(f, self._open(name))
        # claim -> owner kept
        frappe.set_user(f); api.claim_fulfillment(name); frappe.set_user("Administrator")
        self.assertIn(f, self._open(name))
        # complete -> all open ToDos closed
        frappe.set_user(f)
        api.complete_fulfillment(name, payload=frappe.as_json({
            "actual_amount": 100, "actual_currency": "VND", "topup_datetime": frappe.utils.now_datetime(),
            "transaction_reference": "T", "payment_proof": "/f/p", "invoice_status": "No Invoice Issued",
            "no_invoice_reason": "no invoice", "confirmed_account_manager": f, "actual_account_email": "x@example.com"}))
        frappe.set_user("Administrator")
        self.assertEqual(self._open(name), [])

    def test_no_duplicate_todos(self):
        m = _user("zzb3_td_m2@example.com"); o1 = _user("zzb3_td_o12@example.com"); o2 = _user("zzb3_td_o22@example.com")
        fin = _user("zzb3_td_fin2@example.com"); f = _user("zzb3_td_f2@example.com"); req = _user("zzb3_td_r2@example.com")
        _proc_todo(m, o1, o2, fin, f)
        name = _submit_fin(req, m, 100)
        # re-reading detail / re-activating must not duplicate the Manager ToDo
        api.get_request_detail(name); api.get_request_detail(name)
        self.assertEqual(len(self._open(name, user=m)), 1)
