# Copyright (c) 2026, eCentric and contributors
"""Funding-source maths WITHOUT a bench: frappe is stubbed, so this runs in CI and locally.

What it pins down (the rules that make "no drift" true):
  * remaining = committed - (approved + in-flight). Rejected/Cancelled release their amount.
  * A draft (no approval request) has not committed anything yet.
  * Editing a request must not count that request against itself (exclude_request).
  * Partial payments accumulate; the last dong is allowed, one dong more is refused.
  * An unknown source type, a missing document, or an unapproved one all fail CLOSED.
  * The legacy `purchase_request` field and the generic pair stay in step both directions.

  python -m unittest ecentric_workspace.approval_center.tests.standalone.test_funding_source
"""
import sys
import types
import unittest


class _Doc(dict):
    __getattr__ = dict.get

    def __setattr__(self, k, v):
        self[k] = v


class _ThrowErr(Exception):
    pass


def _install_frappe_stub(store):
    """Minimal frappe surface used by funding.py / service.py."""
    fr = types.ModuleType("frappe")

    def throw(msg, *a, **kw):
        raise _ThrowErr(msg)

    def get_all(doctype, filters=None, fields=None, **kw):
        rows = []
        for name, rec in store.get(doctype, {}).items():
            ok = True
            for k, v in (filters or {}).items():
                cur = rec.get(k)
                if isinstance(v, list) and v[0] == "is":
                    ok = ok and bool(cur) if v[1] == "set" else ok and not cur
                elif isinstance(v, list) and v[0] == "in":
                    ok = ok and cur in v[1]
                elif isinstance(v, list) and v[0] == "<":
                    ok = ok and (cur or 0) < v[1]
                else:
                    ok = ok and cur == v
                if not ok:
                    break
            if ok:
                row = _Doc(rec)
                row["name"] = name
                rows.append(row)
        return rows

    def get_value(doctype, name, fieldname=None, as_dict=False, **kw):
        rec = store.get(doctype, {}).get(name)
        if rec is None:
            return None
        if as_dict:
            out = _Doc({f: rec.get(f) for f in (fieldname or [])})
            out["name"] = name
            return out
        if isinstance(fieldname, (list, tuple)):
            return [rec.get(f) for f in fieldname]
        return rec.get(fieldname)

    def exists(doctype, name):
        return name in store.get(doctype, {})

    fr.throw = throw
    fr._ = lambda s: s
    fr._dict = _Doc
    fr.get_all = get_all
    fr.db = types.SimpleNamespace(get_value=get_value, exists=exists, sql=lambda *a, **k: None,
                                  has_column=lambda *a, **k: True)
    fr.session = types.SimpleNamespace(user="nv@ec")
    fr.has_permission = lambda *a, **k: True
    fr.logger = lambda: types.SimpleNamespace(info=lambda *a: None)
    utils = types.ModuleType("frappe.utils")
    utils.getdate = lambda *a, **k: None
    utils.now_datetime = utils.add_to_date = lambda *a, **k: None
    fr.utils = utils
    sys.modules["frappe"] = fr
    sys.modules["frappe.utils"] = utils

    caps = types.ModuleType("caps")
    caps.OPEN_STATUSES = ("Pending", "Information Required")
    sys.modules[
        "ecentric_workspace.approval_center.shared.requests.capabilities"] = caps
    return fr


class FundingTestBase(unittest.TestCase):
    def setUp(self):
        self.store = {
            "EC Purchase Request": {
                "PURR-1": {"payment_amount": 100.0, "request_title": "Mua KOC",
                           "supplier_name": "Cty ABC", "approval_request": "AR-P1",
                           "requested_by": "nv@ec"},
                "PURR-DRAFT": {"payment_amount": 50.0, "request_title": "Chua duyet",
                               "supplier_name": "Cty XYZ", "approval_request": "AR-P2",
                               "requested_by": "nv@ec"},
            },
            "Purchase Order": {
                "PO-1": {"grand_total": 200.0, "title": "PO thang 8", "supplier": "NCC-1",
                         "workflow_state": "Approved", "company": "eCentric",
                         "docstatus": 1, "owner": "nv@ec"},
            },
            "EC Approval Request": {
                "AR-P1": {"approval_status": "Approved"},
                "AR-P2": {"approval_status": "Pending"},
            },
            "EC Payment Request": {},
        }
        _install_frappe_stub(self.store)
        for mod in [m for m in list(sys.modules)
                    if m.startswith("ecentric_workspace.approval_center.features.payment_request")]:
            del sys.modules[mod]
        import importlib
        self.funding = importlib.import_module(
            "ecentric_workspace.approval_center.features.payment_request.application.funding")

    def _payr(self, name, amount, source=("EC Purchase Request", "PURR-1"), status="Approved"):
        ar = "AR-" + name
        if status is None:
            ar = None
        else:
            self.store["EC Approval Request"][ar] = {"approval_status": status}
        self.store["EC Payment Request"][name] = {
            "payment_amount": amount, "approval_request": ar,
            "funding_source_doctype": source[0], "funding_source_name": source[1]}


class TestRemainingMaths(FundingTestBase):
    def test_no_payments_yet(self):
        self.assertEqual(self.funding.remaining_for_source("EC Purchase Request", "PURR-1"), 100.0)

    def test_approved_and_inflight_both_consume(self):
        self._payr("PAY-A", 30, status="Approved")
        self._payr("PAY-B", 20, status="Pending")
        self.assertEqual(self.funding.remaining_for_source("EC Purchase Request", "PURR-1"), 50.0)

    def test_rejected_and_cancelled_release_the_amount(self):
        self._payr("PAY-A", 30, status="Approved")
        self._payr("PAY-R", 60, status="Rejected")
        self._payr("PAY-C", 10, status="Cancelled")
        self.assertEqual(self.funding.remaining_for_source("EC Purchase Request", "PURR-1"), 70.0)

    def test_draft_without_approval_request_does_not_consume(self):
        self._payr("PAY-D", 90, status=None)
        self.assertEqual(self.funding.remaining_for_source("EC Purchase Request", "PURR-1"), 100.0)

    def test_editing_a_request_does_not_count_itself(self):
        self._payr("PAY-A", 40, status="Pending")
        self.assertEqual(
            self.funding.remaining_for_source("EC Purchase Request", "PURR-1",
                                              exclude_request="PAY-A"), 100.0)

    def test_other_sources_do_not_leak(self):
        self._payr("PAY-PO", 150, source=("Purchase Order", "PO-1"), status="Approved")
        self.assertEqual(self.funding.remaining_for_source("EC Purchase Request", "PURR-1"), 100.0)
        self.assertEqual(self.funding.remaining_for_source("Purchase Order", "PO-1"), 50.0)


class TestSubmitGuard(FundingTestBase):
    def _doc(self, amount, dt="EC Purchase Request", name="PURR-1", request_name=None):
        return _Doc({"payment_amount": amount, "funding_source_doctype": dt,
                     "funding_source_name": name, "name": request_name})

    def test_within_remainder_passes(self):
        self.funding.validate_funding(self._doc(100))

    def test_exact_last_dong_passes(self):
        self._payr("PAY-A", 70, status="Approved")
        self.funding.validate_funding(self._doc(30))

    def test_one_over_is_refused_with_numbers(self):
        self._payr("PAY-A", 70, status="Approved")
        with self.assertRaises(_ThrowErr) as ctx:
            self.funding.validate_funding(self._doc(31))
        msg = str(ctx.exception)
        self.assertIn("còn lại", msg)
        self.assertIn("PURR-1", msg)

    def test_two_pending_requests_cannot_both_slip_through(self):
        """The second one sees the first one's in-flight amount, so they cannot overspend."""
        self._payr("PAY-A", 60, status="Pending")
        with self.assertRaises(_ThrowErr):
            self.funding.validate_funding(self._doc(60))

    def test_no_source_is_allowed(self):
        self.funding.validate_funding(_Doc({"payment_amount": 10}))

    def test_half_filled_pair_is_refused(self):
        with self.assertRaises(_ThrowErr):
            self.funding.validate_funding(
                _Doc({"payment_amount": 10, "funding_source_doctype": "EC Purchase Request"}))

    def test_unknown_source_type_fails_closed(self):
        with self.assertRaises(_ThrowErr):
            self.funding.validate_funding(self._doc(10, dt="Sales Order", name="SO-1"))

    def test_missing_document_fails_closed(self):
        with self.assertRaises(_ThrowErr):
            self.funding.validate_funding(self._doc(10, name="PURR-NOPE"))

    def test_unapproved_source_fails_closed(self):
        with self.assertRaises(_ThrowErr) as ctx:
            self.funding.validate_funding(self._doc(10, name="PURR-DRAFT"))
        self.assertIn("chưa được duyệt", str(ctx.exception))

    def test_purchase_order_not_in_approved_state_fails_closed(self):
        self.store["Purchase Order"]["PO-1"]["workflow_state"] = "Pending Manager"
        with self.assertRaises(_ThrowErr):
            self.funding.validate_funding(self._doc(10, dt="Purchase Order", name="PO-1"))


class TestPicker(FundingTestBase):
    def test_lists_only_approved_with_balances(self):
        rows = self.funding.list_sources("EC Purchase Request", user="nv@ec")
        self.assertEqual([r["value"] for r in rows], ["PURR-1"])   # PURR-DRAFT is Pending
        self.assertEqual(rows[0]["remaining"], 100.0)
        self.assertEqual(rows[0]["payee"], "Cty ABC")

    def test_balance_reflects_existing_payments(self):
        self._payr("PAY-A", 25, status="Approved")
        rows = self.funding.list_sources("EC Purchase Request", user="nv@ec")
        self.assertEqual(rows[0]["used"], 25.0)
        self.assertEqual(rows[0]["remaining"], 75.0)

    def test_purchase_order_source_listed(self):
        rows = self.funding.list_sources("Purchase Order", user="nv@ec")
        self.assertEqual([r["value"] for r in rows], ["PO-1"])
        self.assertEqual(rows[0]["payee"], "NCC-1")

    def test_other_users_documents_are_not_listed(self):
        rows = self.funding.list_sources("EC Purchase Request", user="khac@ec")
        self.assertEqual(rows, [])

    def test_supported_sources_is_config_driven(self):
        values = [s["value"] for s in self.funding.supported_sources()]
        self.assertIn("EC Purchase Request", values)
        self.assertIn("Purchase Order", values)


class TestLegacyAlias(FundingTestBase):
    """`purchase_request` (old) and the generic pair (new) must stay in step BOTH ways."""

    def _service(self):
        import importlib
        fs = types.ModuleType("fs")
        fs._ = lambda s: s
        fs.frappe = sys.modules["frappe"]
        fs.getdate = lambda *a, **k: None
        sys.modules["ecentric_workspace.approval_center.shared.finance_support"] = fs
        sys.modules.pop(
            "ecentric_workspace.approval_center.features.payment_request.application.service", None)
        return importlib.import_module(
            "ecentric_workspace.approval_center.features.payment_request.application.service")

    def test_new_pair_mirrors_into_legacy_field(self):
        svc = self._service()
        doc = _Doc({"funding_source_doctype": "EC Purchase Request",
                    "funding_source_name": "PURR-1", "details_and_attachments_correct": "Yes"})
        svc.normalize_payment(doc)
        self.assertEqual(doc.purchase_request, "PURR-1")

    def test_purchase_order_source_clears_legacy_field(self):
        """A PO is not an EC Purchase Request - the legacy link must NOT be filled with it."""
        svc = self._service()
        doc = _Doc({"funding_source_doctype": "Purchase Order", "funding_source_name": "PO-1",
                    "purchase_request": "PURR-1", "details_and_attachments_correct": "Yes"})
        svc.normalize_payment(doc)
        self.assertIsNone(doc.purchase_request)

    def test_legacy_only_record_is_promoted(self):
        svc = self._service()
        doc = _Doc({"purchase_request": "PURR-1", "details_and_attachments_correct": "Yes"})
        svc.normalize_payment(doc)
        self.assertEqual(doc.funding_source_doctype, "EC Purchase Request")
        self.assertEqual(doc.funding_source_name, "PURR-1")


if __name__ == "__main__":
    unittest.main(verbosity=2)
