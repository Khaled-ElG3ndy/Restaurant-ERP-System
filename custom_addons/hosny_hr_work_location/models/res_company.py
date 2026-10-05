from odoo import api, models


BRANCHES = {
    "jeddah": ("Jeddah", "جدة", "Jeddah Branch"),
    "madinah": ("Madinah", "المدينة", "Madinah Branch"),
    "riyadh": ("Riyadh", "الرياض", "Riyadh Branch"),
}


class ResCompany(models.Model):
    _inherit = "res.company"

    def _hosny_set_xmlid(self, name, record, noupdate=False):
        self.ensure_one()
        xmlid = self.env["ir.model.data"].sudo().search(
            [("module", "=", "hosny_hr_work_location"), ("name", "=", name)],
            limit=1,
        )
        values = {
            "model": record._name,
            "res_id": record.id,
            "noupdate": noupdate,
        }
        if xmlid:
            xmlid.write(values)
        else:
            self.env["ir.model.data"].sudo().create(
                {
                    "module": "hosny_hr_work_location",
                    "name": name,
                    **values,
                }
            )

    def _hosny_ensure_employee_work_locations(self):
        Partner = self.env["res.partner"].sudo()
        WorkLocation = self.env["hr.work.location"].sudo()
        arabic_installed = bool(
            self.env["res.lang"].sudo().search_count(
                [("code", "=", "ar_001"), ("active", "=", True)]
            )
        )
        main_company = self.env.ref("base.main_company")

        for company in self:
            for code, (english_name, arabic_name, address_name) in BRANCHES.items():
                suffix = "" if company == main_company else f"_company_{company.id}"
                dynamic_company_record = bool(suffix)
                location_xmlid = f"work_location_{code}{suffix}"
                address_xmlid = f"work_address_{code}{suffix}"

                location = self.env.ref(
                    f"hosny_hr_work_location.{location_xmlid}",
                    raise_if_not_found=False,
                )
                if not location:
                    location = WorkLocation.search(
                        [
                            ("company_id", "=", company.id),
                            ("hosny_branch_code", "=", code),
                        ],
                        limit=1,
                    )

                address = location.address_id if location else self.env.ref(
                    f"hosny_hr_work_location.{address_xmlid}",
                    raise_if_not_found=False,
                )
                if not address:
                    address = Partner.with_company(company).create(
                        {
                            "name": address_name,
                            "company_id": company.id,
                            "parent_id": company.partner_id.id,
                            "type": "other",
                        }
                    )
                company._hosny_set_xmlid(
                    address_xmlid,
                    address,
                    noupdate=dynamic_company_record,
                )

                values = {
                    "name": english_name,
                    "company_id": company.id,
                    "address_id": address.id,
                    "location_type": "office",
                    "hosny_branch_code": code,
                    "active": True,
                }
                if location:
                    location.with_context(lang="en_US").write(values)
                else:
                    location = WorkLocation.with_company(company).with_context(
                        lang="en_US"
                    ).create(values)
                company._hosny_set_xmlid(
                    location_xmlid,
                    location,
                    noupdate=dynamic_company_record,
                )

                if arabic_installed:
                    location.with_context(lang="ar_001").write({"name": arabic_name})

        return True

    @api.model_create_multi
    def create(self, vals_list):
        companies = super().create(vals_list)
        if "hr.work.location" in self.env:
            companies._hosny_ensure_employee_work_locations()
        return companies
