# Copyright (c) 2026, Neotec Integrated Solutions

import base64
import json

import frappe
from frappe import _

from neotec_sign import services
from neotec_sign.signing import engine
from neotec_sign.utils import get_rule, read_file_bytes


@frappe.whitelist()
def get_sign_context(doctype: str, name: str):
	doc = frappe.get_doc(doctype, name)
	doc.check_permission("read")
	s, rule = services.settings(), get_rule(doctype) or frappe._dict()
	certs = services.usable_certificates(doc)
	default = rule.certificate or s.default_certificate
	return {
		"enabled": bool(s.enabled),
		"certificates": [
			{"name": c.name, "subject": c.subject, "valid_to": c.valid_to, "ask_password": c.ask_password_on_sign}
			for c in certs
		],
		"default_certificate": default if default in {c.name for c in certs} else (certs[0].name if certs else None),
		"print_formats": frappe.get_all("Print Format", filters={"doc_type": doctype, "disabled": 0}, pluck="name"),
		"print_format": rule.print_format,
		"letter_head": rule.letter_head,
		"pages": rule.pages or s.default_pages or "Last",
		"position": rule.position or s.default_position or "Bottom Right",
		"allow_custom_position": bool(rule.get("allow_custom_position", 1)),
		"box": {"w": s.box_width or engine.DEFAULT_W, "h": s.box_height or engine.DEFAULT_H},
		"signed_count": frappe.db.count("Neotec Sign Log",
			{"reference_doctype": doctype, "reference_name": name, "status": "Success"}),
	}


@frappe.whitelist()
def preview_pdf(doctype: str, name: str, print_format: str | None = None):
	"""Unsigned PDF exactly as it will be signed, plus page geometry for the position picker."""
	doc = frappe.get_doc(doctype, name)
	doc.check_permission("read")
	opt = services.resolve_options(doc, print_format=print_format)
	pdf = services.render_pdf(doc, opt.print_format, opt.letter_head)
	return {"pdf": base64.b64encode(pdf).decode(), "pages": engine.page_boxes(pdf)}


@frappe.whitelist(methods=["POST"])
def sign(doctype: str, name: str, certificate: str | None = None, print_format: str | None = None,
		pages: str | None = None, position: str | None = None, placements: str | None = None,
		password: str | None = None):
	doc = frappe.get_doc(doctype, name)
	custom = json.loads(placements) if placements else None
	return services.sign_document(doc, certificate=certificate, print_format=print_format, pages=pages,
		position=position, placements=custom, password=password)


@frappe.whitelist()
def check_file(file_url: str):
	"""Integrity check of signatures inside an attached PDF."""
	file_name = frappe.db.get_value("File", {"file_url": file_url}, "name")
	if not file_name:
		frappe.throw(_("File not found."))
	file_doc = frappe.get_doc("File", file_name)
	if not file_doc.is_downloadable():
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	data = read_file_bytes(file_url)
	log = frappe.db.get_value("Neotec Sign Log", {"signed_file": file_url, "status": "Success"},
		["name", "sha256", "verification_code"], as_dict=True)
	return {
		"signatures": engine.inspect_signatures(data),
		"sha256": engine.sha256(data),
		"matches_log": bool(log and log.sha256 == engine.sha256(data)),
		"log": log.name if log else None,
	}


@frappe.whitelist(methods=["POST"])
def create_test_certificate(common_name: str, password: str, organisation: str | None = None):
	"""Self-signed PFX so the app can be tried before a real certificate arrives. Testing only."""
	frappe.only_for(("System Manager", "Neotec Sign Manager"))
	try:
		data = engine.make_test_pfx(common_name.strip(), password, (organisation or "").strip())
	except engine.SignError as e:
		frappe.throw(str(e))
	file_doc = frappe.get_doc({
		"doctype": "File",
		"file_name": f"test-{frappe.scrub(common_name)}.pfx",
		"is_private": 1,
		"content": data,
	}).insert(ignore_permissions=True)
	return file_doc.file_url
