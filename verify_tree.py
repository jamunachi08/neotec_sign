"""Structural guard for neotec_sign. Run: python verify_tree.py  (exit 1 on any problem)."""
import ast, csv, json, pathlib, py_compile, re, subprocess, sys

ROOT = pathlib.Path(__file__).parent
APP = ROOT / "neotec_sign"
errors = []
def err(msg): errors.append(msg)

REQUIRED = ["pyproject.toml", "README.md", "CHANGELOG.md", "neotec_sign/__init__.py", "neotec_sign/hooks.py",
	"neotec_sign/modules.txt", "neotec_sign/patches.txt", "neotec_sign/signing/engine.py",
	"neotec_sign/public/js/neotec_sign.js", "neotec_sign/public/js/lib/pdf.min.js",
	"neotec_sign/public/js/lib/pdf.worker.min.js", "neotec_sign/www/sign-verify.html", "neotec_sign/www/sign_verify.py"]
for r in REQUIRED:
	if not (ROOT / r).exists(): err(f"missing {r}")

# python compiles
for py in APP.rglob("*.py"):
	try: py_compile.compile(str(py), doraise=True)
	except py_compile.PyCompileError as e: err(f"compile {py}: {e}")

# doctypes
EXPECTED = {"Neotec Sign Settings", "Neotec Sign Certificate", "Neotec Sign Certificate Role", "Neotec Sign Rule", "Neotec Sign Log"}
found = set()
for j in (APP / "neotec_sign" / "doctype").glob("*/*.json"):
	d = json.loads(j.read_text())
	found.add(d["name"])
	slug = d["name"].lower().replace(" ", "_")
	if j.stem != slug or j.parent.name != slug: err(f"{j}: name/folder mismatch")
	if d.get("module") != "Neotec Sign": err(f"{j}: wrong module")
	names = [f["fieldname"] for f in d["fields"]]
	if names != d["field_order"]: err(f"{j}: field_order mismatch")
	if len(names) != len(set(names)): err(f"{j}: duplicate fieldnames")
	ctrl = j.with_suffix(".py")
	cls = d["name"].replace(" ", "")
	if not ctrl.exists() or f"class {cls}(" not in ctrl.read_text(): err(f"{j}: controller class {cls} missing")
	for f in d["fields"]:
		if f["fieldtype"] in ("Link", "Table MultiSelect", "Dynamic Link") and not f.get("options"):
			err(f"{j}:{f['fieldname']} needs options")
if found != EXPECTED: err(f"doctypes {found ^ EXPECTED}")

# hooks resolve
hooks = ast.parse((APP / "hooks.py").read_text())
dotted = set(re.findall(r'"(neotec_sign\.[\w.]+)"', (APP / "hooks.py").read_text()))
for path in dotted:
	mod, fn = path.rsplit(".", 1)
	f = ROOT / (mod.replace(".", "/") + ".py")
	if not f.exists() or not re.search(rf"^def {fn}\(", f.read_text(), re.M): err(f"hook target {path} not found")
for path in re.findall(r'"(neotec_sign\.[\w.]+)"', "".join(p.read_text() for p in APP.rglob("*.js") if "lib" not in p.parts)):
	mod, fn = path.rsplit(".", 1)
	f = ROOT / (mod.replace(".", "/") + ".py")
	src = f.read_text() if f.exists() else ""
	if not re.search(rf"@frappe\.whitelist\([^)]*\)\s*\ndef {fn}\(", src): err(f"JS calls non-whitelisted {path}")
for path in re.findall(r'"(neotec_sign\.[\w.]+)"', (APP / "events.py").read_text()):
	mod, fn = path.rsplit(".", 1)
	if not re.search(rf"^def {fn}\(", (ROOT / (mod.replace(".", "/") + ".py")).read_text(), re.M): err(f"enqueue target {path} missing")

# engine stays framework-free
if re.search(r"^\s*(import|from)\s+frappe", (APP / "signing/engine.py").read_text(), re.M): err("engine.py must not import frappe")

# JS syntax
for js in APP.rglob("*.js"):
	if "lib" in js.parts: continue
	r = subprocess.run(["node", "--check", str(js)], capture_output=True, text=True)
	if r.returncode: err(f"js syntax {js}: {r.stderr.strip()[:200]}")

# translations
for row in csv.reader((APP / "translations/ar.csv").open(encoding="utf-8")):
	if row and len(row) < 2: err(f"ar.csv bad row {row}")

# originality guard — no foreign product identifiers
banned = re.compile(r"digital_signer|Digital[- ]Signer|IBSL|Document Sign Setting|luckytamrakar", re.I)
for p in ROOT.rglob("*"):
	if p.is_file() and p.suffix in {".py", ".js", ".json", ".md", ".html", ".csv", ".toml", ".txt"} and "lib" not in p.parts:
		if p.name != "verify_tree.py" and banned.search(p.read_text(errors="ignore")): err(f"foreign identifier in {p}")

if errors:
	print("\n".join("FAIL: " + e for e in errors)); sys.exit(1)
print(f"verify_tree: OK ({len(EXPECTED)} doctypes, {len(dotted)} hooks)")
