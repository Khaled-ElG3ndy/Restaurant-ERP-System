from odoo import api, models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    @api.model
    def _prepare_picking_vals(self, partner, picking_type, location_id, location_dest_id):
        """إذن المردود (من العميل إلى المخزن) يذهب إلى المخزن المختار في
        شاشة «مردود المبيعات» (pos.order._create_order_picking يمرره في السياق)."""
        vals = super()._prepare_picking_vals(partner, picking_type, location_id, location_dest_id)
        location_id_ctx = self.env.context.get("hosny_return_location_id")
        if location_id_ctx and self.env["stock.location"].browse(location_id).usage != "internal":
            vals["location_dest_id"] = location_id_ctx
        return vals
