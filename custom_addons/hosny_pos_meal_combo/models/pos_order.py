import logging

from odoo import api, fields, models
from odoo.tools.float_utils import float_is_zero


_logger = logging.getLogger(__name__)


class PosOrderLine(models.Model):
    _inherit = "pos.order.line"

    is_meal_parent = fields.Boolean(string="Meal Parent", default=False)
    is_meal_component = fields.Boolean(string="Meal Component", default=False)
    meal_parent_uuid = fields.Char(index=True)
    meal_component_product_id = fields.Many2one(
        "product.product",
        string="Meal Component Product",
        index=True,
    )
    meal_component_display_mode = fields.Selection(
        [
            ("pos_receipt", "POS + Receipt only"),
            ("pos_receipt_invoice", "POS + Receipt + Invoice"),
            ("internal", "Internal only (stock deduction only)"),
        ],
        string="Meal Component Display Mode",
        default="pos_receipt",
    )
    is_additional_final_parent = fields.Boolean(string="Additional Final Product Parent", default=False)
    is_additional_final_product = fields.Boolean(string="Additional Final Product", default=False)
    additional_final_parent_uuid = fields.Char(index=True)
    additional_final_line_id = fields.Many2one(
        "product.additional.final.line",
        string="Additional Final Rule",
        index=True,
    )
    mrp_direct_cost = fields.Monetary(
        string="Direct Manufacturing Cost",
        readonly=True,
        copy=False,
        help="The cost of this line's own manufacturing order(s), before bundle allocation.",
    )
    additional_final_products_cost = fields.Monetary(
        string="Additional Products Manufacturing Cost",
        readonly=True,
        copy=False,
        help="The cost of linked additional final products allocated to this parent line.",
    )

    def _load_pos_data_fields(self, config):
        return super()._load_pos_data_fields(config) + [
            "is_meal_parent",
            "is_meal_component",
            "meal_parent_uuid",
            "meal_component_product_id",
            "meal_component_display_mode",
            "is_additional_final_parent",
            "is_additional_final_product",
            "additional_final_parent_uuid",
            "additional_final_line_id",
        ]

    def _prepare_tax_base_line_values(self):
        if self.env.context.get("invoicing"):
            return [
                line._prepare_base_line_for_taxes_computation()
                for line in self
                if not line.is_meal_component
                or line.meal_component_display_mode == "pos_receipt_invoice"
            ]
        return super()._prepare_tax_base_line_values()

    def _launch_stock_rule_from_pos_order_lines(self):
        return super(PosOrderLine, self.filtered(lambda line: not line.is_meal_parent))._launch_stock_rule_from_pos_order_lines()

    def _additional_final_qty_in_product_uom(self):
        """Return the absolute line quantity in the product's reference UoM."""
        self.ensure_one()
        return self.product_uom_id._compute_quantity(
            abs(self.qty), self.product_id.uom_id
        )

    def _additional_final_parent_line(self):
        """Find this additional line's visible parent in the same POS order.

        Sales lines use the parent line UUID directly.  POS refund lines keep a
        link to their original POS line, so a refund is matched through that
        original bundle as well.  Supporting both forms is important for old
        tickets and for tickets created by the POS refund screen.
        """
        self.ensure_one()
        if not self.is_additional_final_product:
            return self.env["pos.order.line"]

        parents = self.order_id.lines.filtered("is_additional_final_parent")
        direct_parent = parents.filtered(
            lambda parent: parent.uuid == self.additional_final_parent_uuid
        )[:1]
        if direct_parent:
            return direct_parent

        source_child = self.refunded_orderline_id
        if not source_child:
            return self.env["pos.order.line"]
        return parents.filtered(
            lambda parent: parent.refunded_orderline_id
            and source_child.additional_final_parent_uuid
            == parent.refunded_orderline_id.uuid
        )[:1]

    def _additional_final_children(self):
        """Return the additional final POS lines that belong to this parent."""
        self.ensure_one()
        if not self.is_additional_final_parent:
            return self.env["pos.order.line"]
        return self.order_id.lines.filtered(
            lambda line: line.is_additional_final_product
            and line._additional_final_parent_line() == self
        )

    def _additional_final_completed_mrp_cost_company(self):
        """Return (cost, is_actual) from completed POS MOs in company currency.

        The amount is read from the finished stock moves of the exact MOs linked
        to the POS line.  It therefore uses the real manufacturing valuation and
        never changes a product's ``standard_price``.  If a single MO serves more
        than one POS line, its finished value is apportioned by the source-line
        quantities, which prevents the same MO cost from being counted twice.
        """
        self.ensure_one()

        # A refund has no MO of its own.  Reuse the exact cost of the refunded
        # source line in the returned quantity ratio, with the refund sign.
        if self.qty < 0 and self.refunded_orderline_id:
            source_line = self.refunded_orderline_id
            source_cost, source_is_actual = (
                source_line._additional_final_completed_mrp_cost_company()
            )
            source_qty = source_line._additional_final_qty_in_product_uom()
            if source_is_actual and not float_is_zero(
                source_qty, precision_rounding=self.product_id.uom_id.rounding
            ):
                return (
                    -source_cost
                    * self._additional_final_qty_in_product_uom()
                    / source_qty,
                    True,
                )
            return 0.0, False

        productions = (
            self.mrp_production_id | self.mrp_production_ids
        ).filtered(
            lambda production: production.pos_auto_mrp_generated
            and production.state == "done"
            and production.product_id == self.product_id
        )
        if not productions:
            return 0.0, False

        line_qty = self._additional_final_qty_in_product_uom()
        total_cost = 0.0
        has_actual_cost = False
        for production in productions:
            finished_moves = production.move_finished_ids.filtered(
                lambda move: move.state == "done"
                and move.product_id == self.product_id
            )
            if not finished_moves:
                continue

            source_lines = (
                production.pos_order_line_ids | production.pos_order_line_id
            ).filtered(
                lambda line: line.product_id == self.product_id and line.qty > 0
            )
            total_source_qty = sum(
                line._additional_final_qty_in_product_uom()
                for line in source_lines
            )
            if float_is_zero(
                total_source_qty, precision_rounding=self.product_id.uom_id.rounding
            ):
                total_source_qty = production.product_uom_id._compute_quantity(
                    production.qty_produced or production.product_qty,
                    self.product_id.uom_id,
                )
            if float_is_zero(
                total_source_qty, precision_rounding=self.product_id.uom_id.rounding
            ):
                continue

            # ``stock.move.value`` is the inventory value generated by this MO
            # for its main finished product, in the company currency.
            total_cost += sum(finished_moves.mapped("value")) * line_qty / total_source_qty
            has_actual_cost = True
        return total_cost, has_actual_cost

    def _additional_final_convert_company_cost(self, amount):
        self.ensure_one()
        company_currency = self.company_id.currency_id
        return company_currency._convert(
            amount,
            self.currency_id,
            self.company_id,
            (self.order_id.date_order or fields.Datetime.now()).date(),
            round=False,
        )

    def _additional_final_fallback_direct_cost(self):
        """Use the original POS COGS only until an actual MO cost exists."""
        self.ensure_one()
        if self.qty < 0 and self.refunded_orderline_id:
            source_line = self.refunded_orderline_id
            source_qty = source_line._additional_final_qty_in_product_uom()
            if not float_is_zero(
                source_qty, precision_rounding=self.product_id.uom_id.rounding
            ):
                source_cost = source_line.currency_id._convert(
                    source_line.mrp_direct_cost,
                    self.currency_id,
                    self.company_id,
                    (self.order_id.date_order or fields.Datetime.now()).date(),
                    round=False,
                )
                return (
                    -source_cost
                    * self._additional_final_qty_in_product_uom()
                    / source_qty
                )
        return self.mrp_direct_cost

    def _additional_final_refresh_bundle_costs(self):
        """Allocate each secondary product's cost to its visible parent line.

        The child POS line remains the stock/valuation trace for its own product,
        but its *reporting* COGS is moved to the parent.  Consequently the parent
        carries one combined cost while neither order margin nor ``report.pos.order``
        can count that secondary MO a second time.
        """
        orders = self.mapped("order_id") | self.mapped(
            "refund_orderline_ids.order_id"
        )
        parents = orders.mapped("lines").filtered("is_additional_final_parent")
        for parent in parents:
            children = parent._additional_final_children()
            if not children:
                continue

            direct_costs = {}
            for line in parent | children:
                actual_company_cost, is_actual = (
                    line._additional_final_completed_mrp_cost_company()
                )
                direct_costs[line.id] = (
                    line._additional_final_convert_company_cost(actual_company_cost)
                    if is_actual
                    else line._additional_final_fallback_direct_cost()
                )

            children_cost = sum(direct_costs[child.id] for child in children)
            parent.with_context(additional_final_cost_refresh=True).write({
                "mrp_direct_cost": direct_costs[parent.id],
                "additional_final_products_cost": children_cost,
                "total_cost": direct_costs[parent.id] + children_cost,
            })
            for child in children:
                child.with_context(additional_final_cost_refresh=True).write({
                    "mrp_direct_cost": direct_costs[child.id],
                    "additional_final_products_cost": 0.0,
                    # Child inventory valuation remains unchanged.  Zero here
                    # only prevents a second COGS hit in POS profitability.
                    "total_cost": 0.0,
                })
        return True

    def _compute_total_cost(self, stock_moves):
        """Keep the core COGS as a fallback, then allocate bundle MRP costs."""
        pending_additional_lines = self.filtered(
            lambda line: not line.is_total_cost_computed
            and (line.is_additional_final_parent or line.is_additional_final_product)
        )
        result = super()._compute_total_cost(stock_moves)

        # Core POS cost calculation is still the fallback for a secondary line
        # that has no completed MO yet (or has no manufacturing BOM at all).
        for line in pending_additional_lines:
            line.with_context(additional_final_cost_refresh=True).write({
                "mrp_direct_cost": line.total_cost,
            })
        if pending_additional_lines:
            pending_additional_lines._additional_final_refresh_bundle_costs()
        return result

    @api.depends(
        "price_subtotal",
        "total_cost",
        "is_additional_final_parent",
        "is_additional_final_product",
        "order_id.is_refund",
        "order_id.lines.price_subtotal",
        "order_id.lines.is_additional_final_product",
        "order_id.lines.additional_final_parent_uuid",
        "refunded_orderline_id",
        "refunded_orderline_id.additional_final_parent_uuid",
    )
    def _compute_margin(self):
        super()._compute_margin()
        for line in self:
            if line.is_additional_final_parent:
                children = line._additional_final_children()
                if not children:
                    continue
                sign = -1 if line.order_id.is_refund else 1
                revenue = (line.price_subtotal + sum(children.mapped("price_subtotal"))) * sign
                line.margin = revenue - line.total_cost
                line.margin_percent = (
                    line.margin / revenue
                    if not float_is_zero(
                        revenue, precision_rounding=line.currency_id.rounding
                    )
                    else 0.0
                )
            elif line.is_additional_final_product and line._additional_final_parent_line():
                # Revenue and COGS of an additional product are reported on the
                # visible parent line as one commercial bundle.
                line.margin = 0.0
                line.margin_percent = 0.0


class ReportPosOrder(models.Model):
    _inherit = "report.pos.order"

    def _select(self):
        """Report the bundle margin once, on its visible parent POS line."""
        select = super()._select()
        standard_margin = (
            "((SIGN(l.qty) * SIGN(l.price_unit) * ABS(l.price_subtotal)) - "
            "COALESCE(l.total_cost,0)) / COALESCE(NULLIF(s.currency_rate, 0), 1.0) "
            "AS margin,"
        )
        bundle_margin = """
            CASE
                WHEN l.is_additional_final_product AND EXISTS (
                    SELECT 1
                      FROM pos_order_line parent_line
                     WHERE parent_line.order_id = l.order_id
                       AND parent_line.is_additional_final_parent
                       AND (
                            parent_line.uuid = l.additional_final_parent_uuid
                            OR (
                                parent_line.refunded_orderline_id IS NOT NULL
                                AND (
                                    l.additional_final_parent_uuid = (
                                        SELECT source_parent.uuid
                                          FROM pos_order_line source_parent
                                         WHERE source_parent.id = parent_line.refunded_orderline_id
                                    )
                                    OR l.refunded_orderline_id IN (
                                        SELECT source_child.id
                                          FROM pos_order_line source_child
                                         WHERE source_child.additional_final_parent_uuid = (
                                            SELECT source_parent.uuid
                                              FROM pos_order_line source_parent
                                             WHERE source_parent.id = parent_line.refunded_orderline_id
                                         )
                                    )
                                )
                            )
                       )
                ) THEN 0.0
                WHEN l.is_additional_final_parent THEN (
                    (
                        (SIGN(l.qty) * SIGN(l.price_unit) * ABS(l.price_subtotal))
                        + COALESCE((
                            SELECT SUM(SIGN(child_line.qty) * SIGN(child_line.price_unit) * ABS(child_line.price_subtotal))
                              FROM pos_order_line child_line
                             WHERE child_line.order_id = l.order_id
                               AND child_line.is_additional_final_product
                               AND (
                                    child_line.additional_final_parent_uuid = l.uuid
                                    OR (
                                        l.refunded_orderline_id IS NOT NULL
                                        AND (
                                            child_line.additional_final_parent_uuid = (
                                                SELECT source_parent.uuid
                                                  FROM pos_order_line source_parent
                                                 WHERE source_parent.id = l.refunded_orderline_id
                                            )
                                            OR child_line.refunded_orderline_id IN (
                                                SELECT source_child.id
                                                  FROM pos_order_line source_child
                                                 WHERE source_child.additional_final_parent_uuid = (
                                                    SELECT source_parent.uuid
                                                      FROM pos_order_line source_parent
                                                     WHERE source_parent.id = l.refunded_orderline_id
                                                 )
                                            )
                                        )
                                    )
                               )
                        ), 0.0)
                        - COALESCE(l.total_cost, 0.0)
                    ) / COALESCE(NULLIF(s.currency_rate, 0), 1.0)
                )
                ELSE ((SIGN(l.qty) * SIGN(l.price_unit) * ABS(l.price_subtotal))
                    - COALESCE(l.total_cost, 0.0))
                    / COALESCE(NULLIF(s.currency_rate, 0), 1.0)
            END AS margin,
        """
        if standard_margin not in select:
            _logger.warning(
                "Additional final product margin was not injected into report.pos.order; "
                "the upstream POS report SQL has changed."
            )
            return select
        return select.replace(standard_margin, bundle_margin)
