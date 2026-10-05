from collections import Counter

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class PurchaseRequisition(models.Model):
    _inherit = "purchase.requisition"

    reference = fields.Char(string="Agreement Name", tracking=True)

    def init(self):
        super().init()
        self.env.cr.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1
                      FROM pg_constraint
                     WHERE conname = 'purchase_requisition_hosny_name_unique'
                ) THEN
                    ALTER TABLE purchase_requisition
                        ADD CONSTRAINT purchase_requisition_hosny_name_unique UNIQUE (name);
                END IF;
            END
            $$;
        """)

    @api.constrains("name")
    def _check_hosny_unique_name(self):
        for agreement in self.filtered("name"):
            duplicate = self.search_count([
                ("name", "=", agreement.name),
                ("id", "!=", agreement.id),
            ])
            if duplicate:
                raise ValidationError(_("Purchase agreement names must be unique: %s", agreement.name))

    def _check_hosny_name_available(self, name):
        if not name:
            return
        duplicate = self.search_count([
            ("name", "=", name),
            ("id", "not in", self.ids),
        ])
        if duplicate:
            raise ValidationError(_("Purchase agreement names must be unique: %s", name))

    @api.model_create_multi
    def create(self, vals_list):
        requested_names = [
            vals["reference"].strip()
            for vals in vals_list
            if vals.get("reference") and vals["reference"].strip()
        ]
        duplicate_requested_names = [name for name, count in Counter(requested_names).items() if count > 1]
        if duplicate_requested_names:
            raise ValidationError(_("Purchase agreement names must be unique: %s", ", ".join(duplicate_requested_names)))
        for vals in vals_list:
            reference = vals.get("reference")
            if reference and reference.strip():
                self._check_hosny_name_available(reference.strip())
        records = super().create(vals_list)
        for record, vals in zip(records, vals_list):
            reference = vals.get("reference")
            if reference and reference.strip():
                record.name = reference.strip()
        return records

    def write(self, vals):
        if self.env.context.get("skip_hosny_agreement_name_sync"):
            return super().write(vals)

        clean_reference = vals.get("reference")
        vals_to_write = dict(vals)
        if isinstance(clean_reference, str) and clean_reference.strip():
            vals_to_write["reference"] = clean_reference.strip()
            vals_to_write["name"] = clean_reference.strip()
            self._check_hosny_name_available(clean_reference.strip())

        res = super().write(vals_to_write)
        if ("requisition_type" in vals or "company_id" in vals) and "reference" not in vals:
            for agreement in self.filtered(lambda item: item.reference and item.reference.strip()):
                agreement.with_context(skip_hosny_agreement_name_sync=True).name = agreement.reference.strip()
        return res


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    analytic_account_id = fields.Many2one(
        "account.analytic.account",
        string="Branch",
        check_company=True,
        copy=True,
    )
    hosny_picking_type_id_domain = fields.Binary(
        compute="_compute_hosny_picking_type_id_domain",
        readonly=True,
    )

    def _hosny_get_picking_type_domain(self):
        self.ensure_one()
        if self.analytic_account_id:
            domain = [
                ("code", "=", "incoming"),
                ("warehouse_id.hosny_analytic_account_id", "=", self.analytic_account_id.id),
            ]
            if self.company_id:
                domain.append(("warehouse_id.company_id", "=", self.company_id.id))
            return domain

        domain = [("code", "=", "incoming")]
        company = self.company_id or self.env.company
        if company:
            domain.extend(["|", ("warehouse_id", "=", False), ("warehouse_id.company_id", "=", company.id)])
        return domain

    def _hosny_get_allowed_picking_types(self):
        self.ensure_one()
        return self.env["stock.picking.type"].search(self._hosny_get_picking_type_domain())

    def _hosny_autoselect_single_picking_type(self):
        for order in self:
            allowed_picking_types = order._hosny_get_allowed_picking_types()
            if order.picking_type_id and order.picking_type_id not in allowed_picking_types:
                order.picking_type_id = False
            if not order.picking_type_id and len(allowed_picking_types) == 1:
                order.picking_type_id = allowed_picking_types

    @api.model
    def _hosny_prepare_auto_picking_type_vals(self, vals, base_order=False):
        if "picking_type_id" in vals or not ({"analytic_account_id", "company_id"} & set(vals)):
            return vals

        probe_vals = {}
        if base_order:
            probe_vals = {
                "company_id": base_order.company_id.id,
                "analytic_account_id": base_order.analytic_account_id.id,
                "picking_type_id": base_order.picking_type_id.id,
            }
        probe_vals.update(vals)
        probe = self.new(probe_vals)
        allowed_picking_types = probe._hosny_get_allowed_picking_types()
        current_picking_type = probe.picking_type_id

        next_picking_type = False
        if current_picking_type and current_picking_type in allowed_picking_types:
            return vals
        if len(allowed_picking_types) == 1:
            next_picking_type = allowed_picking_types.id

        prepared_vals = dict(vals)
        prepared_vals["picking_type_id"] = next_picking_type
        return prepared_vals

    @api.depends("analytic_account_id", "company_id")
    def _compute_hosny_picking_type_id_domain(self):
        for order in self:
            order.hosny_picking_type_id_domain = order._hosny_get_picking_type_domain()

    def _hosny_picking_type_matches_branch(self):
        self.ensure_one()
        if not self.analytic_account_id or not self.picking_type_id:
            return True
        return self.picking_type_id._hosny_matches_analytic_branch(self.analytic_account_id)

    def _hosny_check_picking_type_branch(self):
        invalid_orders = self.filtered(lambda order: not order._hosny_picking_type_matches_branch())
        if invalid_orders:
            raise ValidationError(
                _("The selected destination/operation type does not belong to the selected branch.")
            )

    def _hosny_branch_analytic_distribution(self):
        self.ensure_one()
        return {str(self.analytic_account_id.id): 100.0} if self.analytic_account_id else False

    def _hosny_check_branch_before_confirm(self):
        missing_branch = self.filtered(lambda order: not order.analytic_account_id)
        if missing_branch:
            raise UserError(_("Please select the branch before confirming the purchase order."))

    def _hosny_sync_branch_to_order_lines(self):
        """Keep all product lines aligned with the single header branch value."""
        for order in self.filtered("analytic_account_id"):
            distribution = order._hosny_branch_analytic_distribution()
            lines = order.order_line.filtered(lambda line: not line.display_type)
            lines.with_context(skip_hosny_branch_sync=True).write({
                "analytic_distribution": distribution,
            })

    @api.onchange("analytic_account_id")
    def _onchange_hosny_analytic_account_id(self):
        for order in self:
            distribution = order._hosny_branch_analytic_distribution()
            for line in order.order_line.filtered(lambda item: not item.display_type):
                line.analytic_distribution = distribution
            order._hosny_autoselect_single_picking_type()
        if len(self) == 1:
            return {"domain": {"picking_type_id": self.hosny_picking_type_id_domain or []}}

    @api.constrains("analytic_account_id", "picking_type_id", "company_id")
    def _check_hosny_picking_type_branch(self):
        self._hosny_check_picking_type_branch()

    @api.model_create_multi
    def create(self, vals_list):
        vals_list = [self._hosny_prepare_auto_picking_type_vals(vals) for vals in vals_list]
        orders = super().create(vals_list)
        orders._hosny_check_picking_type_branch()
        orders._hosny_sync_branch_to_order_lines()
        return orders

    def write(self, vals):
        if "picking_type_id" not in vals and {"analytic_account_id", "company_id"} & set(vals):
            if len(self) > 1:
                for order in self:
                    order.write(vals)
                return True
            vals = self._hosny_prepare_auto_picking_type_vals(vals, base_order=self)
        res = super().write(vals)
        if {"analytic_account_id", "picking_type_id", "company_id"} & set(vals):
            self._hosny_check_picking_type_branch()
        if not self.env.context.get("skip_hosny_branch_sync") and (
            "analytic_account_id" in vals or "order_line" in vals
        ):
            self._hosny_sync_branch_to_order_lines()
        return res

    def button_confirm(self):
        orders_to_confirm = self.filtered(lambda order: order.state in ("draft", "sent"))
        orders_to_confirm._hosny_check_branch_before_confirm()
        orders_to_confirm._hosny_check_picking_type_branch()
        return super().button_confirm()

    def _prepare_invoice(self):
        vals = super()._prepare_invoice()
        # Vendor bills in this database require the same branch on the move
        # header, while invoice lines keep the analytic distribution.
        if self.analytic_account_id and "analytic_account_id" in self.env["account.move"]._fields:
            vals["analytic_account_id"] = self.analytic_account_id.id
        return vals

    @api.model
    def _hosny_update_purchase_view_translations(self):
        # XML translated fields expect source-term replacements. These keep the
        # views English in en_US and Arabic in ar_001 even for inherited XML.
        translations_by_xmlid = {
            "hosny_purchase_requisition_name.purchase_order_line_search_hosny_lowest_price": {
                "Lowest Price": "أقل سعر",
            },
            "hosny_purchase_requisition_name.purchase_order_line_compare_tree_hosny_branch": {
                "Company": "الشركة",
            },
            "hosny_purchase_requisition_name.purchase_history_tree_hosny_branch": {
                "Company": "الشركة",
            },
            "hosny_purchase_requisition_name.hosny_purchase_price_history_wizard_form": {
                "Last Purchase Prices": "آخر أسعار الشراء",
                "Product": "المنتج",
                "Branch": "الفرع",
                "Last price": "آخر سعر",
                "Lowest price": "أقل سعر",
                "Highest price": "أعلى سعر",
                "Average price": "متوسط السعر",
                "Purchase Date": "تاريخ الشراء",
                "Vendor": "المورد",
                "Quantity": "الكمية",
                "Unit of Measure": "وحدة القياس",
                "Unit Price": "سعر الوحدة",
                "Taxes": "الضرائب",
                "Total Line Amount": "إجمالي مبلغ البند",
                "Source Reference": "مرجع أمر الشراء / فاتورة المورد",
                "Close": "إغلاق",
            },
            "hosny_purchase_requisition_name.stock_warehouse_form_hosny_branch": {
                "Branch": "الفرع",
            },
        }
        for xmlid, translations in translations_by_xmlid.items():
            view = self.env.ref(xmlid, raise_if_not_found=False)
            if view:
                view.update_field_translations("arch_db", {"ar_001": translations}, source_lang="en_US")
        return True

    def get_compare_line_purchase_invoice_price_history(self):
        """Return the last three posted vendor bill prices per compared product.

        The comparison view can load several PO lines at once, so this method
        fetches all product histories in one SQL query and ranks bill lines per
        product. Purchasers may not have full accounting-line access; only this
        limited historical price payload is exposed, and it is constrained to
        the compared order companies that are currently allowed in the session.
        """
        orders = self.exists()
        if not orders:
            return {}

        compared_orders = orders | orders.mapped("alternative_po_ids")
        product_ids = compared_orders.order_line.filtered(
            lambda line: not line.display_type and line.product_id
        ).mapped("product_id").ids
        if not product_ids:
            return {}

        allowed_company_ids = set(self.env.companies.ids)
        order_company_ids = set(compared_orders.company_id.ids)
        company_ids = list(allowed_company_ids & order_company_ids)
        if not company_ids:
            return {}

        lang = self.env.lang or "en_US"
        self.env.cr.execute(
            """
              WITH ranked_lines AS (
                    SELECT
                        aml.id,
                        aml.product_id,
                        row_number() OVER (
                            PARTITION BY aml.product_id
                            ORDER BY am.invoice_date DESC NULLS LAST, am.id DESC, aml.id DESC
                        ) AS row_number
                      FROM account_move_line aml
                      JOIN account_move am ON am.id = aml.move_id
                     WHERE aml.product_id = ANY(%s)
                       AND am.move_type = 'in_invoice'
                       AND am.state = 'posted'
                       AND am.company_id = ANY(%s)
                       AND (aml.display_type IS NULL OR aml.display_type NOT IN ('line_section', 'line_note'))
                )
                SELECT
                    ranked.product_id,
                    COALESCE(NULLIF(am.name, ''), '/') AS bill_number,
                    am.invoice_date AS bill_date,
                    COALESCE(rp.complete_name, rp.name, '') AS vendor_name,
                    aml.quantity,
                    aml.price_unit,
                    rc.name AS currency_name,
                    COALESCE(
                        uu.name ->> %s,
                        uu.name ->> 'en_US',
                        uu.name ->> 'ar_001',
                        ''
                    ) AS uom_name
                  FROM ranked_lines ranked
                  JOIN account_move_line aml ON aml.id = ranked.id
                  JOIN account_move am ON am.id = aml.move_id
             LEFT JOIN res_partner rp ON rp.id = am.partner_id
             LEFT JOIN res_currency rc ON rc.id = COALESCE(aml.currency_id, am.currency_id)
             LEFT JOIN uom_uom uu ON uu.id = aml.product_uom_id
                 WHERE ranked.row_number <= 3
              ORDER BY ranked.product_id, am.invoice_date DESC NULLS LAST, am.id DESC, aml.id DESC
            """,
            (product_ids, company_ids, lang),
        )

        history_by_product = {product_id: [] for product_id in product_ids}
        for row in self.env.cr.dictfetchall():
            product_id = row["product_id"]
            history_by_product.setdefault(product_id, []).append({
                "bill_number": row["bill_number"],
                "bill_date": fields.Date.to_string(row["bill_date"]) if row["bill_date"] else "",
                "vendor_name": row["vendor_name"],
                "quantity": float(row["quantity"] or 0.0),
                "price_unit": float(row["price_unit"] or 0.0),
                "currency_name": row["currency_name"],
                "uom_name": row["uom_name"],
            })
        return history_by_product


class StockWarehouse(models.Model):
    _inherit = "stock.warehouse"

    hosny_analytic_account_id = fields.Many2one(
        "account.analytic.account",
        string="Branch",
        check_company=True,
        help="Purchase orders for this branch may receive products into this warehouse.",
    )
    hosny_purchase_receipt_location_ids = fields.Many2many(
        "stock.location",
        "hosny_warehouse_purchase_receipt_location_rel",
        "warehouse_id",
        "location_id",
        string="Purchase Receipt Destinations",
        domain="[('usage', '=', 'internal'), ('id', 'child_of', lot_stock_id)]",
        help="Destination locations allowed on purchase receipts for this warehouse.",
    )

    @api.model
    def _hosny_normalized_branch_tokens(self, value):
        replacements = {
            "أ": "ا",
            "إ": "ا",
            "آ": "ا",
            "ى": "ي",
            "ة": "ه",
            "-": " ",
            "/": " ",
        }
        normalized = (value or "").strip()
        for source, target in replacements.items():
            normalized = normalized.replace(source, target)
        stop_words = {"مطعم", "حسني", "مخزن", "فرع", "الفرع"}
        tokens = set()
        for token in normalized.split():
            if token.startswith("ال") and len(token) > 3:
                token = token[2:]
            if token and token not in stop_words:
                tokens.add(token)
        return tokens

    @api.model
    def _hosny_seed_warehouse_branch_mapping(self):
        analytics = self.env["account.analytic.account"].search([])
        analytic_tokens = {
            analytic: self._hosny_normalized_branch_tokens(analytic.display_name)
            for analytic in analytics
        }
        for warehouse in self.search([]):
            warehouse_tokens = self._hosny_normalized_branch_tokens(warehouse.display_name)
            if not warehouse.hosny_analytic_account_id:
                scored = [
                    (len(warehouse_tokens & tokens), analytic)
                    for analytic, tokens in analytic_tokens.items()
                    if not analytic.company_id or analytic.company_id == warehouse.company_id
                ]
                scored = [item for item in scored if item[0]]
                if scored:
                    warehouse.hosny_analytic_account_id = max(scored, key=lambda item: item[0])[1]
            if not warehouse.hosny_purchase_receipt_location_ids and warehouse.lot_stock_id:
                allowed_locations = warehouse.lot_stock_id
                branch_tokens = self._hosny_normalized_branch_tokens(
                    warehouse.hosny_analytic_account_id.display_name
                )
                if "مدينه" in branch_tokens:
                    meat_location = self.env["stock.location"].search([
                        ("id", "child_of", warehouse.lot_stock_id.id),
                        ("usage", "=", "internal"),
                        ("name", "ilike", "لحوم"),
                        ("name", "not ilike", "تام"),
                    ], order="id", limit=1)
                    allowed_locations |= meat_location
                warehouse.hosny_purchase_receipt_location_ids = [(6, 0, allowed_locations.ids)]
        return True


class StockPickingType(models.Model):
    _inherit = "stock.picking.type"

    def _hosny_matches_analytic_branch(self, analytic_account):
        self.ensure_one()
        if not analytic_account:
            return True
        return bool(
            self.code == "incoming"
            and self.warehouse_id
            and self.warehouse_id.hosny_analytic_account_id == analytic_account
        )


class PurchaseOrderLine(models.Model):
    _inherit = "purchase.order.line"

    hosny_compare_company_branch_name = fields.Char(
        string="Company",
        compute="_compute_hosny_compare_company_branch_name",
        store=True,
    )
    hosny_is_lowest_compare_price = fields.Boolean(
        string="Lowest Price",
        compute="_compute_hosny_is_lowest_compare_price",
        search="_search_hosny_is_lowest_compare_price",
    )

    @api.depends("order_id.company_id.name", "order_id.analytic_account_id.name")
    def _compute_hosny_compare_company_branch_name(self):
        for line in self:
            line.hosny_compare_company_branch_name = (
                line.order_id.analytic_account_id.name
                or line.order_id.company_id.display_name
                or ""
            )

    def _get_hosny_lowest_compare_line_ids(self):
        order_id = self.env.context.get("purchase_order_id")
        if not order_id and self.env.context.get("active_model") == "purchase.order":
            order_id = self.env.context.get("active_id")
        order = self.env["purchase.order"].browse(order_id).exists() if order_id else self.env["purchase.order"]
        if not order:
            return []
        return order.get_tender_best_lines()[2]

    def _compute_hosny_is_lowest_compare_price(self):
        lowest_line_ids = set(self._get_hosny_lowest_compare_line_ids())
        for line in self:
            line.hosny_is_lowest_compare_price = line.id in lowest_line_ids

    def _search_hosny_is_lowest_compare_price(self, operator, value):
        lowest_line_ids = self._get_hosny_lowest_compare_line_ids()
        if operator in ("=", "=="):
            wants_lowest = bool(value)
        elif operator == "!=":
            wants_lowest = not bool(value)
        elif operator == "in":
            wants_lowest = True in value
        elif operator == "not in":
            wants_lowest = True not in value
        else:
            wants_lowest = False
        if wants_lowest:
            return [("id", "in", lowest_line_ids or [0])]
        return [("id", "not in", lowest_line_ids or [0])]

    def _hosny_purchase_history_tax_field(self):
        if "tax_ids" in self._fields:
            return "tax_ids"
        if "taxes_id" in self._fields:
            return "taxes_id"
        return False

    def _hosny_purchase_history_uom_field(self):
        if "product_uom_id" in self._fields:
            return "product_uom_id"
        if "product_uom" in self._fields:
            return "product_uom"
        return False

    def _hosny_purchase_history_is_arabic(self):
        return (self.env.lang or "").lower().startswith("ar")

    def _hosny_purchase_history_title(self):
        return "آخر أسعار الشراء" if self._hosny_purchase_history_is_arabic() else _("Last Purchase Prices")

    def _hosny_purchase_history_empty_message(self):
        return (
            "لا توجد أسعار شراء سابقة لهذا الصنف"
            if self._hosny_purchase_history_is_arabic()
            else _("No previous purchase prices found for this product")
        )

    @api.model
    def _hosny_purchase_history_title_for_lang(self):
        return "آخر أسعار الشراء" if (self.env.lang or "").lower().startswith("ar") else _("Last Purchase Prices")

    @api.model
    def _hosny_purchase_history_empty_message_for_lang(self):
        return (
            "لا توجد أسعار شراء سابقة لهذا الصنف"
            if (self.env.lang or "").lower().startswith("ar")
            else _("No previous purchase prices found for this product")
        )

    def _hosny_purchase_history_date(self):
        self.ensure_one()
        purchase_datetime = self.order_id.date_approve or self.order_id.date_order or self.create_date
        return fields.Date.to_date(purchase_datetime) or fields.Date.context_today(self)

    def _hosny_purchase_history_source_reference(self):
        self.ensure_one()
        references = []
        if self.order_id.name:
            references.append(self.order_id.name)
        bills = self.invoice_lines.mapped("move_id").filtered(
            lambda move: move.move_type in ("in_invoice", "in_refund") and move.state != "cancel"
        )
        for bill in bills:
            reference = bill.name if bill.name and bill.name != "/" else bill.ref
            if reference and reference not in references:
                references.append(reference)
        return " / ".join(references)

    def _hosny_purchase_history_line_vals(self, target_currency, sequence):
        self.ensure_one()
        tax_field = self._hosny_purchase_history_tax_field()
        uom_field = self._hosny_purchase_history_uom_field()
        purchase_date = self._hosny_purchase_history_date()
        source_currency = self.currency_id or self.order_id.currency_id or target_currency
        company = self.company_id or self.order_id.company_id or self.env.company
        price_unit = self.price_unit
        total_amount = self.price_total if "price_total" in self._fields else self.price_subtotal
        if source_currency and target_currency and source_currency != target_currency:
            price_unit = source_currency._convert(price_unit, target_currency, company, purchase_date)
            total_amount = source_currency._convert(total_amount, target_currency, company, purchase_date)

        taxes = self[tax_field] if tax_field else self.env["account.tax"]
        return {
            "sequence": sequence,
            "order_line_id": self.id,
            "currency_id": target_currency.id,
            "purchase_date": purchase_date,
            "vendor_id": self.order_id.partner_id.id,
            "branch_id": self.order_id.analytic_account_id.id,
            "quantity": self.product_qty,
            "product_uom_id": self[uom_field].id if uom_field and self[uom_field] else False,
            "price_unit": price_unit,
            "tax_display": ", ".join(taxes.with_context(lang=self.env.lang).mapped("name")) or "-",
            "total_amount": total_amount,
            "source_reference": self._hosny_purchase_history_source_reference(),
        }

    def action_hosny_open_price_history(self):
        self.ensure_one()
        if not self.product_id:
            raise UserError(_("Please select a product first."))

        history_lines = self.search([
            ("product_id", "=", self.product_id.id),
            ("display_type", "=", False),
            ("order_id.state", "in", ("purchase", "done")),
            ("id", "!=", self.id),
        ])
        history_lines = history_lines.sorted(
            key=lambda line: (
                line.order_id.date_approve or line.order_id.date_order or line.create_date,
                line.order_id.id,
                line.id,
            ),
            reverse=True,
        )[:3]
        target_currency = self.order_id.currency_id or self.env.company.currency_id
        history_vals = [
            line._hosny_purchase_history_line_vals(target_currency, index * 10)
            for index, line in enumerate(history_lines, start=1)
        ]
        prices = [vals["price_unit"] for vals in history_vals]
        wizard = self.env["hosny.purchase.price.history.wizard"].create({
            "purchase_line_id": self.id,
            "product_id": self.product_id.id,
            "currency_id": target_currency.id,
            "has_history": bool(history_vals),
            "last_price": prices[0] if prices else 0.0,
            "lowest_price": min(prices) if prices else 0.0,
            "highest_price": max(prices) if prices else 0.0,
            "average_price": sum(prices) / len(prices) if prices else 0.0,
            "empty_message": self._hosny_purchase_history_empty_message(),
            "line_ids": [(0, 0, vals) for vals in history_vals],
        })
        return {
            "name": self._hosny_purchase_history_title(),
            "type": "ir.actions.act_window",
            "res_model": "hosny.purchase.price.history.wizard",
            "view_mode": "form",
            "views": [(False, "form")],
            "res_id": wizard.id,
            "target": "new",
        }

    @api.model
    def action_hosny_open_price_history_for_product(self, product_id, currency_id=False):
        product = self.env["product.product"].browse(product_id).exists()
        if not product:
            raise UserError(_("Please select a product first."))

        history_lines = self.search([
            ("product_id", "=", product.id),
            ("display_type", "=", False),
            ("order_id.state", "in", ("purchase", "done")),
        ])
        history_lines = history_lines.sorted(
            key=lambda line: (
                line.order_id.date_approve or line.order_id.date_order or line.create_date,
                line.order_id.id,
                line.id,
            ),
            reverse=True,
        )[:3]
        target_currency = (
            self.env["res.currency"].browse(currency_id).exists()
            or self.env.company.currency_id
        )
        history_vals = [
            line._hosny_purchase_history_line_vals(target_currency, index * 10)
            for index, line in enumerate(history_lines, start=1)
        ]
        prices = [vals["price_unit"] for vals in history_vals]
        wizard = self.env["hosny.purchase.price.history.wizard"].create({
            "product_id": product.id,
            "currency_id": target_currency.id,
            "has_history": bool(history_vals),
            "last_price": prices[0] if prices else 0.0,
            "lowest_price": min(prices) if prices else 0.0,
            "highest_price": max(prices) if prices else 0.0,
            "average_price": sum(prices) / len(prices) if prices else 0.0,
            "empty_message": self._hosny_purchase_history_empty_message_for_lang(),
            "line_ids": [(0, 0, vals) for vals in history_vals],
        })
        return {
            "name": self._hosny_purchase_history_title_for_lang(),
            "type": "ir.actions.act_window",
            "res_model": "hosny.purchase.price.history.wizard",
            "view_mode": "form",
            "views": [(False, "form")],
            "res_id": wizard.id,
            "target": "new",
        }
