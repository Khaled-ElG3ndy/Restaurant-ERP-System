from odoo import _, api, models
from odoo.exceptions import UserError

WAITER_NO_PAYMENT = "حساب المتر لا يستطيع تحصيل الدفع أو تسديد الفواتير — الدفع من الكاشير."
WAITER_NO_REFUND = "حساب المتر لا يستطيع عمل استرداد."
WAITER_DINE_IN_ONLY = "حساب المتر يعمل طلبات محلي على الطاولات فقط — السفري من الكاشير."


class PosOrder(models.Model):
    _inherit = "pos.order"

    @api.model
    def _process_order(self, order, existing_order):
        if self.env.user._hosny_is_pos_waiter():
            self._hosny_check_waiter_order(order, existing_order)
        return super()._process_order(order, existing_order)

    @api.model
    def _hosny_check_waiter_order(self, order, existing_order):
        """ما يرسله جهاز المتر: طلب محلي مفتوح بلا دفع (الشاشة تمنع الباقي)."""
        if any(command and command[0] == 0 for command in order.get("payment_ids") or []):
            raise UserError(_(WAITER_NO_PAYMENT))
        if order.get("state") in ("paid", "done", "invoiced"):
            raise UserError(_(WAITER_NO_PAYMENT))
        if self._get_refunded_orders(order):
            raise UserError(_(WAITER_NO_REFUND))

        has_items = bool(order.get("lines")) or bool(existing_order and existing_order.lines)
        if not has_items:
            # طلب فارغ لا يضر، ورفضه يوقف مزامنة باقي طلبات الجهاز
            return
        table_id = order.get("table_id", existing_order.table_id.id if existing_order else False)
        type_id = order.get("order_type_id") or (existing_order.order_type_id.id if existing_order else False)
        order_type = self.env["pos.order.type"].browse(type_id).exists() if type_id else False
        if (
            not table_id
            or self._hosny_is_takeaway_table(table_id)
            or (order_type and not order_type._hosny_requires_table())
        ):
            raise UserError(_(WAITER_DINE_IN_ONLY))

    def refund(self):
        if self.env.user._hosny_is_pos_waiter():
            raise UserError(_(WAITER_NO_REFUND))
        return super().refund()
