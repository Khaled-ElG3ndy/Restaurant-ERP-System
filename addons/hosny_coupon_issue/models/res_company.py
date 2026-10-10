from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    hosny_coupon_program_id = fields.Many2one(
        "loyalty.program",
        string="برنامج كوبونات الخصم",
        domain="[('program_type', '=', 'gift_card')]",
        help="برنامج أودو للكوبونات المدفوعة (رصيد ينقص مع الاستخدام). الإصدار من المبيعات ينشئ بطاقاته.",
    )
    hosny_coupon_account_id = fields.Many2one(
        "account.account",
        string="حساب الكوبونات (التزام)",
        domain="[('account_type', '=', 'liability_current')]",
        help="يُقيَّد دائناً عند الإصدار، ومديناً عند الاستخدام في نقطة البيع (سطر الكوبون بنفس الحساب).",
    )
