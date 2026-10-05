from odoo import _, models
from odoo.exceptions import UserError


class HrSalaryRule(models.Model):
    _inherit = "hr.salary.rule"

    def _payroll_structure_from_order_context(self):
        self.ensure_one()
        structure_id = self.env.context.get(
            "payroll_rule_order_structure_id"
        )
        try:
            structure_id = int(structure_id)
        except (TypeError, ValueError):
            structure_id = 0
        structure = self.env["hr.payroll.structure"].browse(
            structure_id
        ).exists()
        if not structure:
            raise UserError(
                _(
                    "Save the salary structure before changing the rule order."
                )
            )
        structure.check_access("write")
        if self not in structure.rule_ids:
            raise UserError(
                _(
                    "This salary rule does not belong to the selected salary structure."
                )
            )
        return structure

    def _ordered_structure_rules(self, structure):
        return structure.rule_ids.filtered(
            lambda rule: not rule.parent_rule_id
        ).sorted(key=lambda rule: (rule.sequence, rule.id))

    def _make_structure_sequences_distinct(self, structure):
        last_sequence = None
        for rule in self._ordered_structure_rules(structure):
            next_sequence = rule.sequence
            if (
                last_sequence is not None
                and next_sequence <= last_sequence
            ):
                next_sequence = last_sequence + 1
                rule.write({"sequence": next_sequence})
            last_sequence = next_sequence

    def _move_in_payroll_structure(self, offset):
        self.ensure_one()
        structure = self._payroll_structure_from_order_context()
        self._make_structure_sequences_distinct(structure)
        ordered_rules = self._ordered_structure_rules(structure)
        current_index = ordered_rules.ids.index(self.id)
        target_index = current_index + offset
        if target_index < 0 or target_index >= len(ordered_rules):
            position = _("first") if offset < 0 else _("last")
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Salary Rule Order"),
                    "message": _(
                        "This salary rule is already %(position)s.",
                        position=position,
                    ),
                    "type": "info",
                    "sticky": False,
                },
            }

        target_rule = ordered_rules[target_index]
        current_sequence = self.sequence
        target_sequence = target_rule.sequence
        target_rule.write({"sequence": current_sequence})
        self.write({"sequence": target_sequence})
        return False

    def action_move_up_in_payroll_structure(self):
        return self._move_in_payroll_structure(-1)

    def action_move_down_in_payroll_structure(self):
        return self._move_in_payroll_structure(1)
