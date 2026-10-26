# Copyright (c) 2026, Neotec Integrated Solutions
"""Public verification page: /sign-verify?code=XXXX"""

import re

import frappe
from frappe import _

no_cache = 1


def get_context(context):
	context.no_cache = 1
	context.title = _("Verify Digital Signature")
	context.code = (frappe.form_dict.get("code") or "").strip().upper()
	context.enabled = bool(frappe.db.get_single_value("Neotec Sign Settings", "public_verification"))
	context.record = None
	if context.enabled and re.fullmatch(r"[0-9A-F]{16}", context.code):
		context.record = frappe.db.get_value(
			"Neotec Sign Log",
			{"verification_code": context.code, "status": "Success"},
			["reference_doctype", "reference_name", "signer_subject", "signed_on", "sha256", "pages_signed"],
			as_dict=True,
		)
	return context
