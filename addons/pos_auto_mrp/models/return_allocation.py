import logging

from markupsafe import Markup

from odoo import _, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools.float_utils import float_compare


_logger = logging.getLogger(__name__)


class PosAutoMrpReturnAllocation(models.Model):
    _name = "pos.auto.mrp.return.allocation"
    _description = "Automatic Manufacturing Return Allocation"
    _order = "create_date, id"

    allocation_key = fields.Char(required=True, copy=False, index=True)
    source_type = fields.Selection(
        [("sale", "Sales Return"), ("pos", "POS Refund")],
        required=True,
        index=True,
    )
    state = fields.Selection(
        [("pending", "Pending"), ("done", "Done"), ("cancelled", "Cancelled")],
        required=True,
        default="pending",
        copy=False,
        index=True,
    )
    company_id = fields.Many2one("res.company", required=True, index=True)
    product_id = fields.Many2one("product.product", required=True, index=True)
    product_uom_id = fields.Many2one("uom.uom", required=True)
    quantity = fields.Float(required=True, digits="Product Unit")
    production_id = fields.Many2one(
        "mrp.production", required=True, ondelete="restrict", index=True, check_company=True
    )
    unbuild_id = fields.Many2one(
        "mrp.unbuild", copy=False, ondelete="set null", index=True, check_company=True
    )
    return_picking_id = fields.Many2one(
        "stock.picking", required=True, ondelete="restrict", index=True, check_company=True
    )
    return_move_id = fields.Many2one(
        "stock.move", required=True, ondelete="restrict", index=True, check_company=True
    )
    return_move_line_id = fields.Many2one(
        "stock.move.line", ondelete="restrict", index=True, check_company=True
    )
    lot_id = fields.Many2one("stock.lot", index=True, check_company=True)
    sale_order_line_id = fields.Many2one("sale.order.line", ondelete="restrict", index=True)
    pos_order_line_id = fields.Many2one("pos.order.line", ondelete="restrict", index=True)
    pos_refund_order_line_id = fields.Many2one(
        "pos.order.line", ondelete="restrict", index=True
    )

    _allocation_key_uniq = models.Constraint(
        "unique(allocation_key)",
        "This returned quantity has already been allocated to an unbuild order.",
    )
    _quantity_positive = models.Constraint(
        "check (quantity > 0)",
        "The allocated return quantity must be positive.",
    )

    def _get_recorded_finished_product_locations(self):
        """Read the destination of the actual completed production move."""
        self.ensure_one()
        finished_moves = self.production_id.move_finished_ids.filtered(
            lambda move: move.state == "done"
            and move.product_id == self.product_id
            and move.location_dest_id
        )
        return finished_moves.mapped("location_dest_id") or self.production_id.location_dest_id

    def _get_unbuild_source_location(self):
        """Use the original completed production location before any POS fallback."""
        self.ensure_one()
        production = self.production_id
        returned_location = self.return_move_id.location_dest_id
        recorded_locations = self._get_recorded_finished_product_locations()
        candidates = recorded_locations | returned_location
        required_qty = self.product_uom_id._compute_quantity(
            self.quantity, self.product_id.uom_id
        )
        Quant = self.env["stock.quant"].sudo()
        for location in candidates:
            available_qty = Quant._get_available_quantity(
                self.product_id,
                location,
                lot_id=self.lot_id or None,
                strict=True,
            )
            if float_compare(
                available_qty,
                required_qty,
                precision_rounding=self.product_id.uom_id.rounding,
            ) >= 0:
                if location not in recorded_locations:
                    _logger.info(
                        "POS Auto MRP: allocation %s uses completed POS return location %s because recorded finished-product location(s) %s have insufficient stock.",
                        self.id,
                        location.display_name,
                        ", ".join(recorded_locations.mapped("display_name")),
                    )
                return location
        raise UserError(
            _(
                "Cannot automatically unbuild %(product)s for POS return %(return_move)s: "
                "%(quantity)s is not available in the recorded finished-product location(s) "
                "or the completed return location.",
                product=self.product_id.display_name,
                return_move=self.return_move_id.display_name,
                quantity=self.quantity,
            )
        )

    def _create_unbuild_vals(self):
        self.ensure_one()
        production = self.production_id
        component_locations = production.move_raw_ids.filtered(
            lambda move: move.state == "done" and move.location_id
        ).mapped("location_id")
        component_location = component_locations[:1] or production.location_src_id
        return {
            "product_id": production.product_id.id,
            "bom_id": production.bom_id.id,
            "mo_id": production.id,
            "origin_source": "sale_return" if self.source_type == "sale" else "pos_refund",
            "product_qty": self.product_uom_id._compute_quantity(
                self.quantity, production.product_uom_id
            ),
            "product_uom_id": production.product_uom_id.id,
            "location_id": self._get_unbuild_source_location().id,
            "location_dest_id": component_location.id,
            "company_id": production.company_id.id,
            "lot_id": self.lot_id.id,
            "auto_return_allocation_id": self.id,
        }

    def _create_record_with_access_fallback(self, model, vals):
        """POS cashiers normally lack MRP rights; elevate only the automation write."""
        try:
            return model.create(vals)
        except AccessError:
            _logger.info(
                "POS Auto MRP: using elevated rights for automatic %s creation by user %s.",
                model._name,
                self.env.user.display_name,
            )
            return model.sudo().create(vals)

    def action_create_and_validate_unbuild(self):
        for allocation in self:
            if allocation.state == "done" and allocation.unbuild_id.state == "done":
                continue
            if allocation.unbuild_id and allocation.unbuild_id.state == "done":
                allocation.write({"state": "done"})
                continue

            unbuild_model = allocation.env["mrp.unbuild"].with_company(allocation.company_id)
            unbuild = allocation.unbuild_id
            if not unbuild:
                unbuild = allocation._create_record_with_access_fallback(
                    unbuild_model, allocation._create_unbuild_vals()
                )
                allocation.write({"unbuild_id": unbuild.id})

            try:
                result = unbuild.action_validate()
            except AccessError:
                _logger.info(
                    "POS Auto MRP: using elevated rights to validate automatic unbuild %s by user %s.",
                    unbuild.display_name,
                    allocation.env.user.display_name,
                )
                result = unbuild.sudo().action_validate()

            if unbuild.state != "done":
                raise UserError(
                    _(
                        "The returned product is not available in %(location)s, so automatic unbuild %(unbuild)s could not be completed.",
                        location=unbuild.location_id.display_name,
                        unbuild=unbuild.display_name,
                    )
                )

            allocation.write({"state": "done"})
            if allocation.pos_refund_order_line_id and not allocation.pos_refund_order_line_id.mrp_unbuild_id:
                allocation.pos_refund_order_line_id.write({"mrp_unbuild_id": unbuild.id})
            allocation._post_traceability_messages()
            _logger.info(
                "POS Auto MRP: allocation %s completed with unbuild %s; finished product from %s, components restored through recorded raw moves; result=%s.",
                allocation.id,
                unbuild.display_name,
                unbuild.location_id.display_name,
                result,
            )
        return True

    def _post_traceability_messages(self):
        for allocation in self.filtered(lambda item: item.unbuild_id.state == "done"):
            links = Markup(
                "<p>%s: %s &rarr; %s &rarr; %s</p>"
            ) % (
                _("Automatic return unbuild completed"),
                allocation.return_picking_id._get_html_link(),
                allocation.production_id._get_html_link(),
                allocation.unbuild_id._get_html_link(),
            )
            records = [allocation.production_id, allocation.unbuild_id]
            if allocation.sale_order_line_id:
                records.append(allocation.sale_order_line_id.order_id)
            if allocation.pos_order_line_id:
                records.append(allocation.pos_order_line_id.order_id)
            if allocation.pos_refund_order_line_id:
                records.append(allocation.pos_refund_order_line_id.order_id)
            for record in records:
                record.message_post(body=links, subtype_xmlid="mail.mt_note")

    def unlink(self):
        unbuilds = self.mapped("unbuild_id")
        result = super().unlink()
        unbuilds.filtered(lambda unbuild: unbuild.state != "done").unlink()
        return result
