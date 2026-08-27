# Copyright (c) 2026, eCentric and contributors
"""Sending a request back for more documents must not leave the signing package frozen.

Observed live on 2026-08-27 (EC-PAYR-2026-00027):

    14:07  lien.vu     "Yêu cầu bổ sung"  Pending -> Information Required
    17:54  hoan.tran   "Gửi lại"

`resubmit()` reset the approval levels and left the package alone. Its file list had been
frozen at lock time, so a document attached after 14:07 never entered it - and every later
level would sign the OLD set while believing they had seen the supplemented one. Silent,
and only discoverable in an audit.

`package.create_revision()` had been written for this and its own docstring says "used by
resubmit cycles". Nothing called it. These checks make sure that stays wired, and that the
failure mode when it breaks is loud rather than silent.
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
    m = re.search(r"\ndef %s\(.*?\n(.*?)(?=\ndef |\Z)" % name, src, re.S)
    assert m, "khong tim thay ham %s" % name
    return m.group(1)


def _code_only(body):
    body = re.sub(r'"""[\s\S]*?"""', "", body)
    return re.sub(r"(?m)^\s*#.*$", "", body)


class TestResubmitIsWired(unittest.TestCase):
    def setUp(self):
        self.src = _src("approval_center", "shared", "workflow", "transitions.py")
        self.body = _fn(self.src, "resubmit")

    def test_resubmit_asks_esign_before_touching_levels(self):
        code = _code_only(self.body)
        self.assertIn("_esign_on_reopen(request_name)", code)
        pos_call = code.index("_esign_on_reopen")
        pos_reset = code.index("level_status")
        self.assertLess(pos_call, pos_reset,
                        "phai hoi TRUOC khi reset cap - quyet dinh resume phu thuoc ket qua")

    def test_collected_signatures_force_a_restart_from_level_one(self):
        code = _code_only(self.body)
        self.assertIn('esign.get("force_restart")', code)
        self.assertRegex(code, r'if esign\.get\("force_restart"\):\s*\n\s*restart = True')

    def test_the_change_is_recorded_in_the_timeline(self):
        self.assertIn("log_action(", self.body)
        self.assertIn("note", _code_only(self.body),
                      "doi hanh vi ma khong ghi vet = nguoi dung khong hieu vi sao phai ky lai")


class TestFailureIsLoud(unittest.TestCase):
    def setUp(self):
        self.src = _src("approval_center", "shared", "workflow", "transitions.py")
        self.body = _fn(self.src, "_esign_on_reopen")

    def test_only_a_missing_module_is_tolerated(self):
        code = _code_only(self.body)
        self.assertIn("except ImportError:", code)
        self.assertNotIn("except Exception", code,
                         "nuot loi that o day = tai tao dung cai bug dang sua")

    def test_it_returns_a_usable_shape_when_esign_is_absent(self):
        self.assertIn('"force_restart": False', self.body)


class TestLifecycle(unittest.TestCase):
    def setUp(self):
        self.src = _src("platform", "esign", "lifecycle.py")

    def test_only_frozen_packages_are_revised(self):
        self.assertRegex(self.src, r'_FROZEN = \([^)]*"Locked"')
        self.assertNotIn('"Draft"', re.search(r"_FROZEN = \([^)]*\)", self.src).group(0),
                         "goi Draft tu nhat duoc tep moi - tao ban sao la thua")

    def test_it_calls_create_revision(self):
        self.assertIn("pkgsvc.create_revision(pkg.name)", _code_only(self.src))

    def test_create_revision_failure_propagates(self):
        body = _fn(self.src, "on_request_reopened")
        head = _code_only(body).split("create_revision")[0]
        self.assertNotIn("try:", head.split("if not pkg:")[-1],
                         "khong duoc boc try quanh create_revision - hong thi phai dung lai")

    def test_requester_gate_is_reset_or_the_flow_dead_ends(self):
        self.assertIn('"requester_signature_status", "Pending"', self.src)

    def test_restart_is_decided_by_real_collected_signatures(self):
        self.assertIn('_SIGNED = ("Approval Completed",)', self.src)
        self.assertIn("has_collected_signatures(pkg.name)", self.src)

    def test_it_leaves_an_audit_event(self):
        self.assertIn('events.emit("RequesterPackageReset"', self.src)
        self.assertIn("had_collected_signatures", self.src)

    def test_the_event_type_is_declared_in_the_schema(self):
        schema = _src("approval_center", "doctype", "ec_digital_signature_event",
                      "ec_digital_signature_event.json")
        self.assertIn("RequesterPackageReset", schema,
                      "event_type khong khai trong Select se lam chet job luc chay")

    def test_the_person_is_told_what_happened(self):
        self.assertIn("def reopen_notice(", self.src)
        self.assertIn("ký lại", self.src)


class TestTheOutcomeReachesTheScreen(unittest.TestCase):
    """Ba mat xich. Dut mot cai la nguoi dung bi bat ky lai ma khong biet vi sao."""

    def test_transitions_returns_the_outcome(self):
        body = _fn(_src("approval_center", "shared", "workflow", "transitions.py"), "resubmit")
        self.assertIn('return {"esign": esign}', body)

    def test_resubmitter_passes_it_up(self):
        src = _src("approval_center", "shared", "finance_support.py")
        self.assertIn('outcome.get("esign")', src)
        self.assertNotIn("return {\"restarted\": True}\n", src,
                         "tra ve cung mot dict nhu cu = nuot mat ket qua cua lop ky so")

    def test_command_service_passes_it_out(self):
        src = _src("approval_center", "shared", "requests", "command_service.py")
        body = _fn(src, "resubmit")
        self.assertIn('"esign": result.get("esign")', body)

    def test_the_page_explains_the_restart(self):
        page = _src("approval_center", "features", "payment_request", "ui", "main_section.html")
        self.assertIn("function resubmitMsg(", page)
        self.assertIn("es.force_restart", page)
        self.assertIn("không còn giá trị", page)
        self.assertIn("toast(resubmitMsg(res))", page,
                      "co ham nhung khong goi thi man hinh van im lang")


if __name__ == "__main__":
    unittest.main()
