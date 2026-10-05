from odoo import models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def _create_picking_from_pos_order_lines(self, location_dest_id, lines, picking_type, partner=False):
        component_stock_lines = lines.filtered(lambda line: not line.is_meal_parent)
        return super()._create_picking_from_pos_order_lines(
            location_dest_id,
            component_stock_lines,
            picking_type,
            partner=partner,
        )
