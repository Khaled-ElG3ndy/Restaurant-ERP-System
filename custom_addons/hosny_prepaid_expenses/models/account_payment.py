from odoo import api, fields, models, _
from odoo.exceptions import UserError


class AccountPayment(models.Model):
    _inherit = "account.payment"

    prepaid_schedule_ids = fields.One2many(
        "prepaid.expense.schedule", "vendor_payment_id", string="Prepaid Expenses", copy=False
    )
    prepaid_schedule_count = fields.Integer(compute="_compute_prepaid_amounts")
    prepaid_used_amount = fields.Monetary(
        string="Prepaid Expense Used Amount", currency_field="currency_id", compute="_compute_prepaid_amounts"
    )
    prepaid_available_amount = fields.Monetary(
        string="Prepaid Expense Remaining Amount", currency_field="currency_id", compute="_compute_prepaid_amounts"
    )
    can_create_prepaid_expense = fields.Boolean(compute="_compute_prepaid_amounts")

    @api.depends(
        "state", "partner_type", "payment_type", "amount", "currency_id",
        "move_id.line_ids.amount_residual", "move_id.line_ids.amount_residual_currency",
        "prepaid_schedule_ids.original_amount_currency",
    )
    def _compute_prepaid_amounts(self):
        for payment in self:
            schedules = payment.prepaid_schedule_ids
            payment.prepaid_schedule_count = len(schedules)
            payment.prepaid_used_amount = sum(schedules.mapped("original_amount_currency"))
            counterpart = payment.move_id.line_ids.filtered(
                lambda line: line.account_id == payment.destination_account_id and line.partner_id == payment.partner_id
            )
            if len(counterpart) == 1:
                available = (
                    abs(counterpart.amount_residual_currency)
                    if counterpart.currency_id == payment.currency_id
                    else abs(counterpart.amount_residual)
                )
            else:
                available = 0.0
            payment.prepaid_available_amount = payment.currency_id.round(available)
            payment.can_create_prepaid_expense = (
                payment.partner_type == "supplier"
                and payment.payment_type == "outbound"
                and payment.state in ("in_process", "paid")
                and payment.move_id.state == "posted"
                and payment.currency_id.compare_amounts(available, 0.0) > 0
            )

    def action_create_prepaid_expense(self):
        self.ensure_one()
        if not self.can_create_prepaid_expense:
            raise UserError(_("This vendor payment has no unused amount available for a prepaid expense."))
        return {
            "type": "ir.actions.act_window",
            "name": "إنشاء مصروف مقدم",
            "res_model": "prepaid.expense.payment.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_payment_id": self.id},
        }

    def action_open_prepaid_expenses(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id(
            "hosny_prepaid_expenses.action_prepaid_expense_report"
        )
        action["domain"] = [("vendor_payment_id", "=", self.id)]
        action["context"] = {}
        return action

    def action_draft(self):
        if self.prepaid_schedule_ids:
            raise UserError(_("You cannot reset a vendor payment that has prepaid expense schedules."))
        return super().action_draft()

    def action_cancel(self):
        if self.prepaid_schedule_ids:
            raise UserError(_("You cannot cancel a vendor payment that has prepaid expense schedules."))
        return super().action_cancel()
