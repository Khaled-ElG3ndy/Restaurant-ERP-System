from collections import defaultdict
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare


_logger = logging.getLogger(__name__)


class MrpProduction(models.Model):
    _inherit = "mrp.production"

    def _pos_auto_mrp_component_requirements(self):
        """Return actual storable component demand grouped by product/location."""
        self.ensure_one()
        requirements = defaultdict(float)
        for move in self.move_raw_ids.filtered(
            lambda item: item.state not in ("done", "cancel")
        ):
            product = move.product_id
            if "is_storable" in product._fields and not product.is_storable:
                continue
            if not move.location_id:
                return False
            key = (product, move.location_id)
            requirements[key] += move.product_uom._compute_quantity(
                move.product_uom_qty,
                product.uom_id,
            )
        return requirements

    def _pos_auto_mrp_components_available(self):
        """Check physical stock, including this MO's own existing reservations."""
        self.ensure_one()
        requirements = self._pos_auto_mrp_component_requirements()
        if requirements is False:
            return False

        Quant = self.env["stock.quant"].sudo()
        for (product, location), required_qty in requirements.items():
            available_qty = Quant._get_available_quantity(
                product, location, strict=False
            )
            if self.state != "draft":
                own_reserved_qty = sum(
                    move.product_uom._compute_quantity(
                        move.quantity, product.uom_id
                    )
                    for move in self.move_raw_ids.filtered(
                        lambda item: item.state not in ("done", "cancel")
                        and item.product_id == product
                        and item.location_id == location
                    )
                )
                available_qty += own_reserved_qty
            if float_compare(
                available_qty,
                required_qty,
                precision_rounding=product.uom_id.rounding,
            ) < 0:
                return False
        return True

    def _pos_auto_mrp_complete_if_available(self):
        """Confirm and complete an automatic MO only with sufficient components."""
        self.ensure_one()
        if self.state == "done":
            return True
        if self.state == "cancel":
            return False
        if not self._pos_auto_mrp_components_available():
            _logger.info(
                "POS Auto MRP: MO %s remains in state %s because one or more components are unavailable.",
                self.name,
                self.state,
            )
            return False

        if self.state == "draft":
            self.action_confirm()

        # A finished tracked product needs a user-selected lot/serial. Keep the
        # MO confirmed instead of blocking the originating sale transaction.
        if self.product_id.tracking != "none" and not self.lot_producing_ids:
            _logger.info(
                "POS Auto MRP: MO %s is confirmed but awaits a finished-product lot/serial number.",
                self.name,
            )
            return False

        self.action_assign()
        self.qty_producing = self.product_qty
        for move in self.move_raw_ids.filtered(
            lambda item: item.state not in ("done", "cancel")
        ):
            vals = {}
            if "quantity" in move._fields:
                vals["quantity"] = move.product_uom_qty
            if "picked" in move._fields:
                vals["picked"] = True
            if vals:
                move.write(vals)

        self.button_mark_done()
        if self.state != "done":
            raise UserError(
                _("Automatic completion did not finish manufacturing order %s.")
                % self.display_name
            )
        _logger.info(
            "POS Auto MRP: MO %s was confirmed and marked done automatically because all components were available.",
            self.name,
        )
        return True

    pos_auto_mrp_generated = fields.Boolean(
        string="Automatically Generated",
        copy=False,
        index=True,
        help="This manufacturing order was created by the POS Auto MRP sales workflow.",
    )

    pos_auto_mrp_unbuilt = fields.Boolean(
        string="Has Tracked Unbuild",
        copy=False,
        index=True,
    )

    pos_auto_mrp_unbuild_id = fields.Many2one(
        "mrp.unbuild",
        string="Latest Unbuild",
        copy=False,
        index=True,
        help="Latest unbuild order tracked on this manufacturing order.",
    )

    pos_auto_mrp_refund_status = fields.Char(
        string="Unbuild Status",
        compute="_compute_pos_auto_mrp_refund_status",
    )

    pos_order_id = fields.Many2one(
        "pos.order",
        string="POS Order",
        copy=False,
        index=True,
    )

    pos_order_line_id = fields.Many2one(
        "pos.order.line",
        string="POS Order Line",
        copy=False,
        index=True,
    )

    pos_order_line_ids = fields.Many2many(
        "pos.order.line",
        "pos_auto_mrp_production_pos_line_rel",
        "production_id",
        "pos_line_id",
        string="POS Order Lines",
        copy=False,
    )

    sale_order_id = fields.Many2one(
        "sale.order",
        string="Sales Order",
        copy=False,
        index=True,
    )

    sale_order_line_id = fields.Many2one(
        "sale.order.line",
        string="Sales Order Line",
        copy=False,
        index=True,
    )

    pos_auto_mrp_allocation_ids = fields.One2many(
        "pos.auto.mrp.return.allocation",
        "production_id",
        string="Automatic Return Allocations",
    )

    pos_auto_mrp_unbuild_count = fields.Integer(
        string="Automatic Unbuild Count",
        compute="_compute_pos_auto_mrp_return_quantities",
    )
    pos_auto_mrp_unbuilt_qty = fields.Float(
        string="Automatically Unbuilt Quantity",
        compute="_compute_pos_auto_mrp_return_quantities",
        digits="Product Unit",
    )
    pos_auto_mrp_returnable_qty = fields.Float(
        string="Remaining Returnable Quantity",
        compute="_compute_pos_auto_mrp_return_quantities",
        digits="Product Unit",
    )

    @api.depends(
        "pos_auto_mrp_allocation_ids.state",
        "pos_auto_mrp_allocation_ids.quantity",
        "pos_auto_mrp_allocation_ids.product_uom_id",
        "unbuild_ids.state",
        "unbuild_ids.product_qty",
        "qty_produced",
    )
    def _compute_pos_auto_mrp_return_quantities(self):
        for production in self:
            unbuilds = production.pos_auto_mrp_allocation_ids.filtered(
                lambda allocation: allocation.state == "done"
            ).mapped("unbuild_id")
            production.pos_auto_mrp_unbuild_count = len(unbuilds)
            production.pos_auto_mrp_unbuilt_qty = sum(
                unbuild.product_uom_id._compute_quantity(
                    unbuild.product_qty, production.product_uom_id
                )
                for unbuild in unbuilds.filtered(lambda item: item.state == "done")
            )
            all_reserved = sum(
                unbuild.product_uom_id._compute_quantity(
                    unbuild.product_qty, production.product_uom_id
                )
                for unbuild in production.unbuild_ids
            )
            production.pos_auto_mrp_returnable_qty = max(
                production.qty_produced - all_reserved, 0.0
            )

    pos_order_name = fields.Char(
        string="POS Order Name",
        compute="_compute_order_names",
    )

    sale_order_name = fields.Char(
        string="Sales Order Name",
        compute="_compute_order_names",
    )

    @api.depends("pos_order_id", "sale_order_id")
    def _compute_order_names(self):
        for rec in self:
            rec.pos_order_name = rec.pos_order_id.name if rec.pos_order_id else ""
            rec.sale_order_name = rec.sale_order_id.name if rec.sale_order_id else ""

    @api.depends("pos_auto_mrp_unbuild_id", "pos_auto_mrp_unbuild_id.origin_source")
    def _compute_pos_auto_mrp_refund_status(self):
        label_map = {
            "pos_refund": _("Unbuilt by POS Refund"),
            "sale_return": _("Unbuilt by Sales Return"),
            "manual": _("Manually Unbuilt"),
            "system": _("System Unbuild"),
            "warehouse_adjustment": _("Stock Adjustment Unbuild"),
        }
        for rec in self:
            source = rec.pos_auto_mrp_unbuild_id.origin_source
            if not source and rec.pos_auto_mrp_unbuild_id:
                source = "pos_refund"
            rec.pos_auto_mrp_refund_status = label_map.get(source, False)

    def action_open_pos_order(self):
        self.ensure_one()
        if not self.pos_order_id:
            return False
        return {
            "type": "ir.actions.act_window",
            "name": "POS Order",
            "res_model": "pos.order",
            "view_mode": "form",
            "res_id": self.pos_order_id.id,
            "target": "current",
        }

    def action_open_sale_order(self):
        self.ensure_one()
        if not self.sale_order_id:
            return False
        return {
            "type": "ir.actions.act_window",
            "name": "Sales Order",
            "res_model": "sale.order",
            "view_mode": "form",
            "res_id": self.sale_order_id.id,
            "target": "current",
        }

    def action_open_pos_auto_mrp_unbuild(self):
        self.ensure_one()
        unbuilds = self.pos_auto_mrp_allocation_ids.mapped("unbuild_id") or self.pos_auto_mrp_unbuild_id
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
