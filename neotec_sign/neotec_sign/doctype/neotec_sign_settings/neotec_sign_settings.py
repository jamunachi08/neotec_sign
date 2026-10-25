# Copyright (c) 2026, Neotec Integrated Solutions

import frappe
from frappe import _
from frappe.model.document import Document


class NeotecSignSettings(Document):
	def validate(self):
		if (self.box_width or 0) < 60 or (self.box_height or 0) < 25:
			frappe.throw(_("Stamp must be at least 60 x 25 points."))
		if self.verify_base_url:
			self.verify_base_url = self.verify_base_url.rstrip("/")
