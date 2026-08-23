"""PM v2 - 2026-08-06 (p019): flatten the Task hierarchy to at most 2 levels.

Decision (Hoàn, 2026-08-06): PM keeps Project -> Task -> Sub-task (ONE level of sub-tasks). Any
task nested deeper than level 2 is re-parented to its TOP-LEVEL ancestor, so the whole tree becomes
depth 2. Backend `tasks.create` also blocks creating a sub-task under a sub-task from now on.

SAFETY (production data):
  * We change ONLY the `parent_task` pointer of tasks that are level >= 3 (their parent is itself a
    sub-task). Level-1 and level-2 tasks are untouched. No task is deleted; no other field changes.
  * We use frappe.db.set_value (no doc hooks / no workflow / no notifications fire), then rebuild the
    NestedSet lft/rgt via frappe.utils.nestedset.rebuild_tree so the tree stays consistent.
  * The old parent of every moved task is written to the Frappe log (audit / manual undo).
  * IDEMPOTENT: after a run no task is level >= 3, so a re-run moves nothing.
  * Cycle-safe: ancestor walk is bounded and detects loops (never infinite, never self-parent).

Run AFTER a DB backup (irreversible in practice without the logged old-parent map).
"""

import frappe


def _root_ancestor(name, pmap):
    """Top-most ancestor of `name` following parent_task. Bounded + cycle-safe. Returns the first
    task in the chain that has no parent (or the last safe node if a cycle is hit)."""
    seen = set()
    cur = name
    steps = 0
    while True:
        parent = pmap.get(cur)
        if not parent or parent in seen or steps > 10000:
            return cur
        seen.add(cur)
        cur = parent
        steps += 1


def execute():
    tasks = frappe.get_all("Task", fields=["name", "parent_task"], limit_page_length=0)
    pmap = {t["name"]: (t.get("parent_task") or None) for t in tasks}

    # A task is level >= 3 iff its parent itself has a parent. Re-parent it to its top ancestor.
    reparent = {}
    for name, parent in pmap.items():
        if parent and pmap.get(parent):  # grandparent exists -> level >= 3
            root = _root_ancestor(name, pmap)
            if root and root != name and root != parent:
                reparent[name] = root

    if not reparent:
        frappe.logger().info("p019 flatten: hierarchy already <= 2 levels, nothing to do.")
        return

    # audit: record the old->new parent map before mutating (manual undo reference)
    audit = {n: {"old_parent": pmap.get(n), "new_parent": root} for n, root in reparent.items()}
    frappe.log_error(frappe.as_json(audit)[:130000], "p019 flatten task hierarchy (old->new parent)")

    for name, root in reparent.items():
        frappe.db.set_value("Task", name, "parent_task", root, update_modified=False)

    # rebuild NestedSet lft/rgt for the whole Task tree so the pointers we changed stay consistent
    from frappe.utils.nestedset import rebuild_tree
    rebuild_tree("Task", "parent_task")

    frappe.db.commit()
    frappe.logger().info("p019 flatten: re-parented %s task(s) to their top ancestor; tree rebuilt."
                         % len(reparent))
