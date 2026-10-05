from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


MEAL_COMPONENT_DISPLAY_SELECTION = [
    ("pos_receipt", "POS + Receipt only"),
    ("pos_receipt_invoice", "POS + Receipt + Invoice"),
    ("internal", "Internal only (stock deduction only)"),
]


class ProductTemplate(models.Model):
    _inherit = "product.template"

    is_meal_combo = fields.Boolean(string="Meal Combo")
    meal_component_line_ids = fields.One2many(
        "product.meal.component.line",
        "meal_product_tmpl_id",
        string="Meal Components",
        copy=True,
    )
    additional_final_product_line_ids = fields.One2many(
        "product.additional.final.line",
        "parent_product_tmpl_id",
        string="Additional Final Products",
        copy=True,
    )
    final_cost_with_additional_products = fields.Float(
        string="Final Cost",
        compute="_compute_final_cost_with_additional_products",
        compute_sudo=True,
        min_display_digits="Product Price",
        groups="base.group_user",
        help=(
            "Current product cost plus the current BoM manufacturing cost of "
            "all configured additional products and quantities. This read-only "
            "value does not change standard price or inventory valuation."
        ),
    )
    component_display_mode = fields.Selection(
        MEAL_COMPONENT_DISPLAY_SELECTION,
        string="Component Display Mode",
        default="pos_receipt",
        required=True,
    )
    show_meal_components_config = fields.Boolean(
        compute="_compute_show_meal_components_config",
        string="Show Meal Components Configuration",
    )

    @api.depends_context("company")
    @api.depends(
        "standard_price",
        "additional_final_product_line_ids.product_id",
        "additional_final_product_line_ids.product_id.standard_price",
        "additional_final_product_line_ids.quantity",
        "additional_final_product_line_ids.uom_id",
    )
    def _compute_final_cost_with_additional_products(self):
        """Display the expected bundle cost without mutating valuation data."""
        for template in self:
            company = template.company_id or self.env.company
            company_template = template.with_company(company)
            additional_cost = sum(
                row["total_cost"]
                for row in template._additional_final_expected_cost_rows()
            )
            template.final_cost_with_additional_products = (
                company_template.standard_price + additional_cost
            )

    def _additional_final_expected_cost_rows(self):
        """Return the read-only BoM cost rows used by the product cost display."""
        self.ensure_one()
        company = self.company_id or self.env.company
        rows = []
        for line in self.additional_final_product_line_ids:
            product = line.product_id.sudo().with_company(company)
            bom = self.env["mrp.bom"].sudo()._bom_find(
                product,
                company_id=company.id,
                bom_type="normal",
            ).get(product)
            product_uom_unit_cost = (
                product._compute_bom_price(bom)
                if bom
                else product.standard_price
            )
            product_uom_quantity = line.uom_id._compute_quantity(
                line.quantity,
                product.uom_id,
                round=False,
            )
            rows.append({
                "product_id": product.id,
                "product_name": product.display_name,
                "quantity": line.quantity,
                "uom_name": line.uom_id.display_name,
                "cost_computed": True,
                "total_cost": product_uom_unit_cost * product_uom_quantity,
            })
        return rows

    def action_open_additional_cost_breakdown(self):
        """Open the existing breakdown dialog for the product's expected cost."""
        self.ensure_one()
        wizard = self.env[
            "pos.additional.product.cost.breakdown.wizard"
        ].create_from_product_template(self)
        form_view = self.env.ref(
            "hosny_pos_meal_combo.pos_additional_product_cost_breakdown_wizard_form"
        )
        return {
            "type": "ir.actions.act_window",
            "name": _("Additional Products Cost Details"),
            "res_model": wizard._name,
            "res_id": wizard.id,
            "view_mode": "form",
            "view_id": form_view.id,
            "views": [(form_view.id, "form")],
            "target": "new",
        }

    @api.depends("is_meal_combo", "categ_id", "categ_id.name", "categ_id.parent_id")
    def _compute_show_meal_components_config(self):
        for template in self:
            category = template.categ_id
            is_meal_category = False
            while category:
                if category.name == "الوجبات":
                    is_meal_category = True
                    break
                category = category.parent_id
            template.show_meal_components_config = template.is_meal_combo or is_meal_category

    @api.constrains("is_meal_combo", "meal_component_line_ids")
    def _check_meal_combo_components(self):
        for template in self:
            if template.is_meal_combo and not template.meal_component_line_ids:
                # Allow enabling the flag before saving first component rows in the form.
                continue

    @api.model
    def _load_pos_data_fields(self, config):
        fields_list = super()._load_pos_data_fields(config)
        return fields_list + [
            "is_meal_combo",
            "meal_component_line_ids",
            "component_display_mode",
            "additional_final_product_line_ids",
        ]

    @api.model
    def _load_pos_data_search_read(self, data, config):
        result = super()._load_pos_data_search_read(data, config)
        meal_templates = self.browse([p["id"] for p in result]).filtered("is_meal_combo")
        component_templates = meal_templates.meal_component_line_ids.product_id.product_tmpl_id
        additional_lines = self.env["product.additional.final.line"].search([
            ("parent_product_tmpl_id", "in", [p["id"] for p in result])
        ])
        additional_templates = additional_lines.product_id.product_tmpl_id
        missing_templates = (component_templates | additional_templates) - self.browse([p["id"] for p in result])
        if missing_templates:
            result += self._load_pos_data_read(missing_templates, config)
        return result

    @api.model
    def load_product_from_pos(self, config_id, domain, offset=0, limit=0):
        result = super().load_product_from_pos(config_id, domain, offset=offset, limit=limit)
        config = self.env["pos.config"].browse(config_id)
        template_ids = [product["id"] for product in result.get("product.template", [])]
        meal_template_ids = [product["id"] for product in result.get("product.template", []) if product.get("is_meal_combo")]
        if not template_ids:
            return result

        component_lines = self.env["product.meal.component.line"].search([
            ("meal_product_tmpl_id", "in", meal_template_ids)
        ])
        additional_lines = self.env["product.additional.final.line"].search([
            ("parent_product_tmpl_id", "in", template_ids)
        ])
        existing_template_ids = {product["id"] for product in result.get("product.template", [])}
        existing_product_ids = {product["id"] for product in result.get("product.product", [])}

        linked_products = component_lines.product_id | additional_lines.product_id
        missing_templates = linked_products.product_tmpl_id.filtered(
            lambda template: template.id not in existing_template_ids
        )
        missing_products = linked_products.filtered(
            lambda product: product.id not in existing_product_ids
        )

        if missing_templates:
            result.setdefault("product.template", [])
            result["product.template"] += self._load_pos_data_read(missing_templates, config)
        if missing_products:
            result.setdefault("product.product", [])
            result["product.product"] += self.env["product.product"]._load_pos_data_read(
                missing_products.with_context(display_default_code=False), config
            )

        loaded_line_ids = {line["id"] for line in result.get("product.meal.component.line", [])}
        missing_lines = component_lines.filtered(lambda line: line.id not in loaded_line_ids)
        if missing_lines:
            result.setdefault("product.meal.component.line", [])
            result["product.meal.component.line"] += self.env[
                "product.meal.component.line"
            ]._load_pos_data_read(missing_lines, config)
        loaded_additional_line_ids = {line["id"] for line in result.get("product.additional.final.line", [])}
        missing_additional_lines = additional_lines.filtered(lambda line: line.id not in loaded_additional_line_ids)
        if missing_additional_lines:
            result.setdefault("product.additional.final.line", [])
            result["product.additional.final.line"] += self.env[
                "product.additional.final.line"
            ]._load_pos_data_read(missing_additional_lines, config)
        return result


class ProductProduct(models.Model):
    _inherit = "product.product"

    is_meal_combo = fields.Boolean(related="product_tmpl_id.is_meal_combo", readonly=True)
    component_display_mode = fields.Selection(
        related="product_tmpl_id.component_display_mode",
        readonly=True,
    )

    @api.model
    def _load_pos_data_fields(self, config):
        fields_list = super()._load_pos_data_fields(config)
        return fields_list + ["is_meal_combo", "component_display_mode"]


class ProductMealComponentLine(models.Model):
    _name = "product.meal.component.line"
    _description = "Meal Component Line"
    _inherit = "pos.load.mixin"
    _order = "sequence, id"

    meal_product_tmpl_id = fields.Many2one(
        "product.template",
        string="Meal Product",
        required=True,
        ondelete="cascade",
        index=True,
    )
    product_id = fields.Many2one(
        "product.product",
        string="Component Product",
        required=True,
        domain=[("sale_ok", "=", True)],
    )
    quantity = fields.Float(string="Quantity", default=1.0, required=True)
    uom_id = fields.Many2one("uom.uom", string="Unit of Measure", required=True)
    extra_price = fields.Float(string="Extra Price", digits="Product Price", default=0.0)
    sequence = fields.Integer(default=10)
    note = fields.Char()

    @api.onchange("product_id")
    def _onchange_product_id(self):
        for line in self:
            if line.product_id:
                line.uom_id = line.product_id.uom_id

    @api.constrains("quantity")
    def _check_quantity_positive(self):
        for line in self:
            if line.quantity <= 0:
                raise ValidationError("Meal component quantity must be greater than zero.")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("product_id") and not vals.get("uom_id"):
                vals["uom_id"] = self.env["product.product"].browse(vals["product_id"]).uom_id.id
        return super().create(vals_list)

    @api.model
    def _load_pos_data_domain(self, data, config):
        template_ids = [product["id"] for product in data.get("product.template", [])]
        return [("meal_product_tmpl_id", "in", template_ids)]

    @api.model
    def _load_pos_data_fields(self, config):
        return [
            "id",
            "meal_product_tmpl_id",
            "product_id",
            "quantity",
            "uom_id",
            "extra_price",
            "sequence",
            "note",
            "write_date",
        ]


class ProductAdditionalFinalLine(models.Model):
    _name = "product.additional.final.line"
    _description = "Additional Final Product Line"
    _inherit = "pos.load.mixin"
    _order = "sequence, id"

    parent_product_tmpl_id = fields.Many2one(
        "product.template",
        string="Parent Final Product",
        required=True,
        ondelete="cascade",
        index=True,
    )
    product_id = fields.Many2one(
        "product.product",
        string="Additional Final Product",
        required=True,
        domain=[("sale_ok", "=", True)],
    )
    quantity = fields.Float(string="Quantity", default=1.0, required=True)
    uom_id = fields.Many2one("uom.uom", string="Unit of Measure", required=True)
    price_unit = fields.Float(string="Unit Price", digits="Product Price", default=0.0)
    discount = fields.Float(string="Discount (%)", default=0.0)
    sequence = fields.Integer(default=10)
    note = fields.Char()

    @api.onchange("product_id")
    def _onchange_product_id(self):
        for line in self:
            if line.product_id:
                line.uom_id = line.product_id.uom_id
                line.price_unit = line.product_id.lst_price

    @api.constrains("quantity")
    def _check_quantity_positive(self):
        for line in self:
            if line.quantity <= 0:
                raise ValidationError("Additional final product quantity must be greater than zero.")

    @api.constrains("discount")
    def _check_discount_range(self):
        for line in self:
            if line.discount < 0 or line.discount > 100:
                raise ValidationError("Additional final product discount must be between 0 and 100.")

    @api.constrains("parent_product_tmpl_id", "product_id")
    def _check_not_self_product(self):
        for line in self:
            if line.product_id.product_tmpl_id == line.parent_product_tmpl_id:
                raise ValidationError("A product cannot add itself as an additional final product.")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("product_id"):
                product = self.env["product.product"].browse(vals["product_id"])
                vals.setdefault("uom_id", product.uom_id.id)
                vals.setdefault("price_unit", product.lst_price)
        return super().create(vals_list)

    @api.model
    def _load_pos_data_domain(self, data, config):
        template_ids = [product["id"] for product in data.get("product.template", [])]
        return [("parent_product_tmpl_id", "in", template_ids)]

    @api.model
    def _load_pos_data_fields(self, config):
        return [
            "id",
            "parent_product_tmpl_id",
            "product_id",
            "quantity",
            "uom_id",
            "price_unit",
            "discount",
            "sequence",
            "note",
            "write_date",
        ]
