# Copyright (c) 2026, Neotec Integrated Solutions

import frappe

from neotec_sign.utils import get_rules


def boot_session(bootinfo):
	if frappe.session.user == "Guest":
		return
	try:
		bootinfo.neotec_sign = {"doctypes": sorted((get_rules() or {}).keys())}
	except Exception:
		bootinfo.neotec_sign = {"doctypes": []}  # e.g. during install before tables exist
