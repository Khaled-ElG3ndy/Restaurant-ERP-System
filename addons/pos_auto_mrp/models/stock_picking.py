import logging

from psycopg2 import IntegrityError

from odoo import Command, _, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools.float_utils import float_compare, float_is_zero


_logger = logging.getLogger(__name__)


class StockPicking(models.Model):
    _inherit = "stock.picking"

    pos_auto_mrp_allocation_ids = fields.One2many(
        "pos.auto.mrp.return.allocation",
        "return_picking_id",
        string="Automatic Unbuild Allocations",
    )
    pos_auto_mrp_unbuild_count = fields.Integer(compute="_compute_pos_auto_mrp_unbuild_count")

    def _compute_pos_auto_mrp_unbuild_count(self):
        for picking in self:
            picking.pos_auto_mrp_unbuild_count = len(
                picking.pos_auto_mrp_allocation_ids.mapped("unbuild_id")
            )

    def action_view_pos_auto_mrp_unbuilds(self):
        self.ensure_one()
        unbuilds = self.pos_auto_mrp_allocation_ids.mapped("unbuild_id")
        action = {
            "type": "ir.actions.act_window",
            "name": _("Automatic Return Unbuilds"),
            "res_model": "mrp.unbuild",
            "view_mode": "list,form",
            "domain": [("id", "in", unbuilds.ids)],
            "context": {"create": False},
        }
        if len(unbuilds) == 1:
            action.update({"view_mode": "form", "res_id": unbuilds.id})
        return action

    def _prepare_stock_move_vals(self, first_line, order_lines):
        vals = super()._prepare_stock_move_vals(first_line, order_lines)
        vals["pos_auto_mrp_pos_line_ids"] = [Command.set(order_lines.ids)]
        # Built while a cashier pays: routing reads MOs, BoMs and locations.
        order = first_line.order_id.sudo()
        if not order.config_id.auto_create_mrp_from_pos:
            return vals

        product = first_line.product_id
        if not product or not order._is_product_storable_for_mrp(product):
            return vals

        is_refund = first_line.qty < 0
        if is_refund:
            locations = self.env["stock.location"].sudo()
            for source_line in order_lines.sudo().mapped("refunded_orderline_id"):
                locations |= source_line._pos_auto_mrp_finished_product_locations()
            if not locations:
                return vals
            if len(locations) != 1:
                raise UserError(
                    _(
                        "POS refund %(order)s for %(product)s refers to manufacturing outputs "
                        "in more than one location. Return the original POS lines separately "
                        "so the stock can be routed safely.",
                        order=order.display_name,
                        product=product.display_name,
                    )
                )
            order._validate_pos_auto_mrp_location(
                locations, _("historical finished product location"), product
            )
            vals["location_dest_id"] = locations.id
            _logger.info(
                "POS Auto MRP: routing refund POS order %s, product %s, lines %s to recorded finished-product location %s.",
                order.name,
                product.display_name,
                order_lines.ids,
                locations.display_name,
            )
            return vals

        bom = order._find_manufacturing_bom(product, order.company_id)
        if not bom:
            return vals
        _picking_type, _component_source, final_product_location = (
            order._resolve_pos_auto_mrp_locations(product, bom)
        )
        vals["location_id"] = final_product_location.id
        _logger.info(
            "POS Auto MRP: routing sale POS order %s, product %s, lines %s from finished-product location %s.",
            order.name,
            product.display_name,
            order_lines.ids,
            final_product_location.display_name,
        )
        return vals

    def _action_done(self):
        result = super()._action_done()
        self.env.flush_all()
        self.env["stock.quant"].invalidate_model(["quantity", "reserved_quantity"])
        # A POS refund validates its picking as the cashier; unbuilding reads MOs.
        return_moves = self.sudo().move_ids.filtered(
            lambda move: move.state == "done"
            and move.location_dest_id.usage == "internal"
            and not float_is_zero(move.quantity, precision_rounding=move.product_uom.rounding)
        )
        try:
            return_moves._pos_auto_mrp_process_completed_returns()
        except UserError:
            if not return_moves.mapped("pos_auto_mrp_pos_line_ids"):
                raise
            _logger.info(
                "POS Auto MRP: deferring POS return unbuild processing until after picking %s is fully completed.",
                ", ".join(self.mapped("display_name")),
                exc_info=True,
            )
        return result


class StockMove(models.Model):
    _inherit = "stock.move"

    pos_auto_mrp_pos_line_ids = fields.Many2many(
        "pos.order.line",
        "pos_auto_mrp_stock_move_pos_line_rel",
        "move_id",
        "pos_line_id",
        string="POS Order Lines",
        copy=False,
    )
    pos_auto_mrp_allocation_ids = fields.One2many(
        "pos.auto.mrp.return.allocation",
        "return_move_id",
        string="Automatic Unbuild Allocations",
    )

    def _pos_auto_mrp_get_original_sale_line(self):
        self.ensure_one()
        move = self.origin_returned_move_id
        seen = set()
        while move and move.id not in seen:
            seen.add(move.id)
            if move.sale_line_id:
                return move.sale_line_id
            move = move.origin_returned_move_id
        return self.sale_line_id if self.origin_returned_move_id else self.env["sale.order.line"]

    def _pos_auto_mrp_process_completed_returns(self):
        for move in self:
            sale_line = move._pos_auto_mrp_get_original_sale_line()
            refund_lines = move.pos_auto_mrp_pos_line_ids.filtered(
                lambda line: line.qty < 0 and line.refunded_orderline_id
            ).sorted("id")
            if sale_line:
                move._pos_auto_mrp_process_sale_return(sale_line)
            elif refund_lines:
                move._pos_auto_mrp_process_pos_refund(refund_lines)
        return True

    def _pos_auto_mrp_actual_slices(self):
        """Return actual completed quantities in the product base UoM, split by lot."""
        self.ensure_one()
        slices = []
        if self.product_id.tracking == "none":
            quantity = self.product_uom._compute_quantity(self.quantity, self.product_id.uom_id)
            return [(quantity, self.env["stock.lot"], self.env["stock.move.line"])]
        for move_line in self.move_line_ids.filtered(lambda line: line.quantity > 0).sorted("id"):
            quantity = move_line.product_uom_id._compute_quantity(
                move_line.quantity, self.product_id.uom_id
            )
            slices.append((quantity, move_line.lot_id, move_line))
        return slices

    def _pos_auto_mrp_process_sale_return(self, source_line):
        self.ensure_one()
        for quantity, lot, move_line in self._pos_auto_mrp_actual_slices():
            self._pos_auto_mrp_allocate_return(
                "sale", source_line, quantity, lot=lot, return_move_line=move_line
            )

    def _pos_auto_mrp_process_pos_refund(self, refund_lines):
        self.ensure_one()
        slices = list(self._pos_auto_mrp_actual_slices())
        slice_index = 0
        slice_left = slices[0][0] if slices else 0.0
        for refund_line in refund_lines:
            requested = refund_line.product_uom_id._compute_quantity(
                abs(refund_line.qty), self.product_id.uom_id
            )
            while requested > 0 and slice_index < len(slices):
                _slice_qty, lot, move_line = slices[slice_index]
                take = min(requested, slice_left)
                self._pos_auto_mrp_allocate_return(
                    "pos",
                    refund_line.refunded_orderline_id,
                    take,
                    lot=lot,
                    return_move_line=move_line,
                    refund_line=refund_line,
                )
                requested -= take
                slice_left -= take
                if float_is_zero(slice_left, precision_rounding=self.product_id.uom_id.rounding):
                    slice_index += 1
                    slice_left = slices[slice_index][0] if slice_index < len(slices) else 0.0

    def _pos_auto_mrp_source_productions(self, source_type, source_line, lot=False):
        if source_type == "sale":
            productions = source_line.mrp_production_ids
        else:
            productions = source_line.mrp_production_ids | source_line.mrp_production_id
        productions = productions.filtered(
            lambda production: production.pos_auto_mrp_generated
            and production.state == "done"
            and production.product_id == self.product_id
            and production.bom_id.type == "normal"
        )
        if lot:
            productions = productions.filtered(lambda production: lot in production.lot_producing_ids)
        return productions.sorted(lambda production: (production.date_finished, production.create_date, production.id))

    def _pos_auto_mrp_all_source_productions(self, source_type, source_line):
        productions = source_line.mrp_production_ids
        if source_type == "pos":
            productions |= source_line.mrp_production_id
        return productions.filtered(
            lambda production: production.pos_auto_mrp_generated
            and production.product_id == self.product_id
            and production.bom_id.type == "normal"
        )

    def _pos_auto_mrp_source_sold_qty(self, source_type, source_line):
        if source_type == "sale":
            return source_line.product_uom_id._compute_quantity(
                source_line.product_uom_qty, self.product_id.uom_id
            )
        return source_line.product_uom_id._compute_quantity(source_line.qty, self.product_id.uom_id)

    def _pos_auto_mrp_source_allocated_qty(self, source_type, source_line):
        domain = [("state", "!=", "cancelled")]
        if source_type == "sale":
            domain.append(("sale_order_line_id", "=", source_line.id))
        else:
            domain.append(("pos_order_line_id", "=", source_line.id))
        allocations = self.env["pos.auto.mrp.return.allocation"].search(domain)
        allocated = sum(
            allocation.product_uom_id._compute_quantity(
                allocation.quantity, self.product_id.uom_id
            )
            for allocation in allocations
        )
        if source_type == "pos":
            represented_unbuilds = allocations.mapped("unbuild_id")
            legacy_lines = self.env["pos.order.line"].search([
                ("refunded_orderline_id", "=", source_line.id),
                ("mrp_unbuild_id", "!=", False),
                ("mrp_unbuild_id", "not in", represented_unbuilds.ids),
            ])
            allocated += sum(
                line.product_uom_id._compute_quantity(abs(line.qty), self.product_id.uom_id)
                for line in legacy_lines
                if line.mrp_unbuild_id.state == "done"
            )
        return allocated

    def _pos_auto_mrp_mo_available_qty(self, production):
        produced = production.product_uom_id._compute_quantity(
            production.qty_produced, self.product_id.uom_id
        )
        reserved = sum(
            unbuild.product_uom_id._compute_quantity(
                unbuild.product_qty, self.product_id.uom_id
            )
            for unbuild in production.unbuild_ids
        )
        return max(produced - reserved, 0.0)

    def _pos_auto_mrp_allocate_return(
        self,
        source_type,
        source_line,
        quantity,
        lot=False,
        return_move_line=False,
        refund_line=False,
    ):
        self.ensure_one()
        rounding = self.product_id.uom_id.rounding
        if float_is_zero(quantity, precision_rounding=rounding):
            return

        allocation_domain = [
            ("return_move_id", "=", self.id),
            ("state", "!=", "cancelled"),
            ("lot_id", "=", lot.id if lot else False),
            ("return_move_line_id", "=", return_move_line.id if return_move_line else False),
        ]
        if source_type == "sale":
            allocation_domain.append(("sale_order_line_id", "=", source_line.id))
        else:
            allocation_domain.append(("pos_refund_order_line_id", "=", refund_line.id))
        existing = self.env["pos.auto.mrp.return.allocation"].search(allocation_domain)
        existing_qty = sum(
            item.product_uom_id._compute_quantity(item.quantity, self.product_id.uom_id)
            for item in existing
        )
        pending_existing = existing.filtered(lambda item: item.state != "done")
        if pending_existing:
            pending_existing.action_create_and_validate_unbuild()
        remaining = max(quantity - existing_qty, 0.0)
        if float_is_zero(remaining, precision_rounding=rounding):
            return

        automatic_productions = self._pos_auto_mrp_all_source_productions(
            source_type, source_line
        )
        if not automatic_productions:
            return

        completed_productions = self._pos_auto_mrp_source_productions(
            source_type, source_line
        )
        if not completed_productions:
            _logger.info(
                "POS Auto MRP: return move %s needs no unbuild because the original automatic MO(s) %s never completed.",
                self.display_name,
                automatic_productions.mapped("name"),
            )
            return

        if self.product_id.tracking != "none" and not lot:
            raise UserError(
                _(
                    "Return %(picking)s cannot be unbuilt because %(product)s has no lot/serial number on the completed return move.",
                    picking=self.picking_id.display_name,
                    product=self.product_id.display_name,
                )
            )

        source_available = self._pos_auto_mrp_source_sold_qty(
            source_type, source_line
        ) - self._pos_auto_mrp_source_allocated_qty(source_type, source_line)
        if float_compare(remaining, source_available, precision_rounding=rounding) > 0:
            raise UserError(
                _(
                    "The return quantity for %(product)s exceeds the quantity manufactured for the original %(source)s line. Remaining returnable quantity: %(quantity)s %(uom)s.",
                    product=self.product_id.display_name,
                    source=_("Sales Order") if source_type == "sale" else _("POS Order"),
                    quantity=max(source_available, 0.0),
                    uom=self.product_id.uom_id.display_name,
                )
            )

        productions = self._pos_auto_mrp_source_productions(source_type, source_line, lot=lot)
        if not productions:
            raise UserError(
                _(
                    "No completed automatic manufacturing order with the correct lot/serial number is available for returned product %(product)s.",
                    product=self.product_id.display_name,
                )
            )

        total_mo_available = sum(
            self._pos_auto_mrp_mo_available_qty(production) for production in productions
        )
        if float_compare(remaining, total_mo_available, precision_rounding=rounding) > 0:
            raise UserError(
                _(
                    "The returned quantity of %(product)s exceeds the remaining completed automatic manufacturing quantity. Available to unbuild: %(quantity)s %(uom)s.",
                    product=self.product_id.display_name,
                    quantity=total_mo_available,
                    uom=self.product_id.uom_id.display_name,
                )
            )

        Allocation = self.env["pos.auto.mrp.return.allocation"]
        for production in productions:
            available = self._pos_auto_mrp_mo_available_qty(production)
            take = min(remaining, available)
            if float_is_zero(take, precision_rounding=rounding):
                continue
            source_id = source_line.id
            key = "%s:%s:%s:%s:%s:%s:%s" % (
                source_type,
                self.id,
                return_move_line.id if return_move_line else 0,
                source_id,
                refund_line.id if refund_line else 0,
                production.id,
                lot.id if lot else 0,
            )
            vals = {
                "allocation_key": key,
                "source_type": source_type,
                "company_id": production.company_id.id,
                "product_id": self.product_id.id,
                "product_uom_id": self.product_id.uom_id.id,
                "quantity": take,
                "production_id": production.id,
                "return_picking_id": self.picking_id.id,
                "return_move_id": self.id,
                "return_move_line_id": return_move_line.id if return_move_line else False,
                "lot_id": lot.id if lot else False,
                "sale_order_line_id": source_line.id if source_type == "sale" else False,
                "pos_order_line_id": source_line.id if source_type == "pos" else False,
                "pos_refund_order_line_id": refund_line.id if refund_line else False,
            }
            allocation = Allocation.search([("allocation_key", "=", key)], limit=1)
            if not allocation:
                try:
                    with self.env.cr.savepoint():
                        try:
                            allocation = Allocation.create(vals)
                        except AccessError:
                            _logger.info(
                                "POS Auto MRP: using elevated rights for return allocation creation by user %s.",
                                self.env.user.display_name,
                            )
                            allocation = Allocation.sudo().create(vals)
                except IntegrityError:
                    allocation = Allocation.search([("allocation_key", "=", key)], limit=1)
                    if not allocation:
                        raise UserError(
                            _("This returned quantity is already being processed by another request.")
                        )
            allocation.action_create_and_validate_unbuild()
            remaining -= take
            if float_is_zero(remaining, precision_rounding=rounding):
                break
