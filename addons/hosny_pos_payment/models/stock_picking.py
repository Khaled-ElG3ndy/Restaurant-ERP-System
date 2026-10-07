from odoo import api, models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    @api.model
    def _create_picking_from_pos_order_lines(self, location_dest_id, lines, picking_type, partner=False):
        """أسطر المردود التي اختير لها مخزن في «مردود المبيعات» تُقسم: إذن
        مردود لكل مخزن. يعمل في الإنشاء الفوري وعند إغلاق الوردية معاً، لأن
        الاثنين يمران من هنا. بقية الأسطر كما يعاملها أودو."""
        if self.env.context.get("hosny_return_location_id"):
            return super()._create_picking_from_pos_order_lines(location_dest_id, lines, picking_type, partner)
        routed = lines.filtered(lambda line: line.qty < 0 and line.hosny_return_location_id)
        if not routed:
            return super()._create_picking_from_pos_order_lines(location_dest_id, lines, picking_type, partner)

        pickings = super()._create_picking_from_pos_order_lines(location_dest_id, lines - routed, picking_type, partner)
        company = lines[:1].order_id.company_id
        Location = self.env["stock.location"].sudo()
        for location_id in sorted(set(routed.mapped("hosny_return_location_id"))):
            group = routed.filtered(lambda line: line.hosny_return_location_id == location_id)
            location = Location.browse(location_id).exists()
            valid = location.usage == "internal" and location.company_id in (company, company.browse())
            picking_self = self.with_context(hosny_return_location_id=location.id) if valid else self
            pickings |= super(StockPicking, picking_self)._create_picking_from_pos_order_lines(
                location_dest_id, group, picking_type, partner)
        return pickings

    @api.model
    def _prepare_picking_vals(self, partner, picking_type, location_id, location_dest_id):
        """إذن المردود (من العميل إلى المخزن) يذهب إلى المخزن المختار."""
        vals = super()._prepare_picking_vals(partner, picking_type, location_id, location_dest_id)
        location_id_ctx = self.env.context.get("hosny_return_location_id")
        if location_id_ctx and self.env["stock.location"].browse(location_id).usage != "internal":
            vals["location_dest_id"] = location_id_ctx
        return vals
