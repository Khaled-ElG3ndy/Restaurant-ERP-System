from odoo import models


class ProductTemplateAttributeValue(models.Model):
    _inherit = "product.template.attribute.value"

    def write(self, vals):
        """نقطة البيع المفتوحة لا تطلب من السيرفر إلا الأصناف التي تغيّر تاريخ
        تعديلها. سعر الحجم («ربع كيلو» +46) يُحفظ هنا لا على الصنف، فبدون هذا
        يبقى المتصفح على السعر القديم (صفر) حتى تُقفل الوردية. نلمس الصنف
        ومتغيراته حتى تأخذها نقطة البيع عند فتحها بـ ?from_backend=True."""
        result = super().write(vals)
        if "price_extra" in vals and self:
            templates = self.product_tmpl_id
            self.env.cr.execute(
                "UPDATE product_template SET write_date = now() at time zone 'UTC' WHERE id IN %s",
                [tuple(templates.ids)],
            )
            self.env.cr.execute(
                "UPDATE product_product SET write_date = now() at time zone 'UTC' WHERE product_tmpl_id IN %s",
                [tuple(templates.ids)],
            )
            templates.invalidate_recordset(["write_date"])
            templates.product_variant_ids.invalidate_recordset(["write_date"])
        return result
