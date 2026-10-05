# -*- coding: utf-8 -*-
from odoo import api, fields, models


class PosOrder(models.Model):
    _inherit = "pos.order"

    order_type_id = fields.Many2one(
        "pos.order.type", string="نوع الفاتورة",
        default=lambda self: self.env["pos.order.type"].search(
            [("is_default", "=", True)], limit=1))

    # رقم الطلب داخل الوردية: 1، 2، 3… ويبدأ من جديد مع كل جلسة. هو ما يُطبع
    # في «رقم الفاتورة» على تذكرة المطبخ بدل tracking_number (46009).
    # الخادم وحده يعطيه (عدّاد ذرّي على الجلسة) لأن أكثر من جهاز يعمل على
    # نفس الوردية، فلا يصح أن يحسبه كل جهاز لنفسه.
    hosny_session_number = fields.Integer(
        "رقم الطلب في الوردية", copy=False, readonly=True,
        help="يبدأ من 1 في كل وردية ويُطبع في «رقم الفاتورة» على تذكرة المطبخ.")

    # ملاحظة: لا نضيف _load_pos_data_fields هنا عن قصد.
    # pos.order لا تعرّف قائمة حقول، والـ mixin يرجع [] ومعناها في
    # read([]) هو «كل الحقول». أي تعديل للقائمة يحوّلها إلى قائمة محدودة
    # فتختفي حقول تعتمد عليها موديلات أخرى (res.partner تقرأ partner_id
    # من صفوف pos.order) ويسقط تحميل نقاط البيع بالكامل.
    # الحقول الجديدة تُحمَّل تلقائياً مع بقية الحقول، وكذلك علاقاتها.

    @api.model_create_multi
    def create(self, vals_list):
        # الشاشة ترسل كل الحقول المخزّنة ومنها هذا (false لطلب جديد)، والرقم
        # ملك الخادم فقط، فنتجاهل ما يأتي منها.
        for vals in vals_list:
            vals.pop("hosny_session_number", None)
            self._hosny_prepare_type_and_table(vals)
        orders = super().create(vals_list)
        orders._hosny_assign_session_number()
        orders._hosny_refund_takes_refunded_type()
        return orders

    def write(self, vals):
        vals = dict(vals)
        vals.pop("hosny_session_number", None)
        # نقطة بيع لم يُعَد تحميلها بعد التحديث ترسل order_type_id = false لأنها
        # لا تعرف النوع؛ لا نسمح لها بمسح نوع مسجّل.
        stale_type = "order_type_id" in vals and not vals["order_type_id"]
        if stale_type:
            del vals["order_type_id"]
        if vals.get("order_type_id"):
            self._hosny_prepare_type_and_table(vals)
        elif vals.get("table_id"):
            takeaway = self.filtered(
                lambda o: o.order_type_id and not o.order_type_id._hosny_requires_table())
            if takeaway:
                if stale_type:
                    # الشاشة القديمة ما زالت تظنه على طاولة: النوع المسجّل يبقى
                    # والسفري لا طاولة له.
                    extra = {"table_id": False}
                else:
                    # طاولة بدون تحديد النوع (من خارج الشاشة): الطاولة تجعله محلياً.
                    local = self.env["pos.order.type"]._hosny_local_type(takeaway.company_id[:1])
                    extra = {"order_type_id": local.id}
                others = self - takeaway
                res = others._hosny_write(vals) if others else True
                takeaway._hosny_write(dict(vals, **extra))
                return res
        return self._hosny_write(vals)

    def _hosny_write(self, vals):
        moved = self.browse()
        if vals.get("session_id"):
            moved = self.filtered(lambda o: o.session_id.id != vals["session_id"])
        res = super().write(vals)
        if moved:
            # طلب مفتوح انتقل لوردية جديدة يأخذ رقماً منها حتى لا يتكرر رقم فيها.
            moved._hosny_assign_session_number(force=True)
        return res

    @api.model
    def _hosny_prepare_type_and_table(self, vals):
        """نوع الطلب هو المرجع، والطاولة تتبعه (يُعدّل vals في مكانه).

        - نوع بلا طاولة (سفري / توصيل): table_id = False دائماً، مهما أُرسل.
        - طلب جديد بلا نوع: على طاولة ← محلي، وبدون طاولة ← سفري. لا نعتبر
          طلباً بلا طاولة «محلياً» أبداً. (الشاشة بعد التحديث ترسل النوع دائماً؛
          هذا لنقاط البيع التي لم يُعَد تحميلها ولأي إنشاء من خارج الشاشة.)
        """
        OrderType = self.env["pos.order.type"]
        company = self.env["res.company"].browse(vals.get("company_id")) or self.env.company
        if vals.get("order_type_id"):
            order_type = OrderType.browse(vals["order_type_id"])
        else:
            order_type = (OrderType._hosny_local_type(company) if vals.get("table_id")
                          else OrderType._hosny_takeaway_type(company))
            if order_type:
                vals["order_type_id"] = order_type.id
        if order_type and not order_type._hosny_requires_table():
            vals["table_id"] = False
        return vals

    def _hosny_refund_takes_refunded_type(self):
        """المرتجع يأخذ نوع الطلب الأصلي (مرتجع سفري يبقى سفري في التقارير)."""
        for order in self.filtered("is_refund"):
            refunded_type = order.refunded_order_id.order_type_id
            if refunded_type and refunded_type != order.order_type_id:
                super(PosOrder, order).write({"order_type_id": refunded_type.id})

    def _hosny_assign_session_number(self, force=False):
        for order in self.sorted("id"):
            if not order.session_id or (order.hosny_session_number and not force):
                continue
            number = order.session_id._hosny_next_order_number()
            self.env.cr.execute(
                "UPDATE pos_order SET hosny_session_number = %s WHERE id = %s",
                [number, order.id])
        self.invalidate_recordset(["hosny_session_number"])
