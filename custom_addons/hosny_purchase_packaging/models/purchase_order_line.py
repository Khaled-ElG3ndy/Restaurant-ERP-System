from odoo import Command, _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.float_utils import float_compare


class PurchaseOrderLine(models.Model):
    _inherit = "purchase.order.line"

    # Legacy product-level packaging fields.  They remain available for old
    # purchase documents, but the new workflow never selects a preset
    # automatically.
    hosny_purchase_packaging_id = fields.Many2one(
        "hosny.purchase.packaging",
        string="Purchase Packaging",
        copy=True,
        check_company=True,
        index=True,
    )
    hosny_packaging_content_qty = fields.Float(
        string="Packaging Content",
        compute="_compute_hosny_packaging_content",
        digits="Product Unit",
        store=True,
    )
    hosny_packaging_content_uom_id = fields.Many2one(
        "uom.uom",
        string="Content Unit",
        compute="_compute_hosny_packaging_content",
        store=True,
    )
    hosny_packaging_inner_qty = fields.Float(
        string="Inner Packaging Quantity",
        compute="_compute_hosny_packaging_content",
        digits="Product Unit",
        store=True,
    )
    hosny_packaging_inner_id = fields.Many2one(
        "hosny.purchase.packaging",
        string="Inner Packaging",
        compute="_compute_hosny_packaging_content",
        store=True,
    )
    hosny_packaging_hierarchy = fields.Char(
        string="Packaging Hierarchy",
        related="hosny_purchase_packaging_id.hierarchy_display",
        readonly=True,
    )
    hosny_purchase_packaging_template_id = fields.Many2one(
        "hosny.purchase.packaging.template",
        string="Saved Purchase Packaging",
        copy=True,
        check_company=True,
        index=True,
    )
    hosny_available_purchase_packaging_template_ids = fields.Many2many(
        "hosny.purchase.packaging.template",
        compute="_compute_hosny_available_purchase_packaging_templates",
        string="Available Saved Purchase Packagings",
    )
    hosny_duplicate_warning_acknowledged = fields.Boolean(
        string="Duplicate Product Warning Acknowledged",
        copy=False,
        help="Technical flag set after the user explicitly accepts a repeated product line.",
    )

    # New purchase-line packaging workflow.
    hosny_line_packaging_enabled = fields.Boolean(
        string="استخدام التعبئة",
        copy=True,
        index=True,
    )
    hosny_packaging_level_ids = fields.One2many(
        "hosny.purchase.line.packaging.level",
        "line_id",
        string="مستويات التعبئة",
        copy=True,
    )
    hosny_outer_packaging_type_id = fields.Many2one(
        "hosny.packaging.type",
        string="نوع التعبئة الخارجية",
        copy=True,
        check_company=True,
    )
    hosny_outer_package_qty = fields.Float(
        string="عدد التعبئات",
        digits="Product Unit",
        copy=True,
    )
    hosny_has_inner_packaging = fields.Boolean(
        string="توجد تعبئة داخلية",
        copy=True,
    )
    hosny_inner_packaging_type_id = fields.Many2one(
        "hosny.packaging.type",
        string="نوع التعبئة الداخلية",
        copy=True,
        check_company=True,
    )
    hosny_inner_package_qty = fields.Float(
        string="عدد التعبئات الداخلية في كل تعبئة خارجية",
        digits="Product Unit",
        copy=True,
    )
    hosny_line_content_qty = fields.Float(
        string="محتوى التعبئة",
        digits="Product Unit",
        copy=True,
    )
    hosny_line_content_uom_id = fields.Many2one(
        "uom.uom",
        string="وحدة المحتوى",
        copy=True,
        ondelete="restrict",
    )
    hosny_allowed_content_uom_ids = fields.Many2many(
        "uom.uom",
        compute="_compute_hosny_allowed_content_uom_ids",
        string="وحدات المحتوى المتاحة",
    )
    hosny_packaging_price_method = fields.Selection(
        [
            ("package", "By Main Packaging"),
            ("base_uom", "By Base Unit"),
        ],
        string="طريقة التسعير",
        default="package",
        copy=True,
    )
    hosny_packaging_input_price = fields.Monetary(
        string="السعر المدخل",
        currency_field="currency_id",
        copy=True,
    )
    hosny_line_base_qty = fields.Float(
        string="الكمية الأساسية النهائية",
        compute="_compute_hosny_line_packaging_results",
        digits="Product Unit",
        store=True,
    )
    hosny_packaging_equivalent_unit_price = fields.Monetary(
        string="سعر الوحدة الأساسية المكافئ",
        compute="_compute_hosny_line_packaging_results",
        currency_field="currency_id",
        store=True,
    )
    hosny_line_packaging_summary = fields.Char(
        string="ملخص التعبئة",
        compute="_compute_hosny_line_packaging_results",
        store=True,
    )
    hosny_main_package_base_qty = fields.Float(
        string="محتوى التعبئة الرئيسية",
        compute="_compute_hosny_line_packaging_results",
        digits="Product Unit",
        store=True,
    )
    hosny_packaging_level_count = fields.Integer(
        string="عدد مستويات التعبئة",
        compute="_compute_hosny_packaging_level_count",
    )
    hosny_summary_package_content = fields.Char(
        compute="_compute_hosny_packaging_summary_display"
    )
    hosny_summary_total_quantity = fields.Char(
        compute="_compute_hosny_packaging_summary_display"
    )
    hosny_summary_equivalent_price = fields.Char(
        compute="_compute_hosny_packaging_summary_display"
    )
    hosny_summary_subtotal = fields.Char(
        compute="_compute_hosny_packaging_summary_display"
    )
    hosny_summary_total = fields.Char(
        compute="_compute_hosny_packaging_summary_display"
    )

    _NEW_PACKAGING_DETAIL_FIELDS = {
        "hosny_line_packaging_enabled",
        "hosny_outer_packaging_type_id",
        "hosny_outer_package_qty",
        "hosny_has_inner_packaging",
        "hosny_inner_packaging_type_id",
        "hosny_inner_package_qty",
        "hosny_line_content_qty",
        "hosny_line_content_uom_id",
        "hosny_packaging_price_method",
        "hosny_packaging_input_price",
        "hosny_packaging_level_ids",
        "hosny_purchase_packaging_template_id",
    }

    def init(self):
        """Convert the previous outer-in-level layout without losing data."""
        self.env.cr.execute(
            """
            CREATE TEMP TABLE hosny_packaging_lines_to_v5 ON COMMIT DROP AS
            SELECT line.id
              FROM purchase_order_line line
             WHERE line.hosny_line_packaging_enabled IS TRUE
               AND line.hosny_line_content_qty > 0
               AND line.hosny_line_content_uom_id IS NOT NULL
               AND NOT EXISTS (
                    SELECT 1
                      FROM hosny_purchase_line_packaging_level level
                     WHERE level.line_id = line.id
                       AND level.content_type = 'base_uom'
               )
            """
        )
        self.env.cr.execute(
            """
            INSERT INTO hosny_purchase_line_packaging_level
                (line_id, sequence, content_type, quantity, final_uom_id,
                 company_id, create_uid, create_date, write_uid, write_date)
            SELECT line.id,
                   COALESCE((SELECT MAX(level.sequence) + 10
                               FROM hosny_purchase_line_packaging_level level
                              WHERE level.line_id = line.id), 10),
                   'base_uom', line.hosny_line_content_qty,
                   line.hosny_line_content_uom_id, line.company_id,
                   COALESCE(line.create_uid, 1), COALESCE(line.create_date, NOW()),
                   COALESCE(line.write_uid, 1), COALESCE(line.write_date, NOW())
              FROM purchase_order_line line
              JOIN hosny_packaging_lines_to_v5 migration ON migration.id = line.id
            """
        )
        self.env.cr.execute(
            """
            DELETE FROM hosny_purchase_line_packaging_level outer_level
             USING purchase_order_line line, hosny_packaging_lines_to_v5 migration
             WHERE migration.id = line.id
               AND outer_level.line_id = line.id
               AND outer_level.content_type = 'packaging'
               AND outer_level.packaging_type_id = line.hosny_outer_packaging_type_id
               AND outer_level.quantity = line.hosny_outer_package_qty
               AND outer_level.id = (
                    SELECT candidate.id
                      FROM hosny_purchase_line_packaging_level candidate
                     WHERE candidate.line_id = line.id
                       AND candidate.content_type = 'packaging'
                     ORDER BY candidate.sequence, candidate.id
                     LIMIT 1
               )
            """
        )

    @api.depends("product_uom_id", "price_unit")
    def _compute_price_unit_product_uom(self):
        incomplete_lines = self.filtered(
            lambda line: not line.product_id
            or not line.product_id.uom_id
            or not line.product_uom_id
        )
        incomplete_lines.price_unit_product_uom = 0.0
        complete_lines = self - incomplete_lines
        if complete_lines:
            super(PurchaseOrderLine, complete_lines)._compute_price_unit_product_uom()

    @api.depends(
        "product_id",
        "hosny_purchase_packaging_id",
        "hosny_purchase_packaging_id.final_content_qty",
        "hosny_purchase_packaging_id.final_content_uom_id",
        "hosny_purchase_packaging_id.content_type",
        "hosny_purchase_packaging_id.content_qty",
        "hosny_purchase_packaging_id.inner_packaging_id",
    )
    def _compute_hosny_packaging_content(self):
        for line in self:
            packaging = line.hosny_purchase_packaging_id
            line.hosny_packaging_content_uom_id = packaging.final_content_uom_id
            line.hosny_packaging_content_qty = packaging.final_content_qty
            line.hosny_packaging_inner_qty = (
                packaging.content_qty
                if packaging.content_type == "packaging"
                else 0.0
            )
            line.hosny_packaging_inner_id = packaging.inner_packaging_id

    @api.depends("product_id", "product_id.uom_id")
    def _compute_hosny_allowed_content_uom_ids(self):
        all_uoms = self.env["uom.uom"].search([])
        compatible_by_base_uom = {}
        for line in self:
            base_uom = line.product_id.uom_id
            if not base_uom:
                line.hosny_allowed_content_uom_ids = self.env["uom.uom"]
                continue
            if base_uom.id not in compatible_by_base_uom:
                compatible_by_base_uom[base_uom.id] = all_uoms.filtered(
                    lambda uom: uom._has_common_reference(base_uom)
                )
            line.hosny_allowed_content_uom_ids = compatible_by_base_uom[base_uom.id]

    @api.depends("product_id", "company_id")
    def _compute_hosny_available_purchase_packaging_templates(self):
        Template = self.env["hosny.purchase.packaging.template"]
        for line in self:
            if not line.product_id:
                line.hosny_available_purchase_packaging_template_ids = Template
                continue
            company = line.company_id or self.env.company
            line.hosny_available_purchase_packaging_template_ids = Template.search(
                [
                    ("active", "=", True),
                    ("product_tmpl_id", "=", line.product_id.product_tmpl_id.id),
                    ("company_id", "in", [False, company.id]),
                ],
                order="sequence, name, id",
            )

    @staticmethod
    def _hosny_number(value):
        return f"{value:g}"

    @staticmethod
    def _hosny_relational_id(value):
        if isinstance(value, models.BaseModel):
            return value.id
        if isinstance(value, (tuple, list)) and value and not isinstance(value[0], int):
            return value[0]
        return value or False

    def _hosny_level_dicts_from_commands(self, commands):
        self.ensure_one()
        levels = [
            {
                "id": level.id,
                "sequence": level.sequence,
                "content_type": level.content_type,
                "packaging_type_id": level.packaging_type_id.id,
                "quantity": level.quantity,
                "final_uom_id": level.final_uom_id.id,
            }
            for level in self.hosny_packaging_level_ids.sorted("sequence")
        ]
        for command in commands or []:
            operation, record_id, payload = command
            if operation == Command.CREATE:
                level_values = {
                    "id": False,
                    "sequence": payload.get("sequence", 10),
                    "content_type": payload.get("content_type", "packaging"),
                    "packaging_type_id": self._hosny_relational_id(
                        payload.get("packaging_type_id")
                    ),
                    "quantity": payload.get("quantity", 1.0),
                    "final_uom_id": self._hosny_relational_id(
                        payload.get("final_uom_id")
                    ),
                }
                levels.append(level_values)
            elif operation == Command.UPDATE:
                for level in levels:
                    if level["id"] == record_id:
                        level.update(payload)
                        level["packaging_type_id"] = self._hosny_relational_id(
                            level.get("packaging_type_id")
                        )
                        level["final_uom_id"] = self._hosny_relational_id(
                            level.get("final_uom_id")
                        )
                        break
            elif operation in (Command.DELETE, Command.UNLINK):
                levels = [level for level in levels if level["id"] != record_id]
            elif operation == Command.LINK:
                linked = self.env["hosny.purchase.line.packaging.level"].browse(record_id)
                levels.append(
                    {
                        "id": linked.id,
                        "sequence": linked.sequence,
                        "content_type": linked.content_type,
                        "packaging_type_id": linked.packaging_type_id.id,
                        "quantity": linked.quantity,
                        "final_uom_id": linked.final_uom_id.id,
                    }
                )
            elif operation == Command.CLEAR:
                levels = []
            elif operation == Command.SET:
                linked_levels = self.env[
                    "hosny.purchase.line.packaging.level"
                ].browse(payload).sorted("sequence")
                levels = [
                    {
                        "id": level.id,
                        "sequence": level.sequence,
                        "content_type": level.content_type,
                        "packaging_type_id": level.packaging_type_id.id,
                        "quantity": level.quantity,
                        "final_uom_id": level.final_uom_id.id,
                    }
                    for level in linked_levels
                ]
        return sorted(
            levels,
            key=lambda item: (item.get("sequence", 10), str(item.get("id") or "")),
        )

    def _hosny_packaging_levels_for_values(self, values=None):
        """Return candidate ordered levels, including unsaved x2many commands."""
        self.ensure_one()
        values = values or {}
        explicit_levels = "hosny_packaging_level_ids" in values
        if explicit_levels:
            levels = self._hosny_level_dicts_from_commands(
                values["hosny_packaging_level_ids"]
            )
        else:
            levels = [
                {
                    "id": level.id,
                    "sequence": level.sequence,
                    "content_type": level.content_type,
                    "packaging_type_id": level.packaging_type_id.id,
                    "quantity": level.quantity,
                    "final_uom_id": level.final_uom_id.id,
                }
                for level in self.hosny_packaging_level_ids.sorted("sequence")
            ]

        legacy_changed = bool(
            {
                "hosny_has_inner_packaging",
                "hosny_inner_packaging_type_id",
                "hosny_inner_package_qty",
                "hosny_line_content_qty",
                "hosny_line_content_uom_id",
            }
            & set(values)
        )
        if levels and legacy_changed and not explicit_levels:
            packaging_levels = [
                level for level in levels if level["content_type"] == "packaging"
            ]
            final_levels = [
                level for level in levels if level["content_type"] == "base_uom"
            ]
            has_inner = values.get(
                "hosny_has_inner_packaging", bool(packaging_levels)
            )
            if has_inner:
                inner_values = {
                    "content_type": "packaging",
                    "packaging_type_id": self._hosny_relational_id(
                        values.get(
                            "hosny_inner_packaging_type_id",
                            packaging_levels[0]["packaging_type_id"]
                            if packaging_levels
                            else False,
                        )
                    ),
                    "quantity": values.get(
                        "hosny_inner_package_qty",
                        packaging_levels[0]["quantity"]
                        if packaging_levels
                        else 1.0,
                    ),
                }
                if packaging_levels:
                    packaging_levels[0].update(inner_values)
                else:
                    packaging_levels.append(
                        {"id": False, "sequence": 10, **inner_values, "final_uom_id": False}
                    )
            else:
                packaging_levels = []
            content_qty = values.get(
                "hosny_line_content_qty",
                final_levels[0]["quantity"] if final_levels else 0.0,
            )
            content_uom = self._hosny_relational_id(
                values.get(
                    "hosny_line_content_uom_id",
                    final_levels[0]["final_uom_id"] if final_levels else False,
                )
            )
            if final_levels:
                final_levels[0].update(
                    quantity=content_qty, final_uom_id=content_uom
                )
            elif content_qty or content_uom:
                final_levels = [
                    {
                        "id": False,
                        "sequence": (len(packaging_levels) + 1) * 10,
                        "content_type": "base_uom",
                        "packaging_type_id": False,
                        "quantity": content_qty,
                        "final_uom_id": content_uom,
                    }
                ]
            levels = packaging_levels + final_levels

        if not levels and not explicit_levels:
            has_inner = values.get(
                "hosny_has_inner_packaging", self.hosny_has_inner_packaging
            )
            if has_inner:
                levels.append(
                    {
                        "id": False,
                        "sequence": 10,
                        "content_type": "packaging",
                        "packaging_type_id": self._hosny_relational_id(
                            values.get(
                                "hosny_inner_packaging_type_id",
                                self.hosny_inner_packaging_type_id,
                            )
                        ),
                        "quantity": values.get(
                            "hosny_inner_package_qty",
                            self.hosny_inner_package_qty,
                        ),
                        "final_uom_id": False,
                    }
                )
            content_qty = values.get(
                "hosny_line_content_qty", self.hosny_line_content_qty
            )
            content_uom = self._hosny_relational_id(
                values.get(
                    "hosny_line_content_uom_id",
                    self.hosny_line_content_uom_id,
                )
            )
            if content_qty or content_uom:
                levels.append(
                    {
                        "id": False,
                        "sequence": (len(levels) + 1) * 10,
                        "content_type": "base_uom",
                        "packaging_type_id": False,
                        "quantity": content_qty,
                        "final_uom_id": content_uom,
                    }
                )
        return levels

    @api.model
    def _hosny_build_packaging_chain(
        self, outer_type, levels, outer_quantity=None
    ):
        """Return the shared, translated structure text for a line or template."""
        if outer_quantity is None:
            parts = [outer_type.display_name]
        else:
            parts = [
                _(
                    "%(qty)s %(packaging)s",
                    qty=self._hosny_number(outer_quantity),
                    packaging=outer_type.display_name,
                )
            ]
        for level in levels[:-1]:
            parts.append(
                _(
                    "%(qty)s %(packaging)s",
                    qty=self._hosny_number(level["quantity"]),
                    packaging=level["packaging_type"].display_name,
                )
            )
        if levels:
            final_level = levels[-1]
            parts.append(
                _(
                    "%(qty)s %(unit)s",
                    qty=self._hosny_number(final_level["quantity"]),
                    unit=final_level["final_uom"].display_name,
                )
            )
        return " × ".join(parts)

    def _hosny_get_line_packaging_result(self, values=None, validate=False):
        """Return final base quantity, equivalent base price and summary.

        ``values`` is used by create/write to calculate from the candidate values
        before they reach the database.  Odoo's own UoM conversion is the only
        conversion mechanism used here.
        """
        self.ensure_one()
        values = values or {}

        def value(name):
            return values[name] if name in values else self[name]

        enabled = value("hosny_line_packaging_enabled")
        if not enabled:
            return 0.0, 0.0, False

        product_value = value("product_id")
        product = (
            product_value
            if isinstance(product_value, models.BaseModel)
            else self.env["product.product"].browse(product_value)
        ).exists()
        outer_type_value = value("hosny_outer_packaging_type_id")
        outer_type = (
            outer_type_value
            if isinstance(outer_type_value, models.BaseModel)
            else self.env["hosny.packaging.type"].browse(outer_type_value)
        ).exists()
        outer_qty = value("hosny_outer_package_qty") or 0.0
        level_values = self._hosny_packaging_levels_for_values(values)
        levels = []
        for level_value in level_values:
            packaging_type = self.env["hosny.packaging.type"].browse(
                self._hosny_relational_id(level_value.get("packaging_type_id"))
            ).exists()
            final_uom = self.env["uom.uom"].browse(
                self._hosny_relational_id(level_value.get("final_uom_id"))
            ).exists()
            levels.append(
                {
                    "content_type": level_value.get("content_type") or "packaging",
                    "packaging_type": packaging_type,
                    "quantity": level_value.get("quantity") or 0.0,
                    "final_uom": final_uom,
                }
            )
        price_method = value("hosny_packaging_price_method") or "package"
        input_price = value("hosny_packaging_input_price") or 0.0

        errors = []
        if not product:
            errors.append(_("يجب اختيار المنتج قبل إعداد التعبئة."))
        if not outer_type:
            errors.append(_("يجب اختيار نوع التعبئة الرئيسية."))
        if outer_qty <= 0:
            errors.append(_("عدد التعبئات المشتراة يجب أن يكون أكبر من صفر."))
        if not levels:
            errors.append(_("يجب إضافة مستوى تعبئة واحد على الأقل."))
        if len(levels) > 10:
            errors.append(_("لا يمكن إضافة أكثر من 10 مستويات للتعبئة."))
        seen_types = self.env["hosny.packaging.type"]
        final_indexes = []
        for index, level in enumerate(levels, start=1):
            packaging_type = level["packaging_type"]
            quantity = level["quantity"]
            if quantity <= 0:
                errors.append(_("عدد التعبئة في المستوى %(level)s يجب أن يكون أكبر من صفر.", level=index))
            if level["content_type"] == "packaging":
                if not packaging_type:
                    errors.append(_("يجب اختيار نوع التعبئة في المستوى %(level)s.", level=index))
                elif packaging_type == outer_type or packaging_type in seen_types:
                    errors.append(_("لا يمكن تكرار نفس نوع التعبئة داخل السلسلة."))
                else:
                    seen_types |= packaging_type
                    if (
                        packaging_type.company_id
                        and self.company_id
                        and packaging_type.company_id != self.company_id
                    ):
                        errors.append(_("نوع التعبئة في المستوى %(level)s لا يتبع شركة سطر الشراء.", level=index))
            elif level["content_type"] == "base_uom":
                final_indexes.append(index - 1)
                if not level["final_uom"]:
                    errors.append(_("يجب اختيار وحدة القياس للمحتوى النهائي."))
                elif product and not level["final_uom"]._has_common_reference(product.uom_id):
                    errors.append(_("وحدة المحتوى النهائي غير متوافقة مع وحدة قياس المنتج."))
            else:
                errors.append(_("نوع محتوى المستوى غير صحيح."))
        if len(final_indexes) != 1:
            errors.append(_("يجب وجود محتوى نهائي واحد فقط بوحدة قياس."))
        elif final_indexes[0] != len(levels) - 1:
            errors.append(_("يجب أن يكون محتوى وحدة القياس هو المستوى الأخير."))
        if input_price < 0:
            errors.append(_("السعر لا يمكن أن يكون أقل من صفر."))
        if price_method not in ("package", "base_uom"):
            errors.append(_("يجب اختيار طريقة تسعير صحيحة."))

        if errors:
            if validate:
                raise ValidationError("\n".join(errors))
            return 0.0, 0.0, False

        final_level = levels[-1]
        base_per_outer = final_level["final_uom"]._compute_quantity(
            final_level["quantity"], product.uom_id, round=False
        )
        for level in levels[:-1]:
            base_per_outer *= level["quantity"]
        base_qty = outer_qty * base_per_outer
        if base_per_outer <= 0 or base_qty <= 0:
            if validate:
                raise ValidationError(_("تعذر حساب الكمية الأساسية للتعبئة."))
            return 0.0, 0.0, False
        equivalent_price = (
            input_price / base_per_outer
            if price_method == "package"
            else input_price
        )
        details = self._hosny_build_packaging_chain(
            outer_type, levels, outer_quantity=outer_qty
        )
        summary = _(
            "%(details)s = %(total)s %(unit)s",
            details=details,
            total=self._hosny_number(base_qty),
            unit=product.uom_id.display_name,
        )
        return base_qty, equivalent_price, summary

    @api.depends(
        "product_id",
        "product_id.uom_id",
        "hosny_line_packaging_enabled",
        "hosny_outer_packaging_type_id",
        "hosny_outer_packaging_type_id.name",
        "hosny_outer_package_qty",
        "hosny_has_inner_packaging",
        "hosny_inner_packaging_type_id",
        "hosny_inner_packaging_type_id.name",
        "hosny_inner_package_qty",
        "hosny_line_content_qty",
        "hosny_line_content_uom_id",
        "hosny_line_content_uom_id.name",
        "hosny_packaging_price_method",
        "hosny_packaging_input_price",
        "hosny_packaging_level_ids.sequence",
        "hosny_packaging_level_ids.content_type",
        "hosny_packaging_level_ids.packaging_type_id",
        "hosny_packaging_level_ids.packaging_type_id.name",
        "hosny_packaging_level_ids.quantity",
        "hosny_packaging_level_ids.final_uom_id",
        "hosny_packaging_level_ids.final_uom_id.name",
    )
    def _compute_hosny_line_packaging_results(self):
        for line in self:
            base_qty, equivalent_price, summary = line._hosny_get_line_packaging_result()
            line.hosny_line_base_qty = base_qty
            line.hosny_main_package_base_qty = (
                base_qty / line.hosny_outer_package_qty
                if base_qty and line.hosny_outer_package_qty
                else 0.0
            )
            line.hosny_packaging_equivalent_unit_price = equivalent_price
            line.hosny_line_packaging_summary = summary

    @api.depends("hosny_packaging_level_ids")
    def _compute_hosny_packaging_level_count(self):
        for line in self:
            line.hosny_packaging_level_count = len(line.hosny_packaging_level_ids)

    @api.depends(
        "hosny_line_packaging_enabled",
        "hosny_outer_packaging_type_id.name",
        "hosny_outer_package_qty",
        "hosny_main_package_base_qty",
        "hosny_line_base_qty",
        "hosny_packaging_equivalent_unit_price",
        "hosny_packaging_input_price",
        "hosny_packaging_price_method",
        "hosny_line_packaging_summary",
        "product_id.uom_id.name",
        "price_subtotal",
        "price_total",
        "currency_id.symbol",
    )
    def _compute_hosny_packaging_summary_display(self):
        for line in self:
            if not line.hosny_line_packaging_enabled or not line.product_id:
                line.hosny_summary_package_content = _("لم تُضف تفاصيل تعبئة بعد")
                line.hosny_summary_total_quantity = "—"
                line.hosny_summary_equivalent_price = "—"
                line.hosny_summary_subtotal = "—"
                line.hosny_summary_total = "—"
                continue
            unit_name = line.product_id.uom_id.display_name
            currency = line.currency_id.symbol or line.currency_id.name or ""
            package_name = line.hosny_outer_packaging_type_id.display_name or _("تعبئة")
            line.hosny_summary_package_content = _(
                "1 %(package)s = %(qty)s %(unit)s",
                package=package_name,
                qty=f"{line.hosny_main_package_base_qty:,.4f}",
                unit=unit_name,
            )
            line.hosny_summary_total_quantity = _(
                "%(packages)s %(package)s = %(qty)s %(unit)s",
                packages=f"{line.hosny_outer_package_qty:g}",
                package=package_name,
                qty=f"{line.hosny_line_base_qty:,.4f}",
                unit=unit_name,
            )
            line.hosny_summary_equivalent_price = _(
                "%(price)s %(currency)s / %(unit)s",
                price=f"{line.hosny_packaging_equivalent_unit_price:,.4f}",
                currency=currency,
                unit=unit_name,
            )
            line.hosny_summary_subtotal = _(
                "%(amount)s %(currency)s",
                amount=f"{line.price_subtotal:,.2f}",
                currency=currency,
            )
            line.hosny_summary_total = _(
                "%(amount)s %(currency)s",
                amount=f"{line.price_total:,.2f}",
                currency=currency,
            )

    def _hosny_apply_line_packaging(self):
        for line in self.filtered("hosny_line_packaging_enabled"):
            base_qty, equivalent_price, _summary = line._hosny_get_line_packaging_result()
            if not base_qty or not line.product_id:
                continue
            line.product_uom_id = line.product_id.uom_id
            line.product_qty = base_qty
            line.price_unit = equivalent_price
            line.technical_price_unit = equivalent_price
            line.hosny_purchase_packaging_id = False

    @api.onchange("hosny_line_packaging_enabled")
    def _onchange_hosny_line_packaging_enabled(self):
        for line in self:
            if line.hosny_line_packaging_enabled and line.product_id:
                if not line.hosny_packaging_level_ids:
                    line.hosny_packaging_level_ids = [
                        Command.create({
                            "sequence": 10,
                            "content_type": "base_uom",
                            "quantity": 1.0,
                            "final_uom_id": line.product_id.uom_id.id,
                        })
                    ]
                line.hosny_outer_package_qty = line.hosny_outer_package_qty or 1.0
                line.hosny_packaging_input_price = (
                    line.hosny_packaging_input_price or line.price_unit
                )
            elif not line.hosny_line_packaging_enabled:
                line.hosny_outer_packaging_type_id = False
                line.hosny_outer_package_qty = 0.0
                line.hosny_has_inner_packaging = False
                line.hosny_inner_packaging_type_id = False
                line.hosny_inner_package_qty = 0.0
                line.hosny_line_content_qty = 0.0
                line.hosny_line_content_uom_id = False
                line.hosny_packaging_price_method = "package"
                line.hosny_packaging_input_price = 0.0
                line.hosny_packaging_level_ids = [Command.clear()]
            line._hosny_apply_line_packaging()

    @api.onchange("hosny_purchase_packaging_template_id")
    def _onchange_hosny_purchase_packaging_template_id(self):
        for line in self:
            template = line.hosny_purchase_packaging_template_id
            if not template:
                # Manual entry only detaches the origin.  The current snapshot
                # remains intact, so no confirmation or data loss is needed.
                continue
            company = line.company_id or self.env.company
            if (
                not template.active
                or not line.product_id
                or template.product_tmpl_id != line.product_id.product_tmpl_id
                or (template.company_id and template.company_id != company)
            ):
                line.hosny_purchase_packaging_template_id = False
                raise ValidationError(
                    _("The saved packaging is not available for this product and company.")
                )
            template._structure_result(validate=True)
            package_count = line.hosny_outer_package_qty or 1.0
            input_price = line.hosny_packaging_input_price or line.price_unit
            line.hosny_line_packaging_enabled = True
            line.hosny_outer_packaging_type_id = template.main_packaging_type_id
            line.hosny_outer_package_qty = package_count
            line.hosny_packaging_level_ids = [
                Command.clear(),
                *template._snapshot_level_commands(),
            ]
            line.hosny_packaging_input_price = input_price
            line._onchange_hosny_packaging_level_ids()
            line._hosny_apply_line_packaging()

    @api.onchange("hosny_outer_packaging_type_id", "hosny_outer_package_qty")
    def _onchange_hosny_outer_packaging(self):
        for line in self:
            if (
                line.product_id
                and line.hosny_outer_packaging_type_id
                and line.hosny_outer_package_qty > 0
            ):
                line.hosny_line_packaging_enabled = True
                if not line.hosny_packaging_level_ids:
                    line.hosny_packaging_level_ids = [Command.create({
                        "sequence": 10,
                        "content_type": "base_uom",
                        "quantity": 1.0,
                        "final_uom_id": line.product_id.uom_id.id,
                    })]
                line.hosny_packaging_input_price = (
                    line.hosny_packaging_input_price or line.price_unit
                )
            line._hosny_apply_line_packaging()

    @api.onchange("hosny_packaging_level_ids")
    def _onchange_hosny_packaging_level_ids(self):
        for line in self:
            levels = line.hosny_packaging_level_ids.sorted("sequence")
            packaging_levels = levels.filtered(
                lambda level: level.content_type == "packaging"
            )
            final_levels = levels.filtered(
                lambda level: level.content_type == "base_uom"
            )
            line.hosny_line_packaging_enabled = bool(
                levels
                and line.hosny_outer_packaging_type_id
                and line.hosny_outer_package_qty > 0
            )
            first_inner = packaging_levels[:1]
            final_level = final_levels[:1]
            line.hosny_has_inner_packaging = bool(first_inner)
            line.hosny_inner_packaging_type_id = first_inner.packaging_type_id
            line.hosny_inner_package_qty = first_inner.quantity if first_inner else 0.0
            line.hosny_line_content_qty = final_level.quantity if final_level else 0.0
            line.hosny_line_content_uom_id = final_level.final_uom_id
            line._hosny_apply_line_packaging()

    @api.onchange("hosny_has_inner_packaging")
    def _onchange_hosny_has_inner_packaging(self):
        for line in self:
            if line.hosny_has_inner_packaging:
                line.hosny_inner_package_qty = line.hosny_inner_package_qty or 1.0
            else:
                line.hosny_inner_packaging_type_id = False
                line.hosny_inner_package_qty = 0.0
            line._hosny_apply_line_packaging()

    @api.onchange(
        "hosny_outer_packaging_type_id",
        "hosny_outer_package_qty",
        "hosny_inner_packaging_type_id",
        "hosny_inner_package_qty",
        "hosny_line_content_qty",
        "hosny_line_content_uom_id",
        "hosny_packaging_price_method",
        "hosny_packaging_input_price",
        "hosny_packaging_level_ids",
    )
    def _onchange_hosny_line_packaging_details(self):
        self._hosny_apply_line_packaging()

    def _product_id_change(self):
        result = super()._product_id_change()
        for line in self:
            line.hosny_duplicate_warning_acknowledged = False
            line.hosny_purchase_packaging_id = False
            line.hosny_purchase_packaging_template_id = False
            line.hosny_line_packaging_enabled = False
            line.hosny_outer_packaging_type_id = False
            line.hosny_outer_package_qty = 0.0
            line.hosny_has_inner_packaging = False
            line.hosny_inner_packaging_type_id = False
            line.hosny_inner_package_qty = 0.0
            line.hosny_line_content_qty = 0.0
            line.hosny_line_content_uom_id = False
            line.hosny_packaging_input_price = 0.0
            line.hosny_packaging_level_ids = [Command.clear()]
        return result

    @api.onchange("product_id")
    def _onchange_hosny_purchase_line_product_validation(self):
        """Present the legacy duplicate check as a non-blocking warning popup."""
        result = super()._onchange_hosny_purchase_line_product_validation()
        if result.get("warning") and self[:1].product_id:
            result["warning"] = {
                "title": self.env._("Duplicate Product Warning"),
                "message": self.env._(
                    "The product %(product)s already exists on another purchase line.",
                    product=self[:1].product_id.display_name,
                ),
                "type": "dialog",
            }
        return result

    @api.onchange("hosny_purchase_packaging_id")
    def _onchange_hosny_purchase_packaging_id(self):
        for line in self:
            if line.hosny_line_packaging_enabled:
                line.hosny_purchase_packaging_id = False
            elif line.hosny_purchase_packaging_id:
                line.product_uom_id = line.hosny_purchase_packaging_id.uom_id
            elif line.product_id:
                line.product_uom_id = line.product_id.uom_id

    @api.depends(
        "product_id",
        "product_id.uom_id",
        "product_id.uom_ids",
        "product_id.seller_ids",
        "product_id.seller_ids.product_uom_id",
        "hosny_purchase_packaging_id",
    )
    def _compute_allowed_uom_ids(self):
        super()._compute_allowed_uom_ids()
        for line in self.filtered("hosny_purchase_packaging_id"):
            line.allowed_uom_ids |= line.hosny_purchase_packaging_id.uom_id

    @api.model
    def _hosny_prepare_new_packaging_vals(self, vals, line=None):
        values = dict(vals)
        line = line or self.new()
        if line.id and "product_id" in values:
            new_product = self.env["product.product"].browse(values["product_id"])
            if new_product != line.product_id:
                values.update(
                    hosny_duplicate_warning_acknowledged=False,
                    hosny_line_packaging_enabled=False,
                    hosny_outer_packaging_type_id=False,
                    hosny_outer_package_qty=0.0,
                    hosny_has_inner_packaging=False,
                    hosny_inner_packaging_type_id=False,
                    hosny_inner_package_qty=0.0,
                    hosny_line_content_qty=0.0,
                    hosny_line_content_uom_id=False,
                    hosny_packaging_input_price=0.0,
                    hosny_packaging_level_ids=[Command.clear()],
                    hosny_purchase_packaging_id=False,
                    hosny_purchase_packaging_template_id=False,
                )
                return values

        if values.get("hosny_purchase_packaging_template_id"):
            template = self.env["hosny.purchase.packaging.template"].browse(
                self._hosny_relational_id(
                    values["hosny_purchase_packaging_template_id"]
                )
            ).exists()
            product = self.env["product.product"].browse(
                self._hosny_relational_id(values.get("product_id", line.product_id))
            ).exists()
            company = line.company_id or self.env.company
            if (
                not template
                or not template.active
                or not product
                or template.product_tmpl_id != product.product_tmpl_id
                or (template.company_id and template.company_id != company)
            ):
                raise ValidationError(
                    _("The saved packaging is not available for this product and company.")
                )

        if "hosny_packaging_level_ids" in values:
            has_levels = bool(line._hosny_packaging_levels_for_values(values))
            outer_type_id = self._hosny_relational_id(
                values.get(
                    "hosny_outer_packaging_type_id",
                    line.hosny_outer_packaging_type_id,
                )
            )
            outer_qty = values.get(
                "hosny_outer_package_qty", line.hosny_outer_package_qty
            )
            values["hosny_line_packaging_enabled"] = bool(
                has_levels and outer_type_id and outer_qty > 0
            )
        enabled = values.get(
            "hosny_line_packaging_enabled", line.hosny_line_packaging_enabled
        )
        if not enabled:
            if "hosny_line_packaging_enabled" in values:
                values.update(
                    hosny_outer_packaging_type_id=False,
                    hosny_outer_package_qty=0.0,
                    hosny_has_inner_packaging=False,
                    hosny_inner_packaging_type_id=False,
                    hosny_inner_package_qty=0.0,
                    hosny_line_content_qty=0.0,
                    hosny_line_content_uom_id=False,
                    hosny_packaging_price_method="package",
                    hosny_packaging_input_price=0.0,
                    hosny_packaging_level_ids=[Command.clear()],
                )
            packaging_id = values.get(
                "hosny_purchase_packaging_id", line.hosny_purchase_packaging_id.id
            )
            packaging = self.env["hosny.purchase.packaging"].browse(packaging_id)
            if packaging:
                values["product_uom_id"] = packaging.uom_id.id
            return values
        candidate = {}
        for field_name in self._NEW_PACKAGING_DETAIL_FIELDS | {"product_id"}:
            if field_name in values:
                candidate[field_name] = values[field_name]
            elif line and field_name != "hosny_packaging_level_ids":
                field_value = line[field_name]
                candidate[field_name] = (
                    field_value.id
                    if isinstance(field_value, models.BaseModel)
                    else field_value
                )
        base_qty, equivalent_price, _summary = line._hosny_get_line_packaging_result(
            candidate, validate=True
        )
        product = self.env["product.product"].browse(candidate["product_id"])
        levels = line._hosny_packaging_levels_for_values(candidate)
        current_level_ids = set(line.hosny_packaging_level_ids.ids)
        level_commands = []
        for index, level in enumerate(levels, start=1):
            content_type = level.get("content_type") or "packaging"
            level_values = {
                "sequence": index * 10,
                "content_type": content_type,
                "packaging_type_id": (
                    self._hosny_relational_id(level.get("packaging_type_id"))
                    if content_type == "packaging"
                    else False
                ),
                "quantity": level["quantity"],
                "final_uom_id": (
                    self._hosny_relational_id(level.get("final_uom_id"))
                    if content_type == "base_uom"
                    else False
                ),
            }
            if level.get("id"):
                current_level_ids.discard(level["id"])
                level_commands.append(Command.update(level["id"], level_values))
            else:
                level_commands.append(Command.create(level_values))
        level_commands.extend(Command.delete(level_id) for level_id in current_level_ids)
        packaging_levels = [
            level for level in levels if level.get("content_type") == "packaging"
        ]
        final_levels = [
            level for level in levels if level.get("content_type") == "base_uom"
        ]
        first_inner = packaging_levels[0] if packaging_levels else False
        final_level = final_levels[0] if final_levels else False
        values.update(
            product_qty=base_qty,
            product_uom_id=product.uom_id.id,
            price_unit=equivalent_price,
            technical_price_unit=equivalent_price,
            hosny_purchase_packaging_id=False,
            hosny_packaging_level_ids=level_commands,
            hosny_has_inner_packaging=bool(first_inner),
            hosny_inner_packaging_type_id=(
                self._hosny_relational_id(first_inner.get("packaging_type_id"))
                if first_inner
                else False
            ),
            hosny_inner_package_qty=(first_inner["quantity"] if first_inner else 0.0),
            hosny_line_content_qty=(final_level["quantity"] if final_level else 0.0),
            hosny_line_content_uom_id=(
                self._hosny_relational_id(final_level.get("final_uom_id"))
                if final_level
                else False
            ),
        )
        return values

    @api.model_create_multi
    def create(self, vals_list):
        prepared_vals_list = [
            self._hosny_prepare_new_packaging_vals(vals) for vals in vals_list
        ]
        created_lines = super(PurchaseOrderLine, self.with_context(
            skip_hosny_level_parent_refresh=True
        )).create(prepared_vals_list)
        # Do not leak the internal child-refresh suppression context to the
        # caller.  Otherwise a later direct edit of a level can look saved but
        # leave the purchase quantity stale until a full reload.
        lines = created_lines.with_env(self.env)
        lines.filtered(lambda line: not line.hosny_line_packaging_enabled)._sync_explicit_packaging_from_uom()
        return lines

    def write(self, vals):
        if self.env.context.get("skip_hosny_line_packaging_prepare"):
            return super().write(vals)
        if self._NEW_PACKAGING_DETAIL_FIELDS & set(vals) or "product_id" in vals:
            for line in self:
                prepared = self._hosny_prepare_new_packaging_vals(vals, line=line)
                super(PurchaseOrderLine, line.with_context(
                    skip_hosny_line_packaging_prepare=True,
                    skip_hosny_level_parent_refresh=True,
                )).write(prepared)
            return True

        prepared_vals = dict(vals)
        if (
            "hosny_purchase_packaging_id" in prepared_vals
            and not self.env.context.get("hosny_keep_product_uom")
        ):
            packaging = self.env["hosny.purchase.packaging"].browse(
                prepared_vals["hosny_purchase_packaging_id"]
            )
            prepared_vals["product_uom_id"] = (
                packaging.uom_id.id
                if packaging
                else (self.product_id.uom_id.id if len(self.product_id) == 1 else False)
            )
        result = super().write(prepared_vals)
        if not self.env.context.get("skip_hosny_packaging_sync") and (
            {"product_id", "product_uom_id"} & set(prepared_vals)
        ):
            self._sync_explicit_packaging_from_uom()
        return result

    def _hosny_refresh_from_levels(self):
        """Keep standard purchase fields correct after a direct level edit."""
        for line in self.filtered("hosny_line_packaging_enabled"):
            base_qty, equivalent_price, _summary = (
                line._hosny_get_line_packaging_result(validate=True)
            )
            levels = line.hosny_packaging_level_ids.sorted("sequence")
            if not levels:
                continue
            packaging_levels = levels.filtered(
                lambda level: level.content_type == "packaging"
            )
            final_levels = levels.filtered(
                lambda level: level.content_type == "base_uom"
            )
            first_inner = packaging_levels[:1]
            final_level = final_levels[:1]
            super(PurchaseOrderLine, line.with_context(
                skip_hosny_line_packaging_prepare=True,
                skip_hosny_level_parent_refresh=True,
                skip_hosny_packaging_sync=True,
            )).write({
                "product_qty": base_qty,
                "product_uom_id": line.product_id.uom_id.id,
                "price_unit": equivalent_price,
                "technical_price_unit": equivalent_price,
                "hosny_has_inner_packaging": bool(first_inner),
                "hosny_inner_packaging_type_id": (
                    first_inner.packaging_type_id.id or False
                ),
                "hosny_inner_package_qty": (
                    first_inner.quantity if first_inner else 0.0
                ),
                "hosny_line_content_qty": (
                    final_level.quantity if final_level else 0.0
                ),
                "hosny_line_content_uom_id": (
                    final_level.final_uom_id.id or False
                ),
            })

    def _sync_explicit_packaging_from_uom(self):
        Packaging = self.env["hosny.purchase.packaging"]
        for line in self.filtered(
            lambda item: item.product_id
            and not item.display_type
            and not item.hosny_line_packaging_enabled
        ):
            matching = Packaging._purchase_configs(
                line.product_id, line.company_id or self.env.company
            ).filtered(
                lambda config: config.purchase_ok and config.uom_id == line.product_uom_id
            )[:1]
            if line.hosny_purchase_packaging_id != matching:
                line.with_context(
                    skip_hosny_packaging_sync=True,
                    hosny_keep_product_uom=True,
                ).write({"hosny_purchase_packaging_id": matching.id or False})

    def _prepare_account_move_line(self, move=False):
        values = super()._prepare_account_move_line(move=move)
        values.update(
            hosny_purchase_packaging_id=self.hosny_purchase_packaging_id.id or False,
            hosny_line_packaging_enabled=self.hosny_line_packaging_enabled,
            hosny_outer_packaging_type_id=self.hosny_outer_packaging_type_id.id or False,
            hosny_outer_package_qty=self.hosny_outer_package_qty,
            hosny_has_inner_packaging=self.hosny_has_inner_packaging,
            hosny_inner_packaging_type_id=self.hosny_inner_packaging_type_id.id or False,
            hosny_inner_package_qty=self.hosny_inner_package_qty,
            hosny_line_content_qty=self.hosny_line_content_qty,
            hosny_line_content_uom_id=self.hosny_line_content_uom_id.id or False,
            hosny_packaging_price_method=self.hosny_packaging_price_method,
            hosny_packaging_input_price=self.currency_id._convert(
                self.hosny_packaging_input_price,
                move.currency_id if move else self.currency_id,
                self.company_id,
                move.date if move else fields.Date.today(),
                round=False,
            ),
            hosny_line_packaging_summary=self.hosny_line_packaging_summary,
            hosny_packaging_unit_base_qty=(
                self.hosny_line_base_qty / self.hosny_outer_package_qty
                if self.hosny_line_packaging_enabled and self.hosny_outer_package_qty
                else 0.0
            ),
        )
        return values

    @api.constrains(
        "hosny_packaging_level_ids",
        "product_id",
        "product_uom_id",
        "product_qty",
        "company_id",
        "hosny_purchase_packaging_id",
        "hosny_line_packaging_enabled",
        "hosny_outer_packaging_type_id",
        "hosny_outer_package_qty",
        "hosny_has_inner_packaging",
        "hosny_inner_packaging_type_id",
        "hosny_inner_package_qty",
        "hosny_line_content_qty",
        "hosny_line_content_uom_id",
        "hosny_packaging_price_method",
        "hosny_packaging_input_price",
    )
    def _check_hosny_purchase_packaging(self):
        precision = self.env["decimal.precision"].precision_get("Product Unit")
        for line in self.filtered(lambda item: not item.display_type and item.product_id):
            if not line.product_uom_id:
                continue
            if not line.product_uom_id._has_common_reference(line.product_id.uom_id):
                raise ValidationError(_("وحدة الشراء غير متوافقة مع وحدة قياس المنتج."))
            if line.hosny_line_packaging_enabled:
                base_qty, _price, _summary = line._hosny_get_line_packaging_result(
                    validate=True
                )
                if line.product_uom_id != line.product_id.uom_id:
                    raise ValidationError(
                        _("يجب أن تكون وحدة سطر الشراء هي الوحدة الأساسية للمنتج عند استخدام التعبئة.")
                    )
                if float_compare(
                    line.product_qty, base_qty, precision_digits=precision
                ) != 0:
                    raise ValidationError(
                        _("الكمية النهائية لا تطابق الكمية المحسوبة من تفاصيل التعبئة.")
                    )
                continue

            packaging = line.hosny_purchase_packaging_id
            if packaging:
                if (
                    packaging.product_id != line.product_id
                    or not packaging.purchase_ok
                    or (
                        packaging.company_id
                        and line.company_id
                        and packaging.company_id != line.company_id
                    )
                    or packaging.uom_id != line.product_uom_id
                ):
                    raise ValidationError(
                        _("التعبئة المحددة غير مفعلة للشراء لهذا المنتج وهذه الشركة.")
                    )
                if line.product_qty <= 0:
                    raise ValidationError(_("عدد تعبئات الشراء يجب أن يكون أكبر من صفر."))
