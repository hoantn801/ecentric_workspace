# Copyright (c) 2026, eCentric and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import get_datetime, time_diff_in_hours


class ECPMTimeBlock(Document):
	def validate(self):
		if self.start and self.end:
			if get_datetime(self.end) <= get_datetime(self.start):
				frappe.throw("Giờ kết thúc phải sau giờ bắt đầu.")
			# hours is DERIVED from the block span (single source of truth for the slot);
			# confirmed actual hours may be edited by the owner at confirm time.
			if not self.get("hours"):
				self.hours = round(time_diff_in_hours(self.end, self.start), 2)
		if not self.user:
			self.user = frappe.session.user
		if not self.state:
			self.state = "Dự kiến"
