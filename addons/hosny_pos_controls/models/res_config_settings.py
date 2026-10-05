from odoo import models, fields

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    pos_require_manager_discount  = fields.Boolean(
        'Require Manager PIN for Discounts',
        config_parameter='hosny_pos_controls.require_manager_discount',
        default=True)
    pos_require_manager_refund    = fields.Boolean(
        'Require Manager PIN for Refunds',
        config_parameter='hosny_pos_controls.require_manager_refund',
        default=True)
    pos_require_manager_void      = fields.Boolean(
        'Require Manager PIN for Voids',
        config_parameter='hosny_pos_controls.require_manager_void',
        default=True)
    pos_require_manager_price     = fields.Boolean(
        'Require Manager PIN for Price Edits',
        config_parameter='hosny_pos_controls.require_manager_price',
        default=True)
    pos_max_discount_pct          = fields.Integer(
        'Max Discount % without Manager',
        config_parameter='hosny_pos_controls.max_discount_pct',
        default=5)
