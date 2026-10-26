"""Tolerant renderer test (no bench). python tests/test_render.py"""
import os, stat, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import pdfkit  # noqa: E402
from neotec_sign.pdf_render import run_wkhtmltopdf, useful_lines  # noqa: E402

def wrapper(write_pdf: bool):
	"""Behaves like Frappe Cloud's wkhtmltopdf on a 404: (optionally) writes the PDF, then exits 1."""
	path = tempfile.mktemp(suffix=".sh")
	render = '"$(command -v wkhtmltopdf)" "$@" 2>/dev/null' if write_pdf else ":"
	open(path, "w").write(f"""#!/bin/sh
if [ "$1" = "--version" ]; then exec wkhtmltopdf --version; fi
{render}
for i in 1 2 3; do echo 'Fontconfig warning: "/etc/fonts/conf.d/40-nonlatin.conf", line 34: Having multiple <family> in <alias> isn'"'"'t supported' >&2; done
echo 'Warning: Failed to load https://neoirsaa.frappe.cloud/files/IRSAAlogo-en.png (ignore)' >&2
echo 'Exit with code 1 due to network error: ContentNotFoundError' >&2
exit 1
""")
	os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)
	return pdfkit.configuration(wkhtmltopdf=path)

html = "<html><head><meta charset='utf-8'></head><body><h1>فاتورة ضريبية — Tax Invoice</h1></body></html>"
opts = {"disable-javascript": "", "load-error-handling": "ignore"}

# 1. Exactly your server's behaviour: PDF written, exit code 1 -> we keep the PDF.
pdf, warnings = run_wkhtmltopdf(html, opts, configuration=wrapper(True))
assert pdf[:5] == b"%PDF-", pdf[:20]
assert warnings == ["Warning: Failed to load https://neoirsaa.frappe.cloud/files/IRSAAlogo-en.png (ignore)",
	"Exit with code 1 due to network error: ContentNotFoundError"], warnings
print("PDF kept despite exit 1:", len(pdf), "bytes; reported:", warnings[0])

# 2. Nothing written -> clear failure, Fontconfig noise stripped.
try:
	run_wkhtmltopdf(html, opts, configuration=wrapper(False)); raise AssertionError("should fail")
except RuntimeError as e:
	assert "Fontconfig" not in str(e) and "ContentNotFoundError" in str(e), e
	print("no PDF -> clean error:", str(e).splitlines()[-1])

# 3. Normal success path still works.
pdf, warnings = run_wkhtmltopdf(html, opts)
assert pdf[:5] == b"%PDF-" and warnings == []
print("RENDER TESTS PASSED")
