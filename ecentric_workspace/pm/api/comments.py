"""PM v2 - governed comment service for Project / Task timelines.

Why: the PM UI must let any PM Member comment on a Project/Task they can access, WITHOUT
granting broad `create`/`read` DocPerm on the core `Comment` DocType (which would let them
comment on unrelated ERP documents). This service is the trust boundary:

  * requires a logged-in enabled user with PM module access (require_pm_access);
  * restricts reference_doctype to {"Project", "Task"} only -- never other ERP docs;
  * checks the caller can access the referenced Project/Task under PM visibility rules
    (can_view_task / can_view_project);
  * only then creates/reads the Comment via the service boundary.

Because the PM checks above are the gate, the Comment row itself is written with
ignore_permissions=True (same pattern as the rest of the PM service layer) and read with
frappe.get_all (low-level, no DocPerm) AFTER the access check -- so no Comment DocPerm change
is needed. A user cannot comment on, or read comments of, a document they cannot access, and
cannot target any doctype outside {Project, Task}.

Module path: ecentric_workspace.pm.api.comments
"""

import frappe
from frappe import _

from ecentric_workspace.pm import permissions as pmperm

_ALLOWED_REF = ("Project", "Task")


def _require_access(reference_doctype, reference_name):
    """Gate: logged-in + PM access + reference is a PM doc the caller can view. Raises on failure."""
    pmperm.require_pm_access()
    user = frappe.session.user
    if user in ("Guest", "", None):
        frappe.throw(_("Bạn cần đăng nhập."), frappe.PermissionError)
    if reference_doctype not in _ALLOWED_REF:
        # never allow PM comments on unrelated ERP documents
        frappe.throw(_("Bình luận PM chỉ áp dụng cho Dự án hoặc Nhiệm vụ."), frappe.PermissionError)
    if not reference_name or not frappe.db.exists(reference_doctype, reference_name):
        frappe.throw(_("Không tìm thấy tài liệu."), frappe.DoesNotExistError)
    if reference_doctype == "Task":
        d = frappe.db.get_value(
            "Task", reference_name, ["name", "owner", "project", "_assign"], as_dict=True
        )
        if not pmperm.can_view_task(d, user):
            frappe.throw(_("Bạn không có quyền truy cập nhiệm vụ này."), frappe.PermissionError)
    else:  # Project
        if not pmperm.can_view_project(reference_name, user):
            frappe.throw(_("Bạn không có quyền truy cập dự án này."), frappe.PermissionError)


@frappe.whitelist()
def add(reference_doctype, reference_name, content):
    """Add a timeline comment to a PM Project/Task the caller can access. Governed + audited
    (Comment carries its own owner/creation). Returns the new comment row."""
    content = (content or "").strip()
    if not content:
        frappe.throw(_("Nội dung bình luận trống."))
    _require_access(reference_doctype, reference_name)
    doc = frappe.get_doc({
        "doctype": "Comment",
        "comment_type": "Comment",
        "reference_doctype": reference_doctype,
        "reference_name": reference_name,
        "content": content,
    })
    # PM access + can_view checked above = the trust boundary; no broad Comment DocPerm needed.
    doc.insert(ignore_permissions=True)
    return {"name": doc.name, "content": doc.content,
            "owner": doc.owner, "creation": str(doc.creation)}


@frappe.whitelist()
def list(reference_doctype, reference_name):
    """Read timeline comments for a PM Project/Task the caller can access. Access-gated first,
    then a low-level read (scoped to this reference only)."""
    _require_access(reference_doctype, reference_name)
    rows = frappe.get_all(
        "Comment",
        filters={"reference_doctype": reference_doctype,
                 "reference_name": reference_name, "comment_type": "Comment"},
        fields=["name", "content", "owner", "creation"],
        order_by="creation asc", limit_page_length=200,
    )
    return {"rows": rows}
