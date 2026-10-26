"""Resolver + neutraliser tests with a stub Frappe (no bench). python tests/test_resolver.py"""
import os, sys, tempfile, types, unicodedata
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

root = tempfile.mkdtemp(); site = os.path.join(root, "neoirsaa.frappe.cloud")
for d in ("public/files", "private/files", "../assets/app"):
	os.makedirs(os.path.join(site, d), exist_ok=True)
w = lambda rel, b=b"\x89PNG": open(os.path.join(site, rel), "wb").write(b)
w("public/files/IRSAAlogo-en.png")                                   # plain
w("private/files/" + unicodedata.normalize("NFD", "ختم اسلام.png"))     # made private + NFD spelling
w("public/files/توقيع.png")                                           # stored without the space
w("public/files/renamed-a1b2c3.png", b"\x89PNG-renamed")              # re-upload renamed by Frappe

class FileDoc(dict):
	__getattr__ = dict.get
	def get_content(self):
		return open(os.path.join(site, "public/files", self.file_url.rsplit("/", 1)[-1]), "rb").read()
records = {"F1": FileDoc(name="F1", file_name="stamp-old.png", file_url="/files/renamed-a1b2c3.png")}
def get_all(dt, filters=None, **k):
	names = [n for n, r in records.items() if r.file_name in filters.get("file_name", [None, []])[1]] if "file_name" in filters else []
	return names
fr = types.ModuleType("frappe")
fr.local = types.SimpleNamespace(sites_path=root, request=None)
fr.get_site_path = lambda *p: os.path.join(site, *p)
fr.get_all = get_all
fr.get_doc = lambda dt, n: records[n]
fu = types.ModuleType("frappe.utils"); fu.get_url = lambda: "https://neoirsaa.frappe.cloud"
rq = types.ModuleType("requests")
class R:  # own-site fallback: pretend nginx serves /files/served-by-web.png
	def __init__(s, url): s.ok = url.endswith("served-by-web.png"); s.status_code = 200 if s.ok else 404
	headers = property(lambda s: {"Content-Type": "image/png" if s.ok else "text/html"})
	content = b"\x89PNGweb"
rq.get = lambda url, timeout=0: R(url)
sys.modules.update({"frappe": fr, "frappe.utils": fu, "requests": rq})

from neotec_sign import pdf_images as pi  # noqa: E402
diag = {}; r = pi.make_frappe_resolver(diag)
assert r("/files/IRSAAlogo-en.png"), diag
assert r("/files/ختم اسلام.png"), diag["/files/ختم اسلام.png"]            # private + NFD
assert r("/files/%D8%AA%D9%88%D9%82%D9%8A%D8%B9%20.png"), diag            # url-encoded, trailing space
assert r("/files/stamp-old.png")[0] == b"\x89PNG-renamed", diag           # via File record
assert r("/files/served-by-web.png")[0] == b"\x89PNGweb", diag            # via own site HTTPS
assert r("/files/../site_config.json") is None
assert r("/files/really-gone.png") is None
print("diagnostics for a missing file:", diag["/files/really-gone.png"])

html = """<link rel="icon" href="/favicon.ico"><img src="/x.png" srcset="/a.png 2x">
<script src="/assets/x.js"></script><iframe src="https://a"></iframe>
<div style="background:url(https://cdn.example/bg.png)"></div><a href="/app/x">link</a>"""
left = pi.remaining_references(html)
out = pi.neutralise_references(html)
assert "/app/x" in out and "/app/x" not in left
assert pi.remaining_references(out) == [], pi.remaining_references(out)
print("leftovers found then removed:", left)
try:
	import pdfkit
	sys.modules.pop("requests")
	pdf = pdfkit.from_string(out + '<p>تجربة Test</p>', False, options={"quiet": ""})
	assert pdf[:4] == b"%PDF"; print("wkhtmltopdf renders neutralised HTML")
except ImportError:
	pass
print("RESOLVER TESTS PASSED")
