from collections import defaultdict

from odoo import _, fields, models
from odoo.exceptions import AccessError

# طرق الدفع التي يكتب الكاشير مبلغها عند الإغلاق (النقدي له حقل العدّ الخاص به)
COUNTED_TYPES = ("bank", "pay_later")


class HosnyShiftMethodLine(models.Model):
    """سطر لكل طريقة دفع في تقرير إغلاق الوردية: المتوقع والمكتوب والفرق."""

    _name = "hosny.shift.method.line"
    _description = "تقرير الوردية — طريقة دفع"
    _order = "session_id desc, sequence, id"

    session_id = fields.Many2one("pos.session", required=True, ondelete="cascade", index=True)
    config_id = fields.Many2one(related="session_id.config_id", store=True, string="الفرع")
    stop_at = fields.Datetime(related="session_id.stop_at", store=True, string="الإغلاق")
    sequence = fields.Integer()
    payment_method_id = fields.Many2one("pos.payment.method", string="طريقة الدفع", required=True)
    method_type = fields.Selection(related="payment_method_id.type", store=True, string="النوع")
    currency_id = fields.Many2one(related="session_id.currency_id")
    payment_count = fields.Integer(string="عدد الدفعات")
    expected = fields.Monetary(string="المتوقع")
    counted = fields.Monetary(string="المكتوب عند الإغلاق")
    has_count = fields.Boolean(string="كُتب مبلغ")
    difference = fields.Monetary(string="الفرق")


class PosSession(models.Model):
    _inherit = "pos.session"

    hosny_close_counts = fields.Json(copy=False)
    hosny_cash_counted = fields.Monetary(string="النقدية المعدودة", copy=False, readonly=True)
    hosny_handover_amount = fields.Monetary(string="المسلَّم لخزنة الفرع", copy=False, readonly=True)
    hosny_handover_line_id = fields.Many2one(
        "account.bank.statement.line", string="قيد التسليم للخزنة", copy=False, readonly=True
    )
    hosny_order_count = fields.Integer(string="عدد الطلبات", copy=False, readonly=True)
    hosny_sales_total = fields.Monetary(string="إجمالي المبيعات", copy=False, readonly=True)
    hosny_refund_total = fields.Monetary(string="المرتجعات", copy=False, readonly=True)
    hosny_refund_count = fields.Integer(string="عدد المرتجعات", copy=False, readonly=True)
    hosny_discount_total = fields.Monetary(string="الخصومات", copy=False, readonly=True)
    hosny_hospitality_total = fields.Monetary(string="الضيافة", copy=False, readonly=True)
    hosny_hospitality_count = fields.Integer(string="أصناف الضيافة", copy=False, readonly=True)
    hosny_coupon_total = fields.Monetary(string="كوبونات الخصم", copy=False, readonly=True)
    hosny_coupon_count = fields.Integer(string="طلبات بكوبون", copy=False, readonly=True)
    hosny_giftcard_total = fields.Monetary(string="بطاقات الهدايا المستخدمة", copy=False, readonly=True)
    hosny_giftcard_count = fields.Integer(string="عدد استخدامات البطاقات", copy=False, readonly=True)
    hosny_void_total = fields.Monetary(string="إلغاءات بعد الإرسال", copy=False, readonly=True)
    hosny_void_count = fields.Integer(string="عدد الإلغاءات", copy=False, readonly=True)
    hosny_cash_difference = fields.Monetary(string="فرق النقدية", copy=False, readonly=True)
    hosny_paylater_expected = fields.Monetary(string="الأجل (النظام)", copy=False, readonly=True)
    hosny_paylater_counted = fields.Monetary(string="الأجل (المكتوب)", copy=False, readonly=True)
    hosny_paylater_difference = fields.Monetary(string="فرق الأجل", copy=False, readonly=True)
    hosny_method_line_ids = fields.One2many(
        "hosny.shift.method.line", "session_id", string="طرق الدفع", readonly=True
    )

    # ── كل وردية تبدأ من صفر ─────────────────────────────────────────────
    def action_pos_session_open(self):
        result = super().action_pos_session_open()
        for session in self:
            if session.state == "opening_control" and session.config_id.hosny_safe_account_id and not session.rescue:
                session.cash_register_balance_start = 0.0
        return result

    # ── من نافذة الإغلاق ─────────────────────────────────────────────────
    def _hosny_check_pos_user(self):
        if not self.env.user.has_group("point_of_sale.group_pos_user"):
            raise AccessError(_("ليس لديك صلاحية على ورديات نقطة البيع."))
        self.check_access("read")

    def hosny_save_close_counts(self, counts):
        """ما كتبه الكاشير في نافذة الإغلاق: {"cash": n, "methods": {method_id: n}}."""
        self.ensure_one()
        self._hosny_check_pos_user()
        if self.state == "closed":
            return False
        clean = {"cash": None, "methods": {}}
        try:
            if counts.get("cash") is not None:
                clean["cash"] = float(counts["cash"])
            for method_id, value in (counts.get("methods") or {}).items():
                if value is not None and value != "":
                    clean["methods"][str(int(method_id))] = float(value)
        except (TypeError, ValueError):
            return False
        self.sudo().hosny_close_counts = clean
        return True

    def hosny_shift_close_summary(self):
        """ملخص نافذة الإغلاق: الخصومات والضيافة وبطاقات الهدايا والمرتجعات والإلغاءات."""
        self.ensure_one()
        self._hosny_check_pos_user()
        data = self.sudo()._hosny_extras()
        data["safe_account"] = self.config_id.hosny_safe_account_id.display_name or False
        return data

    # ── الحسابات ─────────────────────────────────────────────────────────
    def _hosny_line_discount(self, line):
        """قيمة خصم السطر شاملة الضريبة (نفس حساب تقرير الوردية)."""
        if not (line.discount and line.price_unit):
            return 0.0
        base = line.price_unit * line.qty * line.discount / 100.0
        taxes = line.tax_ids_after_fiscal_position.compute_all(
            base,
            currency=line.order_id.currency_id or self.currency_id,
            quantity=1.0,
            product=line.product_id,
            partner=line.order_id.partner_id,
        )
        return taxes["total_included"]

    def _hosny_extras(self):
        self.ensure_one()
        orders = self._get_closed_orders()
        sales = orders.filtered(lambda o: o.amount_total >= 0)
        refunds = orders - sales
        discount_product = self.config_id.discount_product_id

        discount_total = coupon_total = giftcard_total = hospitality_total = 0.0
        giftcard_count = hospitality_count = 0
        coupon_orders = set()
        for line in orders.lines:
            if line.is_hospitality:
                hospitality_count += 1
                hospitality_total += (line.hospitality_original_price or 0.0) * line.qty
                continue
            program_type = line.reward_id.program_id.program_type if line.is_reward_line else False
            if program_type == "ewallet":
                continue  # المحفظة دفع لا خصم
            if program_type:
                # كوبونات الخصم: كوبونات حسني المدفوعة (برنامج الرصيد / gift_card — تُصدر من المبيعات)
                # وأي برنامج خصم آخر (كود، عرض) — منفصلة عن الخصم اليدوي
                coupon_total += -line.price_subtotal_incl
                coupon_orders.add(line.order_id.id)
                if program_type == "gift_card":
                    giftcard_count += 1
                    giftcard_total += -line.price_subtotal_incl
                continue
            if discount_product and line.product_id == discount_product:
                discount_total += -line.price_subtotal_incl
                continue
            discount_total += self._hosny_line_discount(line)

        voids = self.env["pos.audit.log"].search([("pos_session_id", "=", self.id), ("action", "=", "void_line")])
        round_ = self.currency_id.round
        return {
            "order_count": len(orders),
            "sales_total": round_(sum(sales.mapped("amount_total"))),
            "refund_total": round_(-sum(refunds.mapped("amount_total"))),
            "refund_count": len(refunds),
            "discount_total": round_(discount_total),
            "hospitality_total": round_(hospitality_total),
            "hospitality_count": hospitality_count,
            "coupon_total": round_(coupon_total),
            "coupon_count": len(coupon_orders),
            "giftcard_total": round_(giftcard_total),
            "giftcard_count": giftcard_count,
            "void_total": round_(sum(voids.mapped("amount"))),
            "void_count": len(voids),
        }

    def _hosny_cash_moves(self):
        """الإيداع / السحب في الوردية + تسويات pos_multi_payment_reconciliation — كما في نافذة الإغلاق."""
        self.ensure_one()
        moves = sum((self.statement_line_ids - self.hosny_handover_line_id).mapped("amount"))
        cash_method = self.payment_method_ids.filtered(lambda pm: pm.type == "cash")[:1]
        adjustments = self._get_multi_cash_in_out_move_adjustments() if cash_method else {}
        return moves + adjustments.get(cash_method.id, 0.0)

    def _hosny_method_rows(self, cash_moves):
        """المتوقع لكل طريقة دفع؛ النقدي = الافتتاح + نقدي الطلبات + الحركات (قبل فرق العدّ)."""
        self.ensure_one()
        totals = defaultdict(float)
        counts = defaultdict(int)
        for payment in self._get_closed_orders().payment_ids:
            totals[payment.payment_method_id] += payment.amount
            counts[payment.payment_method_id] += 1
        rows = []
        for sequence, method in enumerate(self.payment_method_ids.sorted(lambda m: (m.type != "cash", m.id))):
            expected = totals.get(method, 0.0)
            if method.type == "cash":
                expected = self.cash_register_balance_start + expected + cash_moves
            rows.append({
                "sequence": sequence,
                "method": method,
                "expected": self.currency_id.round(expected),
                "count": counts.get(method, 0),
            })
        return rows

    def _hosny_snapshot(self, cash_moves):
        """تقرير الإغلاق محفوظاً على الوردية — للمقارنة بين الورديات لاحقاً."""
        self.ensure_one()
        counts = self.hosny_close_counts or {}
        written = counts.get("methods") or {}
        cash_counted = self.hosny_cash_counted
        lines = [(5, 0, 0)]
        snapshot = {}
        for row in self._hosny_method_rows(cash_moves):
            method = row["method"]
            if method.type == "cash":
                counted, has_count = cash_counted, True
            elif str(method.id) in written:
                counted, has_count = written[str(method.id)], True
            else:
                counted, has_count = 0.0, False
            difference = self.currency_id.round(counted - row["expected"]) if has_count else 0.0
            lines.append((0, 0, {
                "sequence": row["sequence"],
                "payment_method_id": method.id,
                "payment_count": row["count"],
                "expected": row["expected"],
                "counted": counted,
                "has_count": has_count,
                "difference": difference,
            }))
            if method.type == "cash":
                snapshot["hosny_cash_difference"] = difference
            if method.type == "pay_later":
                snapshot["hosny_paylater_expected"] = snapshot.get("hosny_paylater_expected", 0.0) + row["expected"]
                snapshot["hosny_paylater_counted"] = snapshot.get("hosny_paylater_counted", 0.0) + counted
                snapshot["hosny_paylater_difference"] = snapshot.get("hosny_paylater_difference", 0.0) + difference
        extras = self._hosny_extras()
        snapshot.update({f"hosny_{key}": value for key, value in extras.items()})
        snapshot["hosny_method_line_ids"] = lines
        self.write(snapshot)

    # ── الإغلاق: تسليم النقدية للخزنة ثم حفظ التقرير ─────────────────────
    def _validate_session(self, balancing_account=False, amount_to_balance=0, bank_payment_method_diffs=None):
        counted = self.cash_register_balance_end_real
        # قبل الإغلاق: أودو يضيف بعده سطر فرق العدّ إلى حركات الصندوق
        cash_moves = self.sudo()._hosny_cash_moves()
        result = super()._validate_session(balancing_account, amount_to_balance, bank_payment_method_diffs)
        if result is True and self.state == "closed":
            session = self.sudo()
            session.hosny_cash_counted = counted
            session._hosny_handover(counted)
            session._hosny_snapshot(cash_moves)
        return result

    def _hosny_handover(self, counted):
        """النقدية المعدودة كلها من صندوق نقطة البيع إلى خزنة الفرع (مرة واحدة لكل وردية).

        بعده رصيد الصندوق في الدفاتر = صفر، فتبدأ الوردية التالية من صفر بلا فرق.
        فرق العدّ (زيادة / عجز) يسجله أودو قبل ذلك كالمعتاد.
        """
        self.ensure_one()
        safe = self.config_id.hosny_safe_account_id
        if not safe or not self.cash_journal_id or self.hosny_handover_line_id:
            return
        amount = self.currency_id.round(counted or 0.0)
        if self.currency_id.is_zero(amount) or amount < 0:
            return
        line = self.env["account.bank.statement.line"].with_context(no_retrieve_partner=True).create({
            "journal_id": self.cash_journal_id.id,
            "amount": -amount,
            "date": fields.Date.context_today(self),
            "payment_ref": _("%s - تسليم نقدية الوردية لخزنة الفرع", self.name),
            "counterpart_account_id": safe.id,
        })
        self.write({"hosny_handover_line_id": line.id, "hosny_handover_amount": amount})
        line.move_id.message_post(body=_("تسليم نقدية الوردية: %s", self._get_html_link()))
        self.message_post(body=_(
            "سُلِّم %(amount)s من الصندوق إلى %(safe)s — الوردية التالية تبدأ من صفر.",
            amount=self.currency_id.format(amount),
            safe=safe.display_name,
        ))

    def _get_related_account_moves(self):
        return super()._get_related_account_moves() | self.hosny_handover_line_id.move_id

