from collections import defaultdict

from odoo import _, models
from odoo.tools import float_compare


class LoyaltyCard(models.Model):
    _inherit = "loyalty.card"

    def _hosny_coupon_rounding(self):
        self.ensure_one()
        return self.currency_id.rounding or 0.01

    def _hosny_pos_usage_by_order(self):
        usage_by_card_order = defaultdict(float)
        if not self:
            return usage_by_card_order

        pos_lines = self.env["pos.order.line"].sudo().search([
            ("coupon_id", "in", self.ids),
            ("points_cost", ">", 0),
            ("order_id.state", "in", ("paid", "done", "invoiced")),
        ])
        for line in pos_lines:
            usage_by_card_order[(line.coupon_id.id, line.order_id.id)] += line.points_cost
        return usage_by_card_order

    def _hosny_sync_usage_from_pos_orders(self):
        cards = self.sudo().exists()
        if not cards:
            return

        usage_by_card_order = cards._hosny_pos_usage_by_order()
        if not usage_by_card_order:
            return

        histories = self.env["loyalty.history"].sudo().search([
            ("card_id", "in", cards.ids),
        ])
        histories_by_card = defaultdict(lambda: self.env["loyalty.history"].sudo())
        pos_histories_by_key = defaultdict(lambda: self.env["loyalty.history"].sudo())
        for history in histories:
            histories_by_card[history.card_id.id] |= history
            if history.order_model == "pos.order" and history.order_id:
                pos_histories_by_key[(history.card_id.id, history.order_id)] |= history

        for card in cards:
            card_usage = [
                (order_id, usage)
                for (card_id, order_id), usage in usage_by_card_order.items()
                if card_id == card.id
            ]
            if not card_usage:
                continue

            card_histories = histories_by_card[card.id]
            issued_total = sum(card_histories.mapped("issued"))
            non_pos_used = sum(
                history.used
                for history in card_histories
                if history.order_model != "pos.order" or not history.order_id
            )
            remaining_for_pos = max(issued_total - non_pos_used, 0.0) if issued_total else None
            synced_pos_used = 0.0

            for order_id, actual_usage in sorted(card_usage):
                used = actual_usage
                if remaining_for_pos is not None:
                    used = min(actual_usage, remaining_for_pos)
                    remaining_for_pos -= used
                synced_pos_used += used

                current_histories = pos_histories_by_key[(card.id, order_id)]
                current_issued = sum(current_histories.mapped("issued"))
                if current_histories:
                    main_history = current_histories[0]
                    rounding = card._hosny_coupon_rounding()
                    if (
                        float_compare(main_history.used, used, precision_rounding=rounding)
                        or float_compare(main_history.issued, current_issued, precision_rounding=rounding)
                    ):
                        main_history.write({
                            "used": used,
                            "issued": current_issued,
                        })
                    duplicates = current_histories - main_history
                    if duplicates:
                        duplicates.write({
                            "used": 0.0,
                            "issued": 0.0,
                        })
                else:
                    order = self.env["pos.order"].sudo().browse(order_id)
                    self.env["loyalty.history"].sudo().create({
                        "card_id": card.id,
                        "order_model": "pos.order",
                        "order_id": order_id,
                        "description": _("Onsite %s", order.display_name),
                        "used": used,
                        "issued": 0.0,
                    })

            if issued_total:
                expected_points = max(issued_total - non_pos_used - synced_pos_used, 0.0)
                rounding = card._hosny_coupon_rounding()
                if float_compare(card.points, expected_points, precision_rounding=rounding):
                    card.with_context(loyalty_no_mail=True).write({"points": expected_points})

    def web_read(self, specification):
        if not self.env.context.get("hosny_skip_coupon_usage_sync"):
            self._hosny_sync_usage_from_pos_orders()
        return super(
            LoyaltyCard,
            self.with_context(hosny_skip_coupon_usage_sync=True),
        ).web_read(specification)
