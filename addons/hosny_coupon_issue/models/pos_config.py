from odoo import _, api, fields, models

from .coupon_code import is_hosny_code, luhn_valid, normalize_code


class PosConfig(models.Model):
    _inherit = "pos.config"

    hosny_coupon_prefix = fields.Char(
        string="كود الفرع في الكوبونات", size=2,
        help="أول رقمين في كوبونات هذا الفرع (مثلاً 10 جدة، 20 المدينة، 30 الرياض).",
    )

    def use_coupon_code(self, code, creation_date, partner_id, pricelist_id):
        """الكاشير يكتب الكود بمسافات أو شرطات أو أرقام عربية؛ ورقم التحقق يكشف الخطأ."""
        code = normalize_code(code)
        if is_hosny_code(code) and not luhn_valid(code):
            return {
                "successful": False,
                "payload": {"error_message": _("رقم الكوبون غلط (%s) — راجع الأرقام وأعد كتابته.", code)},
            }
        return super().use_coupon_code(code, creation_date, partner_id, pricelist_id)

    @api.constrains("hosny_coupon_prefix")
    def _check_hosny_coupon_prefix(self):
        for config in self:
            prefix = config.hosny_coupon_prefix
            if prefix and not (len(prefix) == 2 and prefix.isdigit()):
                from odoo.exceptions import ValidationError
                raise ValidationError(_("كود الفرع في الكوبونات رقمان (مثل 20)."))
