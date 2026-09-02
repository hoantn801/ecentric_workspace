# Copyright (c) 2026, eCentric and contributors
"""Ask the provider who may receive the step, instead of assuming our chain is theirs.

2026-08-28 20:25, EC-PAYR-2026-00034. ERP sent the transition with toUsers = [Lam (CEO),
Hoan]. eContract answered 2xx and did nothing at all: no workflow row, no signature, five
empty signature areas. Minutes earlier the portal's own call on the SAME document, with a
toUsers of ONE, signed immediately.

Sending to yourself is not the problem - the portal's successful call did exactly that. The
difference is the second recipient: the next state is "Truong bo phan" and Lam holds CEO.

ERP has an approval chain; eContract has a workflow. They are not required to agree, and when
they disagree eContract discards the whole command silently. `users-for-transition` is the
provider's own answer to "who may receive this", so ask it.
"""
import io
import os
import re
import sys
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))


def _src(*parts):
    root = _HERE
    tried = []
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


def _load_plan_handover(eligible_result, ids):
    """Chay THAT doan loc, voi cac phu thuoc thay bang stub."""
    src = _src("platform", "esign", "next_handler.py")
    m = re.search(r"(?m)^    ids, unmapped = provider_ids_for.*?(?=\n    if discovery_note)",
                  src, re.S)
    assert m, "khong tim thay doan chon nguoi nhan"
    body = m.group(0)

    class _Adapter(object):
        calls = []

        def eligible_recipients(self, instance_id, transition_id, user_id):
            _Adapter.calls.append((instance_id, transition_id, user_id))
            if isinstance(eligible_result, Exception):
                raise eligible_result
            return eligible_result

    fn = ("def run(adapter, instance_id, cfg, dsr, users, environment):\n"
          + body + "\n    return out\n")
    g = {"provider_ids_for": lambda u, e: (list(ids), []),
         "dropped": None}
    exec(compile(fn, "plan", "exec"), g)
    _Adapter.calls = []
    return g["run"], _Adapter


_CFG = {"transition_id": -2, "sign_type": "ky-tham-gia"}
_DSR = {"effective_scts_user_id": "HOAN"}
_LAM, _HOAN = "715d828a", "73f72e15"


class TestIneligibleRecipientsAreDropped(unittest.TestCase):
    def test_the_ceo_is_dropped_when_the_step_is_for_the_manager(self):
        run, Adapter = _load_plan_handover({_HOAN}, [_LAM, _HOAN])
        out = run(Adapter(), "DOC", _CFG, _DSR, ["lam@x", "hoan@x"], "UAT")
        self.assertEqual(out["mode"], "transition")
        self.assertEqual(out["to_users"], [_HOAN])
        self.assertEqual(out["dropped_not_eligible"], [_LAM],
                         "bi loai phai duoc ghi lai, khong im lang")

    def test_it_asks_with_the_transition_id_being_sent(self):
        run, Adapter = _load_plan_handover({_HOAN}, [_HOAN])
        a = Adapter()
        run(a, "DOC", _CFG, _DSR, ["hoan@x"], "UAT")
        self.assertEqual(Adapter.calls, [("DOC", -2, "HOAN")],
                         "phai hoi dung buoc dang gui, khong phai buoc khac")

    def test_nobody_eligible_falls_back_to_pool_rather_than_a_doomed_send(self):
        run, Adapter = _load_plan_handover(set(), [_LAM, _HOAN])
        out = run(Adapter(), "DOC", _CFG, _DSR, ["lam@x", "hoan@x"], "UAT")
        self.assertEqual(out["mode"], "pool")
        self.assertIn("no_eligible_recipient", out["reason"])

    def test_everyone_eligible_changes_nothing(self):
        run, Adapter = _load_plan_handover({_LAM, _HOAN}, [_LAM, _HOAN])
        out = run(Adapter(), "DOC", _CFG, _DSR, ["lam@x", "hoan@x"], "UAT")
        self.assertEqual(out["to_users"], [_LAM, _HOAN])
        self.assertNotIn("dropped_not_eligible", out)


class TestNotAskingIsNotTheSameAsAnEmptyAnswer(unittest.TestCase):
    """`None` = khong hoi duoc. Tap rong = hoi duoc, va cau tra loi la "khong ai"."""

    def test_an_unreachable_check_keeps_the_original_list(self):
        run, Adapter = _load_plan_handover(None, [_LAM, _HOAN])
        out = run(Adapter(), "DOC", _CFG, _DSR, ["lam@x", "hoan@x"], "UAT")
        self.assertEqual(out["mode"], "transition")
        self.assertEqual(out["to_users"], [_LAM, _HOAN])
        self.assertTrue(out.get("recipients_unverified"),
                        "khong hoi duoc thi phai NOI RA, khong trong nhu da kiem")

    def test_no_adapter_means_no_check_and_no_crash(self):
        run, _A = _load_plan_handover(None, [_HOAN])
        out = run(None, None, _CFG, _DSR, ["hoan@x"], "UAT")
        self.assertEqual(out["to_users"], [_HOAN])
        self.assertNotIn("recipients_unverified", out)


class TestTheAdapterSeparatesUnknownFromEmpty(unittest.TestCase):
    def setUp(self):
        self.src = _src("platform", "esign", "providers", "scts.py")
        self.body = re.search(r"(?m)^    def eligible_recipients.*?(?=\n    def )",
                              self.src, re.S).group(0)

    def test_a_failed_call_returns_none_not_an_empty_set(self):
        # `as exc` la tuy chon - bat ca hai dang, neu khong test do vi mot thay doi khong lien
        # quan (da xay ra 02/09 khi them ghi log vao dung nhanh nay).
        m = re.search(r"except Exception(?: as \w+)?:\s*\n(?:.*\n)*?\s*return (\S+)",
                      self.body)
        self.assertIsNotNone(m, "khong tim thay nhanh xu ly loi trong eligible_recipients")
        self.assertEqual(m.group(1), "None",
                         "loi goi ma tra set() rong = bao 'khong ai duoc nhan' - sai han")

    def test_khong_hoi_duoc_thi_phai_GHI_LAI_vi_sao(self):
        """Tra None am tham = lop bao ve tat ma khong ai biet.

        Lop nay chan viec gui mot lenh ma eContract chac chan bo qua. Khi no tra None, tang
        tren gui dai theo chuoi cua ERP. 02/09 chan ky HOF di dung duong do: 2xx kem ma giao
        dich, 20 phut sau khong co chu ky nao. Khong ai lan ra duoc vi sao lop bao ve khong
        chay, vi cho nay nuot sach loi.
        """
        self.assertIn("log_error", self.body,
                      "phai ghi log khi khong hoi duoc - nguoi chan doan can biet VI SAO")
        self.assertIn("safe_error", self.body,
                      "ghi noi dung loi da lam sach, khong chi ten loai loi")

    def test_it_reads_the_id_under_any_of_the_shapes_seen(self):
        for key in ('"id"', '"userId"'):
            self.assertIn(key, self.body)


if __name__ == "__main__":
    unittest.main()
