from odoo import Command, _, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare, float_is_zero


class PosOrder(models.Model):
    _inherit = "pos.order"

    hosny_advance_reclass_move_id = fields.Many2one(
        "account.move",
        string="Advance Account Reclassification Entry",
        copy=False,
        readonly=True,
    )

    def _hosny_check_advance_account_customer(self):
        for order in self:
            if (
                order.payment_ids.filtered(lambda payment: payment.payment_method_id.type == "pay_later")
                and not order.partner_id
            ):
                raise UserError(_("لازم تختار العميل قبل الدفع الآجل."))

    def action_pos_order_paid(self):
        self._hosny_check_advance_account_customer()
        return super().action_pos_order_paid()

    def _generate_pos_order_invoice(self):
        invoice = super()._generate_pos_order_invoice()
        for order in self:
            order._hosny_reclassify_advance_invoice_receivable(order.account_move or invoice)
        return invoice

    def _hosny_advance_account_payments(self):
        self.ensure_one()
        return self.payment_ids.filtered(
            lambda payment: payment.payment_method_id.type == "pay_later"
            and payment.payment_method_id.receivable_account_id
        )

    def _hosny_advance_reclass_journal(self):
        self.ensure_one()
        journal = self.config_id.journal_id
        if journal and journal.type == "general":
            return journal

        Journal = self.env["account.journal"].sudo().with_company(self.company_id)
        return Journal.search(
            [("company_id", "=", self.company_id.id), ("type", "=", "general")],
            limit=1,
        )

    def _hosny_advance_reclass_ref(self, invoice):
        self.ensure_one()
        return _("تحويل الدفع الآجل للطلب %(order)s - %(invoice)s", order=self.name, invoice=invoice.name)

    def _hosny_advance_reclass_name(self, invoice):
        """ADV/<رقم الفاتورة>، أو False إن كان الاسم مستخدماً في دفتر القيد.

        الاسم الصريح يصبح نمط تسلسل الدفتر، فقيد إقفال جلسة لاحق على نفس
        الدفتر يُسمّى ADV/INV/…/00002؛ ولو حُذفت فاتورة وأعاد الترقيم رقمها
        لفاتورة جديدة تصطدم ADV/<رقمها> بذلك القيد (account_move_unique_name)
        وتفشل الفوترة كلها. عند التصادم يترك الاسم لتسلسل الدفتر؛ الربط
        بالفاتورة باقٍ في ref.
        """
        name = "ADV/%s" % (invoice.name or invoice.id)
        journal = self._hosny_advance_reclass_journal()
        taken = self.env["account.move"].sudo().search_count(
            [("journal_id", "=", journal.id), ("name", "=", name)], limit=1
        )
        return False if taken else name

    def _hosny_prepare_advance_reclass_move_vals(self, invoice, advance_account, receivable_account, partner, balance):
        self.ensure_one()
        company_currency = self.company_id.currency_id
        amount = company_currency.round(abs(balance))
        label = _("تحويل فاتورة نقاط البيع إلى الدفع الآجل - %s", invoice.name)
        receivable_line_vals = {
            "name": label,
            "account_id": receivable_account.id,
            "partner_id": partner.id,
            "date_maturity": invoice.invoice_date_due or invoice.invoice_date or invoice.date,
        }
        advance_line_vals = {
            "name": label,
            "account_id": advance_account.id,
            "partner_id": partner.id,
        }

        if balance > 0:
            advance_line_vals.update({"debit": amount, "credit": 0.0})
            receivable_line_vals.update({"debit": 0.0, "credit": amount})
        else:
            receivable_line_vals.update({"debit": amount, "credit": 0.0})
            advance_line_vals.update({"debit": 0.0, "credit": amount})

        move_vals = {
            "move_type": "entry",
            "journal_id": self._hosny_advance_reclass_journal().id,
            "date": invoice.invoice_date or invoice.date,
            "ref": self._hosny_advance_reclass_ref(invoice),
            "line_ids": [
                Command.create(advance_line_vals),
                Command.create(receivable_line_vals),
            ],
        }
        name = self._hosny_advance_reclass_name(invoice)
        if name:
            move_vals["name"] = name
        if "analytic_account_id" in self.env["account.move"]._fields and invoice.analytic_account_id:
            move_vals["analytic_account_id"] = invoice.analytic_account_id.id
        return move_vals

    def _hosny_reconcile_advance_invoice_receivable(self, invoice, reclass_move, receivable_account):
        self.ensure_one()
        if not receivable_account.reconcile:
            return

        invoice_lines = invoice.line_ids.filtered(
            lambda line: line.account_id == receivable_account and not line.reconciled
        )
        reclass_lines = reclass_move.line_ids.filtered(
            lambda line: line.account_id == receivable_account and not line.reconciled
        )
        if invoice_lines and reclass_lines:
            (invoice_lines | reclass_lines).sudo().with_company(self.company_id).reconcile()

    def _hosny_reclassify_advance_invoice_receivable(self, invoice=False):
        self.ensure_one()
        invoice = invoice or self.account_move
        advance_payments = self._hosny_advance_account_payments()
        if not invoice or not advance_payments or not self.partner_id:
            return self.env["account.move"]

        existing_move = self.hosny_advance_reclass_move_id
        if existing_move and existing_move.state != "cancel":
            return existing_move

        partner = self.env["res.partner"]._find_accounting_partner(self.partner_id)
        receivable_account = partner.with_company(self.company_id).property_account_receivable_id
        receivable_lines = invoice.line_ids.filtered(
            lambda line: line.account_id == receivable_account and not line.reconciled
        )
        receivable_balance = self.company_id.currency_id.round(sum(receivable_lines.mapped("amount_residual")))
        if not receivable_lines or self.company_id.currency_id.is_zero(receivable_balance):
            return self.env["account.move"]

        ref = self._hosny_advance_reclass_ref(invoice)
        AccountMove = self.env["account.move"].sudo().with_company(self.company_id)
        existing_move = AccountMove.search(
            [
                ("company_id", "=", self.company_id.id),
                ("move_type", "=", "entry"),
                ("ref", "=", ref),
                ("state", "!=", "cancel"),
            ],
            limit=1,
        )
        if existing_move:
            self.sudo().write({"hosny_advance_reclass_move_id": existing_move.id})
            self._hosny_reconcile_advance_invoice_receivable(invoice, existing_move, receivable_account)
            return existing_move

        advance_account = advance_payments[0].payment_method_id.receivable_account_id
        order_currency = self.currency_id
        advance_amount = sum(
            payment.amount
            for payment in advance_payments.filtered(
                lambda payment: payment.payment_method_id.receivable_account_id == advance_account
            )
        )
        advance_amount = order_currency._convert(
            abs(advance_amount),
            self.company_id.currency_id,
            self.company_id,
            fields.Date.context_today(self, self.date_order),
        )
        balance = min(abs(receivable_balance), advance_amount)
        balance = balance if receivable_balance > 0 else -balance
        if self.company_id.currency_id.is_zero(balance):
            return self.env["account.move"]

        reclass_move = AccountMove.create(
            self._hosny_prepare_advance_reclass_move_vals(
                invoice,
                advance_account,
                receivable_account,
                partner,
                balance,
            )
        )
        reclass_move.action_post()
        self.sudo().write({"hosny_advance_reclass_move_id": reclass_move.id})
        self._hosny_reconcile_advance_invoice_receivable(invoice, reclass_move, receivable_account)
        return reclass_move

    def _hosny_coupon_rounding(self, coupon):
        return coupon.currency_id.rounding or 0.01

    def _hosny_lock_existing_coupons(self, coupon_ids):
        coupon_ids = [coupon_id for coupon_id in coupon_ids if coupon_id > 0]
        if not coupon_ids:
            return self.env["loyalty.card"]
        self.env.cr.execute(
            "SELECT id FROM loyalty_card WHERE id IN %s FOR UPDATE",
            [tuple(coupon_ids)],
        )
        return self.env["loyalty.card"].browse(coupon_ids).exists()

    def _hosny_coupon_spend_by_card(self, coupon_ids, coupon_data):
        spend_by_coupon = {}
        coupon_ids = set(coupon_ids)
        for line in self.lines:
            coupon = line.coupon_id
            if coupon.id in coupon_ids and line.points_cost > 0:
                spend_by_coupon[coupon.id] = spend_by_coupon.get(coupon.id, 0.0) + line.points_cost

        for coupon_id in coupon_ids:
            if coupon_id in spend_by_coupon:
                continue
            points_change = coupon_data.get(coupon_id, {}).get("points", 0.0) or 0.0
            if points_change < 0:
                spend_by_coupon[coupon_id] = -points_change
        return spend_by_coupon

    def _hosny_assert_coupon_balances(self, coupons, spend_by_coupon):
        for coupon in coupons:
            spend = spend_by_coupon.get(coupon.id, 0.0)
            if not spend:
                continue
            rounding = self._hosny_coupon_rounding(coupon)
            if float_compare(coupon.points, spend, precision_rounding=rounding) < 0:
                raise UserError(
                    _(
                        "The coupon %(code)s has only %(remaining).2f remaining, "
                        "but this order is trying to use %(used).2f. "
                        "Please reload the POS and apply the coupon again.",
                        code=coupon.code,
                        remaining=coupon.points,
                        used=spend,
                    )
                )

    def _hosny_normalize_coupon_data_from_order(self, coupon_data, spend_by_coupon):
        normalized = {coupon_id: dict(vals) for coupon_id, vals in coupon_data.items()}
        for coupon_id, spent in spend_by_coupon.items():
            if coupon_id not in normalized:
                continue
            earned = normalized[coupon_id].get("points_earned")
            if earned is None:
                earned = max(normalized[coupon_id].get("points", 0.0) or 0.0, 0.0)
            normalized[coupon_id]["points_earned"] = earned
            normalized[coupon_id]["points_spent"] = spent
            normalized[coupon_id]["points"] = earned - spent
        return normalized

    def _hosny_zero_fully_used_coupons(self, coupons):
        for coupon in coupons:
            rounding = self._hosny_coupon_rounding(coupon)
            if float_is_zero(coupon.points, precision_rounding=rounding) or (
                coupon.points < 0
                and float_compare(coupon.points, 0.0, precision_rounding=rounding) >= 0
            ):
                coupon.sudo().points = 0.0

    def _hosny_append_coupon_updates(self, payload, coupons):
        coupon_updates = payload.setdefault("coupon_updates", [])
        updated_coupon_ids = {update.get("id") for update in coupon_updates}
        for coupon in coupons:
            if coupon.id in updated_coupon_ids:
                continue
            coupon_updates.append(
                {
                    "old_id": coupon.id,
                    "id": coupon.id,
                    "points": coupon.points,
                    "code": coupon.code,
                    "program_id": coupon.program_id.id,
                    "partner_id": coupon.partner_id.id,
                }
            )

    def _hosny_reconcile_coupon_history(self, coupons, spend_by_coupon, balance_before):
        for coupon in coupons:
            spend = spend_by_coupon.get(coupon.id, 0.0)
            if not spend:
                continue

            histories = coupon.sudo().history_ids
            current_histories = histories.filtered(
                lambda history: history.order_model == self._name and history.order_id == self.id
            )
            other_histories = histories - current_histories
            issued_total = sum(histories.mapped("issued"))
            other_used = sum(other_histories.mapped("used"))
            original_value = max(issued_total, (balance_before.get(coupon.id) or 0.0) + other_used)
            used = min(spend, max(original_value - other_used, 0.0))
            current_issued = sum(current_histories.mapped("issued"))

            if current_histories:
                current_histories[0].sudo().write({
                    "used": used,
                    "issued": current_issued,
                })
                (current_histories - current_histories[0]).sudo().write({
                    "used": 0.0,
                    "issued": 0.0,
                })
            else:
                self.env["loyalty.history"].sudo().create({
                    "card_id": coupon.id,
                    "order_model": self._name,
                    "order_id": self.id,
                    "description": _("Onsite %s", self.display_name),
                    "used": used,
                    "issued": 0.0,
                })

    def confirm_coupon_programs(self, coupon_data):
        normalized_coupon_data = {int(k): v for k, v in coupon_data.items()}
        existing_coupon_ids = [coupon_id for coupon_id in normalized_coupon_data if coupon_id > 0]
        locked_coupons = self._hosny_lock_existing_coupons(existing_coupon_ids)
        balance_before = {coupon.id: coupon.points for coupon in locked_coupons}
        spend_by_coupon = self._hosny_coupon_spend_by_card(
            locked_coupons.ids, normalized_coupon_data
        )
        self._hosny_assert_coupon_balances(locked_coupons, spend_by_coupon)
        normalized_coupon_data = self._hosny_normalize_coupon_data_from_order(
            normalized_coupon_data, spend_by_coupon
        )

        payload = super().confirm_coupon_programs(normalized_coupon_data)

        spent_coupons = locked_coupons.filtered(lambda coupon: spend_by_coupon.get(coupon.id, 0.0))
        self._hosny_zero_fully_used_coupons(spent_coupons)
        self._hosny_reconcile_coupon_history(spent_coupons, spend_by_coupon, balance_before)
        spent_coupons._hosny_sync_usage_from_pos_orders()
        self._hosny_append_coupon_updates(payload, spent_coupons)
        return payload
