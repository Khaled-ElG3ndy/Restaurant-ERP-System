from collections import defaultdict
import logging

from odoo import Command, _, api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools.float_utils import float_is_zero


_logger = logging.getLogger(__name__)


class PosOrder(models.Model):
    _inherit = "pos.order"

    @api.model
    def _get_refunded_orders(self, order):
        """Discard stale frontend refund links before core dereferences them."""
        requested_ids = {
            command[2].get("refunded_orderline_id")
            for command in order.get("lines", [])
            if command[0] in (0, 1)
            and len(command) > 2
            and command[2].get("refunded_orderline_id")
        }
        existing_ids = set(
            self.env["pos.order.line"].browse(list(requested_ids)).exists().ids
        )
        for command in order.get("lines", []):
            if command[0] not in (0, 1) or len(command) <= 2:
                continue
            if command[2].get("refunded_orderline_id") not in existing_ids:
                command[2]["refunded_orderline_id"] = False
        return super()._get_refunded_orders(order)

    mrp_production_count = fields.Integer(
        string="Manufacturing Orders",
        compute="_compute_pos_auto_mrp_counts",
        compute_sudo=True,
    )
    mrp_unbuild_count = fields.Integer(
        string="Unbuild Orders",
        compute="_compute_pos_auto_mrp_counts",
        compute_sudo=True,
    )

    @api.depends(
        "lines.mrp_production_id",
        "lines.mrp_production_ids",
        "lines.mrp_unbuild_id",
        "lines.pos_auto_mrp_allocation_ids.unbuild_id",
        "lines.pos_auto_mrp_refund_allocation_ids.unbuild_id",
    )
    def _compute_pos_auto_mrp_counts(self):
        for order in self:
            order.mrp_production_count = len(
                order.lines.mapped("mrp_production_ids") | order.lines.mapped("mrp_production_id")
            )
            allocations = (
                order.lines.mapped("pos_auto_mrp_allocation_ids")
                | order.lines.mapped("pos_auto_mrp_refund_allocation_ids")
            )
            order.mrp_unbuild_count = len(
                allocations.mapped("unbuild_id") | order.lines.mapped("mrp_unbuild_id")
            )

    def _process_order(self, order, existing_order):
        order_id = super()._process_order(order, existing_order)
        pos_order = self.browse(order_id)
        draft = order.get("state") == "draft"
        pos_order._run_pos_auto_mrp_post_processing(
            create_mrp=not draft,
            create_unbuilds=not draft,
            source="_process_order",
        )
        return order_id

    def _process_saved_order(self, draft):
        order_id = super()._process_saved_order(draft)
        if not draft:
            self._run_pos_auto_mrp_post_processing(
                create_mrp=True,
                create_unbuilds=True,
                source="_process_saved_order",
            )
        return order_id

    def _create_order_picking(self):
        """Produce POS items before core creates the POS stock moves.

        The core POS flow creates its picking while processing the order.  Creating
        the automatic MO first makes the finished quantity available at the same
        routed location from which the POS move will be taken.
        """
        # Cashiers usually have POS rights only; the MO work is automation.
        for order in self.sudo().filtered("config_id.auto_create_mrp_from_pos"):
            order._create_mrp_from_pos_if_needed()
        return super()._create_order_picking()

    def _run_pos_auto_mrp_post_processing(self, create_mrp=True, create_unbuilds=True, source="unknown"):
        # Runs inside the cashier's payment sync.  Cashiers usually have POS
        # rights only, so reading mrp.production (e.g. lines.mrp_production_ids)
        # as them raises AccessError and rolls back the whole payment.
        for order in self.sudo():
            positive_lines = order.lines.filtered(lambda line: line.qty > 0)
            refund_lines = order.lines.filtered(lambda line: line.qty < 0)
            _logger.info(
                "POS Auto MRP: post-processing POS order %s from %s: positive lines=%s, refund lines=%s.",
                order.name,
                source,
                len(positive_lines),
                len(refund_lines),
            )
            if positive_lines:
                if create_mrp:
                    order._create_mrp_from_pos_if_needed()
                else:
                    _logger.info(
                        "POS Auto MRP: skipping sale MO processing for POS order %s from %s because create_mrp is disabled for this pass.",
                        order.name,
                        source,
                    )
            if refund_lines:
                if create_unbuilds:
                    order._create_mrp_unbuild_from_refund_if_needed()
                else:
                    _logger.info(
                        "POS Auto MRP: skipping refund unbuild processing for POS order %s from %s because create_unbuilds is disabled for this pass.",
                        order.name,
                        source,
                    )

    def _create_mrp_unbuild_from_refund_if_needed(self):
        for order in self:
            refund_lines = order.lines.filtered(lambda line: line.qty < 0)
            if not refund_lines:
                _logger.info(
                    "POS Auto MRP: no refund lines detected for POS order %s.",
                    order.name,
                )
                continue
            _logger.info(
                "POS Auto MRP: checking %s refund line(s) for POS order %s.",
                len(refund_lines),
                order.name,
            )
            completed_moves = order.picking_ids.filtered(
                lambda picking: picking.state == "done"
            ).move_ids
            completed_moves._pos_auto_mrp_process_completed_returns()
            if not completed_moves:
                automatic_sources = refund_lines.mapped(
                    "refunded_orderline_id.mrp_production_ids"
                ).filtered(
                    lambda production: production.pos_auto_mrp_generated
                    and production.state == "done"
                    and production.qty_produced > 0
                )
                failed_real_time_pickings = order.picking_ids.filtered(
                    lambda picking: picking.state not in ("done", "cancel")
                )
                if automatic_sources and failed_real_time_pickings:
                    raise UserError(
                        _(
                            "The POS refund stock movement could not be completed, so no automatic unbuild was created. Check the returned quantity and lot/serial number, then retry the refund."
                        )
                    )
                _logger.info(
                    "POS Auto MRP: refund order %s is waiting for its completed stock movement before unbuild.",
                    order.name,
                )

    def action_view_mrp_productions(self):
        self.ensure_one()
        productions = self.lines.mapped("mrp_production_ids") | self.lines.mapped("mrp_production_id")
        action = {
            "name": _("Manufacturing Orders"),
            "type": "ir.actions.act_window",
            "res_model": "mrp.production",
            "view_mode": "tree,form",
            "domain": [("id", "in", productions.ids)],
            "context": {"create": False},
        }
        if len(productions) == 1:
            action.update({
                "view_mode": "form",
                "res_id": productions.id,
            })
        return action

    def action_view_mrp_unbuilds(self):
        self.ensure_one()
        allocations = (
            self.lines.mapped("pos_auto_mrp_allocation_ids")
            | self.lines.mapped("pos_auto_mrp_refund_allocation_ids")
        )
        unbuilds = allocations.mapped("unbuild_id") | self.lines.mapped("mrp_unbuild_id")
        action = {
            "name": _("Unbuild Orders"),
            "type": "ir.actions.act_window",
            "res_model": "mrp.unbuild",
            "view_mode": "tree,form",
            "domain": [("id", "in", unbuilds.ids)],
            "context": {"create": False},
        }
        if len(unbuilds) == 1:
            action.update({
                "view_mode": "form",
                "res_id": unbuilds.id,
            })
        return action

    @staticmethod
    def _get_product_stock_type(product):
        if "is_storable" in product._fields:
            return "product" if product.is_storable else product.type
        if "detailed_type" in product._fields:
            return product.detailed_type
        return product.type

    def _is_product_storable_for_mrp(self, product):
        return self._get_product_stock_type(product) == "product"

    def _is_product_service_for_mrp(self, product):
        return self._get_product_stock_type(product) == "service"

    def _create_mrp_from_pos_if_needed(self):
        for order in self:
            config = order.config_id
            if not config.auto_create_mrp_from_pos:
                _logger.info(
                    "POS Auto MRP: skipping POS order %s because automatic MO creation is disabled on POS config %s.",
                    order.name,
                    config.display_name,
                )
                continue

            sale_lines = order.lines.filtered(lambda line: line.qty > 0)
            if not sale_lines:
                _logger.info(
                    "POS Auto MRP: no positive sale lines found for POS order %s.",
                    order.name,
                )
                continue

            grouped_lines = defaultdict(lambda: {
                "lines": self.env["pos.order.line"],
                "qty": 0.0,
                "product": False,
                "bom": False,
            })

            for line in sale_lines:
                _logger.info(
                    "POS Auto MRP: sale line detected: POS order line %s, product %s, qty %s, existing MO %s.",
                    line.id,
                    line.product_id.display_name if line.product_id else False,
                    line.qty,
                    line.mrp_production_id.display_name or False,
                )

                if not line.product_id:
                    _logger.info(
                        "POS Auto MRP: skipping sale line %s because it has no product.",
                        line.id,
                    )
                    continue

                product_stock_type = order._get_product_stock_type(line.product_id)
                if order._is_product_service_for_mrp(line.product_id):
                    _logger.info(
                        "POS Auto MRP: skipping sale line %s because product %s is type %s.",
                        line.id,
                        line.product_id.display_name,
                        product_stock_type,
                    )
                    continue

                bom = order._find_manufacturing_bom(line.product_id, order.company_id)
                if not bom:
                    _logger.info(
                        "POS Auto MRP: product %s has no manufacturing BOM for company %s; skipping sale line %s.",
                        line.product_id.display_name,
                        order.company_id.display_name,
                        line.id,
                    )
                    continue

                existing_productions = (
                    line.mrp_production_id | line.mrp_production_ids
                ).filtered(
                    lambda production: production.pos_auto_mrp_generated
                    and production.product_id == line.product_id
                    and production.state != "cancel"
                )
                if existing_productions:
                    _logger.info(
                        "POS Auto MRP: skipping POS order %s sale line %s product %s because MO(s) %s already exist.",
                        order.name,
                        line.id,
                        line.product_id.display_name,
                        ", ".join(existing_productions.mapped("display_name")),
                    )
                    continue

                _logger.info(
                    "POS Auto MRP: product %s has BOM %s for sale line %s.",
                    line.product_id.display_name,
                    bom.display_name,
                    line.id,
                )

                key = (line.product_id.id, bom.id)
                grouped_lines[key]["lines"] |= line
                grouped_lines[key]["qty"] += line.qty
                grouped_lines[key]["product"] = line.product_id
                grouped_lines[key]["bom"] = bom

            if not grouped_lines:
                _logger.info(
                    "POS Auto MRP: no sale lines require MO creation for POS order %s.",
                    order.name,
                )
                continue

            for vals in grouped_lines.values():
                product = vals["product"]
                bom = vals["bom"]
                qty = vals["qty"]
                lines = vals["lines"]

                if not product or not bom:
                    _logger.info(
                        "POS Auto MRP: skipping grouped sale lines %s because product or BOM is missing.",
                        lines.ids,
                    )
                    continue

                if float_is_zero(qty, precision_rounding=product.uom_id.rounding):
                    _logger.info(
                        "POS Auto MRP: skipping grouped sale lines %s because grouped quantity is zero.",
                        lines.ids,
                    )
                    continue

                _logger.info(
                    "POS Auto MRP: creating MO for POS order %s, product %s, BOM %s, qty %s, sale lines %s.",
                    order.name,
                    product.display_name,
                    bom.display_name,
                    qty,
                    lines.ids,
                )
                production = order._create_mrp_production_for_pos_lines(
                    product=product,
                    bom=bom,
                    qty=qty,
                    source_lines=lines,
                )

                if production:
                    _logger.info(
                        "POS Auto MRP: MO %s created and linked to POS sale lines %s.",
                        production.name,
                        lines.ids,
                    )
                    order._apply_component_source_locations(production)

                    if config.auto_done_mrp_from_pos:
                        order._auto_done_mrp_production(production)
                    else:
                        order._auto_confirm_mrp_production(production)
                        _logger.info(
                            "POS Auto MRP: MO %s remains in state %s because automatic MO completion is disabled on POS config %s; automatic confirmation is handled independently.",
                            production.name,
                            production.state,
                            config.display_name,
                        )

    def _find_manufacturing_bom(self, product, company):
        self.ensure_one()

        domain = [
            ("type", "=", "normal"),
            ("product_tmpl_id", "=", product.product_tmpl_id.id),
            "|",
                ("product_id", "=", False),
                ("product_id", "=", product.id),
            "|",
                ("company_id", "=", False),
                ("company_id", "=", company.id),
        ]
        return self.env["mrp.bom"].search(domain, order="product_id desc, sequence, id", limit=1)

    def _get_mrp_picking_type(self, bom, company):
        picking_type = bom.picking_type_id
        if picking_type:
            return picking_type

        picking_type = self.env["stock.picking.type"].search([
            ("code", "=", "mrp_operation"),
            ("company_id", "=", company.id),
        ], limit=1)

        if not picking_type:
            raise UserError(_("No Manufacturing Operation Type found for company %s.") % company.display_name)

        return picking_type

    def _validate_pos_auto_mrp_location(self, location, purpose, product):
        """Reject unsafe locations instead of silently routing stock elsewhere."""
        self.ensure_one()
        if not location or not location.active or location.usage != "internal":
            raise UserError(
                _(
                    "POS order %(order)s cannot manufacture %(product)s: %(purpose)s must be "
                    "an active internal stock location.",
                    order=self.display_name,
                    product=product.display_name,
                    purpose=purpose,
                )
            )
        if (
            location.company_id and location.company_id != self.company_id
        ) or (
            location.warehouse_id.company_id
            and location.warehouse_id.company_id != self.company_id
        ):
            raise UserError(
                _(
                    "POS order %(order)s cannot manufacture %(product)s: %(purpose)s "
                    "'%(location)s' is not available for company %(company)s.",
                    order=self.display_name,
                    product=product.display_name,
                    purpose=purpose,
                    location=location.display_name,
                    company=self.company_id.display_name,
                )
            )
        return location

    def _resolve_pos_auto_mrp_locations(self, product, bom):
        """Return the physical component and finished-product locations for one POS item.

        A product profile is the authoritative section mapping.  If the product
        has no profile, the Manufacturing Operation Type is the explicit Odoo
        fallback; there is intentionally no lookup by location name or ID.
        """
        self.ensure_one()
        picking_type = self._get_mrp_picking_type(bom, self.company_id)
        profile = product.product_tmpl_id.pos_mrp_source_profile_id
        component_source_location = product.product_tmpl_id._get_pos_mrp_source_location(
            self.config_id
        )
        location_src = (
            component_source_location
            or bom.picking_type_id.default_location_src_id
            or picking_type.default_location_src_id
        )
        if not component_source_location:
            _logger.info(
                "POS Auto MRP: POS order %s product %s has no POS source profile; using Manufacturing Operation Type source %s.",
                self.name,
                product.display_name,
                location_src.display_name if location_src else False,
            )

        # The routed section is both the component source and the finished
        # product destination.  This is set before Odoo computes raw, finished,
        # and by-product moves during mrp.production.create().
        location_dest = location_src
        self._validate_pos_auto_mrp_location(
            location_src, _("component source location"), product
        )
        self._validate_pos_auto_mrp_location(
            location_dest, _("finished product location"), product
        )
        _logger.info(
            "POS Auto MRP: POS order %s product %s profile=%s; components from %s; finished product to %s.",
            self.name,
            product.display_name,
            profile.display_name or _("Operation Type fallback"),
            location_src.display_name,
            location_dest.display_name,
        )
        return picking_type, location_src, location_dest

    def _create_mrp_production_for_pos_lines(self, product, bom, qty, source_lines):
        self.ensure_one()

        company = self.company_id
        picking_type, location_src, location_dest = self._resolve_pos_auto_mrp_locations(
            product, bom
        )

        source_lines_sudo = source_lines.sudo()
        existing_productions = (
            source_lines_sudo.mapped("mrp_production_id")
            | source_lines_sudo.mapped("mrp_production_ids")
        ).filtered(
            lambda production: production.pos_auto_mrp_generated
            and production.product_id == product
            and production.state != "cancel"
        )
        if existing_productions:
            _logger.info(
                "POS Auto MRP: reusing existing MO(s) %s for POS order %s product %s lines %s; no duplicate MO will be created.",
                ", ".join(existing_productions.mapped("display_name")),
                self.name,
                product.display_name,
                source_lines.ids,
            )
            return existing_productions[:1]

        origin = self.pos_reference or self.name or _("POS Order")
        line_names = ", ".join(source_lines.mapped("product_id.display_name"))

        production_vals = {
            "product_id": product.id,
            "product_qty": qty,
            "product_uom_id": product.uom_id.id,
            "bom_id": bom.id,
            "origin": "%s - %s" % (origin, line_names),
            "date_deadline": fields.Datetime.now(),
            "company_id": company.id,
            "picking_type_id": picking_type.id,
            "location_src_id": location_src.id,
            "location_dest_id": location_dest.id,
            "pos_order_id": self.id,
            "pos_order_line_id": source_lines[:1].id if source_lines else False,
            "pos_order_line_ids": [Command.set(source_lines.ids)],
            "pos_auto_mrp_generated": True,
        }
        try:
            production = self.env["mrp.production"].create(production_vals)
        except AccessError:
            _logger.info(
                "POS Auto MRP: using elevated rights to create POS MO for order %s by user %s.",
                self.name,
                self.env.user.display_name,
            )
            production = self.env["mrp.production"].sudo().create(production_vals)
        production = production.sudo()

        # Cashiers do not need direct Manufacturing access in the UI, but the
        # generated MO still has to be linked to the POS lines for stock/refunds.
        source_lines_sudo.write({
            "mrp_production_id": production.id,
            "mrp_production_ids": [Command.link(production.id)],
        })

        production.message_post(
            body=_(
                "Automatically created from POS order %(order)s for lines %(lines)s.",
                order=self.display_name,
                lines=", ".join(str(line.id) for line in source_lines),
            ),
            subtype_xmlid="mail.mt_note",
        )

        _logger.info(
            "POS Auto MRP: MO %s created for POS order %s, product %s; components from %s, finished product to %s; current state is %s.",
            production.name,
            self.name,
            product.display_name,
            location_src.display_name,
            location_dest.display_name,
            production.state,
        )
        return production

    def _apply_component_source_locations(self, production):
        self.ensure_one()

        if not production.pos_auto_mrp_generated:
            return

        component_source_location = self._validate_pos_auto_mrp_location(
            production.location_src_id,
            _("component source location"),
            production.product_id,
        )
        final_product_location = self._validate_pos_auto_mrp_location(
            production.location_dest_id,
            _("finished product location"),
            production.product_id,
        )

        raw_moves = production.move_raw_ids.filtered(
            lambda move: move.state not in ("done", "cancel")
            and move.location_id != component_source_location
        )
        if raw_moves:
            raw_moves.write({"location_id": component_source_location.id})

        # `move_finished_ids` contains both the main finished item and every
        # by-product.  Keep each pending output in the same routed section.
        finished_moves = production.move_finished_ids.filtered(
            lambda move: move.state not in ("done", "cancel")
            and move.location_dest_id != final_product_location
        )
        if finished_moves:
            finished_moves.write({"location_dest_id": final_product_location.id})


    def _all_components_available_for_auto_done(self, production):
        self.ensure_one()
        return production._pos_auto_mrp_components_available()

    def _auto_confirm_mrp_production(self, production):
        """Confirm a newly generated POS MO only when every component is available."""
        self.ensure_one()

        self._apply_component_source_locations(production)

        if production.state != "draft":
            return True

        if not self._all_components_available_for_auto_done(production):
            _logger.info(
                "POS Auto MRP: MO %s remains in draft because one or more components are unavailable for automatic confirmation.",
                production.name,
            )
            return False

        try:
            production.action_confirm()
        except Exception as e:
            raise UserError(_("MO confirmation failed: %s") % str(e))

        self._apply_component_source_locations(production)
        _logger.info(
            "POS Auto MRP: MO %s confirmed automatically for POS order %s because all components are available.",
            production.name,
            self.name,
        )
        return True

    def _auto_done_mrp_production(self, production):
        self.ensure_one()

        self._apply_component_source_locations(production)
        completed = production._pos_auto_mrp_complete_if_available()

        _logger.info(
            "POS Auto MRP: automatic completion result for MO %s from POS order %s is %s; current state is %s.",
            production.name,
            self.name,
            completed,
            production.state,
        )
        return completed
