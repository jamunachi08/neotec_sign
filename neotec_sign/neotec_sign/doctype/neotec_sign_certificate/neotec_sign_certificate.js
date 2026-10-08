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
	},
});
