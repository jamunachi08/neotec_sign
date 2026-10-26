# Copyright (c) 2026, Neotec Integrated Solutions
"""Idempotent seeders — safe to run on every migrate."""

import frappe

ROLES = ("Neotec Sign Manager", "Neotec Signer")
DEFAULTS = {
	"enabled": 1,
	"stamp_text": "Digitally signed by\n%(signer)s\n%(ts)s",
	"add_qr_code": 1,
	"default_position": "Bottom Right",
	"default_pages": "Last",
	"box_width": 190,
	"box_height": 60,
	"public_verification": 1,
}


def after_install():
	seed()


def after_migrate():
	seed()


def seed():
	for role in ROLES:
		if not frappe.db.exists("Role", role):
			frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(ignore_permissions=True)

	for field, value in DEFAULTS.items():
		if frappe.db.get_single_value("Neotec Sign Settings", field) in (None, "", 0) and value:
			if field in ("enabled", "add_qr_code", "public_verification") and frappe.db.get_value(
				"Singles", {"doctype": "Neotec Sign Settings", "field": field}):
				continue  # admin deliberately switched it off — respect that
			frappe.db.set_single_value("Neotec Sign Settings", field, value)
	frappe.db.commit()
