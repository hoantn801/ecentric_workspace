# Copyright (c) 2026, eCentric and contributors
"""No department manager? The requester names one department head - or the request is blocked.

Level 1 of PAYMENT_REQUEST used to carry two participant rows, "Department Manager" and
"Requester Manager". For ordinary staff both name the same person. For a department head they
diverge: himself, and his own manager one level up - a CEO, who eContract will not accept at
the "Truong bo phan" step. That is why every request on 2026-08-28 was broadcast to seven
department heads instead of one named person.

The second row still had a job: nobody must be left unable to submit. That job now belongs to
a CHOICE. When the department-manager lookup finds nobody, the level takes the person the
requester picked on the form. Nothing picked, nobody found - the submit is refused with an
actionable message, and HR fills in the department's manager.

Decided 2026-08-28 after an explicit alternative was rejected: opening the level to ALL
department heads. That would let any head approve for any department, which is a governance
change nobody asked for. So the pool is deliberately NOT a thing here.
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
    raise AssertionError("khong tim thay %s" % parts[-1])


_SRC = _src("approval_center", "shared", "workflow", "transitions.py")


def _load(resolved, chosen, active=None):
    m = re.search(r"(?m)^def resolve_participants\(.*?(?=\n\n# -----)", _SRC, re.S)
    assert m, "khong tim thay resolve_participants"
    act = active if active is not None else {x for x in (resolved, chosen) if x}
    g = {
        "frappe": type("F", (), {"get_all": staticmethod(lambda *a, **k: []),
                                 "db": type("D", (), {"get_value": staticmethod(
                                     lambda *a, **k: None)})()})(),
        "_is_active_system_user": lambda u: u in act,
        "resolve_department_manager_user": lambda d: resolved,
        "_emp_user": lambda u: {"department": "__D__"},
        "_ref_field_value": lambda ctx, field: chosen if field == "level1_approver" else None,
        "_manager_user_of_employee": lambda *a: None,
    }
    exec(compile(m.group(0), "rp", "exec"), g)
    return g["resolve_participants"]


class _Row(dict):
    def __getattr__(self, k):
        return self.get(k)


_ROW = _Row({"source_type": "Department Manager", "sort_order": 0, "department": None,
             "reference_field": "level1_approver"})


class TestTheChoiceOnlyAppliesWhenNobodyResolved(unittest.TestCase):
    def test_a_real_manager_wins_and_the_choice_is_ignored(self):
        fn = _load(resolved="mgr@x", chosen="head@x")
        out = fn([_ROW], "staff@x")
        self.assertEqual([u for u, _l in out], ["mgr@x"],
                         "da co truong phong that thi khong duoc lay nguoi tu chon")

    def test_no_manager_takes_the_chosen_head(self):
        fn = _load(resolved=None, chosen="head@x")
        out = fn([_ROW], "orphan@x")
        self.assertEqual(out, [("head@x", "Chosen Department Head")])

    def test_the_label_records_that_it_was_a_choice(self):
        fn = _load(resolved=None, chosen="head@x")
        self.assertEqual(fn([_ROW], "orphan@x")[0][1], "Chosen Department Head",
                         "phai phan biet duoc voi truong hop tra ra truong phong that")

    def test_nothing_chosen_and_nobody_found_blocks(self):
        fn = _load(resolved=None, chosen=None)
        self.assertEqual(fn([_ROW], "orphan@x"), [],
                         "khong ai -> build_snapshot chan viec gui, dung nhu da chot")

    def test_an_inactive_choice_is_refused(self):
        fn = _load(resolved=None, chosen="gone@x", active=set())
        self.assertEqual(fn([_ROW], "orphan@x"), [])

    def test_a_row_without_the_configured_field_just_blocks(self):
        row = _Row({"source_type": "Department Manager", "sort_order": 0, "department": None})
        fn = _load(resolved=None, chosen="head@x")
        self.assertEqual(fn([row], "orphan@x"), [],
                         "chua cau hinh o chon thi khong duoc tu suy ra nguoi nao")


class TestThePoolIsDeliberatelyAbsent(unittest.TestCase):
    """Phuong an "mo cho ca nhom truong phong" da bi bac 28/08. Neu ai do dinh lam lai,
    phep kiem nay phai keu len."""

    def test_no_helper_lists_every_department_manager(self):
        self.assertNotIn("all_department_manager_users", _SRC,
                          "mo cap cho MOI truong phong = ai cung duyet duoc cho phong khac")

    def test_the_department_manager_branch_adds_at_most_one_person(self):
        m = re.search(r'elif st == "Department Manager":(.*?)elif st ==', _SRC, re.S)
        self.assertIsNotNone(m)
        self.assertNotIn("for u in", m.group(1),
                         "khong duoc lap qua mot danh sach nguoi o nhanh nay")


if __name__ == "__main__":
    unittest.main()
