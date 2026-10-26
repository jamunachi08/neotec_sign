# Copyright (c) 2026, Neotec Integrated Solutions
"""Signing workflow: permissions -> PDF -> sign -> attach -> audit log."""

import secrets

import frappe
from frappe import _
from frappe.utils import get_datetime, get_url, now_datetime

from neotec_sign import __version__
from neotec_sign.signing import engine
from neotec_sign.utils import get_rule, read_file_bytes

SIGNER_ROLE = "Neotec Signer"


def settings():
	return frappe.get_cached_doc("Neotec Sign Settings")


# ---------------------------------------------------------------- permissions
def allowed_roles(cert) -> set:
	return {r.role for r in (cert.allowed_roles or [])} or {SIGNER_ROLE}


def usable_certificates(doc=None, user=None) -> list:
	"""Enabled, unexpired certificates this user may use for this document."""
	user = user or frappe.session.user
	roles = set(frappe.get_roles(user))
	company = doc.get("company") if doc else None
	out = []
	for name in frappe.get_all("Neotec Sign Certificate", filters={"enabled": 1}, pluck="name"):
		cert = frappe.get_cached_doc("Neotec Sign Certificate", name)
		if cert.valid_to and get_datetime(cert.valid_to) < now_datetime():
			continue
		if cert.company and company and cert.company != company:
			continue
		if user != "Administrator" and not (allowed_roles(cert) & roles):
			continue
		out.append(cert)
	return out


def check_can_sign(doc, cert):
	if not settings().enabled:
		frappe.throw(_("Digital signing is disabled in Neotec Sign Settings."))
	doc.check_permission("read")
	if doc.meta.is_submittable and doc.docstatus != 1:
		frappe.throw(_("Only submitted documents can be signed."))
	if cert.name not in {c.name for c in usable_certificates(doc)}:
		frappe.throw(_("You are not allowed to sign this document with certificate {0}.").format(cert.name),
			frappe.PermissionError)


# ---------------------------------------------------------------- main flow
def render_pdf(doc, print_format=None, letter_head=None) -> tuple[bytes, list[str]]:
	"""Standard print PDF. If the PDF engine fails on images it cannot load, rebuild the page with
	every image embedded from disk and leave out (and report) only the ones that truly don't exist."""
	kwargs = dict(print_format=print_format or None, doc=doc, letterhead=letter_head or None, no_letterhead=0)
	try:
		return frappe.get_print(doc.doctype, doc.name, as_pdf=True, **kwargs), []
	except frappe.ValidationError as e:
		if "broken image" not in str(e).lower():
			raise
		if getattr(frappe.local, "message_log", None):
			frappe.local.message_log.pop()  # we recover below; don't show Frappe's error

	from frappe.utils.pdf import get_pdf

	from neotec_sign import pdf_images

	diagnostics = {}
	html = frappe.get_print(doc.doctype, doc.name, as_pdf=False, **kwargs)
	html, broken = pdf_images.inline_images(html, pdf_images.make_frappe_resolver(diagnostics))
	leftovers = pdf_images.remaining_references(html)
	html = pdf_images.neutralise_references(html)

	if broken or leftovers:
		report = [f"Neotec Sign {__version__} — {doc.doctype} {doc.name}", "", "Not found:"]
		for url in broken:
			report.append(f"  {url}")
			report.extend(f"      - {line}" for line in diagnostics.get(url, []))
		if leftovers:
			report += ["", "Other references removed before rendering:"] + [f"  {u}" for u in leftovers]
		frappe.log_error("\n".join(report), f"Neotec Sign: resources left out of {doc.name}")

	if broken and settings().strict_images:
		frappe.throw(
			_("These images in the print format or letter head could not be found: {0}").format(
				"<br>" + "<br>".join(frappe.bold(u) for u in broken)),
			title=_("Missing Images"),
		)

	try:
		return get_pdf(html), broken
	except Exception:
		if getattr(frappe.local, "message_log", None):
			frappe.local.message_log.pop()
		frappe.log_error(frappe.get_traceback(), f"Neotec Sign {__version__}: PDF rebuild failed for {doc.name}")
		frappe.throw(
			_("The print format could not be turned into a PDF even with every external link removed. "
			"Full details are in the Error Log ('Neotec Sign … PDF rebuild failed'). Missing: {0}").format(
				", ".join(broken) or _("none")),
			title=_("PDF Failed"),
		)


def resolve_options(doc, certificate=None, print_format=None, letter_head=None, pages=None, position=None):
	s, rule = settings(), get_rule(doc.doctype) or frappe._dict()
	cert_name = certificate or rule.certificate or s.default_certificate
	if not cert_name:
		frappe.throw(_("No signing certificate configured."))
	return frappe._dict(
		cert=frappe.get_cached_doc("Neotec Sign Certificate", cert_name),
		print_format=print_format or rule.print_format,
		letter_head=letter_head or rule.letter_head,
		pages=pages or rule.pages or s.default_pages or "Last",
		position=position or rule.position or s.default_position or "Bottom Right",
		allow_custom=bool(rule.get("allow_custom_position", 1)),
	)


def sign_document(doc, certificate=None, print_format=None, letter_head=None, pages=None,
		position=None, placements=None, password=None, mode="Manual"):
	s = settings()
	opt = resolve_options(doc, certificate, print_format, letter_head, pages, position)
	cert = opt.cert
	check_can_sign(doc, cert)
	if placements and not opt.allow_custom:
		frappe.throw(_("Custom signature positions are not allowed for {0}.").format(doc.doctype))

	log = frappe.new_doc("Neotec Sign Log")
	log.update({
		"reference_doctype": doc.doctype, "reference_name": doc.name, "mode": mode,
		"signed_by": frappe.session.user, "signed_on": now_datetime(), "certificate": cert.name,
		"signer_subject": cert.subject, "cert_serial": cert.serial_no,
		"print_format": opt.print_format, "verification_code": secrets.token_hex(8).upper(),
	})

	try:
		if cert.ask_password_on_sign:
			if not password:
				frappe.throw(_("Certificate password is required."))
		else:
			password = cert.get_password("password")

		signer = engine.load_signer(read_file_bytes(cert.pfx_file), password)
		pdf, missing_images = render_pdf(doc, opt.print_format, opt.letter_head)
		w, h = s.box_width or engine.DEFAULT_W, s.box_height or engine.DEFAULT_H
		plan = engine.build_placements(pdf, pages=opt.pages, preset=opt.position, custom=placements, w=w, h=h)

		verify_url = None
		if s.add_qr_code:
			base = s.verify_base_url or get_url()
			verify_url = f"{base}/sign-verify?code={log.verification_code}"

		signed = engine.sign_pdf(
			pdf, signer, plan,
			reason=cert.reason or _("Approved"), location=cert.location or "", contact=cert.contact or "",
			stamp=engine.StampOptions(
				text=s.stamp_text or engine.StampOptions.text,
				verify_url=verify_url,
				image=read_file_bytes(cert.signature_image) if cert.signature_image else None,
			),
			tsa_url=s.tsa_url or None,
		)
	except frappe.ValidationError as e:
		_fail(log, str(e))
		raise  # message already shown once by frappe.throw — don't repeat it
	except engine.SignError as e:
		_fail(log, str(e))
		frappe.throw(str(e))
	except Exception:
		_fail(log, frappe.get_traceback())
		frappe.throw(_("Signing failed. Details were saved in Neotec Sign Log {0}.").format(log.name))

	file_doc = frappe.get_doc({
		"doctype": "File",
		"file_name": f"{doc.name.replace('/', '-')}-signed.pdf",
		"attached_to_doctype": doc.doctype,
		"attached_to_name": doc.name,
		"is_private": 1,
		"content": signed,
	}).insert(ignore_permissions=True)

	log.update({
		"status": "Success", "signed_file": file_doc.file_url, "sha256": engine.sha256(signed),
		"pages_signed": ", ".join(str(p + 1) for p, _box in plan),
		"warnings": "\n".join(f"Missing image: {u}" for u in missing_images) or None,
	})
	log.insert(ignore_permissions=True)
	doc.add_comment("Info", _("Digitally signed by {0} ({1}). Verification code {2}.").format(
		cert.subject, frappe.session.user, log.verification_code))
	return {"file_url": file_doc.file_url, "log": log.name, "verification_code": log.verification_code,
		"missing_images": missing_images}


def _fail(log, error):
	try:
		log.status = "Failed"
		log.error = (error or "")[:2000]
		log.insert(ignore_permissions=True)
		frappe.db.commit()  # keep the failure record even though the request rolls back
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Neotec Sign: could not write log")


def auto_sign(doctype, name):
	"""Background job enqueued on submit."""
	doc = frappe.get_doc(doctype, name)
	try:
		sign_document(doc, mode="Auto")
	except Exception:
		frappe.log_error(frappe.get_traceback(), f"Neotec Sign: auto-sign failed for {doctype} {name}")
