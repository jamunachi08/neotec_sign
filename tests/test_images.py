"""Standalone test of the image inliner (no bench). python tests/test_images.py"""
import base64, os, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from neotec_sign.pdf_images import BLANK, inline_images  # noqa: E402

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
files = {"/files/logo.png": PNG, "/files/My%20sign.jpg.jpeg": PNG}
resolve = lambda url: (files[url], "image/png") if url in files else None

html = """<div class="letter-head"><img src="/files/logo.png" alt=x></div>
<img class='sig' src='/files/My%20sign.jpg.jpeg'>
<img src="https://neo15.example/files/deleted-logo.png">
<div style="background:url('/files/missing-bg.jpg')"></div>
<img src="data:image/png;base64,AAAA">
<style>@font-face{src:url(/assets/x.woff2)}</style>"""
out, broken = inline_images(html, resolve)
assert out.count("data:image/png;base64,") == 3, out          # 2 inlined + 1 untouched data URI
assert broken == ["https://neo15.example/files/deleted-logo.png", "/files/missing-bg.jpg"], broken
assert out.count(BLANK) == 2 and "/assets/x.woff2" in out     # fonts are left alone
print("inliner ok, broken:", broken)

# Reproduce the real failure with wkhtmltopdf, then show the inlined HTML renders.
try:
	import pdfkit
except ImportError:
	sys.exit(0)
bad = '<html><body><h1>Invoice</h1><img src="http://127.0.0.1:9/files/deleted-logo.png"></body></html>'
try:
	pdfkit.from_string(bad, False, options={"quiet": ""})
	print("note: this wkhtmltopdf build tolerated the broken image")
except OSError as e:
	assert "ContentNotFoundError" in str(e) or "network error" in str(e), e
	print("reproduced:", str(e).strip().splitlines()[-1])
fixed, broken = inline_images(bad, lambda u: None)
pdf = pdfkit.from_string(fixed, False, options={"quiet": ""})
assert pdf[:4] == b"%PDF"; print("recovered PDF bytes:", len(pdf), "missing:", broken)
print("IMAGE TESTS PASSED")
