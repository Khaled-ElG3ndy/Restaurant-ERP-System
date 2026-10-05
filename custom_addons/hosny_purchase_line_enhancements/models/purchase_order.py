from odoo import api, fields, models
from odoo.exceptions import ValidationError


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    hosny_global_discount_type = fields.Selection(
        [
            ("percent", "Percentage"),
            ("amount", "Amount"),
        ],
        string="Discount Type",
        default="percent",
        copy=False,
    )
    hosny_global_discount_percent = fields.Float(
        string="الخصم %",
        digits="Discount",
        copy=True,
    )
    hosny_global_discount_amount = fields.Monetary(
        string="الخصم",
        currency_field="currency_id",
        copy=True,
    )
    hosny_global_discount_base_amount = fields.Monetary(
        string="المبلغ قبل الخصم الكلي",
        compute="_compute_hosny_global_discount_base_amount",
        currency_field="currency_id",
    )

    def _hosny_discountable_order_lines(self):
        self.ensure_one()
        return self.order_line.filtered(lambda line: not line.display_type and not line.is_downpayment)

    def _hosny_get_global_discount_base_amount(self):
        self.ensure_one()
        return sum(line._hosny_get_line_amount_after_line_discount() for line in self._hosny_discountable_order_lines())

    @api.depends("order_line.price_unit", "order_line.product_qty", "order_line.discount", "order_line.display_type")
    def _compute_hosny_global_discount_base_amount(self):
        for order in self:
            order.hosny_global_discount_base_amount = order._hosny_get_global_discount_base_amount()

    def _hosny_sync_global_discount_from_percent(self):
        for order in self:
            base_amount = order._hosny_get_global_discount_base_amount()
            order.hosny_global_discount_amount = order.currency_id.round(
                base_amount * order.hosny_global_discount_percent / 100.0
            )

    def _hosny_sync_global_discount_from_amount(self):
        for order in self:
            base_amount = order._hosny_get_global_discount_base_amount()
            order.hosny_global_discount_percent = base_amount and (
                order.hosny_global_discount_amount / base_amount * 100.0
            ) or 0.0

    @api.onchange("hosny_global_discount_percent")
    def _onchange_hosny_global_discount_percent(self):
        for order in self:
            order.hosny_global_discount_type = "percent"
        self._hosny_sync_global_discount_from_percent()

    @api.onchange("hosny_global_discount_amount")
    def _onchange_hosny_global_discount_amount(self):
        for order in self:
            order.hosny_global_discount_type = "amount"
        self._hosny_sync_global_discount_from_amount()

    @api.onchange("order_line", "currency_id")
    def _onchange_hosny_global_discount_base(self):
        for order in self:
            if order.hosny_global_discount_type == "amount":
                order._hosny_sync_global_discount_from_amount()
            else:
                order._hosny_sync_global_discount_from_percent()

    @api.constrains("hosny_global_discount_percent", "hosny_global_discount_amount", "order_line")
    def _check_hosny_global_discount(self):
        for order in self:
            base_amount = order._hosny_get_global_discount_base_amount()
            if order.hosny_global_discount_percent < 0 or order.hosny_global_discount_percent > 100:
                raise ValidationError("الخصم الكلي يجب أن يكون بين 0% و 100%.")
            if order.hosny_global_discount_amount < 0:
                raise ValidationError("قيمة الخصم الكلي لا يمكن أن تكون أقل من صفر.")
            if order.currency_id.compare_amounts(order.hosny_global_discount_amount, base_amount) > 0:
                raise ValidationError("قيمة الخصم الكلي لا يمكن أن تكون أكبر من إجمالي أمر الشراء.")

    @api.model_create_multi
    def create(self, vals_list):
        orders = super().create(vals_list)
        for order, vals in zip(orders, vals_list):
            if self.env.context.get("hosny_skip_global_discount_sync"):
                continue
            if "hosny_global_discount_amount" in vals and "hosny_global_discount_percent" not in vals:
                order._hosny_sync_global_discount_from_amount()
            elif "hosny_global_discount_percent" in vals and "hosny_global_discount_amount" not in vals:
                order._hosny_sync_global_discount_from_percent()
        return orders

    def write(self, vals):
        res = super().write(vals)
        if self.env.context.get("hosny_skip_global_discount_sync"):
            return res
        if {"hosny_global_discount_amount", "hosny_global_discount_percent", "order_line", "currency_id"} & set(vals):
            for order in self:
                sync_vals = {}
                if "hosny_global_discount_amount" in vals and "hosny_global_discount_percent" not in vals:
                    base_amount = order._hosny_get_global_discount_base_amount()
                    sync_vals["hosny_global_discount_percent"] = base_amount and (
                        order.hosny_global_discount_amount / base_amount * 100.0
                    ) or 0.0
                    sync_vals["hosny_global_discount_type"] = "amount"
                elif "hosny_global_discount_percent" in vals and "hosny_global_discount_amount" not in vals:
                    base_amount = order._hosny_get_global_discount_base_amount()
                    sync_vals["hosny_global_discount_amount"] = order.currency_id.round(
                        base_amount * order.hosny_global_discount_percent / 100.0
                    )
                    sync_vals["hosny_global_discount_type"] = "percent"
                elif "order_line" in vals or "currency_id" in vals:
                    base_amount = order._hosny_get_global_discount_base_amount()
                    if order.hosny_global_discount_type == "amount":
                        sync_vals["hosny_global_discount_percent"] = base_amount and (
                            order.hosny_global_discount_amount / base_amount * 100.0
                        ) or 0.0
                    else:
                        sync_vals["hosny_global_discount_amount"] = order.currency_id.round(
                            base_amount * order.hosny_global_discount_percent / 100.0
                        )
                if sync_vals:
                    order.with_context(hosny_skip_global_discount_sync=True).write(sync_vals)
        return res


class PurchaseOrderLine(models.Model):
    _inherit = "purchase.order.line"

    hosny_tax_amount = fields.Monetary(
        string="قيمة الضرايب",
        compute="_compute_hosny_tax_amount",
        currency_field="currency_id",
        store=True,
    )
    hosny_free_qty = fields.Float(
        string="كميه مجانيه",
        digits="Product Unit",
        default=0.0,
    )
    hosny_discount_amount = fields.Monetary(
        string="الخصم (قيمة)",
        compute="_compute_hosny_discount_amount",
        inverse="_inverse_hosny_discount_amount",
        currency_field="currency_id",
        store=True,
        readonly=False,
    )

    @api.depends("price_tax", "currency_id")
    def _compute_hosny_tax_amount(self):
        for line in self:
            line.hosny_tax_amount = line.price_tax

    def _hosny_get_line_discount_base_amount(self):
        self.ensure_one()
        return (self.price_unit or 0.0) * (self.product_qty or 0.0)

    def _hosny_get_line_amount_after_line_discount(self):
        self.ensure_one()
        return self.currency_id.round(
            self._hosny_get_line_discount_base_amount() * (1 - (self.discount or 0.0) / 100.0)
        )

    @api.depends("discount", "price_unit", "product_qty", "currency_id")
    def _compute_hosny_discount_amount(self):
        for line in self:
            line.hosny_discount_amount = line.currency_id.round(
                line._hosny_get_line_discount_base_amount() * (line.discount or 0.0) / 100.0
            )

    def _inverse_hosny_discount_amount(self):
        for line in self:
            base_amount = line._hosny_get_line_discount_base_amount()
            line.discount = base_amount and line.hosny_discount_amount / base_amount * 100.0 or 0.0

    @api.onchange("hosny_discount_amount")
    def _onchange_hosny_discount_amount(self):
        self._inverse_hosny_discount_amount()

    @api.onchange("discount", "price_unit", "product_qty")
    def _onchange_hosny_discount_percent_or_base(self):
        self._compute_hosny_discount_amount()

    def _hosny_get_combined_discount_percent(self):
        self.ensure_one()
        line_discount = min(max(self.discount or 0.0, 0.0), 100.0) / 100.0
        order_discount = min(max(self.order_id.hosny_global_discount_percent or 0.0, 0.0), 100.0) / 100.0
        return (1 - ((1 - line_discount) * (1 - order_discount))) * 100.0

    @api.depends("product_qty", "price_unit", "tax_ids", "discount", "order_id.hosny_global_discount_percent")
    def _compute_amount(self):
        return super()._compute_amount()

    @api.depends("discount", "price_unit", "order_id.hosny_global_discount_percent")
    def _compute_price_unit_discounted(self):
        for line in self:
            line.price_unit_discounted = line.price_unit * (1 - line._hosny_get_combined_discount_percent() / 100.0)

    def _prepare_base_line_for_taxes_computation(self):
        base_line = super()._prepare_base_line_for_taxes_computation()
        if not self.display_type and not self.is_downpayment:
            base_line["discount"] = self._hosny_get_combined_discount_percent()
        return base_line

    def _prepare_account_move_line(self, move=False):
        res = super()._prepare_account_move_line(move=move)
        if not self.display_type and not self.is_downpayment:
            res["discount"] = self._hosny_get_combined_discount_percent()
        return res

    @api.depends("invoice_lines.move_id.state", "invoice_lines.quantity", "qty_received", "product_uom_qty", "order_id.state", "hosny_free_qty")
    def _compute_qty_invoiced(self):
        super()._compute_qty_invoiced()
        for line in self.filtered(lambda item: item.hosny_free_qty and item.order_id.state == "purchase"):
            if line.product_id.purchase_method != "purchase":
                billable_received_qty = min(line.qty_received, line.product_qty)
                line.qty_to_invoice = billable_received_qty - line.qty_invoiced

    def _prepare_stock_moves(self, picking):
        self.ensure_one()
        if not self.hosny_free_qty:
            return super()._prepare_stock_moves(picking)

        res = []
        if self.product_id.type != "consu":
            return res

        total_qty = self.product_qty + self.hosny_free_qty
        price_unit = self._get_stock_move_price_unit()
        if total_qty:
            price_unit *= self.product_qty / total_qty
        else:
            price_unit = 0.0

        qty = self._get_qty_procurement()
        move_dests = self.move_dest_ids or self.move_ids.move_dest_ids
        move_dests = move_dests.filtered(lambda move: move.state != "cancel" and not move._is_purchase_return())

        if not move_dests:
            qty_to_attach = 0
            qty_to_push = total_qty - qty
        else:
            move_dests_initial_demand = self._get_move_dests_initial_demand(move_dests)
            qty_to_attach = move_dests_initial_demand - qty
            qty_to_push = total_qty - move_dests_initial_demand

        if self.product_uom_id.compare(qty_to_attach, 0.0) > 0:
            product_uom_qty, product_uom = self.product_uom_id._adjust_uom_quantities(qty_to_attach, self.product_id.uom_id)
            res.append(self._prepare_stock_move_vals(picking, price_unit, product_uom_qty, product_uom))
        if not self.product_uom_id.is_zero(qty_to_push):
            product_uom_qty, product_uom = self.product_uom_id._adjust_uom_quantities(qty_to_push, self.product_id.uom_id)
            extra_move_vals = self._prepare_stock_move_vals(picking, price_unit, product_uom_qty, product_uom)
            extra_move_vals["move_dest_ids"] = False
            res.append(extra_move_vals)
        return res

    @api.constrains("hosny_free_qty", "hosny_discount_amount", "discount", "price_unit", "product_qty")
    def _check_hosny_line_amounts(self):
        for line in self.filtered(lambda item: not item.display_type):
            if line.hosny_free_qty < 0:
                raise ValidationError("كميه مجانيه لا يمكن أن تكون أقل من صفر.")
            if line.discount < 0 or line.discount > 100:
                raise ValidationError("خصم السطر يجب أن يكون بين 0% و 100%.")
            if line.hosny_discount_amount < 0:
                raise ValidationError("قيمة خصم السطر لا يمكن أن تكون أقل من صفر.")
            base_amount = line._hosny_get_line_discount_base_amount()
            if line.currency_id.compare_amounts(line.hosny_discount_amount, base_amount) > 0:
                raise ValidationError("قيمة خصم السطر لا يمكن أن تكون أكبر من السعر الأساسي للسطر.")
