# Copyright (c) 2026, eCentric and contributors
"""PM Task Seen - "đã mở việc" tracking for the /pm redesign (16/10/2026).

One row per (task, user): first_seen = first time an assignee opened the task (tasks.get),
last_seen = latest open. Written only by ecentric_workspace.pm.task_flow.record_seen.
Read by pm_inbox.received (unopened list, rejected-unseen badge) and pm_inbox.given (opened).
"""
from frappe.model.document import Document


class PMTaskSeen(Document):
    def autoname(self):
        # Natural key -> at most ONE row per task+user even under concurrent opens
        # (a second insert raises DuplicateEntryError, which record_seen swallows).
        self.name = "{0}::{1}".format(self.task, self.user)
