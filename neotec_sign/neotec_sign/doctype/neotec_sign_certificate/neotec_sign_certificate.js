// Copyright (c) 2026, Neotec Integrated Solutions
frappe.ui.form.on("Neotec Sign Certificate", {
	refresh(frm) {
		if (frm.doc.valid_to) {
			const days = frappe.datetime.get_day_diff(frm.doc.valid_to, frappe.datetime.now_date());
			const color = days < 0 ? "red" : days < 30 ? "orange" : "green";
			frm.dashboard.set_headline(
				`<span class="indicator ${color}">${__("Valid until {0} ({1} days)", [frappe.datetime.str_to_user(frm.doc.valid_to), days])}</span>`
			);
		}
		if (frm.doc.self_signed) {
			frm.set_intro(__("Self-signed test certificate — fine for trying the app, not for real documents. PDF readers will show the signature as 'validity unknown'."), "orange");
		}
		if (!frm.doc.pfx_file) {
			frm.add_custom_button(__("Create Test Certificate"), () => make_test_certificate(frm));
		}
	},
	pfx_file(frm) {
		const f = (frm.doc.pfx_file || "").toLowerCase();
		if (f && !/\.(pfx|p12)$/.test(f)) {
			frappe.msgprint({
				title: __("Wrong File Type"),
				indicator: "red",
				message: __("This is not a certificate. Upload the .pfx or .p12 file from your certificate provider. A picture of your signature belongs in <b>Signature Image</b>."),
			});
		}
	},
});

function make_test_certificate(frm) {
	frappe.prompt(
		[
			{ fieldname: "common_name", label: __("Name on Certificate"), fieldtype: "Data", reqd: 1,
				default: frm.doc.certificate_name || frappe.session.user_fullname },
			{ fieldname: "organisation", label: __("Organisation"), fieldtype: "Data", default: frm.doc.company },
			{ fieldname: "password", label: __("New Password (min 6)"), fieldtype: "Password", reqd: 1 },
		],
		(v) =>
			frappe.call({
				method: "neotec_sign.api.create_test_certificate",
				args: v,
				freeze: true,
				callback(r) {
					if (!r.message) return;
					frm.set_value("pfx_file", r.message);
					frm.set_value("password", v.password);
					frappe.show_alert({ message: __("Test certificate created — click Save."), indicator: "green" });
				},
			}),
		__("Create Test Certificate"),
		__("Create")
	);
}
