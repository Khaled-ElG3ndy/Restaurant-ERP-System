from odoo import _, models
from odoo.exceptions import ValidationError


class ProductProduct(models.Model):
    _inherit = "product.product"

    def _update_uom(self, to_uom_id):
        """Protect line-level packaging calculations from a base-UoM rewrite.

        Odoo updates historical purchase lines while changing a product UoM.
        A packaging line also stores an independently selected content UoM and
        a calculated quantity, so silently rewriting only one side would make
        the stock quantity inconsistent.  The safe production behaviour is to
        require removing the draft packaging details first (or creating a new
        product when documents already exist).
        """
        target_uom = self.env["uom.uom"].browse(to_uom_id)
        changed_products = self.filtered(lambda product: product.uom_id != target_uom)
        if changed_products:
            packaging_lines = self.env["purchase.order.line"].search(
                [
                    ("product_id", "in", changed_products.ids),
                    ("hosny_line_packaging_enabled", "=", True),
                    ("display_type", "=", False),
                ],
                limit=1,
            )
            if packaging_lines:
                raise ValidationError(
                    _(
                        "لا يمكن تغيير وحدة قياس المنتج أثناء وجود سطور شراء تستخدم تفاصيل التعبئة. "
                        "أزل تفاصيل التعبئة من السطور المسودة أولًا، أو أنشئ منتجًا جديدًا للمستندات السابقة."
                    )
                )
        return super()._update_uom(to_uom_id)
