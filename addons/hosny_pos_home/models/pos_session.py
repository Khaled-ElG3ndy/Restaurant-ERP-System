from collections import defaultdict
from datetime import datetime, time, timedelta

import pytz

from odoo import models

DONE_STATES = ("paid", "done", "invoiced")


class PosSession(models.Model):
    _inherit = "pos.session"

    def hosny_home_summary(self):
        """أرقام الشاشة الرئيسية — قراءة فقط، لنقطة بيع هذه الجلسة."""
        self.ensure_one()
        self.check_access("read")
        session = self.sudo()
        config = session.config_id
        tz = pytz.timezone(self.env.user.tz or "Asia/Riyadh")
        now = datetime.now(tz)
        day_start = tz.localize(datetime.combine(now.date(), time.min))

        def utc(dt):
            return dt.astimezone(pytz.utc).replace(tzinfo=None)

        Order = self.env["pos.order"].sudo()
        base = [("config_id", "=", config.id), ("state", "in", DONE_STATES)]
        today = Order.search(base + [("date_order", ">=", utc(day_start))], order="date_order desc")
        yesterday = Order.search(base + [
            ("date_order", ">=", utc(day_start - timedelta(days=1))),
            ("date_order", "<=", utc(now - timedelta(days=1))),
        ])
        in_session = Order.search(base + [("session_id", "=", session.id)])

        hourly = [0.0] * 24
        for order in today:
            hourly[pytz.utc.localize(order.date_order).astimezone(tz).hour] += order.amount_total

        payments = defaultdict(float)
        for payment in today.payment_ids:
            payments[payment.payment_method_id.name] += payment.amount

        products = defaultdict(lambda: [0.0, 0.0])
        for line in today.lines:
            entry = products[line.product_id.display_name]
            entry[0] += line.qty
            entry[1] += line.price_subtotal_incl
        top = sorted(products.items(), key=lambda kv: kv[1][1], reverse=True)[:5]

        def place(order):
            if order.table_id:
                return "طاولة %s" % order.table_id.table_number
            return "سفري"

        start = session.start_at and pytz.utc.localize(session.start_at).astimezone(tz)
        return {
            "today_total": sum(today.mapped("amount_total")),
            "today_count": len(today),
            "yesterday_total": sum(yesterday.mapped("amount_total")),
            "session_total": sum(in_session.mapped("amount_total")),
            "session_count": len(in_session),
            "session_name": session.name,
            "session_start": start and start.strftime("%Y-%m-%d %H:%M:%S"),
            "session_user": session.user_id.name,
            "hourly": hourly,
            "current_hour": now.hour,
            "payments": sorted(
                ({"name": k, "amount": v} for k, v in payments.items()),
                key=lambda p: p["amount"], reverse=True,
            ),
            "top_products": [{"name": k, "qty": v[0], "amount": v[1]} for k, v in top],
            "last_orders": [{
                "ref": o.tracking_number or o.pos_reference or o.name,
                "time": pytz.utc.localize(o.date_order).astimezone(tz).strftime("%H:%M"),
                "ts": pytz.utc.localize(o.date_order).timestamp(),
                "amount": o.amount_total,
                "place": place(o),
                "invoiced": o.state == "invoiced" or bool(o.account_move),
            } for o in today[:6]],
        }

    def hosny_shift_report(self):
        """تقرير الوردية (2026-10-07): كل الأرقام لهذه الوردية فقط.

        الطلبات هي نفسها التي يعدّها «إغلاق الوردية» (_get_closed_orders)،
        والنقد المتوقع بنفس معادلته (الافتتاح + نقدي الطلبات + الإيداع/السحب)،
        فيتطابق التقرير مع نافذة الإغلاق. «اليوم» يبقى رقماً جانبياً: الوردية
        قد تمتد لأكثر من يوم.
        """
        self.ensure_one()
        self.check_access("read")
        session = self.sudo()
        config = session.config_id
        currency = config.currency_id
        tz = pytz.timezone(self.env.user.tz or "Asia/Riyadh")
        now = datetime.now(tz)
        day_start = tz.localize(datetime.combine(now.date(), time.min))

        orders = session._get_closed_orders()
        sales = orders.filtered(lambda o: o.amount_total >= 0)
        refunds = orders - sales
        open_orders = session.order_ids.filtered(lambda o: o.state == "draft")

        # طرق الدفع: كل الدفعات (الآجل معها) — عدد الطلبات والمبلغ
        methods = {}
        for payment in orders.payment_ids:
            method = payment.payment_method_id
            row = methods.setdefault(method.id, {
                "name": method.name, "type": method.type, "amount": 0.0, "orders": set(),
            })
            row["amount"] += payment.amount
            row["orders"].add(payment.pos_order_id.id)
        payments = sorted((
            {"name": r["name"], "type": r["type"], "amount": r["amount"], "count": len(r["orders"])}
            for r in methods.values()
        ), key=lambda r: r["amount"], reverse=True)

        # الأصناف: بلا مكوّنات الكومبو (سعرها على الكومبو) ولا الرسوم ولا البقشيش
        fee_codes = {"HOSNY_FEE_SERVICE", "HOSNY_FEE_DELIVERY", "HOSNY_FEE_DRIVER"}
        tip_product = config.tip_product_id
        products = defaultdict(lambda: [0.0, 0.0])
        fees_total = 0.0
        discount_total = 0.0
        for line in orders.lines:
            if line.discount and line.price_unit:
                base = line.price_unit * line.qty * line.discount / 100.0
                taxes = line.tax_ids_after_fiscal_position.compute_all(
                    base, currency=line.order_id.currency_id or currency, quantity=1.0,
                    product=line.product_id, partner=line.order_id.partner_id,
                )
                discount_total += taxes["total_included"]
            if line.product_id.default_code in fee_codes:
                fees_total += line.price_subtotal_incl
                continue
            if line.combo_parent_id or (tip_product and line.product_id == tip_product):
                continue
            entry = products[line.product_id.display_name]
            entry[0] += line.qty
            entry[1] += line.price_subtotal_incl
        top = sorted(products.items(), key=lambda kv: kv[1][1], reverse=True)[:8]

        # النقد في الدرج — نفس default_cash_details في get_closing_control_data
        cash = {}
        cash_method = session.payment_method_ids.filtered(lambda pm: pm.type == "cash")[:1]
        if cash_method:
            cash_payments = orders.payment_ids.filtered(lambda p: p.payment_method_id == cash_method)
            moves = sum(session.statement_line_ids.mapped("amount"))
            paid = sum(cash_payments.mapped("amount"))
            cash = {
                "name": cash_method.name,
                "opening": session.cash_register_balance_start,
                "payments": paid,
                "moves": moves,
                "expected": session.cash_register_balance_start + paid + moves,
            }

        Order = self.env["pos.order"].sudo()
        today = Order.search([
            ("config_id", "=", config.id), ("state", "in", DONE_STATES),
            ("date_order", ">=", day_start.astimezone(pytz.utc).replace(tzinfo=None)),
        ])

        start = session.start_at and pytz.utc.localize(session.start_at).astimezone(tz)
        minutes = int((now - start).total_seconds() // 60) if start else 0
        total = sum(orders.mapped("amount_total"))
        return {
            "session_name": session.name,
            "session_user": session.user_id.name,
            "session_start": start and start.strftime("%d/%m/%Y %H:%M"),
            "duration": "%d:%02d" % (minutes // 60, minutes % 60),
            "printed_at": now.strftime("%d/%m/%Y %H:%M"),
            "total": total,
            "count": len(orders),
            "sales_total": sum(sales.mapped("amount_total")),
            "sales_count": len(sales),
            "average": (sum(sales.mapped("amount_total")) / len(sales)) if sales else 0.0,
            "refund_total": -sum(refunds.mapped("amount_total")),
            "refund_count": len(refunds),
            "discount_total": discount_total,
            "fees_total": fees_total,
            "open_count": len(open_orders),
            "open_total": sum(open_orders.mapped("amount_total")),
            "payments": payments,
            "payments_total": sum(r["amount"] for r in payments),
            "top_products": [{"name": k, "qty": v[0], "amount": v[1]} for k, v in top],
            "cash": cash,
            "today_total": sum(today.mapped("amount_total")),
            "today_count": len(today),
        }
