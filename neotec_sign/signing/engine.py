# Copyright (c) 2026, Neotec Integrated Solutions
# Pure PDF signing engine — no Frappe imports so it can be unit-tested standalone.

import hashlib
from dataclasses import dataclass
from io import BytesIO

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.serialization import pkcs12
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.pdf_utils.reader import PdfFileReader
from pyhanko.sign import fields, signers
from pyhanko.sign.timestamps import HTTPTimeStamper
from pyhanko.stamp import QRStampStyle, TextStampStyle

DEFAULT_W, DEFAULT_H, MARGIN = 190.0, 60.0, 36.0
PRESETS = ("Bottom Right", "Bottom Left", "Bottom Center", "Top Right", "Top Left")


class SignError(Exception):
	pass


# ---------------------------------------------------------------- certificates
_NOT_CERT = {
	b"\xff\xd8\xff": "a JPEG image",
	b"\x89PNG": "a PNG image",
	b"GIF8": "a GIF image",
	b"%PDF": "a PDF document",
	b"PK\x03\x04": "a ZIP/Office file",
	b"-----BEGIN": "a PEM text file (convert it to .pfx first)",
}


def file_kind_problem(data: bytes) -> str | None:
	"""Explain why a file is clearly not a PKCS#12 certificate, or None if it may be one."""
	if not data:
		return "The certificate file is empty."
	for magic, kind in _NOT_CERT.items():
		if data.startswith(magic):
			return (f"The uploaded file is {kind}, not a certificate. Upload the .pfx or .p12 file "
				"issued by your certificate provider. A signature picture goes in 'Signature Image'.")
	if data[:1] != b"\x30":  # PKCS#12 is DER: always starts with a SEQUENCE tag
		return "The uploaded file is not a PFX/P12 certificate."
	return None


def _load_p12(pfx_bytes: bytes, password: str | None):
	problem = file_kind_problem(pfx_bytes)
	if problem:
		raise SignError(problem)
	try:
		return pkcs12.load_key_and_certificates(pfx_bytes, (password or "").encode() or None)
	except ValueError as e:
		raise SignError("Wrong certificate password (the file is a valid certificate, but it would not open).") from e


def certificate_info(pfx_bytes: bytes, password: str | None) -> dict:
	"""Return human-readable details of the signing certificate inside a PFX."""
	key, cert, _chain = _load_p12(pfx_bytes, password)
	if not key or not cert:
		raise SignError("The PFX file has no private key or no certificate.")

	def _cn(name):
		attrs = name.get_attributes_for_oid(x509.NameOID.COMMON_NAME)
		return attrs[0].value if attrs else name.rfc4514_string()

	return {
		"subject": _cn(cert.subject),
		"subject_dn": cert.subject.rfc4514_string(),
		"issuer": _cn(cert.issuer),
		"serial": format(cert.serial_number, "X"),
		"valid_from": cert.not_valid_before_utc.replace(tzinfo=None),
		"valid_to": cert.not_valid_after_utc.replace(tzinfo=None),
		"fingerprint": cert.fingerprint(hashes.SHA256()).hex().upper(),
		"self_signed": cert.subject == cert.issuer,
	}


def make_test_pfx(common_name: str, password: str, organisation: str = "", days: int = 365) -> bytes:
	"""Self-signed certificate for TESTING only — real documents need a CA-issued certificate."""
	import datetime

	from cryptography.hazmat.primitives import serialization
	from cryptography.hazmat.primitives.asymmetric import rsa

	if not password or len(password) < 6:
		raise SignError("Choose a password of at least 6 characters.")
	key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
	attrs = [x509.NameAttribute(x509.NameOID.COMMON_NAME, common_name)]
	if organisation:
		attrs.append(x509.NameAttribute(x509.NameOID.ORGANIZATION_NAME, organisation))
	name = x509.Name(attrs)
	now = datetime.datetime.now(datetime.timezone.utc)
	cert = (
		x509.CertificateBuilder()
		.subject_name(name).issuer_name(name).public_key(key.public_key())
		.serial_number(x509.random_serial_number())
		.not_valid_before(now - datetime.timedelta(minutes=5))
		.not_valid_after(now + datetime.timedelta(days=days))
		.add_extension(x509.KeyUsage(True, True, False, False, False, False, False, False, False), critical=True)
		.sign(key, hashes.SHA256())
	)
	return pkcs12.serialize_key_and_certificates(
		common_name.encode(), key, cert, None, serialization.BestAvailableEncryption(password.encode())
	)


def load_signer(pfx_bytes: bytes, password: str | None) -> signers.SimpleSigner:
	_load_p12(pfx_bytes, password)  # friendly error first
	signer = signers.SimpleSigner.load_pkcs12_data(
		pfx_bytes, other_certs=[], passphrase=(password or "").encode() or None
	)
	if signer is None:
		raise SignError("Could not load the signing key from the certificate.")
	return signer


# ---------------------------------------------------------------- geometry
def _inherited(page, key):
	node = page
	while node is not None:
		if key in node:
			return node[key]
		node = node.get("/Parent")
		node = node.get_object() if node is not None else None
	return None


def page_boxes(pdf_bytes: bytes) -> list[tuple[float, float, float, float]]:
	"""Visible box (x0, y0, x1, y1) of every page, honouring CropBox."""
	reader = PdfFileReader(BytesIO(pdf_bytes))
	count = int(reader.root["/Pages"]["/Count"])
	out = []
	for i in range(count):
		page = reader.find_page_for_modification(i)[0].get_object()
		box = _inherited(page, "/CropBox") or _inherited(page, "/MediaBox") or [0, 0, 595, 842]
		x0, y0, x1, y1 = (float(v) for v in box)
		out.append((min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)))
	return out


def resolve_pages(spec: str, total: int) -> list[int]:
	"""'Last', 'First', 'All' or a range like '1,3-5' -> sorted 0-based indexes."""
	spec = (spec or "Last").strip()
	key = spec.lower()
	if key == "last":
		return [total - 1]
	if key == "first":
		return [0]
	if key == "all":
		return list(range(total))
	pages = set()
	for part in spec.replace(" ", "").split(","):
		if not part:
			continue
		try:
			if "-" in part:
				a, b = (int(v) for v in part.split("-", 1))
				pages.update(range(min(a, b), max(a, b) + 1))
			else:
				pages.add(int(part))
		except ValueError as e:
			raise SignError(f"Invalid page range: {spec}") from e
	result = sorted(p - 1 for p in pages if 1 <= p <= total)
	if not result:
		raise SignError(f"Page range '{spec}' does not match any page (document has {total}).")
	return result


def preset_box(page_box, preset: str, w=DEFAULT_W, h=DEFAULT_H):
	x0, y0, x1, y1 = page_box
	preset = preset or "Bottom Right"
	if preset not in PRESETS:
		raise SignError(f"Unknown position: {preset}")
	if "Right" in preset:
		x = x1 - MARGIN - w
	elif "Left" in preset:
		x = x0 + MARGIN
	else:
		x = (x0 + x1 - w) / 2
	y = (y1 - MARGIN - h) if preset.startswith("Top") else (y0 + MARGIN)
	return (round(x, 2), round(y, 2), round(x + w, 2), round(y + h, 2))


def build_placements(pdf_bytes, pages="Last", preset="Bottom Right", custom=None, w=DEFAULT_W, h=DEFAULT_H):
	"""Return [(page_index, (x0,y0,x1,y1)), ...].

	custom: list of {"page": 1-based, "x": .., "y": .., "w": .., "h": ..} in PDF points
	(bottom-left origin) — typically picked visually in the browser.
	"""
	boxes = page_boxes(pdf_bytes)
	total = len(boxes)
	if custom:
		out = []
		for c in custom:
			p = int(c.get("page", total)) - 1
			if not 0 <= p < total:
				raise SignError(f"Page {p + 1} is out of range (document has {total}).")
			cw, ch = float(c.get("w") or w), float(c.get("h") or h)
			x, y = float(c["x"]), float(c["y"])
			out.append((p, (round(x, 2), round(y, 2), round(x + cw, 2), round(y + ch, 2))))
		return out
	return [(p, preset_box(boxes[p], preset, w, h)) for p in resolve_pages(pages, total)]


# ---------------------------------------------------------------- signing
@dataclass
class StampOptions:
	text: str = "Digitally signed by\n%(signer)s\n%(ts)s"
	verify_url: str | None = None  # when set, a QR code pointing here is drawn
	image: bytes | None = None  # handwritten signature / company seal shown behind the text


def _background(image_bytes):
	from PIL import Image
	from pyhanko.pdf_utils.images import PdfImage

	try:
		img = Image.open(BytesIO(image_bytes))
		img.load()
	except Exception as e:
		raise SignError("The signature image could not be read. Use a PNG or JPEG.") from e
	if img.mode not in ("RGB", "L"):
		bg = Image.new("RGB", img.size, "white")  # flatten transparency onto white
		bg.paste(img, mask=img.convert("RGBA").split()[-1])
		img = bg
	img.thumbnail((600, 300))
	return PdfImage(img)


def sign_pdf(pdf_bytes, signer, placements, reason="", location="", contact="", stamp=None, tsa_url=None):
	"""Apply one visible signature per placement. Returns signed PDF bytes."""
	if not placements:
		raise SignError("Nothing to sign — no signature placement given.")
	stamp = stamp or StampOptions()
	timestamper = HTTPTimeStamper(tsa_url) if tsa_url else None

	extra = {}
	if stamp.image:
		extra = {"background": _background(stamp.image), "background_opacity": 0.45}
	if stamp.verify_url:
		style = QRStampStyle(stamp_text=stamp.text + "\nScan to verify", border_width=1, **extra)
		params = {"url": stamp.verify_url}
	else:
		style = TextStampStyle(stamp_text=stamp.text, border_width=1, **extra)
		params = {}

	current = BytesIO(pdf_bytes)
	for n, (page, box) in enumerate(placements, start=1):
		current.seek(0)
		writer = IncrementalPdfFileWriter(current, strict=False)
		name = f"NeotecSig{n}_P{page + 1}"
		fields.append_signature_field(writer, fields.SigFieldSpec(sig_field_name=name, box=box, on_page=page))
		meta = signers.PdfSignatureMetadata(
			field_name=name,
			reason=reason or None,
			location=location or None,
			contact_info=contact or None,
			md_algorithm="sha256",
		)
		pdf_signer = signers.PdfSigner(meta, signer=signer, stamp_style=style, timestamper=timestamper)
		out = BytesIO()
		pdf_signer.sign_pdf(writer, output=out, appearance_text_params=params)
		current = out
	return current.getvalue()


def sha256(data: bytes) -> str:
	return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------- inspection
def inspect_signatures(pdf_bytes: bytes) -> list[dict]:
	"""Integrity check of every embedded signature (trust chain not evaluated)."""
	import logging

	from pyhanko.sign.validation import validate_pdf_signature

	# Trust-path warnings are expected (no trust roots configured) — keep logs quiet.
	for name in ("pyhanko", "pyhanko_certvalidator"):
		logging.getLogger(name).setLevel(logging.ERROR)

	reader = PdfFileReader(BytesIO(pdf_bytes), strict=False)
	results = []
	for sig in reader.embedded_signatures:
		try:
			st = validate_pdf_signature(sig)
			cert = sig.signer_cert
			results.append(
				{
					"field": sig.field_name,
					"signer": cert.subject.native.get("common_name") if cert else None,
					"intact": bool(st.intact),
					"cryptographically_valid": bool(st.valid),
					"covers_whole_document": st.coverage.name == "ENTIRE_FILE",
					"modification_level": getattr(st.modification_level, "name", None),
					"signed_at": str(st.signer_reported_dt) if st.signer_reported_dt else None,
				}
			)
		except Exception as e:  # pragma: no cover - defensive
			results.append({"field": sig.field_name, "error": str(e)})
	return results
