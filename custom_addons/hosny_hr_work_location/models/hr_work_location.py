from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class HrWorkLocation(models.Model):
    _inherit = "hr.work.location"

    name = fields.Char(
        string="Work Location",
        required=True,
        translate=True,
    )
    hosny_branch_code = fields.Selection(
        [
            ("jeddah", "Jeddah"),
            ("madinah", "Madinah"),
            ("riyadh", "Riyadh"),
        ],
        string="Employee Branch",
        copy=False,
        index=True,
        help="Only locations marked as an employee branch are selectable on employees.",
    )

    _hosny_company_branch_unique = models.Constraint(
        "UNIQUE(company_id, hosny_branch_code)",
        "An employee branch can only have one work location per company.",
    )

    @api.constrains("company_id", "address_id")
    def _check_hosny_address_company(self):
        for location in self.filtered("hosny_branch_code"):
            if (
                location.address_id.company_id
                and location.address_id.company_id != location.company_id
            ):
                raise ValidationError(
                    _("The work location address must belong to the same company.")
                )
