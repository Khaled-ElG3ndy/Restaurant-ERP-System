from odoo import api, fields, models


class HrAttendance(models.Model):
    _inherit = "hr.attendance"
    _check_company_auto = True

    work_location_id = fields.Many2one(
        "hr.work.location",
        string="Work Location",
        readonly=True,
        copy=False,
        index=True,
        check_company=True,
        help=(
            "Employee work location captured at check-in. Later employee changes "
            "do not alter this attendance history."
        ),
    )

    @api.model_create_multi
    def create(self, vals_list):
        employee_ids = {
            vals.get("employee_id") for vals in vals_list if vals.get("employee_id")
        }
        employees = self.env["hr.employee"].sudo().browse(employee_ids)
        locations = {
            employee.id: employee.work_location_id.id for employee in employees
        }
        for vals in vals_list:
            if not self.env.context.get("hosny_allow_work_location_snapshot"):
                vals.pop("work_location_id", None)
            if locations.get(vals.get("employee_id")):
                vals.setdefault(
                    "work_location_id", locations[vals["employee_id"]]
                )
        return super().create(vals_list)

    def write(self, vals):
        if (
            "work_location_id" in vals
            and not self.env.context.get("hosny_allow_work_location_snapshot")
        ):
            vals = {
                key: value for key, value in vals.items()
                if key != "work_location_id"
            }
        return super().write(vals)
