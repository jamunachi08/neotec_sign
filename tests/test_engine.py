"""Standalone engine test: python tests/test_engine.py (no bench needed)."""
import datetime, sys, os
from io import BytesIO
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "neotec_sign", "signing"))
import engine  # noqa
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID


def make_pfx(pw=b"secret"):
	key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
	name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Neotec Test Signer")])
	now = datetime.datetime.now(datetime.timezone.utc)
	cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
		.serial_number(x509.random_serial_number()).not_valid_before(now - datetime.timedelta(days=1))
		.not_valid_after(now + datetime.timedelta(days=365))
		.add_extension(x509.KeyUsage(True, True, False, False, False, False, False, False, False), critical=True)
		.sign(key, hashes.SHA256()))
	return pkcs12.serialize_key_and_certificates(b"t", key, cert, None, serialization.BestAvailableEncryption(pw))


def make_pdf(pages=3):
	from reportlab.pdfgen import canvas
	from reportlab.lib.pagesizes import A4, landscape
	buf = BytesIO(); c = canvas.Canvas(buf, pagesize=A4)
	for i in range(pages):
		if i == 1: c.setPageSize(landscape(A4))
		c.drawString(72, 300, f"Invoice page {i+1}"); c.showPage()
	c.save(); return buf.getvalue()


pfx, pdf = make_pfx(), make_pdf()
info = engine.certificate_info(pfx, "secret"); assert info["subject"] == "Neotec Test Signer", info
try:
	engine.certificate_info(pfx, "wrong"); raise AssertionError("bad pw accepted")
except engine.SignError: pass

assert engine.resolve_pages("Last", 3) == [2]
assert engine.resolve_pages("1,3-5", 3) == [0, 2]
assert engine.resolve_pages("All", 3) == [0, 1, 2]
boxes = engine.page_boxes(pdf); assert boxes[1][2] > boxes[1][3]  # landscape
print("boxes", boxes)

signer = engine.load_signer(pfx, "secret")
for label, kwargs, stamp in [
	("preset-all", dict(pages="All", preset="Bottom Right"), engine.StampOptions(verify_url="https://example.com/sign-verify?code=ABC")),
	("custom", dict(custom=[{"page": 2, "x": 500, "y": 400}]), engine.StampOptions()),
]:
	pl = engine.build_placements(pdf, **kwargs)
	out = engine.sign_pdf(pdf, signer, pl, reason="Approved", location="Riyadh", stamp=stamp)
	res = engine.inspect_signatures(out)
	print(label, pl, res)
	assert len(res) == len(pl) and all(r["intact"] for r in res)
	assert res[-1]["covers_whole_document"]
	open(f"/tmp/{label}.pdf", "wb").write(out)
print("ALL ENGINE TESTS PASSED")

# --- v1.0.1: wrong file types, test certificate, signature image
from PIL import Image, ImageDraw
img = Image.new("RGB", (400, 150), "white"); dr = ImageDraw.Draw(img)
dr.line([(20, 100), (120, 40), (200, 110), (300, 30), (380, 90)], fill="navy", width=6)
jpg = BytesIO(); img.save(jpg, "JPEG"); jpg = jpg.getvalue()
try:
	engine.certificate_info(jpg, "x"); raise AssertionError("jpeg accepted")
except engine.SignError as e:
	assert "JPEG image" in str(e), e; print("jpeg rejected:", e)
try:
	engine.certificate_info(pfx, "nope"); raise AssertionError
except engine.SignError as e:
	assert "Wrong certificate password" in str(e)

test = engine.make_test_pfx("Noor Test", "secret1", "Neotec")
ti = engine.certificate_info(test, "secret1"); assert ti["self_signed"] and ti["subject"] == "Noor Test"
signer2 = engine.load_signer(test, "secret1")
out = engine.sign_pdf(pdf, signer2, engine.build_placements(pdf),
	stamp=engine.StampOptions(image=jpg, verify_url="https://x/sign-verify?code=A"))
assert engine.inspect_signatures(out)[0]["intact"]
open("/tmp/with-image.pdf", "wb").write(out)
print("V1.0.1 TESTS PASSED")
