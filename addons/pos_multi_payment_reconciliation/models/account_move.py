from odoo import fields, models


class AccountMove(models.Model):
    _inherit = "account.move"

    pos_session_id = fields.Many2one(
        "pos.session",
        string="POS Session",
        copy=False,
        index=True,
    )
    pos_payment_method_id = fields.Many2one(
        "pos.payment.method",
        string="POS Payment Method",
        copy=False,
        index=True,
    )
    is_pos_payment_adjustment = fields.Boolean(
        string="POS Payment Adjustment",
        copy=False,
        index=True,
    )
    pos_adjustment_amount = fields.Float(
        string="POS Adjustment Amount",
        digits="Account",
        copy=False,
    )
    pos_expected_amount = fields.Float(
        string="POS Expected Amount",
        digits="Account",
        copy=False,
    )
    pos_counted_amount = fields.Float(
        string="POS Counted Amount",
        digits="Account",
        copy=False,
    )
    pos_adjustment_reason = fields.Char(
        string="POS Adjustment Reason",
        copy=False,
    )
