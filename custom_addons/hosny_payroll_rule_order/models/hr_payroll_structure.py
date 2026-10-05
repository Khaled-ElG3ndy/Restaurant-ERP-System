from odoo import api, fields, models


class HrPayrollStructure(models.Model):
    _inherit = "hr.payroll.structure"

    hosny_first_rule_id = fields.Many2one(
        "hr.salary.rule",
        compute="_compute_hosny_boundary_rules",
    )
    hosny_last_rule_id = fields.Many2one(
        "hr.salary.rule",
        compute="_compute_hosny_boundary_rules",
    )

    @api.depends(
        "rule_ids",
        "rule_ids.sequence",
        "rule_ids.parent_rule_id",
    )
    def _compute_hosny_boundary_rules(self):
        for structure in self:
            ordered_rules = structure.rule_ids.filtered(
                lambda rule: not rule.parent_rule_id
            ).sorted(key=lambda rule: (rule.sequence, rule.id))
            structure.hosny_first_rule_id = ordered_rules[:1]
            structure.hosny_last_rule_id = ordered_rules[-1:]

