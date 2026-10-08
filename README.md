# Neotec Sign

Digitally sign the PDF of **any** ERPNext document with your company's PFX/P12 certificate — from one button, or automatically on submit. Every signature is logged, carries a QR code, and can be verified by the recipient.

Frappe / ERPNext v15 · Neotec Integrated Solutions

---

## Setup (3 steps)

1. **Install**
   Add the repo to your Frappe Cloud bench (or `bench get-app` + `bench --site <site> install-app neotec_sign`). Python dependencies (`pyHanko[qr]`, `cryptography`) install automatically from `pyproject.toml`.

2. **Add a certificate** — *Neotec Sign Certificate → New*
   Upload the `.pfx`/`.p12` as **Private**, type its password, save. The holder, issuer, serial number and validity are read from the file and shown on the form. Tick *Ask Password at Every Signing* if the password must not be stored.
   Set **Allowed Roles** (default: *Neotec Signer*) and optionally a **Company**.

3. **Add a rule** — *Neotec Sign Rule → New*
   Pick the Document Type (Sales Invoice, Purchase Order, Quotation, Delivery Note, Salary Slip … anything). Optionally set print format, letter head, pages and position. Tick *Sign Automatically on Submit* for hands-off signing.

Reload the browser once after adding a new rule. Submitted documents of that type now show **Digital Signature → Sign PDF**.

## Signing

The dialog asks for the certificate, print format, pages (Last / First / All / range such as `1,3-5`) and position:

- **Preset** — Bottom Right, Bottom Left, Bottom Center, Top Right, Top Left.
- **Choose on Preview** — the exact PDF opens in-app; click to drop one or more signature boxes, click a box to remove it.

The signed PDF is attached privately to the document, a timeline comment is added, and a **Neotec Sign Log** record is written.

## Verification

- The stamp's QR code opens `/sign-verify?code=…` on your site, showing the document, signer, time and file fingerprint. The recipient can select their copy and the browser confirms whether it is byte-for-byte identical (the file is never uploaded).
- **Check Signatures** (on the document or the log) validates the embedded signatures: unaltered, covering the whole file, signer and time.
- Adobe Reader shows the signature panel as usual. Trust ("green tick") depends on your certificate's issuing CA.

## Settings — *Neotec Sign Settings*

| Setting | Purpose |
|---|---|
| Enable Digital Signing | Master switch |
| Default Certificate | Used when a rule has none |
| Stamp Text | `%(signer)s` and `%(ts)s` placeholders |
| Add Verification QR Code | QR linking to the verification page |
| Verification Base URL | Public URL if different from the site URL |
| Default Position / Pages, Stamp Width / Height | Defaults for rules |
| TSA URL | Optional RFC 3161 trusted timestamp |
| Allow Public Verification Page | Turn `/sign-verify` on or off |

## Roles

| Role | Can |
|---|---|
| Neotec Sign Manager | Manage settings, certificates, rules; read all logs |
| Neotec Signer | Sign with certificates that allow this role; read own logs |

## Security notes

- The signer must have *read* permission on the document **and** an allowed role on the certificate. Certificate passwords are stored encrypted, or not at all.
- Only submitted documents (for submittable types) can be signed.
- Successful log entries cannot be deleted.
- pdf.js is bundled — no external CDN calls.

## Developer

- `python tests/test_engine.py` — standalone test of the signing engine (no bench needed).
- `python verify_tree.py` — structural guard: doctypes, hooks, whitelisted calls, JS syntax.
- All signing logic is in `neotec_sign/signing/engine.py` (framework-free); workflow in `services.py`.
