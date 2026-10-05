from odoo import _, models
from odoo.exceptions import UserError


class PosSession(models.Model):
    _inherit = "pos.session"

    def _get_split_receivable_vals(self, payment, amount, amount_converted):
        advance_account = payment.payment_method_id.receivable_account_id
        if payment.payment_method_id.type != "pay_later" or not advance_account:
            return super()._get_split_receivable_vals(payment, amount, amount_converted)

        accounting_partner = self.env["res.partner"]._find_accounting_partner(payment.partner_id)
        if not accounting_partner:
            raise UserError(
                _(
                    "لازم تختار العميل قبل الدفع الآجل للطلب %(order)s.",
                    order=payment.pos_order_id.name,
                )
            )
        partial_vals = {
            "account_id": advance_account.id,
            "move_id": self.move_id.id,
            "partner_id": accounting_partner.id,
            "name": "%s - %s" % (self.name, payment.payment_method_id.name),
        }
        return self._debit_amounts(partial_vals, amount, amount_converted)
