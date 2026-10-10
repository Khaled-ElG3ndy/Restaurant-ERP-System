from odoo import api, fields, models


class ResUsers(models.Model):
    _inherit = "res.users"

    hosny_pos_waiter = fields.Boolean(
        string="متر (طلبات محلي فقط)",
        help=(
            "حساب المتر في نقطة البيع: طلبات محلي على الطاولات وإرسالها للمطبخ "
            "فقط. لا سفري، ولا دفع أو تسديد فواتير، ولا فتح أو إغلاق الوردية. "
            "حدّد فرعه في «نقاط البيع المسموحة». لا تنطبق على المدير."
        ),
    )

    def _hosny_is_pos_waiter(self):
        self.ensure_one()
        user = self.sudo()
        return bool(user.hosny_pos_waiter) and not (
            user._has_group("base.group_system")
            or user._has_group("point_of_sale.group_pos_manager")
        )

    @api.model
    def _load_pos_data_read(self, records, config):
        read_records = super()._load_pos_data_read(records, config)
        if read_records:
            # نفس طريقة _role في أودو: مفتاح على المستخدم الحالي فقط
            read_records[0]["_hosny_waiter"] = self.env.user._hosny_is_pos_waiter()
        return read_records

    @api.model
    def hosny_pos_profile(self):
        """من المستخدم فعلاً الآن (يُسأل عند كل فتح لنقطة البيع).

        أودو 19 يعيد استخدام بيانات المتصفح (IndexedDB) طوال الوردية المفتوحة،
        والمخزن باسم نقطة البيع لا المستخدم: صلاحيات تغيّرت، أو مستخدم آخر
        على نفس الجهاز، لا تظهر حتى الوردية التالية بدون هذا الفحص.
        """
        return {"id": self.env.uid, "waiter": self.env.user._hosny_is_pos_waiter()}
