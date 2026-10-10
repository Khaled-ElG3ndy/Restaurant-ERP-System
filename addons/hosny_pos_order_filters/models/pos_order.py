from datetime import timedelta

from odoo import api, fields, models
from odoo.fields import Domain


class PosOrder(models.Model):
    _inherit = "pos.order"

    @api.model
    def _hosny_filter_config_ids(self, config_id):
        config = self.env["pos.config"].browse(int(config_id)).exists()
        return [config.id] + config.trusted_config_ids.ids if config else []

    @api.model
    def hosny_order_filter_options(self, config_id):
        """خيارات فلاتر شاشة «الطلبات»: الورديات، طرق الدفع، أنواع الطلب، والموظفون."""
        config_ids = self._hosny_filter_config_ids(config_id)
        config = self.env["pos.config"].browse(int(config_id))
        sessions = self.env["pos.session"].search(
            [("config_id", "in", config_ids)], order="id desc", limit=60
        )
        recent = [
            ("config_id", "in", config_ids),
            ("date_order", ">=", fields.Datetime.now() - timedelta(days=120)),
        ]
        users = [
            {"id": user.id, "name": user.name}
            for user, in self._read_group(recent + [("user_id", "!=", False)], ["user_id"])
        ]
        types = [
            {"id": order_type.id, "name": order_type.name}
            for order_type, in self._read_group(recent + [("order_type_id", "!=", False)], ["order_type_id"])
        ]
        return {
            "sessions": [
                {
                    "id": session.id,
                    "name": session.name,
                    "start_at": fields.Datetime.to_string(session.start_at) if session.start_at else False,
                    "opened": session.state == "opened",
                }
                for session in sessions
            ],
            "payment_methods": [{"id": m.id, "name": m.name} for m in config.payment_method_ids],
            "order_types": sorted(types, key=lambda t: t["id"]),
            "users": sorted(users, key=lambda u: u["name"]),
        }

    @api.model
    def hosny_order_summary(self, config_id, domain):
        """عدد وإجمالي الطلبات المدفوعة المطابقة للفلاتر، وإجمالي كل طريقة دفع.

        نفس شرط search_paid_order_ids (لا مسودة ولا ملغي، نقطة البيع نفسها).
        """
        config_ids = self._hosny_filter_config_ids(config_id)
        real_domain = (
            Domain(domain or [])
            & Domain("state", "not in", ("draft", "cancel"))
            & Domain("config_id", "in", config_ids)
        )
        [(count, total)] = self._read_group(real_domain, [], ["__count", "amount_total:sum"])
        methods = self.env["pos.payment"]._read_group(
            [("pos_order_id", "in", self._search(real_domain))],
            ["payment_method_id"],
            ["amount:sum"],
        )
        return {
            "count": count,
            "total": total or 0.0,
            "methods": [
                {"id": method.id, "name": method.name, "amount": amount}
                for method, amount in methods
                if method
            ],
        }
