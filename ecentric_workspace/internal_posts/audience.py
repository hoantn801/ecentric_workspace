# Copyright (c) 2026, eCentric and contributors
"""Ai nam trong pham vi mot bai (toan cong ty / phong ban + phong con) - dung chung cho luot
xem, xac nhan da doc, nhac viec. Quy tac thuan o domain.in_scope; day chi ghep voi repo."""
from ecentric_workspace.internal_posts import domain as D


def selected_ranges(repo, depts):
    tree = repo.dept_tree()
    return [(tree[d][0], tree[d][1]) if d in tree else (None, None) for d in depts or ()]


def scope_label(repo, depts):
    if not depts:
        return ""
    tree = repo.dept_tree()
    return ", ".join(tree[d][2] if d in tree else d for d in depts)


def audience(repo, depts):
    sel = selected_ranges(repo, depts)
    return [e["user"] for e in repo.active_employees() if D.in_scope(sel, e["lft"])]
