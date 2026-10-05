from odoo import Command, _, api, fields, models
from odoo.exceptions import ValidationError


class HosnyPurchasePackaging(models.Model):
    _name = "hosny.purchase.packaging"
    _description = "Product Purchase Packaging"
    _order = "purchase_default desc, sequence, id"
    _check_company_auto = True

    sequence = fields.Integer(default=10)
    packaging_type_id = fields.Many2one(
        "hosny.packaging.type",
        string="Packaging Type",
        required=True,
        ondelete="restrict",
        check_company=True,
        index=True,
    )
    name = fields.Char(
        string="Packaging Name",
        related="packaging_type_id.name",
        store=True,
        readonly=True,
    )
    product_id = fields.Many2one(
        "product.product",
        string="Product",
        required=True,
        ondelete="cascade",
        check_company=True,
        index=True,
    )
    product_tmpl_id = fields.Many2one(
        "product.template",
        string="Product Template",
        related="product_id.product_tmpl_id",
        store=True,
        index=True,
    )
    uom_id = fields.Many2one(
        "uom.uom",
        string="Technical Packaging Unit",
        required=True,
        ondelete="restrict",
        index=True,
        readonly=True,
    )
    content_qty = fields.Float(
        string="Packaging Content",
        digits="Product Unit",
        required=True,
        default=1.0,
    )
    content_type = fields.Selection(
        [
            ("base_uom", "Base Product Unit"),
            ("packaging", "Another Packaging"),
        ],
        string="Content Type",
        required=True,
        default="base_uom",
        index=True,
    )
    inner_packaging_id = fields.Many2one(
        "hosny.purchase.packaging",
        string="Inner Packaging",
        ondelete="restrict",
        check_company=True,
        index=True,
    )
    parent_packaging_ids = fields.One2many(
        "hosny.purchase.packaging",
        "inner_packaging_id",
        string="Containing Packagings",
    )
    content_uom_id = fields.Many2one(
        "uom.uom",
        string="Content Unit",
        related="product_id.uom_id",
        store=True,
        readonly=True,
    )
    final_content_qty = fields.Float(
        string="Final Base Content",
        compute="_compute_final_content_qty",
        digits="Product Unit",
        recursive=True,
        store=True,
    )
    final_content_uom_id = fields.Many2one(
        "uom.uom",
        string="Final Base Unit",
        related="product_id.uom_id",
        store=True,
        readonly=True,
    )
    hierarchy_display = fields.Char(
        string="Packaging Hierarchy",
        compute="_compute_hierarchy_display",
        recursive=True,
    )
    managed_uom = fields.Boolean(default=False, copy=False)
    barcode = fields.Char(
        string="Barcode",
        compute="_compute_barcode",
        inverse="_inverse_barcode",
    )
    sale_ok = fields.Boolean(string="Sales", default=True)
    purchase_ok = fields.Boolean(string="Purchase", default=True, index=True)
    purchase_default = fields.Boolean(string="Default Purchase Packaging", index=True)
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        default=lambda self: self.env.company,
        index=True,
    )

    _unique_product_type_company = models.Constraint(
        "UNIQUE(product_id, packaging_type_id, company_id)",
        "This packaging type is already configured for this product and company.",
    )

    def init(self):
        self.env.cr.execute(
            "DROP INDEX IF EXISTS hosny_purchase_packaging_product_uom_company_uniq"
        )
        self.env.cr.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS
                hosny_purchase_packaging_product_type_company_uniq
            ON hosny_purchase_packaging
                (product_id, packaging_type_id, COALESCE(company_id, 0))
            """
        )
        # Old UI deletions could leave managed technical UoMs attached to the
        # product after their packaging configuration was gone.  Hide and
        # detach only those orphan units; archiving preserves historical
        # document references safely.
        self.env.cr.execute(
            """
            DELETE FROM product_template_uom_uom_rel relation
            USING uom_uom uom
            WHERE relation.uom_uom_id = uom.id
              AND uom.hosny_is_technical_purchase_packaging IS TRUE
              AND NOT EXISTS (
                  SELECT 1
                    FROM hosny_purchase_packaging packaging
                   WHERE packaging.uom_id = uom.id
              )
            """
        )
        self.env.cr.execute(
            """
            UPDATE uom_uom uom
               SET active = FALSE
             WHERE uom.hosny_is_technical_purchase_packaging IS TRUE
               AND NOT EXISTS (
                   SELECT 1
                     FROM hosny_purchase_packaging packaging
                    WHERE packaging.uom_id = uom.id
               )
            """
        )
        self.env.cr.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS
                hosny_purchase_packaging_default_company_uniq
            ON hosny_purchase_packaging
                (product_id, COALESCE(company_id, 0))
            WHERE purchase_default IS TRUE
            """
        )

    def _barcode_domain(self):
        self.ensure_one()
        return [
            ("product_id", "=", self.product_id.id),
            ("uom_id", "=", self.uom_id.id),
            ("company_id", "=", self.company_id.id or False),
        ]

    @api.depends(
        "content_type",
        "content_qty",
        "inner_packaging_id",
        "inner_packaging_id.final_content_qty",
    )
    def _compute_final_content_qty(self):
        for packaging in self:
            if packaging.content_type == "packaging" and packaging.inner_packaging_id:
                packaging.final_content_qty = (
                    packaging.content_qty
                    * packaging.inner_packaging_id.final_content_qty
                )
            elif packaging.content_type == "base_uom":
                packaging.final_content_qty = packaging.content_qty
            else:
                packaging.final_content_qty = 0.0

    @api.depends(
        "name",
        "content_type",
        "content_qty",
        "content_uom_id.name",
        "final_content_qty",
        "final_content_uom_id.name",
        "inner_packaging_id",
        "inner_packaging_id.name",
        "inner_packaging_id.hierarchy_display",
    )
    def _compute_hierarchy_display(self):
        for packaging in self:
            packaging.hierarchy_display = packaging._build_hierarchy_display()

    def _build_hierarchy_display(self):
        self.ensure_one()
        if not self:
            return False
        parts = [self.name or ""]
        current = self
        seen = self.browse()
        while current and current not in seen:
            seen |= current
            if current.content_type == "packaging" and current.inner_packaging_id:
                parts.append(
                    _("%(qty)s × %(packaging)s", qty=f"{current.content_qty:g}", packaging=current.inner_packaging_id.name)
                )
                current = current.inner_packaging_id
            else:
                parts.append(
                    _("%(qty)s %(unit)s", qty=f"{current.content_qty:g}", unit=current.content_uom_id.display_name)
                )
                break
        return _(
            "%(chain)s = %(total)s %(unit)s",
            chain=" → ".join(parts),
            total=f"{self.final_content_qty:g}",
            unit=self.final_content_uom_id.display_name,
        )

    @api.depends("product_id", "uom_id", "company_id")
    def _compute_barcode(self):
        ProductUom = self.env["product.uom"]
        for packaging in self:
            barcode_link = (
                ProductUom.search(packaging._barcode_domain(), limit=1)
                if packaging.product_id and packaging.uom_id
                else ProductUom
            )
            packaging.barcode = barcode_link.barcode

    def _inverse_barcode(self):
        ProductUom = self.env["product.uom"]
        for packaging in self:
            if not packaging.product_id or not packaging.uom_id:
                continue
            barcode_link = ProductUom.search(packaging._barcode_domain(), limit=1)
            if packaging.barcode:
                values = {
                    "product_id": packaging.product_id.id,
                    "uom_id": packaging.uom_id.id,
                    "company_id": packaging.company_id.id or False,
                    "barcode": packaging.barcode,
                }
                if barcode_link:
                    barcode_link.write({"barcode": packaging.barcode})
                else:
                    ProductUom.create(values)
            elif barcode_link:
                barcode_link.unlink()

    @api.constrains(
        "product_id",
        "company_id",
        "uom_id",
        "content_qty",
        "content_type",
        "inner_packaging_id",
    )
    def _check_compatible_uom(self):
        for packaging in self:
            if (
                packaging.product_id
                and packaging.uom_id
                and not packaging.uom_id._has_common_reference(packaging.product_id.uom_id)
            ):
                raise ValidationError(
                    _(
                        "Packaging %(packaging)s cannot be converted to the product unit %(unit)s.",
                        packaging=packaging.uom_id.display_name,
                        unit=packaging.product_id.uom_id.display_name,
                    )
                )
            if packaging.content_qty <= 0:
                raise ValidationError(_("Packaging content must be greater than zero."))
            packaging._validate_inner_packaging()

    def _validate_inner_packaging(self):
        for packaging in self:
            inner = packaging.inner_packaging_id
            if packaging.content_type == "packaging" and not inner:
                raise ValidationError(_("Select the inner packaging."))
            if packaging.content_type == "base_uom" and inner:
                raise ValidationError(
                    _("A base-unit packaging cannot contain another packaging.")
                )
            if not inner:
                continue
            if inner == packaging:
                raise ValidationError(_("A packaging cannot contain itself."))
            if inner.product_id != packaging.product_id:
                raise ValidationError(
                    _("The inner packaging must belong to the same product.")
                )
            if inner.company_id != packaging.company_id:
                raise ValidationError(
                    _("The inner packaging must belong to the same company.")
                )
            current = inner
            visited = self.browse()
            while current:
                if current == packaging:
                    raise ValidationError(
                        _("Circular packaging references are not allowed.")
                    )
                if current in visited:
                    raise ValidationError(
                        _("Circular packaging references are not allowed.")
                    )
                visited |= current
                current = current.inner_packaging_id

    def _validate_candidate_hierarchy(self, vals):
        for packaging in self:
            content_type = vals.get("content_type", packaging.content_type)
            inner = self.browse(
                vals.get("inner_packaging_id", packaging.inner_packaging_id.id)
            )
            product = self.env["product.product"].browse(
                vals.get("product_id", packaging.product_id.id)
            )
            company = self.env["res.company"].browse(
                vals.get("company_id", packaging.company_id.id)
            )
            if content_type == "base_uom":
                inner = self.browse()
            if content_type == "packaging" and not inner:
                raise ValidationError(_("Select the inner packaging."))
            if not inner:
                continue
            if inner == packaging:
                raise ValidationError(_("A packaging cannot contain itself."))
            if inner.product_id != product:
                raise ValidationError(
                    _("The inner packaging must belong to the same product.")
                )
            if inner.company_id != company:
                raise ValidationError(
                    _("The inner packaging must belong to the same company.")
                )
            current = inner
            visited = self.browse()
            while current:
                if current == packaging or current in visited:
                    raise ValidationError(
                        _("Circular packaging references are not allowed.")
                    )
                visited |= current
                current = current.inner_packaging_id

    @api.constrains("purchase_default", "purchase_ok", "product_id", "company_id")
    def _check_purchase_default(self):
        for packaging in self.filtered("purchase_default"):
            if not packaging.purchase_ok:
                raise ValidationError(
                    _("The default purchase packaging must be enabled for purchases.")
                )
            duplicate = self.search_count(
                [
                    ("id", "!=", packaging.id),
                    ("product_id", "=", packaging.product_id.id),
                    ("company_id", "=", packaging.company_id.id or False),
                    ("purchase_default", "=", True),
                ],
                limit=1,
            )
            if duplicate:
                raise ValidationError(
                    _(
                        "Only one default purchase packaging is allowed per product and company."
                    )
                )

    @api.model
    def _default_product_from_context(self):
        """Resolve the product opened by the product-template form.

        Inline one2many commands do not reliably include invisible defaults in
        every client save path.  The template id is stable and explicitly sent
        by the view, so a single-variant product can always be recovered here.
        Multi-variant templates deliberately require an explicit variant.
        """
        product_id = self.env.context.get("default_product_id")
        product = self.env["product.product"].browse(product_id).exists()
        if product:
            return product
        template_id = self.env.context.get("default_product_tmpl_id")
        template = self.env["product.template"].browse(template_id).exists()
        variants = template.product_variant_ids if template else product
        return variants if len(variants) == 1 else product

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        if "product_id" in fields_list and not values.get("product_id"):
            product = self._default_product_from_context()
            if product:
                values["product_id"] = product.id
        return values

    @api.model_create_multi
    def create(self, vals_list):
        prepared_vals_list = []
        seen_keys = set()
        for incoming_vals in vals_list:
            vals = dict(incoming_vals)
            product = self.env["product.product"].browse(
                vals.get("product_id")
            ).exists() or self._default_product_from_context()
            if product:
                vals["product_id"] = product.id
            packaging_type = self.env["hosny.packaging.type"].browse(
                vals.get("packaging_type_id")
            )
            content_qty = vals.get("content_qty", 1.0)
            content_type = vals.get("content_type", "base_uom")
            inner_packaging = self.browse(vals.get("inner_packaging_id"))
            if not product:
                raise ValidationError(_("A product is required for the packaging."))
            if not packaging_type:
                raise ValidationError(_("Select a packaging type, such as Carton or Sack."))
            if content_qty <= 0:
                raise ValidationError(_("Packaging content must be greater than zero."))
            if content_type == "packaging":
                if not inner_packaging:
                    raise ValidationError(_("Select the inner packaging."))
                if inner_packaging.product_id != product:
                    raise ValidationError(
                        _("The inner packaging must belong to the same product.")
                    )
                packaging_company = vals.get("company_id") or False
                if inner_packaging.company_id.id != packaging_company:
                    raise ValidationError(
                        _("The inner packaging must belong to the same company.")
                    )
            else:
                vals["inner_packaging_id"] = False
            company_id = vals.get("company_id") or False
            duplicate_key = (product.id, packaging_type.id, company_id)
            if duplicate_key in seen_keys or self.search_count(
                [
                    ("product_id", "=", product.id),
                    ("packaging_type_id", "=", packaging_type.id),
                    ("company_id", "=", company_id),
                ],
                limit=1,
            ):
                raise ValidationError(
                    _("This packaging type is already configured for this product and company.")
                )
            seen_keys.add(duplicate_key)
            if not vals.get("uom_id"):
                final_content_qty = content_qty * (
                    inner_packaging.final_content_qty
                    if content_type == "packaging"
                    else 1.0
                )
                packaging_uom = self.env["uom.uom"].create(
                    {
                        "name": packaging_type.name,
                        "relative_uom_id": product.uom_id.id,
                        "relative_factor": final_content_qty,
                        "hosny_is_technical_purchase_packaging": True,
                    }
                )
                vals.update(uom_id=packaging_uom.id, managed_uom=True)
            prepared_vals_list.append(vals)
        records = super().create(prepared_vals_list)
        records._sync_product_packagings()
        records.mapped("final_content_qty")
        records._sync_managed_uom()
        return records

    def write(self, vals):
        prepared_vals = dict(vals)
        if prepared_vals.get("content_type") == "base_uom":
            prepared_vals["inner_packaging_id"] = False
        self._validate_candidate_hierarchy(prepared_vals)
        affected_before = self._get_self_and_parent_packagings()
        if {"product_id", "packaging_type_id", "company_id"} & set(prepared_vals):
            seen_keys = set()
            for packaging in self:
                product_id = prepared_vals.get("product_id", packaging.product_id.id)
                packaging_type_id = prepared_vals.get(
                    "packaging_type_id", packaging.packaging_type_id.id
                )
                company_id = prepared_vals.get("company_id", packaging.company_id.id) or False
                duplicate_key = (product_id, packaging_type_id, company_id)
                if duplicate_key in seen_keys or self.search_count(
                    [
                        ("id", "not in", self.ids),
                        ("product_id", "=", product_id),
                        ("packaging_type_id", "=", packaging_type_id),
                        ("company_id", "=", company_id),
                    ],
                    limit=1,
                ):
                    raise ValidationError(
                        _("This packaging type is already configured for this product and company.")
                    )
                seen_keys.add(duplicate_key)
        if {
            "content_qty",
            "content_type",
            "inner_packaging_id",
            "product_id",
            "packaging_type_id",
            "company_id",
        } & set(prepared_vals):
            self._check_content_can_change()
        result = super().write(prepared_vals)
        affected = affected_before | self._get_self_and_parent_packagings()
        if {
            "packaging_type_id",
            "content_qty",
            "content_type",
            "inner_packaging_id",
            "product_id",
        } & set(prepared_vals):
            affected.mapped("final_content_qty")
            affected._sync_managed_uom()
            affected._recompute_draft_documents()
        if {"product_id", "uom_id"} & set(prepared_vals):
            self._sync_product_packagings()
        return result

    @api.onchange("content_type")
    def _onchange_content_type(self):
        for packaging in self:
            if packaging.content_type == "base_uom":
                packaging.inner_packaging_id = False

    def _get_self_and_parent_packagings(self):
        result = self
        pending = self
        while pending:
            parents = pending.parent_packaging_ids - result
            if not parents:
                break
            result |= parents
            pending = parents
        return result

    def _check_content_can_change(self):
        PurchaseLine = self.env["purchase.order.line"]
        AccountLine = self.env["account.move.line"]
        StockMove = self.env["stock.move"]
        for packaging in self._get_self_and_parent_packagings():
            used = (
                PurchaseLine.search_count(
                    [
                        ("product_id", "=", packaging.product_id.id),
                        ("product_uom_id", "=", packaging.uom_id.id),
                        ("state", "not in", ("draft", "sent", "cancel")),
                    ],
                    limit=1,
                )
                or AccountLine.search_count(
                    [
                        ("product_id", "=", packaging.product_id.id),
                        ("product_uom_id", "=", packaging.uom_id.id),
                        ("move_id.state", "=", "posted"),
                    ],
                    limit=1,
                )
                or StockMove.search_count(
                    [
                        ("product_id", "=", packaging.product_id.id),
                        ("packaging_uom_id", "=", packaging.uom_id.id),
                        ("state", "not in", ("draft", "cancel")),
                    ],
                    limit=1,
                )
            )
            if used:
                raise ValidationError(
                    _(
                        "This packaging is already used in business documents. Create a new packaging instead of changing its content."
                    )
                )

    def _recompute_draft_documents(self):
        purchase_lines = self.env["purchase.order.line"].search(
            [
                ("hosny_purchase_packaging_id", "in", self.ids),
                ("state", "in", ("draft", "sent")),
            ]
        )
        if purchase_lines:
            purchase_lines._compute_product_uom_qty()
            purchase_lines._compute_price_unit_product_uom()
            purchase_lines._compute_hosny_packaging_content()
        bill_lines = self.env["account.move.line"].search(
            [
                ("hosny_purchase_packaging_id", "in", self.ids),
                ("move_id.state", "=", "draft"),
            ]
        )
        if bill_lines:
            bill_lines._compute_hosny_packaging_quantities()

    def _sync_managed_uom(self):
        for packaging in self.filtered("managed_uom"):
            if packaging.final_content_qty <= 0:
                continue
            packaging.uom_id.write(
                {
                    "name": packaging.packaging_type_id.name,
                    "relative_uom_id": packaging.product_id.uom_id.id,
                    "relative_factor": packaging.final_content_qty,
                    "hosny_is_technical_purchase_packaging": True,
                }
            )

    @api.ondelete(at_uninstall=False)
    def _unlink_except_used_as_inner_packaging(self):
        # A complete hierarchy can be removed from the product in one save.
        # Only block a packaging when a parent *outside* the same deletion
        # batch still references it.  The previous per-record check also
        # rejected the valid UI case where all rows were deleted together.
        used = self.filtered(lambda packaging: packaging.parent_packaging_ids - self)
        if used:
            raise ValidationError(
                _(
                    "Remove the inner-packaging links before deleting: %(packagings)s",
                    packagings=", ".join(used.mapped("display_name")),
                )
            )

    def unlink(self):
        managed_uoms = self.filtered("managed_uom").uom_id
        result = super().unlink()
        orphan_uoms = managed_uoms.filtered(
            lambda uom: not self.with_context(active_test=False).search_count(
                [("uom_id", "=", uom.id)], limit=1
            )
        )
        if orphan_uoms:
            templates = self.env["product.template"].with_context(active_test=False).search(
                [("uom_ids", "in", orphan_uoms.ids)]
            )
            if templates:
                templates.write(
                    {"uom_ids": [Command.unlink(uom_id) for uom_id in orphan_uoms.ids]}
                )
            orphan_uoms.write({"active": False})
        return result

    def _sync_product_packagings(self):
        for product, records in self.grouped("product_id").items():
            if product:
                product.product_tmpl_id.uom_ids |= records.uom_id

    @api.model
    def _purchase_configs(self, product, company):
        return self.search(
            [
                ("product_id", "=", product.id),
                ("company_id", "in", [False, company.id]),
            ]
        )

    @api.model
    def _default_purchase_config(self, product, company):
        configs = self._purchase_configs(product, company).filtered(
            lambda config: config.purchase_ok and config.purchase_default
        )
        return configs.sorted(
            key=lambda config: (config.company_id != company, config.sequence, config.id)
        )[:1]


class ProductTemplate(models.Model):
    _inherit = "product.template"

    hosny_purchase_packaging_ids = fields.One2many(
        "hosny.purchase.packaging",
        "product_tmpl_id",
        string="Purchase Packagings",
    )


class ProductProduct(models.Model):
    _inherit = "product.product"

    hosny_purchase_packaging_ids = fields.One2many(
        "hosny.purchase.packaging",
        "product_id",
        string="Purchase Packagings",
    )
