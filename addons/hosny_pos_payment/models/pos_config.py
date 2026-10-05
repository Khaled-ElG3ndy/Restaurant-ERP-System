from odoo import api, models

# رسوم تُكتب من شاشة الدفع: كل واحدة سطر بمنتج خدمة خاص بها.
FEE_PRODUCT_XMLIDS = (
    "hosny_pos_payment.product_fee_service",
    "hosny_pos_payment.product_fee_delivery",
    "hosny_pos_payment.product_fee_driver",
)


class PosConfig(models.Model):
    _inherit = "pos.config"

    @api.model
    def _get_special_products(self):
        """منتجات الرسوم تُحمَّل دائماً في نقطة البيع (حتى مع التحميل المحدود)
        وتُخفى من شبكة الأصناف، كمنتج الإكرامية."""
        products = super()._get_special_products()
        for xmlid in FEE_PRODUCT_XMLIDS:
            product = self.env.ref(xmlid, raise_if_not_found=False)
            if product:
                products |= product
        return products
