from odoo import _, api, models
from odoo.exceptions import UserError

from .pos_order import WAITER_NO_PAYMENT


class PosPayment(models.Model):
    _inherit = "pos.payment"

    @api.model_create_multi
    def create(self, vals_list):
        # كل طرق الدفع تمر من هنا: شاشة الدفع، «تسديد الفواتير»، ومعالج الدفع في الخلفية
        if self.env.user._hosny_is_pos_waiter():
            raise UserError(_(WAITER_NO_PAYMENT))
        return super().create(vals_list)
