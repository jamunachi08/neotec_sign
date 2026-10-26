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


def make_frappe_resolver():
	"""Resolver for a Frappe site: disk first, network only for genuinely external hosts."""
	import frappe
	import requests
	from frappe.utils import get_url

	site_hosts = {urlparse(get_url()).netloc.lower()}
	if getattr(frappe.local, "request", None) is not None:
		site_hosts.add((frappe.local.request.host or "").lower())
	sites_path = os.path.abspath(frappe.local.sites_path)

	def _read(path, base):
		path, base = os.path.abspath(path), os.path.abspath(base)
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

	def resolve(url):
		u = urlparse(url)
		if u.scheme in ("http", "https") and u.netloc.lower() not in site_hosts:
			r = requests.get(url, timeout=5)
			ctype = r.headers.get("Content-Type", "").split(";")[0]
			if r.ok and not ctype.startswith("text/html"):  # an HTML error page is not an image/font/css
				return r.content, ctype or _mime(u.path)
			return None

		path = unquote(u.path or "")
		if path.startswith("/private/files/"):
			base = frappe.get_site_path("private", "files")
			data = _read(os.path.join(base, path[len("/private/files/"):]), base)
		elif path.startswith("/files/"):
			base = frappe.get_site_path("public", "files")
			data = _read(os.path.join(base, path[len("/files/"):]), base)
		elif path.startswith("/assets/"):
			data = _read(os.path.join(sites_path, path.lstrip("/")), os.path.join(sites_path, "assets"))
		else:
			data = None
		return (data, _mime(path)) if data else None

	return resolve
