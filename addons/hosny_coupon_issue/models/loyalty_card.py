from odoo import api, fields, models

from .coupon_code import display_code, normalize_code


class LoyaltyCard(models.Model):
    _inherit = "loyalty.card"

    hosny_issue_id = fields.Many2one("hosny.coupon.issue", string="إصدار الكوبون", index=True, readonly=True, copy=False)
    hosny_initial_value = fields.Float(string="قيمة الكوبون", readonly=True, copy=False)
    hosny_used_value = fields.Float(string="المستخدم", compute="_compute_hosny_status")
    hosny_code_display = fields.Char(string="رقم الكوبون", compute="_compute_hosny_code_display")
    hosny_status = fields.Selection(
        [("active", "صالح"), ("used", "استُخدم بالكامل"), ("expired", "منتهي"), ("cancelled", "ملغي")],
        string="الحالة",
        compute="_compute_hosny_status",
    )

    @api.depends("points", "hosny_initial_value", "expiration_date", "hosny_issue_id.state")
    def _compute_hosny_status(self):
        today = fields.Date.context_today(self)
        for card in self:
            card.hosny_used_value = max(0.0, (card.hosny_initial_value or 0.0) - (card.points or 0.0))
            if card.sudo().hosny_issue_id.state == "cancelled":
                card.hosny_status = "cancelled"
            elif (card.points or 0.0) <= 0.0001:
                card.hosny_status = "used"
            elif card.expiration_date and card.expiration_date < today:
                card.hosny_status = "expired"
            else:
                card.hosny_status = "active"

    def _has_source_order(self):
        # كوبون من إصدار صادر = مدفوع (بفاتورة: نقدي / بنك / أجل) — فلا تسأل نقطة البيع «بطاقة هدايا غير مدفوعة»
        # يُستدعى من نقطة البيع بحساب الكاشير: حالة الإصدار تُقرأ بـ sudo
        return super()._has_source_order() or self.sudo().hosny_issue_id.state == "issued"

    @api.depends("code")
    def _compute_hosny_code_display(self):
        for card in self:
            card.hosny_code_display = display_code(card.code or "")

    @api.model
    def get_loyalty_card_partner_by_code(self, code):
        return super().get_loyalty_card_partner_by_code(normalize_code(code))
