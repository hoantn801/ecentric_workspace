# Copyright (c) 2026, eCentric and contributors
"""PM Task Follower - người theo dõi (CC) một việc trong /pm (PO 20/10/2026).

One row per (task, user). A follower is NOT an assignee: they can view and comment, get a
notice when CC'd, when the work is done and when it runs late, and see the task under
"Tôi đã giao -> Tôi theo dõi". Written only by ecentric_workspace.pm.task_flow
(add_followers / remove_follower). `for_users` keeps which assignees an automatic CC was for
(the follower is their department head), so per-person notices go to the right manager.
"""
from frappe.model.document import Document


class PMTaskFollower(Document):
    def autoname(self):
        # Natural key -> at most ONE row per task+user even under concurrent writes.
        self.name = "{0}::{1}".format(self.task, self.user)
