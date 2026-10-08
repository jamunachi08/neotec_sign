# Copyright (c) 2026, Neotec Integrated Solutions

import frappe
from frappe import _
from frappe.model.document import Document


class NeotecSignLog(Document):
	def on_trash(self):
		if not frappe.flags.in_test and self.status == "Success":
			frappe.throw(_("Successful signature logs are permanent audit records and cannot be deleted."))
