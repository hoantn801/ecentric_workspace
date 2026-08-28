# Copyright (c) 2026, eCentric and contributors
"""Close the gap between "provider accepted" and "the screen says so".

2026-08-28: "bam duyet va ky roi nhung no van con nut nay, va phai 1 luc sau co 2-5 phut
no moi bao da xu ly. Delay nhu nay kha khong tot cho UI UX."

The single immediate re-poll runs about one second after the provider ACCEPTS the command,
and the signature typically appears 20-40 seconds later - so that poll essentially always
misses. After it, nothing asks again until the cron tick, and queue latency stretches the
felt wait to minutes.

A short bounded follow-up loop closes it. The one property that must never bend: this loop
READS. `process_signing_request` only sends a signing command from status "Queued", and a
leg in "Provider Accepted"/"Verifying" skips straight to polling - so calling it repeatedly
cannot produce a second signature. A non-idempotent signing write must never be replayed
automatically.
"""
import io
import os
import re
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))


def _src(*parts):
    root, tried = _HERE, []
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
    m = re.search(r"(?m)^def %s\(.*?(?=\n@|\ndef )" % name, src, re.S)
    assert m, "khong tim thay %s" % name
    return m.group(0)


class _Db(object):
    def __init__(self, states):
        self.states = list(states)
        self.reads = 0

    def get_value(self, dt, name, field):
        v = self.states[min(self.reads, len(self.states) - 1)]
        self.reads += 1
        return v


def _load_fast_verify(states, on_process):
    src = _src("platform", "esign", "tasks.py")
    g = {"time": type("T", (), {"sleep": staticmethod(lambda s: None)}),
         "DSR": "EC Digital Signature Request",
         "_disabled": lambda: False,
         "process_signing_request": on_process,
         "frappe": type("F", (), {"db": _Db(states),
                                  "get_traceback": staticmethod(lambda: ""),
                                  "log_error": staticmethod(lambda *a, **k: None)})()}
    exec(compile(_fn(src, "fast_verify"), "fv", "exec"), g)
    exec(compile(re.search(r"(?m)^FAST_VERIFY_DELAYS = .*$", src).group(0), "d", "exec"), g)
    exec(compile(re.search(r"(?m)^_FAST_VERIFY_LIVE = .*$", src).group(0), "l", "exec"), g)
    return g["fast_verify"]


class TestItNeverResendsASigningCommand(unittest.TestCase):
    """Bat bien quan trong nhat: vong nay CHI DOC."""

    def test_every_signing_call_sits_inside_the_queued_branch(self):
        """Doc CAY CU PHAP. Dem vi tri chuoi la sai: co HAI cho goi poll_status trong
        ham nay, va phep kiem dau tien cua minh bat nham cai o nhanh khac."""
        import ast
        src = _src("platform", "esign", "tasks.py")
        tree = ast.parse(src)
        fn = next(n for n in ast.walk(tree)
                  if isinstance(n, ast.FunctionDef) and n.name == "process_signing_request")
        parents = {}
        for node in ast.walk(fn):
            for child in ast.iter_child_nodes(node):
                parents[child] = node

        def guarded_by_queued(node):
            cur = parents.get(node)
            while cur is not None:
                if isinstance(cur, ast.If):
                    t = cur.test
                    if (isinstance(t, ast.Compare)
                            and isinstance(t.left, ast.Attribute)
                            and t.left.attr == "status"
                            and any(isinstance(c, ast.Constant) and c.value == "Queued"
                                    for c in t.comparators)):
                        return True
                cur = parents.get(cur)
            return False

        sends = [n for n in ast.walk(fn)
                 if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                 and n.func.attr in ("approve_and_sign", "transition_with_recipients")]
        self.assertTrue(sends, "khong tim thay lenh gui ky nao - phep kiem nay da mu")
        for call in sends:
            self.assertTrue(guarded_by_queued(call),
                            "lenh %s nam NGOAI nhanh Queued -> goi lai se ky lan hai"
                            % call.func.attr)

    def test_fast_verify_calls_nothing_that_writes_to_the_provider(self):
        body = _fn(_src("platform", "esign", "tasks.py"), "fast_verify")
        for banned in ("approve_and_sign", "transition_with_recipients", "bulk_process",
                       "_client.", "create_document"):
            self.assertNotIn(banned, body, "vong doi soat khong duoc gui gi: %s" % banned)


class TestItStopsAsSoonAsThereIsAnAnswer(unittest.TestCase):
    def test_it_returns_the_moment_the_leg_leaves_the_live_states(self):
        """Hai cho phai dung: dau vong (truoc khi hoi) VA ngay sau khi hoi xong.

        Bo phep kiem sau-khi-hoi thi mot chan ky ky xong o lan dau van bi hoi them mot
        lan nua - phep dot bien AF lot dung vi thieu cho nay.
        """
        calls = []
        # Doc 1 (dau vong)  = Verifying  -> hoi
        # Doc 2 (sau khi hoi) = Approval Completed -> phai dung NGAY
        fv = _load_fast_verify(["Verifying", "Approval Completed"], lambda n: calls.append(n))
        fv("DSR-1")
        self.assertEqual(len(calls), 1, "da xong roi ma van hoi tiep")

    def test_it_checks_again_right_after_asking(self):
        """Sau moi lan hoi phai doc lai trang thai, khong doi den dau vong sau."""
        body = _fn(_src("platform", "esign", "tasks.py"), "fast_verify")
        after = body.split("process_signing_request(dsr_name)")[-1]
        self.assertIn("_FAST_VERIFY_LIVE", after,
                      "hoi xong khong kiem lai -> ngu them mot nhip roi hoi lan nua vo ich")
        self.assertIn("return", after)

    def test_it_does_not_even_start_when_already_finished(self):
        calls = []
        fv = _load_fast_verify(["Approval Completed"], lambda n: calls.append(n))
        fv("DSR-1")
        self.assertEqual(calls, [], "chan ky da xong ma van goi")

    def test_it_is_bounded(self):
        src = _src("platform", "esign", "tasks.py")
        delays = eval(re.search(r"FAST_VERIFY_DELAYS = (\(.*?\))", src).group(1))
        self.assertLessEqual(len(delays), 8, "khong duoc quay lau - cron la luoi an toan")
        self.assertLessEqual(sum(delays), 120,
                             "tong thoi gian phai duoi 2 phut, sau do nhuong cho cron")
        self.assertTrue(all(d > 0 for d in delays))

    def test_a_failure_stops_the_loop_instead_of_hammering(self):
        def boom(_n):
            raise RuntimeError("provider down")
        fv = _load_fast_verify(["Verifying"] * 10, boom)
        fv("DSR-1")   # khong duoc nem ra ngoai


class TestItIsWiredInAtTheRightMoment(unittest.TestCase):
    def test_it_is_started_when_the_provider_accepts_but_has_not_signed_yet(self):
        body = _fn(_src("platform", "esign", "tasks.py"), "process_signing_request")
        m = re.search(r'if dsr\.status == "Provider Accepted":(.*?)elif dsr\.status',
                      body, re.S)
        self.assertIsNotNone(m)
        self.assertIn("_enqueue_fast_verify(dsr_name)", m.group(1),
                      "khong bam vong doi soat -> lai cho cron nhu cu")

    def test_starting_it_can_never_break_signing(self):
        body = _fn(_src("platform", "esign", "tasks.py"), "_enqueue_fast_verify")
        self.assertIn("except Exception:", body,
                      "day la tang tang toc; hong thi phai im, khong duoc giet chan ky")
        self.assertIn("enqueue_after_commit=True", body)


if __name__ == "__main__":
    unittest.main()
