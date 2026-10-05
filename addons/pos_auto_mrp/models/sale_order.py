import logging

from odoo import _, api, fields, models
from odoo.exceptions import AccessError
from odoo.tools.float_utils import float_is_zero


_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = "sale.order"

    pos_auto_mrp_production_count = fields.Integer(compute="_compute_pos_auto_mrp_counts")
    pos_auto_mrp_unbuild_count = fields.Integer(compute="_compute_pos_auto_mrp_counts")

    @api.depends(
        "order_line.mrp_production_ids",
        "order_line.pos_auto_mrp_allocation_ids.unbuild_id",
    )
    def _compute_pos_auto_mrp_counts(self):
        for order in self:
            order.pos_auto_mrp_production_count = len(order.order_line.mapped("mrp_production_ids"))
            order.pos_auto_mrp_unbuild_count = len(
                order.order_line.mapped("pos_auto_mrp_allocation_ids.unbuild_id")
            )

    def action_confirm(self):
        res = super().action_confirm()

        for order in self:
            order._create_mrp_from_so_if_needed()

        return res

    @staticmethod
    def _pos_auto_mrp_product_type(product):
        if "detailed_type" in product._fields:
            return product.detailed_type
        return product.type

    def _pos_auto_mrp_sale_line_demands(self, line):
        """Return products that must be manufactured for one sales line."""
        product = line.product_id
        demands_by_key = {}

        def add_demand(demand_product, qty, uom, note=False):
            key = (demand_product.id, uom.id, note or "")
            if key not in demands_by_key:
                demands_by_key[key] = {
                    "product": demand_product,
                    "qty": 0.0,
                    "uom": uom,
                    "note": note,
                }
            demands_by_key[key]["qty"] += qty

        add_demand(product, line.product_uom_qty, line.product_uom_id)

        if "additional_final_product_line_ids" not in product.product_tmpl_id._fields:
            return list(demands_by_key.values())

        parent_qty = line.product_uom_id._compute_quantity(
            line.product_uom_qty,
            product.uom_id,
            round=False,
        )
        for additional in product.product_tmpl_id.additional_final_product_line_ids:
            linked_product = additional.product_id
            if not linked_product:
                continue
            linked_uom = additional.uom_id or linked_product.uom_id
            linked_qty = linked_uom._compute_quantity(
                additional.quantity * parent_qty,
                linked_product.uom_id,
                round=False,
            )
            add_demand(
                linked_product,
                linked_qty,
                linked_product.uom_id,
                note=_("linked product of %s") % product.display_name,
            )
        return list(demands_by_key.values())

    def _pos_auto_mrp_find_bom(self, product, company):
        return self.env["mrp.bom"]._bom_find(
            product,
            company_id=company.id,
            bom_type="normal",
        ).get(product)

    def _pos_auto_mrp_existing_sale_production(self, line, product):
        return line.mrp_production_ids.filtered(
            lambda production: production.pos_auto_mrp_generated
            and production.product_id == product
            and production.state != "cancel"
        )

    def _pos_auto_mrp_create_sale_production(
        self, order, line, product, qty, uom, bom, note=False
    ):
        picking_type = bom.picking_type_id or order.warehouse_id.manu_type_id

        production_vals = {
            "product_id": product.id,
            "product_qty": qty,
            "product_uom_id": uom.id,
            "bom_id": bom.id,
            "origin": order.name,
            "sale_order_id": order.id,
            "sale_order_line_id": line.id,
            "pos_auto_mrp_generated": True,
            "picking_type_id": picking_type.id,
            "location_src_id": picking_type.default_location_src_id.id,
            "location_dest_id": picking_type.default_location_dest_id.id,
        }

        try:
            production = self.env["mrp.production"].create(production_vals)
        except AccessError:
            _logger.info(
                "POS Auto MRP: using elevated rights to create Sales MO for %s by user %s.",
                order.display_name,
                self.env.user.display_name,
            )
            production = self.env["mrp.production"].sudo().create(production_vals)
        production._pos_auto_mrp_complete_if_available()
        production.message_post(
            body=_(
                "Automatically created from sales order %(order)s, line %(line)s, product %(product)s%(note)s.",
                order=order.display_name,
                line=line.id,
                product=product.display_name,
                note=" (%s)" % note if note else "",
            ),
            subtype_xmlid="mail.mt_note",
        )
        return production

    def _create_mrp_from_so_if_needed(self):
        for order in self:
            for line in order.order_line:
                if not line.product_id or line.product_uom_qty <= 0:
                    continue

                for demand in order._pos_auto_mrp_sale_line_demands(line):
                    product = demand["product"]
                    qty = demand["qty"]
                    uom = demand["uom"]

                    if not product or order._pos_auto_mrp_product_type(product) == "service":
                        continue
                    if float_is_zero(qty, precision_rounding=uom.rounding):
                        continue

                    bom = order._pos_auto_mrp_find_bom(product, order.company_id)
                    if not bom:
                        continue

                    existing_productions = order._pos_auto_mrp_existing_sale_production(
                        line, product
                    )
                    if existing_productions:
                        _logger.info(
                            "POS Auto MRP: skipping Sales order %s line %s product %s because MO(s) %s already exist.",
                            order.name,
                            line.id,
                            product.display_name,
                            ", ".join(existing_productions.mapped("display_name")),
                        )
                        continue

                    _logger.info(
                        "POS Auto MRP: creating Sales MO for order %s, line %s, product %s, BOM %s, qty %s %s.",
                        order.name,
                        line.id,
                        product.display_name,
                        bom.display_name,
                        qty,
                        uom.display_name,
                    )
                    order._pos_auto_mrp_create_sale_production(
                        order,
                        line,
                        product,
                        qty,
                        uom,
                        bom,
                        note=demand.get("note"),
                    )

    def action_view_pos_auto_mrp_productions(self):
        self.ensure_one()
        productions = self.order_line.mapped("mrp_production_ids")
        return self._pos_auto_mrp_open_records(productions, _("Manufacturing Orders"))

    def action_view_pos_auto_mrp_unbuilds(self):
        self.ensure_one()
        unbuilds = self.order_line.mapped("pos_auto_mrp_allocation_ids.unbuild_id")
        return self._pos_auto_mrp_open_records(unbuilds, _("Unbuild Orders"))

    def _pos_auto_mrp_open_records(self, records, name):
        action = {
            "type": "ir.actions.act_window",
            "name": name,
            "res_model": records._name,
            "view_mode": "list,form",
            "domain": [("id", "in", records.ids)],
            "context": {"create": False},
        }
        if len(records) == 1:
            action.update({"view_mode": "form", "res_id": records.id})
        return action
