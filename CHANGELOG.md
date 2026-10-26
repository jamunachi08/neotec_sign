# Changelog

## 1.0.4 — 2026-10-26
- Much more thorough file lookup when rebuilding a PDF. For each image or font the app now tries:
  - the file on disk under every spelling of its name (Unicode NFC/NFD for Arabic names, trimmed spaces such as `توقيع .png`), in both the public and private folders (catches files that were made private);
  - the File record, by URL and then by file name (catches files Frappe renamed on re-upload);
  - the site's own public URL over HTTPS.
- Final safety pass: every reference still left in the page (icons, preloads, scripts, iframes, srcset, unreachable CSS urls) is removed before rendering, so the PDF engine has nothing left to fetch.
- Error Log entry "Neotec Sign: resources left out of …" lists each missing file with exactly what was tried (disk paths, File records, HTTP status).
- Error messages are shown once instead of three times.

## 1.0.3 — 2026-10-26
- PDF recovery now also embeds stylesheets (`<link rel="stylesheet">`) and fonts, including paths relative to the stylesheet. Missing ones are dropped and reported, the same way as images.
- The rebuilt PDF runs with "continue on load errors", so one unreachable resource can no longer stop signing.
- If the rebuild still fails, a clear "PDF Failed" message lists what was missing, and the full trace goes to the Error Log.
- The sign dialog footer shows the installed Neotec Sign version, so you can check which release a site is running.

## 1.0.2 — 2026-10-26
- Fixed "PDF generation failed because of broken image links". When the PDF engine cannot load an image, Neotec Sign rebuilds the page with every image embedded directly from the site's disk (public files, private files, app assets) or downloaded once (external URLs). The PDF engine then needs no network access.
- Images that genuinely don't exist (e.g. a deleted letter head logo) are left out instead of failing, listed to the user after signing and in the preview, and recorded in the Sign Log *Warnings* field and the Error Log.
- New setting **Stop Signing if an Image is Missing** for clients who prefer a hard stop.
- Path-traversal protection on embedded file paths.

## 1.0.1 — 2026-10-25
- Clear "Wrong File Type" message when an image, PDF or other non-certificate file is uploaded as the certificate (checked on upload, on save, and by file content). Wrong-password errors are now reported separately.
- New **Signature Image** field: a handwritten signature or company seal (PNG/JPEG) printed inside the stamp, behind the signer text.
- New **Create Test Certificate** button: generates a private self-signed PFX so the app can be tried before a CA certificate is available. Such certificates are flagged "Self-Signed (Testing Only)".
- Version range widened to Frappe/ERPNext v15 and v16.

## 1.0.0 — 2026-10-08
- First release of Neotec Sign.
- Sign any submitted document type from one Rule record — no per-doctype code.
- Certificate register: password stored encrypted (or asked at every signing), holder/issuer/validity read from the PFX automatically, expiry warnings, per-company and per-role control.
- Placement: preset positions (bottom/top, left/center/right), pages Last / First / All / range, or click-to-place on an in-app preview (pdf.js bundled, no CDN).
- Automatic signing on submit with optional condition, run as a background job.
- QR code on the stamp linking to a public verification page; recipients can check their copy's SHA-256 in the browser.
- Neotec Sign Log: permanent audit trail (who, when, certificate, pages, file hash, verification code, failures).
- Signature integrity check for any signed attachment.
- Optional RFC 3161 trusted timestamp (TSA).
