# Copyright (c) 2026, eCentric and contributors
"""EC Internal Post - xem internal_posts/README.md."""
from frappe.model.document import Document

from ecentric_workspace.internal_posts import lifecycle


class ECInternalPost(Document):
    # Moi quy tac nam o lifecycle (dung chung cho trang viet bai va form /app).
    def validate(self):
        lifecycle.validate(self)

    def on_update(self):
        lifecycle.after_save(self)

    def on_trash(self):
        lifecycle.on_trash(self)
