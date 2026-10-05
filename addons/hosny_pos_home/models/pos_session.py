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
                "amount": o.amount_total,
                "place": place(o),
            } for o in today[:5]],
        }
