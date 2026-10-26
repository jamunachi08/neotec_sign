# Copyright (c) 2026, Neotec Integrated Solutions

import frappe
from frappe import _
from frappe.model.document import Document

from neotec_sign.signing.engine import SignError, resolve_pages
from neotec_sign.utils import clear_rule_cache


class NeotecSignRule(Document):
	def validate(self):
		meta = frappe.get_meta(self.document_type)
		if meta.istable or meta.issingle:
			frappe.throw(_("Choose a normal document type (not a child table or single)."))
		if self.print_format:
			pf_dt = frappe.db.get_value("Print Format", self.print_format, "doc_type")
			if pf_dt and pf_dt != self.document_type:
				frappe.throw(_("Print Format {0} belongs to {1}.").format(self.print_format, pf_dt))
		if self.pages:
			try:
				resolve_pages(self.pages, 9999)
			except SignError as e:
				frappe.throw(str(e))
		if self.auto_sign_on_submit:
			if not meta.is_submittable:
				frappe.throw(_("{0} is not submittable, so it cannot be signed on submit.").format(self.document_type))
			cert = self.certificate or frappe.db.get_single_value("Neotec Sign Settings", "default_certificate")
			if not cert:
				frappe.throw(_("Automatic signing needs a certificate (here or in Neotec Sign Settings)."))
			if frappe.db.get_value("Neotec Sign Certificate", cert, "ask_password_on_sign"):
				frappe.throw(_("Certificate {0} asks for a password at every signing, so it cannot sign automatically.").format(cert))

	def on_update(self):
		clear_rule_cache()

	def on_trash(self):
		clear_rule_cache()
