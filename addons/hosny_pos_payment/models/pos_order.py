from odoo import api, fields, models

PAID_STATES = ("paid", "done", "invoiced")
LIST_LIMIT = 1000


class PosOrder(models.Model):
    _inherit = "pos.order"

    @api.model
    def hosny_invoice_list(self, config_id, filters=None):
        """فواتير شاشة «تسديد الفواتير» لنقطة البيع هذه، بفلاتر FERP.

        filters: date_from / date_to (UTC «YYYY-MM-DD HH:MM:SS»)، order_type_id،
        number (رقم الفاتورة أو المرجع)، status (all / paid / open / pay_later /
        refund)، table_id. يعيد الأسطر وأنواع الفواتير والطاولات للفلاتر.
        """
        filters = filters or {}
        config = self.env["pos.config"].browse(config_id)
        config.check_access("read")
        has_type = "order_type_id" in self._fields
        has_session_number = "hosny_session_number" in self._fields

        domain = [("config_id", "=", config.id)]
        if filters.get("date_from"):
            domain.append(("date_order", ">=", filters["date_from"]))
        if filters.get("date_to"):
            domain.append(("date_order", "<=", filters["date_to"]))
        if has_type and filters.get("order_type_id"):
            domain.append(("order_type_id", "=", int(filters["order_type_id"])))
        if filters.get("table_id"):
            domain.append(("table_id", "=", int(filters["table_id"])))
        number = (filters.get("number") or "").strip()
        if number:
            number_domain = [
                "|", "|",
                ("tracking_number", "ilike", number),
                ("pos_reference", "ilike", number),
                ("name", "ilike", number),
            ]
            if has_session_number and number.isdigit():
                number_domain = ["|", ("hosny_session_number", "=", int(number))] + number_domain
            domain += number_domain
        status = filters.get("status") or "all"
        if status == "paid":
            domain.append(("state", "in", PAID_STATES))
        elif status == "open":
            domain.append(("state", "=", "draft"))
        elif status == "pay_later":
            domain += [("state", "in", PAID_STATES), ("payment_ids.payment_method_id.type", "=", "pay_later")]
        elif status == "refund":
            domain.append(("is_refund", "=", True))

        total_count = self.search_count(domain)
        orders = self.search(domain, order="date_order desc, id desc", limit=LIST_LIMIT)

        rows = []
        for order in orders:
            pay_later = any(p.payment_method_id.type == "pay_later" for p in order.payment_ids)
            if order.is_refund:
                status_key = "refund"
            elif order.state == "draft":
                status_key = "open"
            elif order.state == "cancel":
                status_key = "cancel"
            elif pay_later:
                status_key = "pay_later"
            else:
                status_key = "paid"
            partner = order.partner_id
            rows.append({
                "id": order.id,
                "uuid": order.uuid,
                "date": fields.Datetime.to_string(order.date_order),
                "number": str(
                    (has_session_number and order.hosny_session_number)
                    or order.tracking_number or order.pos_reference or order.name
                ),
                "reference": order.pos_reference or order.name,
                "type": has_type and order.order_type_id.name or "",
                "table": order.table_id and str(order.table_id.table_number) or "",
                "status": status_key,
                "amount": order.amount_total,
                "refunded": bool(order.refund_orders_count),
                "partner": partner.name or "",
                "phone": partner.phone or getattr(partner, "mobile", "") or "",
                "prints": order.nb_print,
            })

        tables = self.env["restaurant.table"].search(
            [("floor_id", "in", config.floor_ids.ids)], order="table_number"
        )
        return {
            "rows": rows,
            "total_count": total_count,
            "limit": LIST_LIMIT,
            "types": [
                {"id": t.id, "name": t.name}
                for t in (self.env["pos.order.type"].search([]) if has_type else [])
            ],
            "tables": [
                {"id": t.id, "name": "%s · %s" % (t.floor_id.name, t.table_number)}
                for t in tables
            ],
        }
