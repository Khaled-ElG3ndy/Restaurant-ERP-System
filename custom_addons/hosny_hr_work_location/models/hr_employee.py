from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class HrVersion(models.Model):
    _inherit = "hr.version"

    work_location_id = fields.Many2one(
        "hr.work.location",
        string="Work Location",
        domain=(
            "[('company_id', '=', company_id), "
            "('hosny_branch_code', 'in', ['jeddah', 'madinah', 'riyadh'])]"
        ),
        check_company=True,
        tracking=True,
    )

    @api.onchange("work_location_id")
    def _onchange_hosny_work_location_id(self):
        for version in self:
            if version.work_location_id:
                version.address_id = version.work_location_id.address_id

    @api.model_create_multi
    def create(self, vals_list):
        locations = self.env["hr.work.location"].browse(
            [vals.get("work_location_id") for vals in vals_list]
        )
        locations_by_id = {location.id: location for location in locations}
        for vals in vals_list:
            location = locations_by_id.get(vals.get("work_location_id"))
            if location:
                vals["address_id"] = location.address_id.id
        return super().create(vals_list)

    def write(self, vals):
        if vals.get("work_location_id"):
            location = self.env["hr.work.location"].browse(
                vals["work_location_id"]
            ).exists()
            if location:
                vals = {**vals, "address_id": location.address_id.id}
        return super().write(vals)

    @api.constrains("work_location_id", "company_id")
    def _check_hosny_work_location(self):
        for version in self.filtered("work_location_id"):
            if not version.work_location_id.hosny_branch_code:
                raise ValidationError(
                    _("Employees can only use an approved employee work location.")
                )
            if version.work_location_id.company_id != version.company_id:
                raise ValidationError(
                    _("The employee and work location must belong to the same company.")
                )


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    usual_week_location_id = fields.Many2one(
        "hr.work.location",
        string="تطبيق الموقع على كل الأيام",
        compute="_compute_usual_week_location_id",
        inverse="_inverse_usual_week_location_id",
        readonly=False,
        domain=(
            "[('company_id', '=', company_id), "
            "('hosny_branch_code', 'in', ['jeddah', 'madinah', 'riyadh'])]"
        ),
        check_company=True,
    )

    def _get_week_location_fields(self):
        return [
            "monday_location_id",
            "tuesday_location_id",
            "wednesday_location_id",
            "thursday_location_id",
            "friday_location_id",
            "saturday_location_id",
            "sunday_location_id",
        ]

    @api.depends(
        "monday_location_id",
        "tuesday_location_id",
        "wednesday_location_id",
        "thursday_location_id",
        "friday_location_id",
        "saturday_location_id",
        "sunday_location_id",
    )
    def _compute_usual_week_location_id(self):
        week_fields = self._get_week_location_fields()
        for employee in self:
            location_ids = [employee[field_name].id for field_name in week_fields]
            employee.usual_week_location_id = (
                location_ids[0]
                if location_ids[0] and all(location_id == location_ids[0] for location_id in location_ids)
                else False
            )

    def _inverse_usual_week_location_id(self):
        week_fields = self._get_week_location_fields()
        for employee in self:
            if not employee.usual_week_location_id:
                continue
            employee.update(
                {field_name: employee.usual_week_location_id for field_name in week_fields}
            )

    @api.onchange("usual_week_location_id")
    def _onchange_usual_week_location_id(self):
        week_fields = self._get_week_location_fields()
        for employee in self:
            if not employee.usual_week_location_id:
                continue
            employee.update(
                {field_name: employee.usual_week_location_id for field_name in week_fields}
            )
