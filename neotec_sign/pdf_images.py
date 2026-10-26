# Copyright (c) 2026, Neotec Integrated Solutions
"""Make print HTML self-contained so wkhtmltopdf never has to fetch an image over the network.

Every <img src>, srcset-less, and CSS url(...) is replaced with a data: URI read straight from disk
(site files, private files, app assets) or downloaded once with a short timeout (external URLs).
Images that cannot be found are replaced with a transparent pixel and reported back, instead of
failing the whole PDF.
"""

import base64
import mimetypes
import os
import re
from urllib.parse import unquote, urlparse

BLANK = "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"
MAX_BYTES = 8 * 1024 * 1024

_IMG_SRC = re.compile(r"""(<img\b[^>]*?\bsrc\s*=\s*)(["'])(.*?)\2""", re.I | re.S)
_CSS_URL = re.compile(r"""url\(\s*(["']?)([^"')]+)\1\s*\)""", re.I)
_IMAGE_EXT = re.compile(r"\.(png|jpe?g|gif|svg|webp|bmp|ico)(\?.*)?$", re.I)


def inline_images(html: str, resolve) -> tuple[str, list[str]]:
	"""resolve(url) -> (bytes, mimetype) or None. Returns (new_html, broken_urls)."""
	cache, broken = {}, []

	def to_data_uri(url):
		url = (url or "").strip()
		if not url or url.startswith(("data:", "#")):
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
				cache[url] = BLANK
				broken.append(url)
		return cache[url]

	def img_sub(m):
		new = to_data_uri(m.group(3))
		return m.group(0) if new is None else f"{m.group(1)}{m.group(2)}{new}{m.group(2)}"

	def css_sub(m):
		url = m.group(2)
		if not _IMAGE_EXT.search(url.split("#")[0]):
			return m.group(0)  # fonts etc. — not our concern
		new = to_data_uri(url)
		return m.group(0) if new is None else f'url("{new}")'

	html = _IMG_SRC.sub(img_sub, html)
	html = _CSS_URL.sub(css_sub, html)
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

	def _mime(name, fallback="image/png"):
		return mimetypes.guess_type(name)[0] or fallback

	def resolve(url):
		u = urlparse(url)
		if u.scheme in ("http", "https") and u.netloc.lower() not in site_hosts:
			r = requests.get(url, timeout=5)
			ctype = r.headers.get("Content-Type", "").split(";")[0]
			if r.ok and ctype.startswith("image/"):
				return r.content, ctype
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
