from collections import defaultdict

from odoo import api, fields, models


class DuplicatePurchaseLineWarning(models.TransientModel):
    _name = "hosny.duplicate.purchase.line.warning"
    _description = "Duplicate Purchase Product Warning"

    order_ids = fields.Many2many("purchase.order", readonly=True)
    duplicate_line_ids = fields.Many2many("purchase.order.line", readonly=True)
    warning_message = fields.Text(compute="_compute_warning_message")

    @api.depends("duplicate_line_ids", "duplicate_line_ids.product_id")
    def _compute_warning_message(self):
        for wizard in self:
            products_by_order = defaultdict(set)
            for line in wizard.duplicate_line_ids:
                products_by_order[line.order_id.display_name].add(
                    line.product_id.display_name
                )
            details = "\n".join(
                wizard.env._(
                    "%(order)s: %(products)s",
                    order=order_name,
                    products=", ".join(sorted(products)),
                )
                for order_name, products in sorted(products_by_order.items())
            )
            wizard.warning_message = wizard.env._(
                "The following products are repeated on separate purchase lines:\n%(details)s\n\n"
                "Each line, quantity, price, and purchase packaging will remain separate. "
                "Do you want to skip this warning and continue?",
                details=details,
            )

    def action_continue(self):
        self.ensure_one()
        orders = self.order_ids.filtered(lambda order: order.state in ("draft", "sent"))
        current_duplicates = orders._hosny_duplicate_product_lines()
        current_duplicates.write({"hosny_duplicate_warning_acknowledged": True})
        return orders.with_context(
            hosny_skip_duplicate_product_warning=True,
            hosny_allow_duplicate_purchase_product_lines=True,
        ).button_confirm()
