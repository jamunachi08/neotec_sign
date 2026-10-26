# Copyright (c) 2026, Neotec Integrated Solutions

import frappe

from neotec_sign.utils import get_rule


def on_submit(doc, method=None):
	rule = get_rule(doc.doctype)
	if not rule or not rule.auto_sign_on_submit:
		return
	if rule.condition and not frappe.safe_eval(rule.condition, None, {"doc": doc}):
		return
	frappe.enqueue(
		"neotec_sign.services.auto_sign",
		doctype=doc.doctype, name=doc.name,
		queue="default", enqueue_after_commit=True,
		job_id=f"neotec_sign::{doc.doctype}::{doc.name}", deduplicate=True,
	)
