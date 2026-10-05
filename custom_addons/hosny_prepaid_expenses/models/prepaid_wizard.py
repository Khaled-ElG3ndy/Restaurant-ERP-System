from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from odoo.tools import float_compare


class PrepaidExpenseWizardMixin(models.AbstractModel):
    _name = "prepaid.expense.wizard.mixin"
    _description = "Prepaid Expense Wizard Common Fields"

    amount = fields.Monetary(string="Prepaid Expense Amount", required=True)
    available_amount = fields.Monetary(string="Available Amount", readonly=True)
    currency_id = fields.Many2one("res.currency", required=True, readonly=True)
    start_date = fields.Date(string="Start Date", required=True, default=fields.Date.context_today)
    end_date = fields.Date(string="End Date", required=True)
    distribution_method = fields.Selection(
        [("monthly", "شهري"), ("daily", "يومي"), ("custom", "عدد فترات مخصص")],
        string="Distribution Method",
        required=True,
        default="monthly",
    )
    installment_count = fields.Integer(string="Number of Installments", default=1)
    actual_account_id = fields.Many2one(
        "account.account", string="Actual Expense Account", required=True, check_company=True
    )
    prepaid_account_id = fields.Many2one(
        "account.account", string="Prepaid Expense Account", required=True, check_company=True
    )
    name = fields.Char(string="Description", required=True)
    company_id = fields.Many2one("res.company", required=True, readonly=True)
    analytic_account_id = fields.Many2one(
        "account.analytic.account", string="Branch", required=True, check_company=True
    )
    analytic_distribution = fields.Json(string="Analytic Distribution")

    @api.onchange("start_date", "distribution_method", "installment_count")
    def _onchange_period(self):
        for wizard in self:
            if not wizard.start_date:
                continue
            if wizard.distribution_method == "custom" and wizard.installment_count > 0:
                wizard.end_date = wizard.start_date + relativedelta(months=wizard.installment_count, days=-1)
            elif not wizard.end_date:
                wizard.end_date = wizard.start_date + relativedelta(years=1, days=-1)

    @api.constrains("amount", "available_amount", "start_date", "end_date", "installment_count")
    def _check_values(self):
        for wizard in self:
            if float_compare(wizard.amount, 0.0, precision_rounding=wizard.currency_id.rounding) <= 0:
                raise ValidationError(_("The prepaid expense amount must be greater than zero."))
            if float_compare(
                wizard.amount, wizard.available_amount, precision_rounding=wizard.currency_id.rounding
            ) > 0:
                raise ValidationError(_("The prepaid expense amount exceeds the available source amount."))
            if wizard.end_date < wizard.start_date:
                raise ValidationError(_("The prepaid expense end date cannot be before the start date."))
            if wizard.distribution_method == "custom" and wizard.installment_count <= 0:
                raise ValidationError(_("The number of installments must be greater than zero."))

    def _service_values(self):
        self.ensure_one()
        return {
            "amount": self.amount,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "distribution_method": self.distribution_method,
            "installment_count": self.installment_count,
            "actual_account": self.actual_account_id,
            "prepaid_account": self.prepaid_account_id,
            "analytic_account": self.analytic_account_id,
            "analytic_distribution": self.analytic_distribution,
            "name": self.name,
        }


class PrepaidExpenseBillWizard(models.TransientModel):
    _name = "prepaid.expense.bill.wizard"
    _inherit = "prepaid.expense.wizard.mixin"
    _description = "Create Prepaid Expense from Purchase Document"

    move_id = fields.Many2one(
        "account.move", string="Purchase Document", required=True, readonly=True, check_company=True
    )
    line_id = fields.Many2one(
        "account.move.line", string="Purchase Document Line", required=True, check_company=True
    )

    @api.model
    def default_get(self, field_list):
        values = super().default_get(field_list)
        move = self.env["account.move"].browse(values.get("move_id") or self.env.context.get("default_move_id"))
        line = move._prepaid_eligible_source_lines()[:1] if move else self.env["account.move.line"]
        if move:
            values.update({
                "move_id": move.id,
                "company_id": move.company_id.id,
                "currency_id": move.currency_id.id,
                "analytic_account_id": move.analytic_account_id.id,
            })
        if line:
            _company_amount, currency_amount = line._prepaid_source_totals()
            values.update({
                "line_id": line.id,
                "available_amount": currency_amount,
                "amount": currency_amount,
                "actual_account_id": line.prepaid_actual_account_id.id or line.account_id.id,
                "prepaid_account_id": line.prepaid_account_id.id,
                "name": line.name,
                "analytic_distribution": line.analytic_distribution,
                "start_date": line.prepaid_start_date or fields.Date.context_today(self),
                "end_date": line.prepaid_end_date or fields.Date.context_today(self) + relativedelta(years=1, days=-1),
                "distribution_method": line.prepaid_distribution_method or "monthly",
                "installment_count": line.prepaid_installment_count or 1,
            })
        return values

    @api.onchange("line_id")
    def _onchange_line_id(self):
        for wizard in self.filtered("line_id"):
            line = wizard.line_id
            _company_amount, currency_amount = line._prepaid_source_totals()
            wizard.available_amount = currency_amount
            wizard.amount = currency_amount
            wizard.actual_account_id = line.prepaid_actual_account_id or line.account_id
            wizard.prepaid_account_id = line.prepaid_account_id
            wizard.name = line.name
            wizard.analytic_distribution = line.analytic_distribution

    def action_confirm(self):
        self.ensure_one()
        values = self._service_values()
        values.update({"source_type": "vendor_bill", "source": self.move_id, "source_line": self.line_id})
        self.env["prepaid.expense.schedule"].create_from_source(values)
        return {"type": "ir.actions.act_window_close"}


class PrepaidExpensePaymentWizard(models.TransientModel):
    _name = "prepaid.expense.payment.wizard"
    _inherit = "prepaid.expense.wizard.mixin"
    _description = "Create Prepaid Expense from Vendor Payment"

    payment_id = fields.Many2one(
        "account.payment", string="Vendor Payment", required=True, readonly=True, check_company=True
    )
    partner_id = fields.Many2one("res.partner", string="Vendor", readonly=True)
    payment_amount = fields.Monetary(string="Payment Amount", readonly=True)

    @api.model
    def default_get(self, field_list):
        values = super().default_get(field_list)
        payment = self.env["account.payment"].browse(
            values.get("payment_id") or self.env.context.get("default_payment_id")
        )
        if payment:
            values.update({
                "payment_id": payment.id,
                "partner_id": payment.partner_id.id,
                "payment_amount": payment.amount,
                "available_amount": payment.prepaid_available_amount,
                "amount": payment.prepaid_available_amount,
                "company_id": payment.company_id.id,
                "currency_id": payment.currency_id.id,
                "name": payment.memo or payment.name,
                "start_date": payment.date,
                "end_date": payment.date + relativedelta(years=1, days=-1),
            })
        return values

    def action_confirm(self):
        self.ensure_one()
        values = self._service_values()
        values.update({"source_type": "vendor_payment", "source": self.payment_id})
        self.env["prepaid.expense.schedule"].create_from_source(values)
        return {"type": "ir.actions.act_window_close"}
