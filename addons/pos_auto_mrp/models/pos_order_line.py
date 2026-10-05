from odoo import _, api, fields, models


class PosOrderLine(models.Model):
    _inherit = "pos.order.line"

    def _pos_auto_mrp_finished_product_locations(self):
        """Return recorded finished-product locations for completed POS MOs.

        This deliberately reads stock moves, not the current product/profile
        configuration, so historical POS refunds keep their original route.
        """
        self.ensure_one()
        productions = (self.mrp_production_id | self.mrp_production_ids).filtered(
            lambda production: production.pos_auto_mrp_generated
            and production.state == "done"
            and production.product_id == self.product_id
        )
        finished_moves = productions.mapped("move_finished_ids").filtered(
            lambda move: move.state == "done"
            and move.product_id == self.product_id
            and move.location_dest_id
        )
        return finished_moves.mapped("location_dest_id")

    @api.model
    def _pos_auto_mrp_existing_refund_line_id(self, line_id):
        if not line_id:
            return False
        return self.browse(line_id).exists().id or False

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("refunded_orderline_id"):
                vals["refunded_orderline_id"] = self._pos_auto_mrp_existing_refund_line_id(
                    vals["refunded_orderline_id"]
                )
        return super().create(vals_list)

    def write(self, vals):
        if vals.get("refunded_orderline_id"):
            vals["refunded_orderline_id"] = self._pos_auto_mrp_existing_refund_line_id(
                vals["refunded_orderline_id"]
            )
        return super().write(vals)

    mrp_production_id = fields.Many2one(
        "mrp.production",
        string="Manufacturing Order",
        copy=False,
        index=True,
    )
    mrp_unbuild_id = fields.Many2one(
        "mrp.unbuild",
        string="Unbuild Order",
        copy=False,
        index=True,
    )

    mrp_production_ids = fields.Many2many(
        "mrp.production",
        "pos_auto_mrp_production_pos_line_rel",
        "pos_line_id",
        "production_id",
        string="Manufacturing Orders",
        copy=False,
    )
    pos_auto_mrp_allocation_ids = fields.One2many(
        "pos.auto.mrp.return.allocation",
        "pos_order_line_id",
        string="Return Allocations",
    )
    pos_auto_mrp_refund_allocation_ids = fields.One2many(
        "pos.auto.mrp.return.allocation",
        "pos_refund_order_line_id",
        string="Refund Allocations",
    )
    mrp_production_count = fields.Integer(
        compute="_compute_pos_auto_mrp_quantities",
        compute_sudo=True,
    )
    mrp_unbuild_count = fields.Integer(
        compute="_compute_pos_auto_mrp_quantities",
        compute_sudo=True,
    )
    manufactured_qty = fields.Float(
        string="Manufactured Quantity",
        compute="_compute_pos_auto_mrp_quantities",
        compute_sudo=True,
        digits="Product Unit",
    )
    returned_qty = fields.Float(
        string="Returned Quantity",
        compute="_compute_pos_auto_mrp_quantities",
        compute_sudo=True,
        digits="Product Unit",
    )
    unbuilt_qty = fields.Float(
        string="Unbuilt Quantity",
        compute="_compute_pos_auto_mrp_quantities",
        compute_sudo=True,
        digits="Product Unit",
    )
    remaining_returnable_qty = fields.Float(
        string="Remaining Returnable Quantity",
        compute="_compute_pos_auto_mrp_quantities",
        compute_sudo=True,
        digits="Product Unit",
    )

    @api.depends(
        "mrp_production_id",
        "mrp_production_ids.state",
        "mrp_production_ids.qty_produced",
        "pos_auto_mrp_allocation_ids.state",
        "pos_auto_mrp_allocation_ids.quantity",
        "pos_auto_mrp_refund_allocation_ids.state",
    )
    def _compute_pos_auto_mrp_quantities(self):
        for line in self:
            productions = line.mrp_production_ids | line.mrp_production_id
            allocations = line.pos_auto_mrp_allocation_ids.filtered(
                lambda allocation: allocation.state == "done"
            )
            refund_allocations = line.pos_auto_mrp_refund_allocation_ids.filtered(
                lambda allocation: allocation.state == "done"
            )
            line.mrp_production_count = len(productions)
            line.mrp_unbuild_count = len(
                (allocations | refund_allocations).mapped("unbuild_id")
            )
            line.manufactured_qty = sum(
                production.product_uom_id._compute_quantity(
                    production.qty_produced, line.product_uom_id
                )
                for production in productions.filtered(lambda production: production.state == "done")
            )
            line.returned_qty = sum(
                allocation.product_uom_id._compute_quantity(
                    allocation.quantity, line.product_uom_id
                )
                for allocation in allocations
            )
            line.unbuilt_qty = line.returned_qty
            line.remaining_returnable_qty = max(
                min(abs(line.qty), line.manufactured_qty) - line.unbuilt_qty, 0.0
            ) if line.qty > 0 else 0.0

    def action_open_mrp_production(self):
        self.ensure_one()
        productions = self.mrp_production_ids | self.mrp_production_id
        if not productions:
            return False
        action = {
            "type": "ir.actions.act_window",
            "name": _("Manufacturing Orders"),
            "res_model": "mrp.production",
            "view_mode": "list,form",
            "domain": [("id", "in", productions.ids)],
            "target": "current",
        }
        if len(productions) == 1:
            action.update({"view_mode": "form", "res_id": productions.id})
        return action

    def action_open_mrp_unbuild(self):
        self.ensure_one()
        unbuilds = (
            self.pos_auto_mrp_allocation_ids | self.pos_auto_mrp_refund_allocation_ids
        ).mapped("unbuild_id") | self.mrp_unbuild_id
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
