# Copyright (c) 2026, eCentric and contributors
"""EC Teams Conversation: per-user Bot Framework conversation reference for 1:1 proactive
messaging. One row per ERP user (autoname field:user). Holds the Entra Object ID and the
conversation reference captured when the user installs/opens the eCentric ERP Bot (or set
up via Graph proactive install). System-Manager only -- it is bot infrastructure, never
user-facing. Secrets (bot password, Graph secret) are NOT stored here; only non-secret
conversation identifiers."""
import frappe
from frappe.model.document import Document


class ECTeamsConversation(Document):
    pass
