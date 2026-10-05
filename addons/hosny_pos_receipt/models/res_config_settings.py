from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    pos_hosny_receipt_title = fields.Char(
        related="pos_config_id.hosny_receipt_title", readonly=False
    )
    pos_hosny_receipt_vat = fields.Char(related="pos_config_id.hosny_receipt_vat", readonly=False)
    pos_hosny_receipt_address = fields.Char(
        related="pos_config_id.hosny_receipt_address", readonly=False
    )
    pos_hosny_receipt_phone = fields.Char(
        related="pos_config_id.hosny_receipt_phone", readonly=False
    )
