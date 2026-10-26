// Copyright (c) 2026, Neotec Integrated Solutions
frappe.ui.form.on("Neotec Sign Log", {
	refresh(frm) {
		if (frm.doc.signed_file) {
			frm.add_custom_button(__("Check Signature Integrity"), () => neotec_sign.check_file(frm.doc.signed_file));
		}
		if (frm.doc.status === "Success" && frm.doc.verification_code) {
			frm.add_custom_button(__("Open Verification Page"), () =>
				window.open(`/sign-verify?code=${encodeURIComponent(frm.doc.verification_code)}`)
			);
		}
	},
});
