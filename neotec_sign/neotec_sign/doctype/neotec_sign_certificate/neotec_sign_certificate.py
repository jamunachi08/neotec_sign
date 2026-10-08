# Copyright (c) 2026, Neotec Integrated Solutions

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, get_datetime, now_datetime
from frappe.utils.password import remove_encrypted_password

from neotec_sign.signing.engine import SignError, certificate_info
from neotec_sign.utils import read_file_bytes


def _typed(value):
	"""A Password field holds '*****' once saved; anything else was just typed."""
	return bool(value) and set(value) != {"*"}


class NeotecSignCertificate(Document):
	def validate(self):
		self._ensure_private_file()
		self._read_certificate()
		if self.ask_password_on_sign:
			self.password = None  # never stored

	def on_update(self):
		if self.ask_password_on_sign:
			remove_encrypted_password(self.doctype, self.name, "password")

	def _ensure_private_file(self):
		if self.pfx_file and not self.pfx_file.startswith("/private/"):
			frappe.throw(_("The certificate file must be uploaded as Private."))

	def _read_certificate(self):
		changed_file = self.has_value_changed("pfx_file")
		if _typed(self.password):
			password = self.password
		elif not self.is_new() and not self.ask_password_on_sign:
			password = self.get_password("password", raise_exception=False)
		else:
			password = None

		if password is None:
			if self.is_new() or changed_file or not self.subject:
				frappe.throw(_("Enter the certificate password so the certificate can be read and validated."))
			return
		if not (changed_file or _typed(self.password) or not self.subject):
			return

		try:
			info = certificate_info(read_file_bytes(self.pfx_file), password)
		except SignError as e:
			frappe.throw(str(e))

		self.subject = info["subject"]
		self.issuer = info["issuer"]
		self.serial_no = info["serial"]
		self.valid_from = info["valid_from"]
		self.valid_to = info["valid_to"]
		self.fingerprint = info["fingerprint"]

		if get_datetime(self.valid_to) < now_datetime():
			frappe.throw(_("This certificate expired on {0}.").format(self.valid_to))
		if get_datetime(self.valid_to) < add_days(now_datetime(), 30):
			frappe.msgprint(_("Note: this certificate expires on {0}.").format(self.valid_to), indicator="orange")
