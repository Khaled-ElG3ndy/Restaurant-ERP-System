from odoo import fields, models


class AccountMove(models.Model):
    _inherit = "account.move"

    hosny_return_picking_ids = fields.One2many(
        "stock.picking",
        "hosny_vendor_refund_id",
        string="Related Stock Returns",
        readonly=True,
    )
