from odoo import api, fields, models


class PosConfig(models.Model):
    _inherit = "pos.config"

    hosny_safe_account_id = fields.Many2one(
        "account.account",
        string="خزنة الفرع",
        domain="[('account_type', '=', 'asset_cash')]",
        check_company=True,
        help="عند إغلاق الوردية تُسلَّم النقدية المعدودة كلها من صندوق نقطة البيع إلى هذا الحساب، "
             "فتبدأ كل وردية من صفر. بدون حساب يبقى سلوك أودو المعتاد (الافتتاح = نقدية آخر إغلاق).",
    )

    # نقطة البيع لا تحمّل سجل الحساب نفسه، فتقرأ هذا العلم
    hosny_shift_zero_start = fields.Boolean(compute="_compute_hosny_shift_zero_start")
    hosny_safe_account_name = fields.Char(compute="_compute_hosny_shift_zero_start")

    @api.depends("hosny_safe_account_id")
    def _compute_hosny_shift_zero_start(self):
        for config in self:
            config.hosny_shift_zero_start = bool(config.hosny_safe_account_id)
            config.hosny_safe_account_name = config.hosny_safe_account_id.sudo().display_name or False
