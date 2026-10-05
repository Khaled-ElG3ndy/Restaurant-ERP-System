from odoo import api, fields, models, _
from odoo.tools import LazyTranslate, format_amount


_lt = LazyTranslate(__name__)


def _get_sales_taxes(product):
    return product.taxes_id._filter_taxes_by_company(product.env.company)


def _compute_price_before_tax(product, price):
    return _get_sales_taxes(product).compute_all(
        price,
        currency=product.currency_id,
        quantity=1.0,
        product=product,
        partner=product.env["res.partner"],
    )["total_excluded"]


def _format_tax_price(product, amount):
    """Keep the normal currency format, with the familiar Arabic SAR label."""
    formatted = format_amount(product.env, amount, product.currency_id)
    if product.env.lang and product.env.lang.startswith("ar") and product.currency_id.name == "SAR":
        formatted = formatted.replace(product.currency_id.symbol, product.env._(_lt("SAR")))
    return formatted


class ProductTemplate(models.Model):
    _inherit = "product.template"

    price_before_tax = fields.Monetary(
        string="Price Before Tax",
        compute="_compute_price_before_tax",
        currency_field="currency_id",
        readonly=True,
    )

    @api.depends("list_price", "taxes_id", "taxes_id.amount", "taxes_id.price_include")
    @api.depends_context("company")
    def _compute_price_before_tax(self):
        for product in self:
            product.price_before_tax = _compute_price_before_tax(product, product.list_price)

    def _construct_tax_string(self, price):
        self.ensure_one()
        result = _get_sales_taxes(self).compute_all(
            price,
            currency=self.currency_id,
            quantity=1.0,
            product=self,
            partner=self.env["res.partner"],
        )
        included = result["total_included"]
        excluded = result["total_excluded"]
        labels = []
        if self.currency_id.compare_amounts(included, price):
            labels.append(_("Price including tax: %(amount)s", amount=_format_tax_price(self, included)))
        if self.currency_id.compare_amounts(excluded, price):
            labels.append(_("Price excluding tax: %(amount)s", amount=_format_tax_price(self, excluded)))
        return f"({', '.join(labels)})" if labels else " "


class ProductProduct(models.Model):
    _inherit = "product.product"

    price_before_tax = fields.Monetary(
        string="Price Before Tax",
        compute="_compute_price_before_tax",
        currency_field="currency_id",
        readonly=True,
    )

    @api.depends("lst_price", "taxes_id", "taxes_id.amount", "taxes_id.price_include")
    @api.depends_context("company", "uom")
    def _compute_price_before_tax(self):
        for product in self:
            product.price_before_tax = _compute_price_before_tax(product, product.lst_price)
