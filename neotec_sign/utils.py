# Copyright (c) 2026, Neotec Integrated Solutions

import frappe
from frappe import _

RULE_CACHE_KEY = "neotec_sign_rules"


def read_file_bytes(file_url: str) -> bytes:
	name = frappe.db.get_value("File", {"file_url": file_url}, "name")
	if not name:
		frappe.throw(_("File {0} not found.").format(file_url))
	return frappe.get_doc("File", name).get_content()


def get_rules() -> dict:
	"""{doctype: rule dict} for enabled rules — cached, cleared on any rule change."""

	def _load():
		rows = frappe.get_all(
			"Neotec Sign Rule",
			filters={"enabled": 1},
			fields=["name", "document_type", "certificate", "print_format", "letter_head", "pages",
				"position", "allow_custom_position", "auto_sign_on_submit", "condition"],
		)
		return {r.document_type: r for r in rows}

	return frappe.cache.get_value(RULE_CACHE_KEY, _load)


def get_rule(doctype: str):
	rule = (get_rules() or {}).get(doctype)
	return frappe._dict(rule) if rule else None


def clear_rule_cache():
	frappe.cache.delete_value(RULE_CACHE_KEY)
