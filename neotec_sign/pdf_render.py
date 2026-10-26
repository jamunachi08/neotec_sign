# Copyright (c) 2026, Neotec Integrated Solutions
"""PDF rendering that survives missing resources.

wkhtmltopdf writes a complete PDF and then exits with code 1 when any resource answers 404
("Exit with code 1 due to network error: ContentNotFoundError"). Frappe renders in memory, so
pdfkit raises before returning the bytes and the finished PDF is lost. Here we render to a
temporary file instead and keep it when it is a complete PDF, recording what failed to load.
"""

import os
import tempfile

NOISE = ("Fontconfig warning", "Fontconfig error")


KEEP = ("Warning:", "Error:", "Exit with code")


def useful_lines(stderr: str) -> list[str]:
	"""Only the lines that say what failed — e.g. 'Warning: Failed to load <url>' — without the
	hundreds of harmless Fontconfig lines or progress bars. Duplicates removed, order kept."""
	out = []
	for raw in (stderr or "").replace("\r", "\n").splitlines():
		line = raw.strip()
		if line.startswith(KEEP) and not line.startswith(NOISE) and line not in out:
			out.append(line)
	return out


def is_complete_pdf(data: bytes) -> bool:
	return data[:5] == b"%PDF-" and b"%%EOF" in data[-2048:]


def run_wkhtmltopdf(html: str, options: dict, configuration=None) -> tuple[bytes, list[str]]:
	"""Render html with already-prepared wkhtmltopdf options. Returns (pdf_bytes, warnings)."""
	import pdfkit

	fd, out = tempfile.mkstemp(prefix="neotec-sign-", suffix=".pdf")
	os.close(fd)
	warnings = []
	try:
		try:
			pdfkit.from_string(html, out, options=options, verbose=True, configuration=configuration)
		except OSError as e:
			warnings = useful_lines(str(e))
			with open(out, "rb") as f:
				data = f.read()
			if not is_complete_pdf(data):
				raise RuntimeError("wkhtmltopdf failed:\n" + "\n".join(warnings or [str(e)[-500:]])) from e
			return data, warnings
		with open(out, "rb") as f:
			data = f.read()
		if not is_complete_pdf(data):
			raise RuntimeError("wkhtmltopdf produced an incomplete PDF.")
		return data, warnings
	finally:
		try:
			os.remove(out)
		except OSError:
			pass


def render_with_frappe_options(html: str) -> tuple[bytes, list[str]]:
	"""Same page setup as Frappe's get_pdf (size, margins, letter head header/footer), tolerant output."""
	from frappe.utils import scrub_urls
	from frappe.utils.pdf import cleanup, get_wkhtmltopdf_version, prepare_options
	from packaging.version import Version

	html = scrub_urls(html)
	html, options = prepare_options(html, {})
	options.update({"disable-javascript": "", "disable-local-file-access": ""})
	try:
		if Version(get_wkhtmltopdf_version()) > Version("0.12.3"):
			options["disable-smart-shrinking"] = ""
	except Exception:
		pass
	options.update({"load-error-handling": "ignore", "load-media-error-handling": "ignore"})
	options.pop("password", None)  # a signed PDF must not be password-encrypted
	options.pop("quiet", None)  # let wkhtmltopdf name the URL it could not load
	try:
		return run_wkhtmltopdf(html, options)
	finally:
		cleanup(options)  # removes Frappe's temporary header/footer files
