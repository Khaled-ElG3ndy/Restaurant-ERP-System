from odoo import Command, models
from odoo.addons.hosny_purchase_order_line_validation.models.purchase_order import (
    DUPLICATE_ISSUE,
)


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    def _hosny_duplicate_product_lines(self):
        """Return every repeated product line after its first occurrence."""
        duplicate_lines = self.env["purchase.order.line"]
        for order in self:
            seen_product_ids = set()
            product_lines = order.order_line.filtered(
                lambda line: line.product_id
                and not line.display_type
                and not line.is_downpayment
            ).sorted(key=lambda line: (line.sequence, line.id))
            for line in product_lines:
                if line.product_id.id in seen_product_ids:
                    duplicate_lines |= line
                else:
                    seen_product_ids.add(line.product_id.id)
        return duplicate_lines

    def _hosny_unacknowledged_duplicate_product_lines(self):
        return self._hosny_duplicate_product_lines().filtered(
            lambda line: not line.hosny_duplicate_warning_acknowledged
        )

    def _hosny_collect_purchase_line_validation_errors(self):
        """Keep the validator's quantity/price errors, but allow accepted duplicates."""
        grouped_errors = super()._hosny_collect_purchase_line_validation_errors()
        if not self.env.context.get("hosny_allow_duplicate_purchase_product_lines"):
            return grouped_errors
        for product_id in list(grouped_errors):
            error = grouped_errors[product_id]
            error["issues"] = [
                issue for issue in error["issues"] if issue != DUPLICATE_ISSUE
            ]
            if not error["issues"]:
                grouped_errors.pop(product_id)
        return grouped_errors

    def button_confirm(self):
        orders_to_confirm = self.filtered(lambda order: order.state in ("draft", "sent"))
        duplicate_lines = (
            orders_to_confirm._hosny_unacknowledged_duplicate_product_lines()
            if not self.env.context.get("hosny_skip_duplicate_product_warning")
            else self.env["purchase.order.line"]
        )
        if duplicate_lines:
            wizard = self.env["hosny.duplicate.purchase.line.warning"].create(
                {
                    "order_ids": [Command.set(duplicate_lines.order_id.ids)],
                    "duplicate_line_ids": [Command.set(duplicate_lines.ids)],
                }
            )
            return {
                "type": "ir.actions.act_window",
                "name": self.env._("Duplicate Product Warning"),
                "res_model": "hosny.duplicate.purchase.line.warning",
                "res_id": wizard.id,
                "view_mode": "form",
                "target": "new",
            }
        acknowledged_duplicates = orders_to_confirm._hosny_duplicate_product_lines()
        orders_for_super = self.with_context(
            hosny_allow_duplicate_purchase_product_lines=bool(
                acknowledged_duplicates
            )
        )
        return super(PurchaseOrder, orders_for_super).button_confirm()
