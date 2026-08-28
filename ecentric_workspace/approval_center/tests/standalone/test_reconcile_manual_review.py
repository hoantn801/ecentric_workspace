# Copyright (c) 2026, eCentric and contributors
"""Getting a stuck leg moving again must never involve re-sending a signing command.

2026-08-28. A leg was moved to Manual Review because the provider had accepted the signing
job and then done nothing for twenty minutes. Hours later the signer opened the provider's
own portal and signed by hand. The signature is real and on the real document - but the ERP
had stopped polling, so the approval sat blocked.

The tempting fix is a "retry" button. It is the wrong one: the signing call is not
idempotent, and re-sending it on a document that is already signed produces a SECOND
signature. Reconciliation therefore reads, verifies and completes - it cannot create a
signature, and the worst it can do is refuse.
"""
import io
import os
import re
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))


def _src(*parts):
    tried = []
    root = _HERE
    for _i in range(8):
        path = os.path.join(root, *parts)
        tried.append(path)
        if os.path.exists(path):
            return io.open(path, encoding="utf-8").read()
        parent = os.path.dirname(root)
        if parent == root:
            break
        root = parent
    raise AssertionError("khong tim thay %s. Da thu:\n  %s" % (parts[-1], "\n  ".join(tried)))


def _fn(src, name):
    m = re.search(r"\ndef %s\(.*?\n(.*?)(?=\n@frappe\.whitelist|\ndef |\Z)" % name, src, re.S)
    assert m, "khong tim thay %s" % name
    return m.group(1)


def _code(body):
    body = re.sub(r'"""[\s\S]*?"""', "", body)
    return re.sub(r"(?m)^\s*#.*$", "", body)


class TestItNeverResends(unittest.TestCase):
    def setUp(self):
        self.body = _code(_fn(_src("platform", "esign", "service.py"),
                              "reconcile_manual_review"))

    def test_no_signing_call_anywhere_in_it(self):
        for banned in ("approve_and_sign", "bulk_process", "transition_with_recipients",
                       "create_document", "submit_", "_client."):
            self.assertNotIn(banned, self.body,
                             "doi soat khong duoc gui bat cu lenh ghi nao: %s" % banned)

    def test_it_only_reads_provider_state(self):
        self.assertIn("adapter.poll_status(doc_id)", self.body)

    def test_it_verifies_before_completing(self):
        pos_verify = self.body.index("verify_signed_result")
        pos_complete = self.body.index("verify_and_complete")
        self.assertLess(pos_verify, pos_complete,
                        "phai xac minh TRUOC khi hoan tat, khong phai nguoc lai")

    def test_a_failed_verification_changes_nothing(self):
        seg = self.body[self.body.index("if not vr.ok:"):]
        self.assertIn("return", seg.split("\n")[1],
                        "khong xac minh duoc thi phai dung lai ngay")
        head = self.body[:self.body.index("if not vr.ok:")]
        self.assertNotIn("set_dsr_status", head,
                         "khong duoc doi trang thai truoc khi biet ket qua xac minh")

    def test_every_attempt_leaves_a_trace(self):
        self.assertIn('events.emit("PollTick"', self.body)
        self.assertIn('"source": "manual_reconcile"', self.body,
                      "phai phan biet duoc voi vong poll tu dong")


class TestScope(unittest.TestCase):
    def test_endpoint_is_system_manager_only(self):
        body = _fn(_src("platform", "esign", "api.py"), "reconcile_signature_request")
        self.assertIn("perms.assert_system_manager()", body)

    def test_endpoint_is_a_post(self):
        src = _src("platform", "esign", "api.py")
        self.assertRegex(src, r'@frappe\.whitelist\(methods=\["POST"\]\)\s*\ndef reconcile_signature_request')

    def test_only_legs_actually_parked_in_manual_review(self):
        for src, fn in ((_src("platform", "esign", "api.py"), "reconcile_signature_request"),
                        (_src("platform", "esign", "service.py"), "reconcile_manual_review")):
            body = _code(_fn(src, fn))
            self.assertIn('!= "Manual Review"', body,
                          "%s phai tu choi chan ky khong o Manual Review" % fn)

    def test_the_state_machine_allows_the_edge(self):
        state = _src("platform", "esign", "state.py")
        m = re.search(r'"Manual Review": \(([^)]*)\)', state)
        self.assertIsNotNone(m)
        self.assertIn('"Signed"', m.group(1),
                      "khong khai canh thi set_dsr_status se bi tu choi luc chay")

    def test_terminal_states_still_have_no_exit(self):
        state = _src("platform", "esign", "state.py")
        for term in ("Approval Completed", "Permanent Failure", "Cancelled"):
            m = re.search(r'"%s": \(([^)]*)\)' % term, state)
            self.assertIsNotNone(m, term)
            self.assertEqual(m.group(1).strip(), "",
                             "%s khong duoc co loi ra - doi soat khong duoc ha cap trang thai"
                             % term)


if __name__ == "__main__":
    unittest.main()
