# Copyright (c) 2026, eCentric and contributors
"""EC Approval Participant - generic child (Approver/Fulfiller/Notify).
Row-level validation runs in the parent (EC Approval Process / EC Approval Level)
via approval_center.engine.participant_rules."""
from frappe.model.document import Document


class ECApprovalParticipant(Document):
    pass
