from odoo import Command, _, api, fields, models
from odoo.exceptions import ValidationError


class HosnyPurchasePackagingTemplate(models.Model):
    _name = "hosny.purchase.packaging.template"
    _description = "Reusable Product Purchase Packaging Template"
    _order = "sequence, name, id"
    _check_company_auto = True

    name = fields.Char(string="Template Name", required=True, translate=True, index=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True, index=True)
    product_tmpl_id = fields.Many2one(
        "product.template", string="Product", required=True, ondelete="cascade", index=True
    )
    company_id = fields.Many2one(
        "res.company", string="Company", default=lambda self: self.env.company, index=True
    )
    main_packaging_type_id = fields.Many2one(
        "hosny.packaging.type",
        string="Main Packaging Type",
        required=True,
        ondelete="restrict",
        check_company=True,
        index=True,
    )
    line_ids = fields.One2many(
        "hosny.purchase.packaging.template.line",
        "template_id",
        string="Packaging Levels",
        copy=True,
    )
    base_uom_id = fields.Many2one(
        "uom.uom",
        string="Base Unit",
        related="product_tmpl_id.uom_id",
        store=True,
        readonly=True,
    )
    allowed_content_uom_ids = fields.Many2many(
        "uom.uom",
        compute="_compute_allowed_content_uoms",
        string="Available Content Units",
    )
    final_base_qty = fields.Float(
        string="Final Content",
        compute="_compute_structure_results",
        digits="Product Unit",
        store=True,
    )
    summary = fields.Char(
        string="Packaging Summary", compute="_compute_structure_results", store=True
    )
    level_count = fields.Integer(compute="_compute_level_count")
    details_button = fields.Boolean(compute="_compute_details_button")

    def _ordered_level_values(self):
        self.ensure_one()
        return [
            {
                "content_type": level.content_type,
                "packaging_type_id": level.packaging_type_id.id or False,
                "quantity": level.quantity,
                "final_uom_id": level.final_uom_id.id or False,
            }
            for level in self.line_ids.sorted(lambda item: (item.sequence, item.id))
        ]

    def _structure_result(self, validate=False):
        """Calculate one main package through the purchase-line engine."""
        self.ensure_one()
        product = self.product_tmpl_id.product_variant_ids[:1]
        if not product or not self.main_packaging_type_id or not self.line_ids:
            if validate:
                raise ValidationError(
                    _("The template must contain a main packaging and at least one packaging level.")
                )
            return 0.0, False

        level_values = self._ordered_level_values()
        purchase_line = self.env["purchase.order.line"].new(
            {"company_id": (self.company_id or self.env.company).id}
        )
        calculation_values = {
            "product_id": product.id,
            "hosny_line_packaging_enabled": True,
            "hosny_outer_packaging_type_id": self.main_packaging_type_id.id,
            "hosny_outer_package_qty": 1.0,
            "hosny_packaging_price_method": "base_uom",
            "hosny_packaging_input_price": 0.0,
            "hosny_packaging_level_ids": [
                Command.create(level_item) for level_item in level_values
            ],
        }
        base_qty, _equivalent_price, _transaction_summary = (
            purchase_line._hosny_get_line_packaging_result(
                calculation_values, validate=validate
            )
        )
        if not base_qty:
            return 0.0, False

        normalized_levels = [
            {
                "content_type": level_item["content_type"],
                "packaging_type": self.env["hosny.packaging.type"].browse(
                    level_item["packaging_type_id"]
                ),
                "quantity": level_item["quantity"],
                "final_uom": self.env["uom.uom"].browse(level_item["final_uom_id"]),
            }
            for level_item in level_values
        ]
        summary = purchase_line._hosny_build_packaging_chain(
            self.main_packaging_type_id, normalized_levels
        )
        return base_qty, summary

    @api.depends(
        "product_tmpl_id",
        "product_tmpl_id.uom_id",
        "company_id",
        "main_packaging_type_id",
        "main_packaging_type_id.name",
        "line_ids.sequence",
        "line_ids.content_type",
        "line_ids.quantity",
        "line_ids.packaging_type_id",
        "line_ids.packaging_type_id.name",
        "line_ids.final_uom_id",
        "line_ids.final_uom_id.name",
    )
    def _compute_structure_results(self):
        for template in self:
            final_base_qty, summary = template._structure_result()
            template.final_base_qty = final_base_qty
            template.summary = summary

    @api.onchange("main_packaging_type_id", "line_ids")
    def _onchange_structure_results(self):
        """Return computed columns in the same RPC that edits the dialog."""
        self._compute_structure_results()

    @api.depends("line_ids")
    def _compute_level_count(self):
        for template in self:
            template.level_count = len(template.line_ids)

    def _compute_details_button(self):
        for template in self:
            template.details_button = True

    @api.depends("base_uom_id")
    def _compute_allowed_content_uoms(self):
        all_uoms = self.env["uom.uom"].search([])
        compatible_by_base = {}
        for template in self:
            base_uom = template.base_uom_id
            if not base_uom:
                template.allowed_content_uom_ids = self.env["uom.uom"]
                continue
            if base_uom.id not in compatible_by_base:
                compatible_by_base[base_uom.id] = all_uoms.filtered(
                    lambda uom: uom._has_common_reference(base_uom)
                )
            template.allowed_content_uom_ids = compatible_by_base[base_uom.id]

    @api.constrains(
        "name", "product_tmpl_id", "company_id", "main_packaging_type_id", "line_ids"
    )
    def _check_template_structure(self):
        for template in self:
            if not (template.name or "").strip():
                raise ValidationError(_("Enter a name for the purchase packaging template."))
            template._structure_result(validate=True)

    def _snapshot_level_commands(self):
        self.ensure_one()
        return [
            Command.create(
                {
                    "sequence": index * 10,
                    "content_type": level.content_type,
                    "packaging_type_id": (
                        level.packaging_type_id.id
                        if level.content_type == "packaging"
                        else False
                    ),
                    "quantity": level.quantity,
                    "final_uom_id": (
                        level.final_uom_id.id
                        if level.content_type == "base_uom"
                        else False
                    ),
                }
            )
            for index, level in enumerate(
                self.line_ids.sorted(lambda item: (item.sequence, item.id)), start=1
            )
        ]

    def action_open_packaging_details(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Packaging Details"),
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "views": [
                (
                    self.env.ref(
                        "hosny_purchase_packaging.hosny_purchase_packaging_template_form_view"
                    ).id,
                    "form",
                )
            ],
            "target": "new",
        }


class HosnyPurchasePackagingTemplateLine(models.Model):
    _name = "hosny.purchase.packaging.template.line"
    _description = "Reusable Purchase Packaging Template Level"
    _order = "sequence, id"
    _check_company_auto = True

    template_id = fields.Many2one(
        "hosny.purchase.packaging.template",
        string="Purchase Packaging Template",
        required=True,
        ondelete="cascade",
        index=True,
    )
    sequence = fields.Integer(default=10, required=True)
    content_type = fields.Selection(
        [
            ("packaging", "Another Packaging"),
            ("base_uom", "Final Unit of Measure"),
        ],
        string="Content Type",
        required=True,
        default="packaging",
        index=True,
    )
    quantity = fields.Float(
        string="Contains", digits="Product Unit", required=True, default=1.0
    )
    packaging_type_id = fields.Many2one(
        "hosny.packaging.type",
        string="Packaging Type",
        ondelete="restrict",
        check_company=True,
        index=True,
    )
    final_uom_id = fields.Many2one(
        "uom.uom", string="Final Content", ondelete="restrict"
    )
    company_id = fields.Many2one(
        "res.company",
        related="template_id.company_id",
        store=True,
        readonly=True,
        index=True,
    )
    is_final_level = fields.Boolean(compute="_compute_is_final_level")
    base_uom_factor = fields.Float(
        string="Base Unit Conversion Factor",
        compute="_compute_base_uom_factor",
        digits=(16, 12),
    )

    @api.depends("content_type")
    def _compute_is_final_level(self):
        for level in self:
            level.is_final_level = level.content_type == "base_uom"

    @api.depends("final_uom_id", "template_id.base_uom_id")
    def _compute_base_uom_factor(self):
        for level in self:
            final_uom = level.final_uom_id
            base_uom = level.template_id.base_uom_id
            level.base_uom_factor = (
                final_uom._compute_quantity(1.0, base_uom, round=False)
                if final_uom and base_uom
                else 0.0
            )

    @api.onchange("content_type")
    def _onchange_content_type(self):
        for level in self:
            if level.content_type == "packaging":
                level.final_uom_id = False
            else:
                level.packaging_type_id = False
                if not level.final_uom_id and level.template_id.base_uom_id:
                    level.final_uom_id = level.template_id.base_uom_id

    @api.constrains(
        "content_type", "quantity", "packaging_type_id", "final_uom_id", "company_id"
    )
    def _check_level_values(self):
        for level in self:
            if level.quantity <= 0:
                raise ValidationError(_("Packaging level quantity must be greater than zero."))
            if level.content_type == "packaging" and not level.packaging_type_id:
                raise ValidationError(_("Select the packaging type for the internal level."))
            if level.content_type == "base_uom" and not level.final_uom_id:
                raise ValidationError(_("Select the final content unit of measure."))
            if level.content_type == "packaging" and level.final_uom_id:
                raise ValidationError(_("An internal packaging level cannot contain a unit of measure."))
            if level.content_type == "base_uom" and level.packaging_type_id:
                raise ValidationError(_("The final unit level cannot contain a packaging type."))


class ProductTemplate(models.Model):
    _inherit = "product.template"

    hosny_purchase_packaging_template_ids = fields.One2many(
        "hosny.purchase.packaging.template",
        "product_tmpl_id",
        string="Purchase Packaging",
    )


class ProductProduct(models.Model):
    _inherit = "product.product"

    hosny_purchase_packaging_template_ids = fields.One2many(
        related="product_tmpl_id.hosny_purchase_packaging_template_ids",
        string="Purchase Packaging",
        readonly=False,
    )
