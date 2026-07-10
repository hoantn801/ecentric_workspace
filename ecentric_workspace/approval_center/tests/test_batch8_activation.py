# Copyright (c) 2026, eCentric and contributors
"""Batch 8 activation tests: publish methods must support a real publish mode
(not dry-run-only), with robust boolean-flag parsing.

  bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_batch8_activation

Covers, per Batch-8 form (Purchase / Payment / Budget Setting / Affiliate Bonus):
  a. no args               -> dry_run, no DB write
  b. commit / publish flag -> writes card_status Active + route
  c. blockers              -> prevent publish (process not Active)
  d. boolean parsing       -> dry_run in {0,"0",false,"false"} (and commit=1/"1"/true)
                              trigger a real publish; ambiguous/empty stays dry.
"""
import frappe
from frappe.tests.utils import FrappeTestCase

from ecentric_workspace.approval_center.purchase_request import (
    setup as pr_setup, activation as pr_act, page_sync as pr_page)
from ecentric_workspace.approval_center.payment_request import (
    setup as pay_setup, activation as pay_act, page_sync as pay_page)
from ecentric_workspace.approval_center.budget_setting import (
    setup as bg_setup, activation as bg_act, page_sync as bg_page)
from ecentric_workspace.approval_center.affiliate_bonus import (
    setup as af_setup, activation as af_act, page_sync as af_page)


def _user(email):
    if not frappe.db.exists("User", email):
        u = frappe.get_doc({"doctype": "User", "email": email, "first_name": email.split("@")[0],
                            "user_type": "System User", "enabled": 1, "send_welcome_email": 0})
        u.flags.no_welcome_mail = True
        u.insert(ignore_permissions=True)
        u.add_roles("Employee")
    return email


def _u(*names):
    return [_user("zzb8_" + n + "@example.com") for n in names]


class _Batch8ActivationMixin:
    """Subclasses set PROCESS, TYPE, ROUTE and implement do_setup()/enable()/publish()
    delegating to the module's activation service."""

    PROCESS = None
    TYPE = None
    ROUTE = None  # stored value, includes leading slash

    def do_setup(self):
        raise NotImplementedError

    def enable(self, **kw):
        raise NotImplementedError

    def publish(self, **kw):
        raise NotImplementedError

    def _reset(self):
        if frappe.db.exists("EC Approval Process", self.PROCESS):
            frappe.db.set_value("EC Approval Process", self.PROCESS, "status", "Draft")
        if frappe.db.exists("EC Approval Type", self.TYPE):
            frappe.db.set_value("EC Approval Type", self.TYPE, {"card_status": "Coming Soon", "route": ""})

    def _reset_card_only(self):
        # keep the process Active (set by enable), reset only the catalog card
        frappe.db.set_value("EC Approval Type", self.TYPE, {"card_status": "Coming Soon", "route": ""})

    def setUp(self):
        self.do_setup()
        self._reset()

    def tearDown(self):
        self._reset()

    def _card_status(self):
        return frappe.db.get_value("EC Approval Type", self.TYPE, "card_status")

    def _route(self):
        return frappe.db.get_value("EC Approval Type", self.TYPE, "route")

    # a. no args -> dry_run, no DB write
    def test_publish_no_args_is_dry_run_no_write(self):
        self.enable(dry_run=0, apply=1)  # process Active so blockers don't mask the dry-run
        rep = self.publish()  # no args at all
        self.assertEqual(rep["mode"], "dry_run")
        self.assertTrue(rep["result"].startswith("DRY_RUN_OK"))
        self.assertNotEqual(self._card_status(), "Active")
        self.assertEqual(self._route(), "")

    # b. publish via commit flag -> writes card_status Active + route
    def test_publish_commit_flag_writes_active_and_route(self):
        self.enable(dry_run=0, apply=1)
        rep = self.publish(commit=1)
        self.assertEqual(rep["mode"], "commit")
        self.assertTrue(rep["result"].startswith("PUBLISHED"))
        self.assertEqual(self._card_status(), "Active")
        self.assertEqual(self._route(), self.ROUTE)
        self.assertEqual(frappe.db.get_value("EC Approval Type", self.TYPE, "category"), "FINANCE_BUDGET")

    # b'. publish via dry_run=0 -> also a real publish (the reported bug)
    def test_publish_dry_run_zero_writes_active(self):
        self.enable(dry_run=0, apply=1)
        rep = self.publish(dry_run=0)
        self.assertEqual(rep["mode"], "commit")
        self.assertTrue(rep["result"].startswith("PUBLISHED"))
        self.assertEqual(self._card_status(), "Active")
        self.assertEqual(self._route(), self.ROUTE)

    # c. blockers prevent publish (process not Active)
    def test_publish_blocked_when_process_not_active(self):
        rep = self.publish(commit=1)  # process still Draft
        self.assertTrue(rep["result"].startswith("BLOCKED"))
        self.assertNotEqual(self._card_status(), "Active")
        self.assertEqual(self._route(), "")

    # d. boolean parsing: string/int false-tokens must NOT be treated as truthy dry_run
    def test_boolean_parsing_false_tokens_publish(self):
        self.enable(dry_run=0, apply=1)
        for token in [0, "0", "false", "False", "no", "off"]:
            self._reset_card_only()
            rep = self.publish(dry_run=token)
            self.assertEqual(rep["mode"], "commit", "dry_run=%r should publish" % (token,))
            self.assertEqual(self._card_status(), "Active", "dry_run=%r should publish" % (token,))

    # d'. commit truthy tokens (incl. 'true') publish and never crash on int() of a word
    def test_boolean_parsing_commit_truthy(self):
        self.enable(dry_run=0, apply=1)
        for token in [1, "1", "true", "True", "yes"]:
            self._reset_card_only()
            rep = self.publish(commit=token)
            self.assertEqual(rep["mode"], "commit", "commit=%r should publish" % (token,))
            self.assertEqual(self._card_status(), "Active", "commit=%r should publish" % (token,))

    # d''. ambiguous / empty dry_run stays safe (dry), no write
    def test_boolean_parsing_ambiguous_stays_dry(self):
        self.enable(dry_run=0, apply=1)
        for token in ["", "  ", 1, "1", "true"]:
            self._reset_card_only()
            rep = self.publish(dry_run=token)
            self.assertEqual(rep["mode"], "dry_run", "dry_run=%r should stay dry" % (token,))
            self.assertNotEqual(self._card_status(), "Active")


class TestPurchaseRequestActivation(_Batch8ActivationMixin, FrappeTestCase):
    PROCESS = "PURCHASE_REQUEST-V1"
    TYPE = "PURCHASE_REQUEST"
    ROUTE = "/approvals/purchase-request"

    def do_setup(self):
        pr_setup.setup_purchase_request_v1(finance=_u("fin"), hof=_u("hof"), ceo=_u("ceo"), dry_run=0, apply=1)
        pr_page.sync()

    def enable(self, **kw):
        return pr_act.enable_purchase_request_uat(**kw)

    def publish(self, **kw):
        return pr_act.publish_purchase_request_after_uat(**kw)


class TestPaymentRequestActivation(_Batch8ActivationMixin, FrappeTestCase):
    PROCESS = "PAYMENT_REQUEST-V1"
    TYPE = "PAYMENT_REQUEST"
    ROUTE = "/approvals/payment-request"

    def do_setup(self):
        pay_setup.setup_payment_request_v1(finance=_u("fin"), hof=_u("hof"), ceo=_u("ceo"), dry_run=0, apply=1)
        pay_page.sync()

    def enable(self, **kw):
        return pay_act.enable_payment_request_uat(**kw)

    def publish(self, **kw):
        return pay_act.publish_payment_request_after_uat(**kw)


class TestBudgetSettingActivation(_Batch8ActivationMixin, FrappeTestCase):
    PROCESS = "BUDGET_SETTING-V1"
    TYPE = "BUDGET_SETTING"
    ROUTE = "/approvals/budget-setting"

    def do_setup(self):
        bg_setup.setup_budget_setting_v1(hof=_u("hof"), ceo=_u("ceo"), dry_run=0, apply=1)
        bg_page.sync()

    def enable(self, **kw):
        return bg_act.enable_budget_setting_uat(**kw)

    def publish(self, **kw):
        return bg_act.publish_budget_setting_after_uat(**kw)


class TestAffiliateBonusActivation(_Batch8ActivationMixin, FrappeTestCase):
    PROCESS = "AFFILIATE_BONUS_REQUEST-V1"
    TYPE = "AFFILIATE_BONUS_REQUEST"
    ROUTE = "/approvals/affiliate-bonus-request"

    def do_setup(self):
        af_setup.setup_affiliate_bonus_v1(vinh=_u("vinh"), ceo=_u("ceo"), dry_run=0, apply=1)
        af_page.sync()

    def enable(self, **kw):
        return af_act.enable_affiliate_bonus_uat(**kw)

    def publish(self, **kw):
        return af_act.publish_affiliate_bonus_after_uat(**kw)
