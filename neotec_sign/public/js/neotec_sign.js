// Copyright (c) 2026, Neotec Integrated Solutions
// Adds "Digital Signature" actions to every document type that has an enabled Neotec Sign Rule.

frappe.provide("neotec_sign");

const NS_LIB = "/assets/neotec_sign/js/lib/";
const NS_PAGES = { Last: "Last", First: "First", All: "All" };
const NS_PICK = "Choose on Preview";

neotec_sign.bind = function () {
	const doctypes = (frappe.boot.neotec_sign && frappe.boot.neotec_sign.doctypes) || [];
	doctypes.forEach((dt) => frappe.ui.form.on(dt, { refresh: neotec_sign.add_buttons }));
};

neotec_sign.add_buttons = function (frm) {
	if (frm.is_new() || (frm.meta.is_submittable && frm.doc.docstatus !== 1)) return;
	const group = __("Digital Signature");
	frm.add_custom_button(__("Sign PDF"), () => neotec_sign.open_sign_dialog(frm), group);
	frm.add_custom_button(__("Signature Log"), () =>
		frappe.set_route("List", "Neotec Sign Log", { reference_doctype: frm.doctype, reference_name: frm.doc.name }),
		group
	);
	const signed = (frm.get_docinfo().attachments || []).filter((a) => /-signed.*\.pdf$/i.test(a.file_name || ""));
	if (signed.length) {
		frm.add_custom_button(__("Check Signatures"), () => neotec_sign.pick_and_check(signed), group);
	}
};

// ------------------------------------------------------------------ sign dialog
neotec_sign.open_sign_dialog = async function (frm) {
	const { message: ctx } = await frappe.call("neotec_sign.api.get_sign_context", {
		doctype: frm.doctype,
		name: frm.doc.name,
	});
	if (!ctx.enabled) return frappe.msgprint(__("Digital signing is disabled in Neotec Sign Settings."));
	if (!ctx.certificates.length)
		return frappe.msgprint(__("No certificate is available to you. Ask your administrator for the Neotec Signer role."));

	const certs = Object.fromEntries(ctx.certificates.map((c) => [c.name, c]));
	const page_mode = NS_PAGES[ctx.pages] ? ctx.pages : "Range";
	const positions = ["Bottom Right", "Bottom Left", "Bottom Center", "Top Right", "Top Left"];
	if (ctx.allow_custom_position) positions.push(NS_PICK);
	let placements = [];

	const d = new frappe.ui.Dialog({
		title: __("Sign {0}", [frm.doc.name]),
		fields: [
			{ fieldname: "certificate", label: __("Certificate"), fieldtype: "Select", reqd: 1,
				options: Object.keys(certs), default: ctx.default_certificate,
				onchange: () => refresh_cert() },
			{ fieldname: "cert_info", fieldtype: "HTML" },
			{ fieldname: "password", label: __("Certificate Password"), fieldtype: "Password", hidden: 1 },
			{ fieldtype: "Column Break" },
			{ fieldname: "print_format", label: __("Print Format"), fieldtype: "Select",
				options: [""].concat(ctx.print_formats), default: ctx.print_format || "",
				description: __("Empty = default print format") },
			{ fieldtype: "Section Break", label: __("Where to sign") },
			{ fieldname: "page_mode", label: __("Pages"), fieldtype: "Select",
				options: ["Last", "First", "All", "Range"], default: page_mode },
			{ fieldname: "page_range", label: __("Page Range"), fieldtype: "Data",
				depends_on: "eval:doc.page_mode=='Range'", default: page_mode === "Range" ? ctx.pages : "",
				description: __("e.g. 1,3-5") },
			{ fieldtype: "Column Break" },
			{ fieldname: "position", label: __("Position"), fieldtype: "Select", options: positions,
				default: ctx.position },
			{ fieldname: "pick", label: __("Open Preview"), fieldtype: "Button",
				depends_on: `eval:doc.position=='${NS_PICK}'`,
				click: () => neotec_sign.pick_positions(frm, d.get_value("print_format"), ctx.box, placements, (p) => {
					placements = p;
					show_picks();
				}) },
			{ fieldname: "picked", fieldtype: "HTML", depends_on: `eval:doc.position=='${NS_PICK}'` },
		],
		primary_action_label: __("Sign & Attach"),
		primary_action(v) {
			const cert = certs[v.certificate];
			if (cert.ask_password && !v.password) return frappe.msgprint(__("Enter the certificate password."));
			const custom = v.position === NS_PICK;
			if (custom && !placements.length) return frappe.msgprint(__("Click on the preview to place at least one signature."));
			if (v.page_mode === "Range" && !v.page_range) return frappe.msgprint(__("Enter a page range."));

			frappe.call({
				method: "neotec_sign.api.sign",
				args: {
					doctype: frm.doctype,
					name: frm.doc.name,
					certificate: v.certificate,
					print_format: v.print_format || null,
					pages: v.page_mode === "Range" ? v.page_range : v.page_mode,
					position: custom ? null : v.position,
					placements: custom ? JSON.stringify(placements.map(({ el, ...p }) => p)) : null,
					password: cert.ask_password ? v.password : null,
				},
				freeze: true,
				freeze_message: __("Signing…"),
				callback(r) {
					if (r.exc || !r.message) return;
					d.hide();
					const missing = r.message.missing_images || [];
					frappe.msgprint({
						title: __("Signed"),
						indicator: missing.length ? "orange" : "green",
						message: __("Signed PDF attached. Verification code: {0}", [`<b>${r.message.verification_code}</b>`]) +
							`<br><a href="${r.message.file_url}" target="_blank">${__("Open signed PDF")}</a>` +
							neotec_sign.missing_images_html(missing),
					});
					frm.reload_doc();
				},
			});
		},
	});

	function refresh_cert() {
		const c = certs[d.get_value("certificate")];
		if (!c) return;
		d.set_df_property("password", "hidden", c.ask_password ? 0 : 1);
		d.fields_dict.cert_info.$wrapper.html(
			`<div class="text-muted small">${__("Issued to")}: <b>${frappe.utils.escape_html(c.subject || "")}</b><br>
			 ${__("Valid until")}: ${frappe.datetime.str_to_user(c.valid_to) || "-"}</div>`
		);
	}
	function show_picks() {
		const txt = placements.length
			? placements.map((p) => __("Page {0}", [p.page])).join(", ")
			: __("No position chosen yet");
		d.fields_dict.picked.$wrapper.html(`<div class="small text-muted">${txt}</div>`);
	}

	d.show();
	refresh_cert();
	show_picks();
	if (ctx.signed_count) {
		d.set_intro(__("This document has already been signed {0} time(s). Signing again adds a new signed copy.", [ctx.signed_count]), "blue");
	}
};

// ------------------------------------------------------------------ position picker
neotec_sign.load_pdfjs = async function () {
	if (!window.pdfjsLib) await frappe.require(NS_LIB + "pdf.min.js");
	window.pdfjsLib.GlobalWorkerOptions.workerSrc = NS_LIB + "pdf.worker.min.js";
	return window.pdfjsLib;
};

neotec_sign.pick_positions = async function (frm, print_format, box, existing, done) {
	const [pdfjs, res] = await Promise.all([
		neotec_sign.load_pdfjs(),
		frappe.call({
			method: "neotec_sign.api.preview_pdf",
			args: { doctype: frm.doctype, name: frm.doc.name, print_format: print_format || null },
			freeze: true,
			freeze_message: __("Preparing preview…"),
		}),
	]);
	if ((res.message.missing_images || []).length) {
		frappe.msgprint({ title: __("Missing Images"), indicator: "orange",
			message: neotec_sign.missing_images_html(res.message.missing_images) });
	}
	const bytes = Uint8Array.from(atob(res.message.pdf), (c) => c.charCodeAt(0));
	const pdf = await pdfjs.getDocument({ data: bytes }).promise;
	let picks = [];

	const d = new frappe.ui.Dialog({
		title: __("Click where the signature should go"),
		size: "extra-large",
		fields: [{ fieldname: "pages", fieldtype: "HTML" }],
		primary_action_label: __("Use These Positions"),
		primary_action() {
			d.hide();
			done(picks);
		},
		secondary_action_label: __("Clear"),
		secondary_action() {
			picks.forEach((p) => p.el.remove());
			picks = [];
		},
	});
	d.show();
	const $host = d.fields_dict.pages.$wrapper.css({ background: "var(--gray-100)", padding: "12px", "max-height": "70vh", overflow: "auto" });
	const width = Math.min($host.width() - 24, 900);

	for (let n = 1; n <= pdf.numPages; n++) {
		const page = await pdf.getPage(n);
		const scale = width / page.getViewport({ scale: 1 }).width;
		const vp = page.getViewport({ scale });
		const $wrap = $(`<div style="position:relative;margin:0 auto 14px;width:${vp.width}px;box-shadow:0 1px 4px rgba(0,0,0,.2);cursor:crosshair">
			<div style="position:absolute;top:4px;inset-inline-end:8px;font-size:11px;color:#888">${__("Page {0}", [n])}</div></div>`);
		const canvas = document.createElement("canvas");
		canvas.width = vp.width;
		canvas.height = vp.height;
		$wrap.prepend(canvas);
		$host.append($wrap);
		await page.render({ canvasContext: canvas.getContext("2d"), viewport: vp }).promise;

		const bw = box.w * scale, bh = box.h * scale;
		$wrap.on("click", (e) => {
			if ($(e.target).hasClass("ns-box")) return;
			const r = canvas.getBoundingClientRect();
			const left = Math.max(0, Math.min(e.clientX - r.left - bw / 2, vp.width - bw));
			const top = Math.max(0, Math.min(e.clientY - r.top - bh / 2, vp.height - bh));
			const [x, y] = vp.convertToPdfPoint(left, top + bh); // bottom-left corner in PDF points
			const el = $(`<div class="ns-box" title="${__("Click to remove")}" style="position:absolute;left:${left}px;top:${top}px;
				width:${bw}px;height:${bh}px;border:2px dashed var(--primary);background:rgba(37,99,235,.08);
				display:flex;align-items:center;justify-content:center;font-size:11px;color:var(--primary);cursor:pointer">
				${__("Signature")}</div>`).appendTo($wrap);
			const pick = { page: n, x: +x.toFixed(2), y: +y.toFixed(2), w: box.w, h: box.h, el };
			el.on("click", () => {
				el.remove();
				picks = picks.filter((p) => p !== pick);
			});
			picks.push(pick);
		});
	}
};

neotec_sign.missing_images_html = function (urls) {
	if (!urls || !urls.length) return "";
	const list = urls.map((u) => `<li><code>${frappe.utils.escape_html(u)}</code></li>`).join("");
	return `<div class="alert alert-warning small" style="margin-top:10px">
		${__("These images could not be found and were left out of the PDF. Fix or re-upload them in the Letter Head / Print Format:")}
		<ul style="margin:6px 0 0">${list}</ul></div>`;
};

// ------------------------------------------------------------------ integrity check
neotec_sign.pick_and_check = function (files) {
	if (files.length === 1) return neotec_sign.check_file(files[0].file_url);
	frappe.prompt(
		{ fieldname: "file", label: __("Signed File"), fieldtype: "Select", reqd: 1, options: files.map((f) => f.file_url) },
		(v) => neotec_sign.check_file(v.file),
		__("Choose a signed file")
	);
};

neotec_sign.check_file = async function (file_url) {
	const { message: r } = await frappe.call({
		method: "neotec_sign.api.check_file",
		args: { file_url },
		freeze: true,
	});
	const yes = (b) => (b ? `<span class="indicator-pill green">${__("Yes")}</span>` : `<span class="indicator-pill red">${__("No")}</span>`);
	const rows = (r.signatures || [])
		.map((s) => s.error
			? `<tr><td>${s.field}</td><td colspan="3" class="text-danger">${frappe.utils.escape_html(s.error)}</td></tr>`
			: `<tr><td>${frappe.utils.escape_html(s.signer || "-")}</td><td>${s.signed_at || "-"}</td><td>${yes(s.intact)}</td><td>${yes(s.covers_whole_document)}</td></tr>`)
		.join("");
	frappe.msgprint({
		title: __("Signature Check"),
		wide: true,
		message: `<table class="table table-bordered small">
			<tr><th>${__("Signer")}</th><th>${__("Signed At")}</th><th>${__("Unaltered")}</th><th>${__("Covers Whole File")}</th></tr>
			${rows || `<tr><td colspan="4">${__("No digital signatures found.")}</td></tr>`}</table>
			<div class="small">${__("Matches audit log")}: ${yes(r.matches_log)} &nbsp; <code>${r.sha256}</code></div>
			<div class="small text-muted">${__("Earlier signatures on multi-page signing show 'Covers Whole File: No' — that is expected; the last one must be Yes.")}</div>`,
	});
};

$(() => neotec_sign.bind());
