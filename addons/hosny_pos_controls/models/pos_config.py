from odoo import _, fields, models


class PosConfig(models.Model):
    _inherit = "pos.config"

    def use_coupon_code(self, code, creation_date, partner_id, pricelist_id):
        result = super().use_coupon_code(code, creation_date, partner_id, pricelist_id)
        if result.get("successful"):
            return result

        coupon = self.env["loyalty.card"].search([("code", "=", code)], limit=1)
        if not coupon:
            message = _("الكود غير صحيح. تحقق من الرقم وحاول مرة أخرى.")
        elif coupon.points <= 0:
            message = _("تم استخدام هذا الكود بالكامل ولا يمكن استخدامه مرة أخرى.")
        elif coupon.expiration_date and coupon.expiration_date < fields.Date.from_string(creation_date[:11]):
            message = _("انتهت صلاحية هذا الكود.")
        elif not coupon.program_id.active:
            message = _("هذا الكود غير نشط حالياً.")
        elif coupon.program_id.pricelist_ids and pricelist_id not in coupon.program_id.pricelist_ids.ids:
            message = _("هذا الكود غير متاح مع قائمة الأسعار الحالية.")
        else:
            message = _("لا يمكن استخدام هذا الكود في نقطة البيع الحالية أو مع هذا الطلب.")

        return {
            "successful": False,
            "payload": {
                "error_message": message,
            },
        }
