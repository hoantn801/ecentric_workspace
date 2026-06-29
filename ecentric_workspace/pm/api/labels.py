"""PM v2 - Batch G4.9: reusable task labels (service layer, hardened trust boundary).

Shared, color-coded labels for the whole PM workspace (DocTypes PM Task Label + PM Task Label
Assignment, created by patch p009 with System-Manager-ONLY DocPerm). ALL business permission
lives here -> this service is the single trust boundary for PM users:

  * leaders manage the catalogue (create / rename / recolor / archive);
  * any PM user who can edit a NON-terminal task may attach/detach EXISTING ACTIVE labels.

Because the DocTypes carry no PM-role DocPerm, PM Manager/PM Member cannot reach them through
generic Frappe CRUD; they must go through these whitelisted methods. Each method runs the full
guard chain (require_pm_access -> can_view_task -> leader/terminal/active/color) BEFORE any
ignore_permissions write. DB-level unique columns (normalized_name, assignment_key) close the
service-layer TOCTOU race for duplicate names / duplicate (task,label) pairs.

Module path: ecentric_workspace.pm.api.labels
"""

import json

import frappe
from frappe import _

from ecentric_workspace.pm import permissions as pmperm

LABEL_DT = "PM Task Label"
ASSIGN_DT = "PM Task Label Assignment"

COLOR_KEYS = ("gray", "blue", "cyan", "green", "yellow", "orange", "red", "purple", "pink")

_TERMINAL_MSG = "Không thể chỉnh nhãn sau khi nhiệm vụ đã hoàn thành/huỷ. Vui lòng Reopen trước."


def _require_label_manager(user):
    """Catalogue CRUD = PM leaders OR PM Manager (canonical can_manage_pm_labels)."""
    if not pmperm.can_manage_pm_labels(user):
        frappe.throw(_("Chỉ quản lý mới được chỉnh danh mục nhãn."), frappe.PermissionError)


def _clean_name(label_name):
    label_name = (label_name or "").strip()
    if not label_name:
        frappe.throw(_("Tên nhãn là bắt buộc."))
    return label_name


def _normalize(label_name):
    return (label_name or "").strip().casefold()


def _check_color(color_key):
    if color_key not in COLOR_KEYS:
        frappe.throw(_("Màu nhãn không hợp lệ."))
    return color_key


def _assert_unique_name(label_name, exclude=None):
    """Friendly pre-check (the DB unique index on normalized_name is the race-safe backstop)."""
    norm = _normalize(label_name)
    for r in frappe.get_all(LABEL_DT, filters={"normalized_name": norm},
                            fields=["name"], limit_page_length=0, ignore_permissions=True):
        if r["name"] != exclude:
            frappe.throw(_("Đã có nhãn tên '{0}'.").format(label_name))


def _as_label(d):
    return {"name": d["name"], "label_name": d.get("label_name"),
            "color_key": d.get("color_key") or "gray", "is_active": d.get("is_active")}


# --------------------------------------------------------------------------
# Catalogue (read + leader-managed CRUD)
# --------------------------------------------------------------------------
@frappe.whitelist()
def list_labels(include_inactive=0):
    """All labels (active only by default). Any PM user may read the catalogue (via the API;
    the DocType has no PM-role DocPerm, so the read is ignore_permissions after require_pm_access)."""
    pmperm.require_pm_access()
    filters = {}
    if include_inactive not in (1, "1", True, "true", "True"):
        filters["is_active"] = 1
    rows = frappe.get_all(LABEL_DT, filters=filters or None,
                          fields=["name", "label_name", "color_key", "is_active"],
                          order_by="label_name asc", limit_page_length=0, ignore_permissions=True)
    return {"rows": [_as_label(r) for r in rows]}


@frappe.whitelist()
def create_label(label_name, color_key):
    """Create a label. LEADER-ONLY. Trimmed, case-insensitively unique (service + DB index),
    palette color."""
    pmperm.require_pm_access()
    _require_label_manager(frappe.session.user)
    label_name = _clean_name(label_name)
    _check_color(color_key)
    _assert_unique_name(label_name)
    doc = frappe.get_doc({"doctype": LABEL_DT, "label_name": label_name, "color_key": color_key,
                          "is_active": 1, "normalized_name": _normalize(label_name)})
    try:
        doc.insert(ignore_permissions=True)
    except frappe.DuplicateEntryError:
        frappe.throw(_("Đã có nhãn tên '{0}'.").format(label_name))
    return _as_label(doc.as_dict())


@frappe.whitelist()
def update_label(name, label_name=None, color_key=None, is_active=None):
    """Rename / recolor / archive a label. LEADER-ONLY. Never hard-deletes; archive via
    is_active=0 (old tasks keep showing it; it just can't be attached anew)."""
    pmperm.require_pm_access()
    _require_label_manager(frappe.session.user)
    doc = frappe.get_doc(LABEL_DT, name)
    if label_name is not None:
        label_name = _clean_name(label_name)
        _assert_unique_name(label_name, exclude=doc.name)
        doc.label_name = label_name
        doc.normalized_name = _normalize(label_name)
    if color_key is not None:
        doc.color_key = _check_color(color_key)
    if is_active is not None:
        doc.is_active = 1 if is_active in (1, "1", True, "true", "True") else 0
    try:
        doc.save(ignore_permissions=True)
    except frappe.DuplicateEntryError:
        frappe.throw(_("Đã có nhãn tên '{0}'.").format(label_name or doc.label_name))
    return _as_label(doc.as_dict())


# --------------------------------------------------------------------------
# Per-task assignment (attach / detach)
# --------------------------------------------------------------------------
@frappe.whitelist()
def get_task_labels(task):
    """Labels attached to one task (read). Permission-checked like the task itself."""
    pmperm.require_pm_access()
    user = frappe.session.user
    doc = frappe.get_doc("Task", task)
    if not pmperm.can_view_task(doc.as_dict(), user):
        frappe.throw(_("Not permitted to view this task."), frappe.PermissionError)
    return {"labels": labels_for_tasks([task]).get(task, [])}


def _assignment_key(task, label):
    return "{0}::{1}".format(task, label)


@frappe.whitelist()
def set_task_labels(task, labels):
    """Replace a task's label set with `labels` (list of PM Task Label names). Full guard chain
    BEFORE any write. A label may be NEWLY attached only if it is active; labels already on the
    task are preserved even if later archived (snapshot). Idempotent: the unique assignment_key
    guarantees no duplicate (task,label) row even under concurrent calls."""
    pmperm.require_pm_access()
    user = frappe.session.user
    doc = frappe.get_doc("Task", task)
    if not pmperm.can_view_task(doc.as_dict(), user):
        frappe.throw(_("Not permitted to edit this task's labels."), frappe.PermissionError)
    pmperm.assert_task_not_terminal(doc, _(_TERMINAL_MSG))

    if isinstance(labels, str):
        try:
            labels = json.loads(labels)
        except Exception:
            labels = [labels]
    want = []
    for l in (labels or []):
        if l and l not in want:
            want.append(l)

    existing = {r["label"]: r["name"] for r in frappe.get_all(
        ASSIGN_DT, filters={"task": task}, fields=["name", "label"],
        limit_page_length=0, ignore_permissions=True)}

    if want:
        meta = {r["name"]: r for r in frappe.get_all(
            LABEL_DT, filters={"name": ["in", tuple(set(want))]},
            fields=["name", "is_active"], limit_page_length=0, ignore_permissions=True)}
        for l in want:
            if l not in meta:
                frappe.throw(_("Nhãn không tồn tại."))
            if l not in existing and not meta[l].get("is_active"):
                frappe.throw(_("Không thể gắn nhãn đã lưu trữ."))

    want_set = set(want)
    for label, row_name in existing.items():
        if label not in want_set:
            frappe.delete_doc(ASSIGN_DT, row_name, ignore_permissions=True)
    for label in want:
        if label not in existing:
            try:
                frappe.get_doc({"doctype": ASSIGN_DT, "task": task, "label": label,
                                "assignment_key": _assignment_key(task, label)}).insert(
                    ignore_permissions=True)
            except frappe.DuplicateEntryError:
                pass  # concurrent attach won the race -> idempotent, the pair already exists

    return {"labels": labels_for_tasks([task]).get(task, [])}


def labels_for_tasks(task_names):
    """Batch: {task_name: [label dict, ...]}. ONE assignment query + ONE label query (no N+1).
    ignore_permissions reads (the calling lists are already permission-scoped; label metadata is
    non-sensitive). Used by tasks.list/get/subtree enrichment + recurrence clone."""
    task_names = [t for t in (task_names or []) if t]
    out = {}
    if not task_names:
        return out
    assigns = frappe.get_all(ASSIGN_DT, filters={"task": ["in", tuple(set(task_names))]},
                             fields=["task", "label"], limit_page_length=0, ignore_permissions=True)
    if not assigns:
        return out
    label_ids = list({a["label"] for a in assigns})
    meta = {r["name"]: r for r in frappe.get_all(
        LABEL_DT, filters={"name": ["in", tuple(label_ids)]},
        fields=["name", "label_name", "color_key", "is_active"],
        limit_page_length=0, ignore_permissions=True)}
    for a in assigns:
        m = meta.get(a["label"])
        if not m:
            continue
        out.setdefault(a["task"], []).append(_as_label(m))
    for t in out:
        out[t].sort(key=lambda x: (x.get("label_name") or "").lower())
    return out


@frappe.whitelist()
def labels_for_tasks_api(task_names):
    """Whitelisted wrapper around labels_for_tasks (read-only batch enrichment)."""
    pmperm.require_pm_access()
    if isinstance(task_names, str):
        try:
            task_names = json.loads(task_names)
        except Exception:
            task_names = [task_names]
    return {"map": labels_for_tasks(task_names)}


def pm_label_before_delete(doc, method=None):
    """G4.9 hard-delete guard (registered as PM Task Label before_delete in hooks.py). An in-use
    label can NEVER be hard-deleted — not via the API, not via generic CRUD, not even by
    Administrator. The governed way to retire a label is archive (is_active=0), which keeps it on
    historical tasks. Detaching an assignment (PM Task Label Assignment) is unaffected."""
    if frappe.flags.in_install or frappe.flags.in_migrate or frappe.flags.in_patch:
        return
    if frappe.db.exists(ASSIGN_DT, {"label": doc.name}):
        frappe.throw(_("Nhãn đang được sử dụng và không thể xoá. "
                       "Vui lòng chuyển sang trạng thái ngừng hoạt động."), frappe.PermissionError)
