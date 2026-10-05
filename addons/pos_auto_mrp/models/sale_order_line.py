from odoo import _, api, fields, models


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    mrp_production_ids = fields.One2many(
        "mrp.production",
        "sale_order_line_id",
        string="Manufacturing Orders",
    )

    mrp_production_count = fields.Integer(
        string="MO Count",
        compute="_compute_mrp_production_count",
    )

    pos_auto_mrp_allocation_ids = fields.One2many(
        "pos.auto.mrp.return.allocation",
        "sale_order_line_id",
        string="Return Allocations",
    )
    mrp_unbuild_count = fields.Integer(compute="_compute_pos_auto_mrp_quantities")
    manufactured_qty = fields.Float(
        string="Manufactured Quantity", compute="_compute_pos_auto_mrp_quantities", digits="Product Unit"
    )
    returned_qty = fields.Float(
        string="Returned Quantity", compute="_compute_pos_auto_mrp_quantities", digits="Product Unit"
    )
    unbuilt_qty = fields.Float(
        string="Unbuilt Quantity", compute="_compute_pos_auto_mrp_quantities", digits="Product Unit"
    )
    remaining_returnable_qty = fields.Float(
        string="Remaining Returnable Quantity",
        compute="_compute_pos_auto_mrp_quantities",
        digits="Product Unit",
    )

    def _compute_mrp_production_count(self):
        for line in self:
            line.mrp_production_count = len(line.mrp_production_ids)

    @api.depends(
        "mrp_production_ids.state",
        "mrp_production_ids.qty_produced",
        "pos_auto_mrp_allocation_ids.state",
        "pos_auto_mrp_allocation_ids.quantity",
        "pos_auto_mrp_allocation_ids.product_uom_id",
    )
    def _compute_pos_auto_mrp_quantities(self):
        for line in self:
            allocations = line.pos_auto_mrp_allocation_ids.filtered(
                lambda allocation: allocation.state == "done"
            )
            line.mrp_unbuild_count = len(allocations.mapped("unbuild_id"))
            line.manufactured_qty = sum(
                production.product_uom_id._compute_quantity(
                    production.qty_produced, line.product_uom_id
                )
                for production in line.mrp_production_ids.filtered(
                    lambda production: production.state == "done" and production.pos_auto_mrp_generated
                )
            )
            line.returned_qty = sum(
                allocation.product_uom_id._compute_quantity(
                    allocation.quantity, line.product_uom_id
                )
                for allocation in allocations
            )
            line.unbuilt_qty = line.returned_qty
            line.remaining_returnable_qty = max(
                min(line.product_uom_qty, line.manufactured_qty) - line.unbuilt_qty, 0.0
            )

    def action_open_mrp_productions(self):
        self.ensure_one()
        if not self.mrp_production_ids:
            return False

        if len(self.mrp_production_ids) == 1:
            return {
                "type": "ir.actions.act_window",
                "name": _("Manufacturing Order"),
                "res_model": "mrp.production",
                "view_mode": "form",
                "res_id": self.mrp_production_ids.id,
                "target": "current",
            }

        return {
            "type": "ir.actions.act_window",
            "name": _("Manufacturing Orders"),
            "res_model": "mrp.production",
            "view_mode": "tree,form",
            "domain": [("id", "in", self.mrp_production_ids.ids)],
            "target": "current",
        }


    def action_open_mrp_unbuilds(self):
        self.ensure_one()
        unbuilds = self.pos_auto_mrp_allocation_ids.mapped("unbuild_id")
        if not unbuilds:
            return False
        action = {
            "type": "ir.actions.act_window",
            "name": _("Unbuild Orders"),
            "res_model": "mrp.unbuild",
            "view_mode": "list,form",
            "domain": [("id", "in", unbuilds.ids)],
            "target": "current",
        }
        if len(unbuilds) == 1:
            action.update({"view_mode": "form", "res_id": unbuilds.id})
        return action
