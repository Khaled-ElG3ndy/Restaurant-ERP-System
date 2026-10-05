from odoo import fields, models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    hosny_vendor_refund_id = fields.Many2one(
        "account.move",
        string="Vendor Credit Note",
        copy=False,
        readonly=True,
        index=True,
        check_company=True,
    )
