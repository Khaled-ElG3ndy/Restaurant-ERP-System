from odoo import fields, models


class PosConfig(models.Model):
    _inherit = "pos.config"

    analytic_account_id = fields.Many2one(
        "account.analytic.account",
        string="الحساب التحليلي",
        check_company=True,
        required=True,
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        help="Analytic account used on journal entries and invoices created from this Point of Sale.",
    )
