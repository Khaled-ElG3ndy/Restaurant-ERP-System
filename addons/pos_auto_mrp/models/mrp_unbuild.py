from odoo import _, api, fields, models
from odoo.exceptions import AccessError


class MrpUnbuild(models.Model):
    _inherit = "mrp.unbuild"

    origin_source = fields.Selection(
        selection="_selection_origin_source",
        string="Origin Source",
        default=lambda self: self._default_origin_source(),
        copy=False,
        index=True,
    )

    @api.model
    def _selection_origin_source(self):
        return [
            ("pos_refund", _("POS Refund")),
            ("sale_return", _("Sales Return")),
            ("manual", _("Manual")),
            ("system", _("System")),
            ("warehouse_adjustment", _("Warehouse Adjustment")),
        ]

    auto_return_allocation_id = fields.Many2one(
        "pos.auto.mrp.return.allocation",
        string="Automatic Return Allocation",
        copy=False,
        ondelete="set null",
        index=True,
    )
    return_picking_id = fields.Many2one(
        related="auto_return_allocation_id.return_picking_id",
        string="Return Transfer",
        store=True,
        index=True,
    )
    return_move_id = fields.Many2one(
        related="auto_return_allocation_id.return_move_id",
        string="Return Stock Move",
        store=True,
        index=True,
    )
    sale_order_line_id = fields.Many2one(
        related="auto_return_allocation_id.sale_order_line_id",
        string="Sales Order Line",
        store=True,
        index=True,
    )
    pos_order_line_id = fields.Many2one(
        related="auto_return_allocation_id.pos_order_line_id",
        string="Original POS Order Line",
        store=True,
        index=True,
    )
    pos_refund_order_line_id = fields.Many2one(
        related="auto_return_allocation_id.pos_refund_order_line_id",
        string="POS Refund Order Line",
        store=True,
        index=True,
    )

    @api.model
    def _default_origin_source(self):
        return (
            self.env.context.get("default_origin_source")
            or self.env.context.get("pos_auto_mrp_origin_source")
            or "manual"
        )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals.setdefault("origin_source", self._default_origin_source())
        return super().create(vals_list)

    def _sync_origin_on_mo(self):
        for unbuild in self.filtered(lambda record: record.state == "done" and record.mo_id):
            vals = {
                "pos_auto_mrp_unbuilt": True,
                "pos_auto_mrp_unbuild_id": unbuild.id,
            }
            try:
                unbuild.mo_id.write(vals)
            except AccessError:
                unbuild.mo_id.sudo().write(vals)

    def _generate_produce_moves(self):
        self.ensure_one()
        if not self.auto_return_allocation_id:
            return super()._generate_produce_moves()
        moves = self.env["stock.move"]
        factor = self.product_qty / self.mo_id.product_uom_id._compute_quantity(
            self.mo_id.qty_produced, self.product_uom_id
        )
        for raw_move in self.mo_id.move_raw_ids.filtered(lambda move: move.state == "done"):
            moves += self._generate_move_from_existing_move(
                raw_move,
                factor,
                raw_move.location_dest_id,
                raw_move.location_id,
            )
        return moves

    def action_validate(self):
        result = super().action_validate()
        self._sync_origin_on_mo()
        return result

    def unlink(self):
        allocations = self.mapped("auto_return_allocation_id")
        result = super().unlink()
        allocations.write({"state": "cancelled", "unbuild_id": False})
        return result
