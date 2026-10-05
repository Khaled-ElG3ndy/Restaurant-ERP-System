from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class PurchaseLinePackagingLevel(models.Model):
    _name = "hosny.purchase.line.packaging.level"
    _description = "Purchase Order Line Packaging Component"
    _order = "sequence, id"
    _check_company_auto = True

    line_id = fields.Many2one(
        "purchase.order.line",
        string="سطر الشراء",
        required=True,
        ondelete="cascade",
        index=True,
    )
    sequence = fields.Integer(default=10, required=True)
    level_number = fields.Integer(string="المستوى", compute="_compute_level_number")
    content_type = fields.Selection(
        [
            ("packaging", "Another Packaging"),
            ("base_uom", "Final Unit of Measure"),
        ],
        string="نوع المحتوى",
        required=True,
        default="packaging",
        index=True,
    )
    quantity = fields.Float(
        string="يحتوي على",
        digits="Product Unit",
        required=True,
        default=1.0,
    )
    packaging_type_id = fields.Many2one(
        "hosny.packaging.type",
        string="نوع التعبئة",
        ondelete="restrict",
        check_company=True,
        index=True,
    )
    final_uom_id = fields.Many2one(
        "uom.uom",
        string="الوحدة النهائية",
        ondelete="restrict",
    )
    company_id = fields.Many2one(
        "res.company",
        related="line_id.company_id",
        store=True,
        readonly=True,
        index=True,
    )
    is_final_level = fields.Boolean(compute="_compute_level_number")

    _unique_line_packaging_type = models.Constraint(
        "UNIQUE(line_id, packaging_type_id)",
        "لا يمكن تكرار نفس نوع التعبئة داخل سلسلة تعبئة سطر الشراء.",
    )

    @api.depends(
        "sequence",
        "content_type",
        "line_id.hosny_packaging_level_ids.sequence",
        "line_id.hosny_packaging_level_ids.content_type",
    )
    def _compute_level_number(self):
        for level in self:
            ordered = level.line_id.hosny_packaging_level_ids.sorted(
                lambda item: (item.sequence, item.id)
            )
            ordered_list = list(ordered)
            level.level_number = (
                ordered_list.index(level) + 1 if level in ordered_list else 1
            )
            level.is_final_level = level.content_type == "base_uom"

    @api.onchange("content_type")
    def _onchange_content_type(self):
        for level in self:
            if level.content_type == "packaging":
                level.final_uom_id = False
            else:
                level.packaging_type_id = False
                if not level.final_uom_id and level.line_id.product_id:
                    level.final_uom_id = level.line_id.product_id.uom_id

    @api.constrains(
        "quantity",
        "content_type",
        "packaging_type_id",
        "final_uom_id",
        "company_id",
    )
    def _check_level_values(self):
        for level in self:
            if level.quantity <= 0:
                raise ValidationError(_("كمية مستوى التعبئة يجب أن تكون أكبر من صفر."))
            if level.content_type == "packaging" and not level.packaging_type_id:
                raise ValidationError(_("يجب اختيار نوع التعبئة للمستوى الداخلي."))
            if level.content_type == "base_uom" and not level.final_uom_id:
                raise ValidationError(_("يجب اختيار وحدة القياس للمحتوى النهائي."))
            if (
                level.packaging_type_id.company_id
                and level.company_id
                and level.packaging_type_id.company_id != level.company_id
            ):
                raise ValidationError(_("نوع التعبئة لا يتبع شركة سطر الشراء."))

    def _refresh_parent_lines(self):
        if self.env.context.get("skip_hosny_level_parent_refresh"):
            return
        self.mapped("line_id")._hosny_refresh_from_levels()

    @api.model_create_multi
    def create(self, vals_list):
        levels = super().create(vals_list)
        levels._refresh_parent_lines()
        return levels

    def write(self, vals):
        lines = self.mapped("line_id")
        result = super().write(vals)
        if not self.env.context.get("skip_hosny_level_parent_refresh"):
            (lines | self.mapped("line_id"))._hosny_refresh_from_levels()
        return result

    def unlink(self):
        lines = self.mapped("line_id")
        result = super().unlink()
        if not self.env.context.get("skip_hosny_level_parent_refresh"):
            lines.exists()._hosny_refresh_from_levels()
        return result
