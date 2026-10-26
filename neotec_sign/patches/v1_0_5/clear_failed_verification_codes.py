# Copyright (c) 2026, Neotec Integrated Solutions
"""Failed signing attempts never produced a signed file, so they must not carry a verification code."""

import frappe


def execute():
	frappe.db.sql(
		"""update `tabNeotec Sign Log` set verification_code = NULL
		where status = 'Failed' and verification_code is not null"""
	)
