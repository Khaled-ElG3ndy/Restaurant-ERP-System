from odoo import fields, models, _


def _hosny_is_arabic(env):
    return (env.lang or "").lower().startswith("ar")


class HosnyPurchasePriceHistoryWizard(models.TransientModel):
    _name = "hosny.purchase.price.history.wizard"
    _description = "Purchase Price History"

    purchase_line_id = fields.Many2one("purchase.order.line", string="Purchase Order Line", readonly=True)
    product_id = fields.Many2one("product.product", string="Product", readonly=True)
    currency_id = fields.Many2one("res.currency", string="Currency", readonly=True)
    line_ids = fields.One2many(
        "hosny.purchase.price.history.wizard.line",
        "wizard_id",
        string="History Lines",
        readonly=True,
    )
    has_history = fields.Boolean(string="Has History", readonly=True)
    last_price = fields.Monetary(string="Last Price", currency_field="currency_id", readonly=True)
    lowest_price = fields.Monetary(string="Lowest Price", currency_field="currency_id", readonly=True)
    highest_price = fields.Monetary(string="Highest Price", currency_field="currency_id", readonly=True)
    average_price = fields.Monetary(string="Average Price", currency_field="currency_id", readonly=True)
    empty_message = fields.Char(
        string="Empty Message",
        default=lambda self: (
            "لا توجد أسعار شراء سابقة لهذا الصنف"
            if _hosny_is_arabic(self.env)
            else _("No previous purchase prices found for this product")
        ),
        readonly=True,
    )


class HosnyPurchasePriceHistoryWizardLine(models.TransientModel):
    _name = "hosny.purchase.price.history.wizard.line"
    _description = "Purchase Price History Line"
    _order = "sequence, id"

    wizard_id = fields.Many2one(
        "hosny.purchase.price.history.wizard",
        required=True,
        ondelete="cascade",
    )
    sequence = fields.Integer(default=10)
    order_line_id = fields.Many2one("purchase.order.line", string="Purchase Order Line", readonly=True)
    currency_id = fields.Many2one("res.currency", string="Currency", readonly=True)
    purchase_date = fields.Date(string="Purchase Date", readonly=True)
    vendor_id = fields.Many2one("res.partner", string="Vendor", readonly=True)
    branch_id = fields.Many2one("account.analytic.account", string="Branch", readonly=True)
    quantity = fields.Float(string="Quantity", readonly=True)
    product_uom_id = fields.Many2one("uom.uom", string="Unit of Measure", readonly=True)
    price_unit = fields.Monetary(string="Unit Price", currency_field="currency_id", readonly=True)
    tax_display = fields.Char(string="Taxes", readonly=True)
    total_amount = fields.Monetary(string="Total Line Amount", currency_field="currency_id", readonly=True)
    source_reference = fields.Char(string="Source Reference", readonly=True)
