from odoo import _, api, fields, models
from odoo.tools.float_utils import float_is_zero
from odoo.tools.misc import formatLang


class PosOrderLineCostDisplay(models.Model):
    _inherit = "pos.order.line"

    ui_product_cost = fields.Char(
        string="Product Cost",
        compute="_compute_cost_display_fields",
    )
    ui_additional_products_cost = fields.Char(
        string="Additional Products Cost",
        compute="_compute_cost_display_fields",
    )
    ui_total_cost = fields.Char(
        string="Total Cost",
        compute="_compute_cost_display_fields",
    )
    ui_margin = fields.Char(
        string="Displayed Margin",
        compute="_compute_cost_display_fields",
    )
    ui_margin_percent = fields.Char(
        string="Margin %",
        compute="_compute_cost_display_fields",
    )
    ui_cost_role = fields.Char(
        string="Type",
        compute="_compute_cost_display_fields",
    )
    ui_has_additional_products = fields.Boolean(
        compute="_compute_cost_display_fields",
    )

    def _cost_display_amount(self, amount):
        self.ensure_one()
        return formatLang(
            self.env,
            amount,
            digits=self.currency_id.decimal_places,
            grouping=True,
        )

    def _additional_final_breakdown_source_line(self):
        """Return the sold child line whose MOs value this sale/refund row."""
        self.ensure_one()
        if self.qty < 0 and self.refunded_orderline_id:
            return self.refunded_orderline_id
        return self

    def _additional_final_breakdown_productions(self):
        """Return exact linked automatic MOs, including pending/cancelled ones."""
        self.ensure_one()
        source_line = self._additional_final_breakdown_source_line()
        return (
            source_line.mrp_production_id | source_line.mrp_production_ids
        ).filtered(
            lambda production: production.pos_auto_mrp_generated
            and production.product_id == source_line.product_id
        ).sorted(lambda production: (production.create_date, production.id))

    def _additional_final_breakdown_is_complete(self):
        """Whether every active additional MO has an actual finished valuation."""
        self.ensure_one()
        if not self.is_additional_final_parent:
            return False
        children = self._additional_final_children()
        if not children:
            return False
        for child in children:
            productions = child._additional_final_breakdown_productions()
            active_productions = productions.filtered(
                lambda production: production.state != "cancel"
            )
            if not active_productions:
                return False
            for production in active_productions:
                finished_moves = production.move_finished_ids.filtered(
                    lambda move: move.state == "done"
                    and move.product_id == production.product_id
                )
                if production.state != "done" or not finished_moves:
                    return False
        return True

    @api.depends(
        "is_additional_final_parent",
        "is_additional_final_product",
        "is_total_cost_computed",
        "mrp_direct_cost",
        "additional_final_products_cost",
        "total_cost",
        "price_subtotal",
        "order_id.is_refund",
        "order_id.lines.is_additional_final_product",
        "order_id.lines.additional_final_parent_uuid",
        "order_id.lines.mrp_direct_cost",
        "order_id.lines.mrp_production_id.state",
        "order_id.lines.mrp_production_ids.state",
    )
    def _compute_cost_display_fields(self):
        not_computed = _("Not Computed Yet")
        for line in self:
            line.ui_has_additional_products = False
            line.ui_cost_role = False
            line.ui_product_cost = False
            line.ui_additional_products_cost = False
            line.ui_total_cost = False
            line.ui_margin = False
            line.ui_margin_percent = False

            # The additional row remains the stock/MO audit trace, but all
            # commercial COGS and margin are intentionally displayed once on
            # its parent.  A badge explains the otherwise blank cost cells.
            if line.is_additional_final_product:
                line.ui_cost_role = _("Additional Product")
                continue

            children = (
                line._additional_final_children()
                if line.is_additional_final_parent
                else self.env["pos.order.line"]
            )
            line.ui_has_additional_products = bool(children)

            if not line.is_total_cost_computed:
                line.ui_product_cost = not_computed
                line.ui_additional_products_cost = (
                    not_computed if children else "—"
                )
                line.ui_total_cost = not_computed
                line.ui_margin = not_computed
                line.ui_margin_percent = not_computed
                continue

            product_cost = (
                line.mrp_direct_cost
                if line.is_additional_final_parent
                else line.total_cost
            )
            line.ui_product_cost = line._cost_display_amount(product_cost)

            if not children:
                line.ui_additional_products_cost = "—"
                line.ui_total_cost = line._cost_display_amount(line.total_cost)
                line.ui_margin = line._cost_display_amount(line.margin)
                line.ui_margin_percent = "%s%%" % formatLang(
                    line.env,
                    line.margin_percent * 100.0,
                    digits=2,
                    grouping=True,
                )
                continue

            if not line._additional_final_breakdown_is_complete():
                line.ui_additional_products_cost = not_computed
                line.ui_total_cost = not_computed
                line.ui_margin = not_computed
                line.ui_margin_percent = not_computed
                continue

            line.ui_additional_products_cost = line._cost_display_amount(
                line.additional_final_products_cost
            )
            line.ui_total_cost = line._cost_display_amount(line.total_cost)
            line.ui_margin = line._cost_display_amount(line.margin)
            line.ui_margin_percent = "%s%%" % formatLang(
                line.env,
                line.margin_percent * 100.0,
                digits=2,
                grouping=True,
            )

    def _additional_final_breakdown_mo_values(self, production):
        """Build one presentation row from the same valuation inputs as COGS.

        This method never writes accounting values.  It only splits the
        already-linked MOs for the read-only dialog.
        """
        self.ensure_one()
        source_line = self._additional_final_breakdown_source_line()
        product = source_line.product_id
        line_qty = source_line._additional_final_qty_in_product_uom()
        source_lines = (
            production.pos_order_line_ids | production.pos_order_line_id
        ).filtered(
            lambda line: line.product_id == product and line.qty > 0
        )
        total_source_qty = sum(
            line._additional_final_qty_in_product_uom()
            for line in source_lines
        )
        if float_is_zero(
            total_source_qty,
            precision_rounding=product.uom_id.rounding,
        ):
            total_source_qty = production.product_uom_id._compute_quantity(
                production.qty_produced or production.product_qty,
                product.uom_id,
            )
        ratio = (
            line_qty / total_source_qty
            if not float_is_zero(
                total_source_qty,
                precision_rounding=product.uom_id.rounding,
            )
            else 0.0
        )

        finished_moves = production.move_finished_ids.filtered(
            lambda move: move.state == "done" and move.product_id == product
        )
        cost_computed = production.state == "done" and bool(finished_moves)
        produced_qty = sum(
            move.product_uom._compute_quantity(move.quantity, product.uom_id)
            for move in finished_moves
        )
        if not cost_computed:
            produced_qty = production.product_uom_id._compute_quantity(
                production.product_qty,
                product.uom_id,
            )
        allocated_qty = produced_qty * ratio
        company_cost = (
            sum(finished_moves.mapped("value")) * ratio
            if cost_computed
            else 0.0
        )

        if self.qty < 0 and self.refunded_orderline_id:
            source_qty = source_line._additional_final_qty_in_product_uom()
            refund_ratio = (
                self._additional_final_qty_in_product_uom() / source_qty
                if not float_is_zero(
                    source_qty,
                    precision_rounding=product.uom_id.rounding,
                )
                else 0.0
            )
            allocated_qty = -allocated_qty * refund_ratio
            company_cost = -company_cost * refund_ratio

        total_cost = (
            self._additional_final_convert_company_cost(company_cost)
            if cost_computed
            else 0.0
        )
        state = "done" if production.state == "done" else "pending"
        if production.state == "cancel":
            state = "cancelled"
        return {
            "product_id": product.id,
            "product_name": product.display_name,
            "quantity": allocated_qty,
            "uom_name": product.uom_id.display_name,
            "production_name": production.display_name,
            "production_state": state,
            "cost_computed": cost_computed,
            "total_cost": total_cost,
        }

    def _additional_final_breakdown_rows(self):
        self.ensure_one()
        rows = []
        for child in self._additional_final_children():
            productions = child._additional_final_breakdown_productions().sudo()
            if not productions:
                rows.append({
                    "product_id": child.product_id.id,
                    "product_name": child.product_id.display_name,
                    "quantity": child.qty,
                    "uom_name": child.product_uom_id.display_name,
                    "production_name": "—",
                    "production_state": "pending",
                    "cost_computed": False,
                    "total_cost": 0.0,
                })
                continue
            rows.extend(
                child._additional_final_breakdown_mo_values(production)
                for production in productions
            )
        return rows

    def action_open_additional_cost_breakdown(self):
        self.ensure_one()
        wizard = self.env[
            "pos.additional.product.cost.breakdown.wizard"
        ].create_from_pos_line(self)
        form_view = self.env.ref(
            "hosny_pos_meal_combo.pos_additional_product_cost_breakdown_wizard_form"
        )
        return {
            "type": "ir.actions.act_window",
            "name": _("Additional Products Cost Details"),
            "res_model": wizard._name,
            "res_id": wizard.id,
            "view_mode": "form",
            "view_id": form_view.id,
            # Odoo's object-button dispatcher normally normalizes view_id /
            # view_mode into ``views``.  The inline field widget calls the
            # action service directly, whose Odoo 19 preprocessor requires
            # the explicit list.
            "views": [(form_view.id, "form")],
            "target": "new",
        }


class PosAdditionalProductCostBreakdownWizard(models.TransientModel):
    _name = "pos.additional.product.cost.breakdown.wizard"
    _description = "POS Additional Product Cost Breakdown"

    order_reference = fields.Char(string="POS Order", readonly=True)
    parent_product_name = fields.Char(string="Main Product", readonly=True)
    is_product_configuration = fields.Boolean(readonly=True)
    currency_id = fields.Many2one("res.currency", readonly=True)
    breakdown_complete = fields.Boolean(readonly=True)
    base_product_cost = fields.Monetary(
        string="Base Product Cost",
        currency_field="currency_id",
        digits="Product Price",
        readonly=True,
    )
    total_additional_cost = fields.Monetary(
        string="Raw Additional Products Cost Total",
        currency_field="currency_id",
        digits="Product Price",
        readonly=True,
    )
    final_product_cost = fields.Monetary(
        string="Final Product Cost",
        currency_field="currency_id",
        digits="Product Price",
        readonly=True,
    )
    total_additional_cost_display = fields.Char(
        string="Additional Products Cost Total",
        compute="_compute_total_additional_cost_display",
    )
    line_ids = fields.One2many(
        "pos.additional.product.cost.breakdown.line",
        "wizard_id",
        string="Additional Products",
        readonly=True,
    )

    @api.depends("breakdown_complete", "total_additional_cost", "line_ids")
    def _compute_total_additional_cost_display(self):
        for wizard in self:
            if not wizard.line_ids:
                wizard.total_additional_cost_display = "—"
            elif not wizard.breakdown_complete:
                wizard.total_additional_cost_display = _("Not Computed Yet")
            else:
                wizard.total_additional_cost_display = formatLang(
                    wizard.env,
                    wizard.total_additional_cost,
                    digits=wizard.currency_id.decimal_places,
                    grouping=True,
                )

    @api.model
    def create_from_pos_line(self, parent_line):
        parent_line.ensure_one()
        rows = parent_line.sudo()._additional_final_breakdown_rows()
        complete = parent_line.sudo()._additional_final_breakdown_is_complete()
        currency = parent_line.currency_id
        authoritative_total = currency.round(
            parent_line.additional_final_products_cost
        )

        for row in rows:
            row["total_cost"] = currency.round(row["total_cost"])
        computed_rows = [row for row in rows if row["cost_computed"]]
        if complete and computed_rows:
            displayed_sum = sum(row["total_cost"] for row in computed_rows)
            # Currency rounding can create a cent residual when several MOs
            # are converted independently.  Keep the dialog sum identical to
            # the authoritative stored parent amount without changing COGS.
            computed_rows[-1]["total_cost"] += authoritative_total - displayed_sum

        for row in rows:
            quantity = row["quantity"]
            row["unit_cost"] = (
                currency.round(abs(row["total_cost"] / quantity))
                if row["cost_computed"]
                and not float_is_zero(
                    quantity,
                    precision_rounding=parent_line.product_uom_id.rounding,
                )
                else 0.0
            )

        return self.create({
            "order_reference": parent_line.order_id.display_name,
            "parent_product_name": parent_line.product_id.display_name,
            "currency_id": currency.id,
            "breakdown_complete": complete,
            "total_additional_cost": authoritative_total,
            "line_ids": [fields.Command.create(row) for row in rows],
        })

    @api.model
    def create_from_product_template(self, template):
        """Build the same dialog from the product's current BoM configuration."""
        template.ensure_one()
        company = template.company_id or self.env.company
        currency = company.currency_id
        rows = template.sudo()._additional_final_expected_cost_rows()
        authoritative_total = sum(
            row["total_cost"] for row in rows
        )
        for row in rows:
            row["unit_cost"] = row["total_cost"] / row["quantity"]

        base_product_cost = template.sudo().with_company(company).standard_price

        return self.create({
            "parent_product_name": template.display_name,
            "currency_id": currency.id,
            "is_product_configuration": True,
            "breakdown_complete": True,
            "base_product_cost": base_product_cost,
            "total_additional_cost": authoritative_total,
            "final_product_cost": base_product_cost + authoritative_total,
            "line_ids": [fields.Command.create(row) for row in rows],
        })


class PosAdditionalProductCostBreakdownLine(models.TransientModel):
    _name = "pos.additional.product.cost.breakdown.line"
    _description = "POS Additional Product Cost Breakdown Line"
    _order = "id"

    wizard_id = fields.Many2one(
        "pos.additional.product.cost.breakdown.wizard",
        required=True,
        ondelete="cascade",
    )
    currency_id = fields.Many2one(
        related="wizard_id.currency_id",
        readonly=True,
    )
    product_name = fields.Char(string="Product Snapshot", readonly=True)
    product_id = fields.Many2one(
        "product.product",
        string="Product",
        readonly=True,
    )
    quantity = fields.Float(string="Quantity", digits="Product Unit", readonly=True)
    uom_name = fields.Char(string="Unit", readonly=True)
    production_name = fields.Char(string="Manufacturing Order", readonly=True)
    production_state = fields.Selection(
        [
            ("pending", "Pending"),
            ("done", "Done"),
            ("cancelled", "Cancelled"),
        ],
        string="MO Status",
        readonly=True,
    )
    cost_computed = fields.Boolean(readonly=True)
    unit_cost = fields.Monetary(
        string="Raw Unit Cost",
        currency_field="currency_id",
        digits="Product Price",
        readonly=True,
    )
    total_cost = fields.Monetary(
        string="Raw Total Cost",
        currency_field="currency_id",
        digits="Product Price",
        readonly=True,
    )
    unit_cost_display = fields.Char(
        string="Unit Cost",
        compute="_compute_cost_displays",
    )
    total_cost_display = fields.Char(
        string="Total Cost",
        compute="_compute_cost_displays",
    )

    @api.depends("cost_computed", "unit_cost", "total_cost", "currency_id")
    def _compute_cost_displays(self):
        for line in self:
            if not line.cost_computed:
                line.unit_cost_display = _("Not Computed Yet")
                line.total_cost_display = _("Not Computed Yet")
                continue
            line.unit_cost_display = formatLang(
                line.env,
                line.unit_cost,
                digits=line.currency_id.decimal_places,
                grouping=True,
            )
            line.total_cost_display = formatLang(
                line.env,
                line.total_cost,
                digits=line.currency_id.decimal_places,
                grouping=True,
            )
