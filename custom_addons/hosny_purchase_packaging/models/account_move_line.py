from odoo import api, fields, models


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    # Legacy snapshot fields kept for historical vendor bills.
    hosny_purchase_packaging_id = fields.Many2one(
        "hosny.purchase.packaging",
        string="Purchase Packaging",
        copy=True,
        check_company=True,
        index=True,
    )
    hosny_packaging_content_qty = fields.Float(
        string="Packaging Content",
        compute="_compute_hosny_packaging_quantities",
        digits="Product Unit",
        store=True,
    )
    hosny_base_quantity = fields.Float(
        string="الكمية الأساسية النهائية",
        compute="_compute_hosny_packaging_quantities",
        digits="Product Unit",
        store=True,
    )
    hosny_packaging_content_uom_id = fields.Many2one(
        "uom.uom",
        string="Content Unit",
        compute="_compute_hosny_packaging_quantities",
        store=True,
    )
    hosny_packaging_inner_qty = fields.Float(
        string="Inner Packaging Quantity",
        compute="_compute_hosny_packaging_quantities",
        digits="Product Unit",
        store=True,
    )
    hosny_packaging_inner_id = fields.Many2one(
        "hosny.purchase.packaging",
        string="Inner Packaging",
        compute="_compute_hosny_packaging_quantities",
        store=True,
    )
    hosny_packaging_hierarchy = fields.Char(
        string="Packaging Hierarchy",
        related="hosny_purchase_packaging_id.hierarchy_display",
        readonly=True,
    )

    # Purchase-line packaging snapshot.  These are deliberately copied values,
    # so a later rename of a packaging type cannot change an already issued
    # vendor document's quantities or price basis.
    hosny_line_packaging_enabled = fields.Boolean(
        string="استخدام التعبئة", copy=True, index=True
    )
    hosny_outer_packaging_type_id = fields.Many2one(
        "hosny.packaging.type",
        string="نوع التعبئة الخارجية",
        copy=True,
        check_company=True,
    )
    hosny_outer_package_qty = fields.Float(
        string="عدد التعبئات في أمر الشراء", digits="Product Unit", copy=True
    )
    hosny_has_inner_packaging = fields.Boolean(
        string="توجد تعبئة داخلية", copy=True
    )
    hosny_inner_packaging_type_id = fields.Many2one(
        "hosny.packaging.type",
        string="نوع التعبئة الداخلية",
        copy=True,
        check_company=True,
    )
    hosny_inner_package_qty = fields.Float(
        string="عدد التعبئات الداخلية", digits="Product Unit", copy=True
    )
    hosny_line_content_qty = fields.Float(
        string="محتوى التعبئة", digits="Product Unit", copy=True
    )
    hosny_line_content_uom_id = fields.Many2one(
        "uom.uom", string="وحدة المحتوى", copy=True, ondelete="restrict"
    )
    hosny_packaging_price_method = fields.Selection(
        [
            ("package", "حسب التعبئة"),
            ("base_uom", "حسب الوحدة الأساسية"),
        ],
        string="طريقة التسعير",
        copy=True,
    )
    hosny_packaging_input_price = fields.Monetary(
        string="السعر المدخل",
        currency_field="currency_id",
        copy=True,
    )
    hosny_line_packaging_summary = fields.Char(
        string="ملخص التعبئة", copy=True
    )
    hosny_packaging_unit_base_qty = fields.Float(
        string="محتوى التعبئة الواحدة بالوحدة الأساسية",
        digits="Product Unit",
        copy=True,
    )
    hosny_invoice_packaging_qty = fields.Float(
        string="عدد التعبئات المفوتر",
        compute="_compute_hosny_packaging_quantities",
        digits="Product Unit",
        store=True,
    )

    @api.depends(
        "product_id",
        "product_id.uom_id",
        "product_uom_id",
        "quantity",
        "hosny_purchase_packaging_id",
        "hosny_purchase_packaging_id.final_content_qty",
        "hosny_purchase_packaging_id.final_content_uom_id",
        "hosny_purchase_packaging_id.content_type",
        "hosny_purchase_packaging_id.content_qty",
        "hosny_purchase_packaging_id.inner_packaging_id",
        "hosny_line_packaging_enabled",
        "hosny_packaging_unit_base_qty",
    )
    def _compute_hosny_packaging_quantities(self):
        for line in self:
            packaging = line.hosny_purchase_packaging_id
            line.hosny_packaging_content_uom_id = packaging.final_content_uom_id
            if line.product_id and line.product_uom_id:
                line.hosny_packaging_content_qty = packaging.final_content_qty
                line.hosny_base_quantity = line.product_uom_id._compute_quantity(
                    line.quantity, line.product_id.uom_id, round=False
                )
            else:
                line.hosny_packaging_content_qty = 0.0
                line.hosny_base_quantity = line.quantity
            line.hosny_packaging_inner_qty = (
                packaging.content_qty
                if packaging.content_type == "packaging"
                else 0.0
            )
            line.hosny_packaging_inner_id = packaging.inner_packaging_id
            line.hosny_invoice_packaging_qty = (
                abs(line.hosny_base_quantity) / line.hosny_packaging_unit_base_qty
                if line.hosny_line_packaging_enabled
                and line.hosny_packaging_unit_base_qty
                else 0.0
            )
