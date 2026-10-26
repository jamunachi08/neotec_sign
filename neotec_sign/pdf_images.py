# Copyright (c) 2026, Neotec Integrated Solutions
"""Make print HTML self-contained so wkhtmltopdf never has to fetch anything over the network.

Every <img src>, <link rel="stylesheet">, and CSS url(...) (images and fonts) is replaced with
inline content read straight from disk (site files, private files, app assets) or downloaded once
with a short timeout (external URLs). Anything that cannot be found is replaced with an empty
placeholder and reported back, instead of failing the whole PDF.
"""

import base64
import mimetypes
import os
import re
from urllib.parse import unquote, urljoin, urlparse

BLANK = "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"
MAX_BYTES = 8 * 1024 * 1024

_IMG_SRC = re.compile(r"""(<img\b[^>]*?\bsrc\s*=\s*)(["'])(.*?)\2""", re.I | re.S)
_CSS_URL = re.compile(r"""url\(\s*(["']?)([^"')]+)\1\s*\)""", re.I)
_IMAGE_EXT = re.compile(r"\.(png|jpe?g|gif|svg|webp|bmp|ico)(\?.*)?$", re.I)
_LINK_CSS = re.compile(r"""<link\b[^>]*?\brel\s*=\s*["']?stylesheet["']?[^>]*>""", re.I | re.S)
_HREF = re.compile(r"""\bhref\s*=\s*(["'])(.*?)\1""", re.I | re.S)
EMPTY = "data:,"


def inline_images(html: str, resolve) -> tuple[str, list[str]]:
	"""resolve(url) -> (bytes, mimetype) or None. Returns (new_html, broken_urls)."""
	cache, broken = {}, []

	def fetch(url):
		try:
			found = resolve(url)
		except Exception:
			found = None
		return found if found and found[0] and len(found[0]) <= MAX_BYTES else None

	def to_data_uri(url, placeholder=BLANK):
		url = (url or "").strip()
		if not url or url.startswith(("data:", "#", "about:")):
			return None  # leave untouched
		if url not in cache:
			try:
				found = resolve(url)
			except Exception:
				found = None
			if found and found[0] and len(found[0]) <= MAX_BYTES:
				data, mime = found
				cache[url] = f"data:{mime};base64,{base64.b64encode(data).decode()}"
			else:
				cache[url] = placeholder
				broken.append(url)
		return cache[url]

	def img_sub(m):
		new = to_data_uri(m.group(3))
		return m.group(0) if new is None else f"{m.group(1)}{m.group(2)}{new}{m.group(2)}"

	def css_urls(css, base=None):
		def sub(m):
			url = m.group(2).strip()
			if url.startswith(("data:", "#", "about:")):
				return m.group(0)
			if base and not urlparse(url).scheme and not url.startswith("/"):
				url = urljoin(base, url)  # relative to the stylesheet, e.g. ../fonts/x.woff2
			clean = url.split("#")[0]
			new = to_data_uri(clean, BLANK if _IMAGE_EXT.search(clean) else EMPTY)
			return m.group(0) if new is None else f'url("{new}")'

		return _CSS_URL.sub(sub, css)

	def link_sub(m):
		href = _HREF.search(m.group(0))
		if not href or href.group(2).startswith("data:"):
			return m.group(0)
		url = href.group(2).strip()
		found = fetch(url)
		if not found:
			broken.append(url)
			return ""  # drop the stylesheet rather than fail the PDF
		css = found[0].decode("utf-8", "replace")
		return f"<style>{css_urls(css, base=url)}</style>"

	html = _LINK_CSS.sub(link_sub, html)
	html = _IMG_SRC.sub(img_sub, html)
	html = css_urls(html)
	return html, broken


def name_variants(name: str) -> list[str]:
	"""Spellings a stored file name may have: as written, Unicode NFC/NFD, trimmed spaces."""
	import unicodedata

	out = []
	for base in (name, name.strip(), re.sub(r"\s+(\.[A-Za-z0-9]+)$", r"\1", name)):  # "توقيع .png" -> "توقيع.png"
		for form in (None, "NFC", "NFD"):
			v = unicodedata.normalize(form, base) if form else base
			if v not in out:
				out.append(v)
	return out


def make_frappe_resolver(diagnostics: dict | None = None):
	"""Resolver for a Frappe site. For each local URL it tries, in order:
	1. the file on disk (public, private, assets) under every spelling of its name,
	2. the File record (by URL, then by file name — catches files made private or renamed on re-upload),
	3. the site's own public URL over HTTPS.
	External hosts are downloaded directly. `diagnostics[url]` records what was tried."""
	import html as htmllib

	import frappe
	import requests
	from frappe.utils import get_url

	site_url = get_url().rstrip("/")
	site_hosts = {urlparse(site_url).netloc.lower()}
	if getattr(frappe.local, "request", None) is not None:
		site_hosts.add((frappe.local.request.host or "").lower())
	sites_path = os.path.abspath(frappe.local.sites_path)
	public_dir = os.path.abspath(frappe.get_site_path("public", "files"))
	private_dir = os.path.abspath(frappe.get_site_path("private", "files"))
	assets_dir = os.path.join(sites_path, "assets")
	diag = diagnostics if diagnostics is not None else {}

	def _read(path, base):
		path = os.path.abspath(path)
		if not path.startswith(base + os.sep):
			return None  # no path traversal out of the allowed folder
		if os.path.isfile(path):
			with open(path, "rb") as f:
				return f.read()
		return None

	def _mime(name):
		ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
		fonts = {"woff": "font/woff", "woff2": "font/woff2", "ttf": "font/ttf", "otf": "font/otf"}
		return fonts.get(ext) or mimetypes.guess_type(name)[0] or "application/octet-stream"

	def _http(url, note):
		try:
			r = requests.get(url, timeout=6)
		except Exception as e:
			note.append(f"GET {url}: {type(e).__name__}")
			return None
		ctype = r.headers.get("Content-Type", "").split(";")[0]
		note.append(f"GET {url}: HTTP {r.status_code} {ctype}")
		if r.ok and r.content and not ctype.startswith("text/html"):  # an HTML error page is not a resource
			return r.content, ctype or _mime(urlparse(url).path)
		return None

	def _from_disk(path, note):
		if path.startswith("/assets/"):
			data = _read(os.path.join(sites_path, path.lstrip("/")), assets_dir)
			note.append(f"disk assets: {'found' if data else 'not found'}")
			return data
		if path.startswith("/private/files/"):
			rel, dirs = path[len("/private/files/"):], (private_dir, public_dir)
		elif path.startswith("/files/"):
			rel, dirs = path[len("/files/"):], (public_dir, private_dir)  # file may have been made private
		else:
			return None
		for d in dirs:
			for v in name_variants(rel):
				data = _read(os.path.join(d, v), d)
				if data:
					note.append(f"disk: found {os.path.basename(d.rstrip(os.sep))}/{v!r}")
					return data
		note.append(f"disk: not found ({len(name_variants(rel))} spellings, public+private)")
		return None

	def _from_file_record(path, note):
		if not path.startswith(("/files/", "/private/files/")):
			return None
		basename = path.rsplit("/", 1)[-1]
		urls = {path} | {path.rsplit("/", 1)[0] + "/" + v for v in name_variants(basename)}
		names = frappe.get_all("File", filters={"file_url": ["in", list(urls)], "is_folder": 0}, pluck="name")
		if not names:
			names = frappe.get_all("File", filters={"file_name": ["in", name_variants(basename)], "is_folder": 0},
				pluck="name", order_by="creation desc", limit=5)
		note.append(f"File records matched: {len(names)}")
		for n in names:
			try:
				f = frappe.get_doc("File", n)
				data = f.get_content()
				if isinstance(data, str):
					data = data.encode()
				if data:
					note.append(f"File {n}: read {f.file_url}")
					return data
			except Exception as e:
				note.append(f"File {n}: {type(e).__name__}")
		return None

	def resolve(url):
		note = diag.setdefault(url, [])
		url = htmllib.unescape(url)
		u = urlparse(url)
		if u.scheme in ("http", "https") and u.netloc.lower() not in site_hosts:
			return _http(url, note)
		path = unquote(u.path or "")
		data = _from_disk(path, note) or _from_file_record(path, note)
		if data:
			return data, _mime(path)
		if path.startswith(("/files/", "/assets/")):  # public on the site itself
			return _http(site_url + u.path, note)
		return None

	return resolve


_ANY_REF = re.compile(
	r"""(\b(?:src|href|poster|data|xlink:href)\s*=\s*)(["'])(?!data:|#|mailto:|tel:|javascript:)([^"']+)\2"""
	r"""|url\(\s*(["']?)(?!data:|#)([^"')]+)\4\s*\)""",
	re.I,
)


def remaining_references(html: str) -> list[str]:
	"""Every URL still left in the HTML that the PDF engine might try to fetch (anchors excluded)."""
	no_anchors = re.sub(r"<a\b[^>]*>", "", html, flags=re.I)
	refs = []
	for m in _ANY_REF.finditer(no_anchors):
		refs.append(m.group(3) or m.group(5))
	return refs


def neutralise_references(html: str) -> str:
	"""Last line of defence: blank out anything still fetchable so the engine has nothing to load."""
	html = re.sub(r"\s+srcset\s*=\s*([\"']).*?\1", "", html, flags=re.I | re.S)
	html = re.sub(r"<script\b[^>]*\bsrc\s*=[^>]*>\s*</script>", "", html, flags=re.I | re.S)
	html = re.sub(r"<(iframe|object|embed|video|audio)\b.*?(</\1>|/>)", "", html, flags=re.I | re.S)
	html = re.sub(r"<link\b[^>]*>", "", html, flags=re.I)  # stylesheets are already inlined; icons/preloads not needed

	def tag_sub(m):
		attr = m.group(1).strip().lower()
		if attr.startswith("href"):
			return m.group(0)  # remaining hrefs are on <a>/<base>; harmless
		return f"{m.group(1)}{m.group(2)}{BLANK}{m.group(2)}"

	html = re.sub(r"""(\b(?:src|poster|xlink:href)\s*=\s*)(["'])(?!data:|#)[^"']+\2""", tag_sub, html, flags=re.I)
	html = re.sub(r"""url\(\s*(["']?)(?!data:|#)[^"')]+\1\s*\)""", 'url("data:,")', html, flags=re.I)
	return html
