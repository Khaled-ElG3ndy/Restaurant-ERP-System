# -*- coding: utf-8 -*-
from odoo import api, fields, models


class PosSession(models.Model):
    _inherit = "pos.session"

    hosny_order_counter = fields.Integer(
        "آخر رقم طلب في الوردية", default=0, copy=False, readonly=True)

    @api.model
    def _load_pos_data_models(self, config):
        data = super()._load_pos_data_models(config)
        return data + ["pos.order.type", "pos.printer.line"]

    def _hosny_next_order_number(self):
        """الرقم التالي في هذه الوردية، بزيادة ذرّية في قاعدة البيانات.

        UPDATE … RETURNING يقفل صف الجلسة حتى نهاية المعاملة: جهازان ينشئان
        طلبين في نفس اللحظة لا يأخذان نفس الرقم — الثاني ينتظر، ولو تعارض
        (serialization failure) يعيد أودو الطلب من أوله تلقائياً.
        """
        self.ensure_one()
        self.env.cr.execute(
            "UPDATE pos_session "
            "SET hosny_order_counter = COALESCE(hosny_order_counter, 0) + 1 "
            "WHERE id = %s RETURNING hosny_order_counter", [self.id])
        number = self.env.cr.fetchone()[0]
        self.invalidate_recordset(["hosny_order_counter"])
        return number
