# Copyright (c) 2026, eCentric and contributors
"""One button. "Gui yeu cau" prepares, locks and signs.

The requester used to face five actions for one intention: place the boxes, send the request,
prepare the package, lock the package, submit for signing. The middle three are internal
state-machine steps - nobody outside the esign module should have to know they exist.

They were also unreachable. On 27 and 28 August the flow stopped there twice with the same
question, "there is no button", and both times it was unblocked by calling the API by hand.
Collapsing the steps removes the class of failure as well as the clicks: there is no button
left to go missing.

Refusing to submit when the placements are incomplete is deliberate. A request that goes out
carrying an unusable signing package is worse than one that refuses to go out - the refusal is
visible immediately, the broken package is not.
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
    m = re.search(r"\ndef %s\(.*?\n(.*?)(?=\n@frappe|\ndef |\Z)" % name, src, re.S)
    assert m, "khong tim thay %s" % name
    return m.group(1)


def _code(body):
    body = re.sub(r'"""[\s\S]*?"""', "", body)
    return re.sub(r"(?m)^\s*#.*$", "", body)


class TestSubmitDoesTheWholeThing(unittest.TestCase):
    def setUp(self):
        self.body = _code(_fn(_src("platform", "esign", "requester.py"), "sign_on_submit"))

    def test_it_prepares_locks_and_signs_in_that_order(self):
        for step in ("prepare_requester_signing_package", "requester_lock_signing_package",
                     "requester_submit_and_sign"):
            self.assertIn(step, self.body, "thieu buoc %s" % step)
        self.assertLess(self.body.index("prepare_requester_signing_package"),
                        self.body.index("requester_lock_signing_package"))
        self.assertLess(self.body.index("requester_lock_signing_package"),
                        self.body.index("requester_submit_and_sign"))

    def test_incomplete_placements_stop_the_submit(self):
        self.assertIn("preflight_for_lock", self.body)
        self.assertIn("frappe.throw", self.body)
        gate = self.body.index("frappe.throw")
        self.assertLess(gate, self.body.index("requester_lock_signing_package"),
                        "phai chan TRUOC khi khoa goi, khong phai sau")

    def test_the_refusal_names_what_is_missing(self):
        self.assertIn("_placement_refusal(missing)", self.body,
                      "phai noi ro thieu o nao, khong chi 'co loi'")


class TestItIsWiredIntoSubmit(unittest.TestCase):
    def setUp(self):
        self.src = _src("approval_center", "shared", "finance_support.py")

    def test_submit_calls_it(self):
        self.assertIn("esign_requester.sign_on_submit(self.doctype, document.name)", self.src)

    def test_only_when_a_requester_signature_is_required(self):
        m = re.search(r"if signature_required:(.*?)(?=\n        frappe\.local|\n        return)",
                      self.src, re.S)
        self.assertIsNotNone(m)
        self.assertIn("sign_on_submit", m.group(1),
                      "phai nam trong nhanh signature_required, khong ap cho moi form")

    def test_the_status_is_set_before_signing(self):
        block = _code(self.src)
        self.assertLess(block.index('"requester_signature_status", "Pending"'),
                        block.index("sign_on_submit"),
                        "cong trong requester.py chi nhan Pending/Failed/Reconciliation Required")


class TestThePanelNoLongerAsksForClicks(unittest.TestCase):
    """Nut chuan bi / khoa goi / trinh ky khong con la viec cua nguoi dung."""

    def setUp(self):
        self.panel = _src("platform", "esign", "ui", "requester_signing_panel.html")

    def test_no_state_machine_buttons_are_ever_shown(self):
        m = re.search(r"var status, prepText, prepShow.*?\n(.*?)\n\s*elStatus\.textContent",
                      self.panel, re.S)
        self.assertIsNotNone(m)
        block = m.group(1)
        for banned in ("prepShow = true", "lockShow = true", "signShow = true"):
            self.assertNotIn(banned, block,
                             "van con bat nguoi dung bam mot buoc noi bo: %s" % banned)

    def test_recovery_is_the_only_action_left(self):
        m = re.search(r"var status, prepText, prepShow.*?\n(.*?)\n\s*elStatus\.textContent",
                      self.panel, re.S)
        self.assertIn("fixShow = true", m.group(1),
                      "goi LOI that su van can nguoi can thiep")



# ---------------------------------------------------------------------------
# Chay THAT ham, khong grep. Phep dot bien `if False and missing:` lot qua moi
# phep kiem tren-source o tren - chung chi thay `frappe.throw` CO MAT trong
# source, khong thay no CO CHAY khong. Xem [[test-asserting-call-exists-proves-nothing]].
# ---------------------------------------------------------------------------
class _Throw(Exception):
    pass


class _Frappe(object):
    def throw(self, msg, *a, **k):
        raise _Throw(msg)


class _Pkg(object):
    """Stub NO khi gap thu chua biet, khong tra mac dinh em ai."""

    def __init__(self, missing, signable="PKG-1"):
        self.missing = missing
        self.signable = signable
        self.calls = []

    def signable_package_for_request(self, ar):
        self.calls.append("signable")
        return self.signable

    def draft_package_for_business(self, dt, dn):
        self.calls.append("draft")
        return self.signable

    def preflight_for_lock(self, pkg):
        self.calls.append("preflight")
        return list(self.missing)

    def __getattr__(self, item):
        raise AssertionError("stub bi goi thu chua khai bao: pkgsvc.%s" % item)


def _load_sign_on_submit(pkg, calls):
    """exec chinh doan source that, voi cac phu thuoc thay bang stub."""
    src = _src("platform", "esign", "requester.py")
    m = re.search(r"(?m)^def sign_on_submit\(.*?(?=\n@|\ndef )", src, re.S)
    assert m, "khong tim thay sign_on_submit"
    g = {
        "frappe": _Frappe(),
        "_": lambda s: s,
        "pkgsvc": pkg,
        "_placement_refusal": lambda missing: "thiếu: " + "; ".join(str(m) for m in missing),
        "_requester_ar": lambda dt, dn: "AR-1",
        "prepare_requester_signing_package": lambda dt, dn: calls.append("prepare"),
        "requester_lock_signing_package": lambda dt, dn: calls.append("lock"),
        "requester_submit_and_sign": lambda dt, dn: (calls.append("sign"), "SENT")[1],
    }
    exec(compile(m.group(0), "sign_on_submit", "exec"), g)
    return g["sign_on_submit"]


class TestItActuallyRuns(unittest.TestCase):
    def test_complete_placements_go_all_the_way_through(self):
        calls = []
        fn = _load_sign_on_submit(_Pkg(missing=[]), calls)
        self.assertEqual(fn("EC Payment Request", "PR-1"), "SENT")
        self.assertEqual(calls, ["prepare", "lock", "sign"])

    def test_incomplete_placements_really_stop_it(self):
        calls = []
        fn = _load_sign_on_submit(_Pkg(missing=["Trưởng bộ phận", "CEO"]), calls)
        with self.assertRaises(_Throw) as cm:
            fn("EC Payment Request", "PR-1")
        self.assertNotIn("lock", calls, "da chan ma van khoa goi")
        self.assertNotIn("sign", calls, "da chan ma van gui lenh ky")
        self.assertIn("Trưởng bộ phận", str(cm.exception))
        self.assertIn("CEO", str(cm.exception))

    def test_no_package_at_all_is_also_a_refusal(self):
        calls = []
        fn = _load_sign_on_submit(_Pkg(missing=[], signable=None), calls)
        with self.assertRaises(_Throw):
            fn("EC Payment Request", "PR-1")
        self.assertNotIn("sign", calls)




class TestTheRefusalHappensBeforeAnythingIsWritten(unittest.TestCase):
    """Chan sau khi da ghi = phieu "da gui" vinh vien khong ai ky duoc."""

    def setUp(self):
        self.sub = _code(_src("approval_center", "shared", "finance_support.py"))

    def test_the_guard_is_signature_required_not_something_that_is_never_true(self):
        """`if False:` van de lai chuoi trong source. Phai doc CAY CU PHAP, khong grep."""
        import ast
        tree = ast.parse(_src("approval_center", "shared", "finance_support.py"))
        found = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.If):
                continue
            calls = [n for n in ast.walk(node)
                     if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                     and n.func.attr in ("assert_ready_to_submit", "sign_on_submit")]
            if calls:
                found.append((node.test, [c.func.attr for c in calls]))
        self.assertTrue(found, "khong nhanh nao goi hai ham nay")
        for test, names in found:
            self.assertIsInstance(
                test, ast.Name,
                "dieu kien bao ngoai %s phai la mot bien, khong phai hang: %s"
                % (names, ast.dump(test)))
            self.assertEqual(test.id, "signature_required",
                             "%s phai chay khi va chi khi signature_required" % names)

    def test_the_check_runs_before_save_and_before_engine_submit(self):
        gate = self.sub.index("assert_ready_to_submit")
        self.assertLess(gate, self.sub.index("document.save(ignore_permissions=True)"),
                        "chan sau khi save -> phieu bi ghi roi moi tu choi")
        self.assertLess(gate, self.sub.index("engine.submit("),
                        "chan sau engine.submit -> approval_request da ton tai, "
                        "Submitter se tu choi lan sau voi 'da duoc gui'")

    def test_it_only_reads(self):
        body = _code(_fn(_src("platform", "esign", "requester.py"), "assert_ready_to_submit"))
        for banned in ("db.set_value", ".save(", ".insert(", "frappe.get_doc(",
                       "prepare_requester_signing_package", "lock_signing_package"):
            self.assertNotIn(banned, body,
                             "phep kiem truoc khi ghi khong duoc ghi gi: %s" % banned)

    def test_it_names_what_is_missing(self):
        body = _code(_fn(_src("platform", "esign", "requester.py"), "assert_ready_to_submit"))
        self.assertIn("_placement_refusal(missing)", body)




class TestTheRefusalIsReadableByAHuman(unittest.TestCase):
    """preflight tra ve ma may. Nem "missing_placement:L2:hoa-don.pdf" vao mat nguoi de
    nghi thi ho khong biet phai bam vao dau."""

    def setUp(self):
        src = _src("platform", "esign", "requester.py")
        g = {"_": lambda s: s}
        exec(compile(re.search(r"(?m)^_PREFLIGHT_VI = \{.*?\n\}", src, re.S).group(0), "x", "exec"), g)
        exec(compile(re.search(r"(?m)^def _preflight_vi.*?(?=\ndef )", src, re.S).group(0), "x", "exec"), g)
        self.vi = g["_preflight_vi"]

    def test_every_code_preflight_can_emit_is_translated(self):
        pkg = _src("platform", "esign", "package.py")
        body = re.search(r"(?m)^def preflight_for_lock.*?(?=\ndef )", pkg, re.S).group(0)
        codes = set(re.findall(r'errs\.append\("([a-z_]+)', body))
        self.assertTrue(codes, "khong doc duoc ma nao tu preflight_for_lock")
        for c in codes:
            out = self.vi(c if ":" not in c else c)
            self.assertNotEqual(out, c, "ma '%s' chua duoc dich sang tieng nguoi" % c)

    def test_placement_code_names_the_level_and_the_file(self):
        out = self.vi("missing_placement:L2:hoa-don.pdf")
        self.assertIn("2", out)
        self.assertIn("hoa-don.pdf", out)

    def test_an_unknown_code_is_passed_through_not_swallowed(self):
        self.assertEqual(self.vi("ma_moi_chua_biet"), "ma_moi_chua_biet",
                         "thieu mot dong dich khong duoc bien thanh loi im lang")



if __name__ == "__main__":
    unittest.main()
