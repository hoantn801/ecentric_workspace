# Copyright (c) 2026, eCentric and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

from ecentric_workspace.ai_tools.features.ai_live import constants as C
from ecentric_workspace.ai_tools.features.ai_live.application.validate_session_service import ValidateSessionService


class ECAILiveSession(Document):
	def validate(self):
		try:
			ValidateSessionService().execute(self)
		except C.AiLiveError as e:
			if self.flags.get("ec_create"):  # 18/11: tao tu /ai-live -> giu ma loi + o sai cho trang hien duoi o
				raise
			frappe.throw(str(e))
