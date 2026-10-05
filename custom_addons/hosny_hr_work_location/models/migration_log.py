from odoo import fields, models


class HosnyHrWorkLocationMigrationLog(models.Model):
    _name = "hosny.hr.work.location.migration.log"
    _description = "Employee Work Location Migration Report"
    _order = "state desc, employee_id"
    _rec_name = "employee_id"
    _check_company_auto = True

    employee_id = fields.Many2one(
        "hr.employee",
        required=True,
        index=True,
        ondelete="cascade",
        check_company=True,
    )
    company_id = fields.Many2one(
        "res.company",
        required=True,
        index=True,
    )
    old_address_id = fields.Many2one(
        "res.partner",
        string="Previous Work Address / Contact",
        readonly=True,
    )
    old_value = fields.Char(string="Previous Value", readonly=True)
    work_location_id = fields.Many2one(
        "hr.work.location",
        readonly=True,
        index=True,
        check_company=True,
    )
    state = fields.Selection(
        [
            ("migrated", "Migrated"),
            ("already_assigned", "Already Assigned"),
            ("unresolved", "Unresolved"),
            ("no_legacy_value", "No Previous Value"),
        ],
        required=True,
        readonly=True,
        index=True,
    )
    message = fields.Text(readonly=True)

    _employee_unique = models.Constraint(
        "UNIQUE(employee_id)",
        "Only one work-location migration result is allowed per employee.",
    )
