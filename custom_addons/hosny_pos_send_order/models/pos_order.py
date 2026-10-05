from odoo import api, fields, models


class PosOrder(models.Model):
    _inherit = "pos.order"

    # الحقلان يُحمَّلان إلى نقطة البيع تلقائياً: pos.order لا تعرّف
    # _load_pos_data_fields، والقائمة الفارغة تعني كل الحقول. لا تُعرَّف هنا
    # ولا تُوسَّع — توسيعها يوقف نقطة البيع بالكامل.
    preparation_state = fields.Selection(
        [("draft", "Draft"), ("sent", "Sent")],
        string="Preparation State",
        default="draft",
        required=True,
        copy=False,
        readonly=True,
        index=True,
    )
    preparation_sent_at = fields.Datetime(
        string="First Sent At",
        copy=False,
        readonly=True,
        index=True,
    )

    @staticmethod
    def _default_preparation_state(vals):
        """نقطة البيع ترسل الحقل بقيمة فارغة للطلب الجديد.

        النموذج العلائقي في أودو 19 يُسلسل كل حقل مخزَّن، وحقل لم تُضبط له قيمة
        في العميل يصل كـ `false`. القيمة الصريحة الفارغة **تتجاوز** `default`
        الحقل، فتصطدم بقيد not-null وترجع 500 على أول مزامنة لكل طلب جديد.
        فنضبط الافتراضي هنا صراحةً.
        """
        if not vals.get("preparation_state"):
            vals["preparation_state"] = "draft"
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._default_preparation_state(vals)
        return super().create(vals_list)

    @api.model
    def _process_order(self, order, existing_order):
        """يمنع جهازاً يحمل نسخة قديمة من الطلب من مسح ختم الإرسال.

        الحالة والوقت يصلان من نقطة البيع مع باقي الحقول، لكن جهازاً ثانياً
        على نفس الطاولة قد يزامن نسخة سابقة للإرسال. القاعدة: ما أُرسل يبقى
        مُرسَلاً، وأول وقت إرسال هو الذي يُعتمد.
        """
        self._default_preparation_state(order)
        previous_state = existing_order.preparation_state if existing_order else False
        previous_sent_at = existing_order.preparation_sent_at if existing_order else False

        order_id = super()._process_order(order, existing_order)
        pos_order = self.browse(order_id)

        vals = {}
        if previous_state == "sent" and pos_order.preparation_state != "sent":
            vals["preparation_state"] = "sent"
        if previous_sent_at and (
            not pos_order.preparation_sent_at
            or pos_order.preparation_sent_at > previous_sent_at
        ):
            vals["preparation_sent_at"] = previous_sent_at
        if vals:
            pos_order.write(vals)

        return order_id
