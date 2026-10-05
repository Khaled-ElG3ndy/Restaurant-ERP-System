from odoo import fields, models


class HrWorkLocation(models.Model):
    _inherit = "hr.work.location"

    hosny_analytic_account_id = fields.Many2one(
        "account.analytic.account",
        string="الحساب التحليلي",
        check_company=True,
        help=(
            "الحساب التحليلي (الفرع) الذي تُحمَّل عليه تكلفة رواتب موظفي هذا "
            "الموقع. يُستخدم في قيد الراتب لأن الحساب التحليلي إلزامي على "
            "قيود اليومية في هذا النظام."
        ),
    )
