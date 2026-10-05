from odoo import api, fields, models


class MrpBomLine(models.Model):
    _inherit = "mrp.bom.line"

    hosny_currency_id = fields.Many2one(
        "res.currency",
        compute="_compute_hosny_bom_line_cost",
    )
    hosny_bom_line_cost = fields.Monetary(
        string="التكلفة",
        compute="_compute_hosny_bom_line_cost",
        currency_field="hosny_currency_id",
    )

    @api.depends(
        "bom_id.company_id",
        "product_id",
        "product_id.standard_price",
        "product_id.uom_id",
        "product_qty",
        "product_uom_id",
    )
    def _compute_hosny_bom_line_cost(self):
        for line in self:
            company = line.bom_id.company_id or line.company_id or self.env.company
            currency = company.currency_id
            line.hosny_currency_id = currency
            if not line.product_id or not line.product_uom_id:
                line.hosny_bom_line_cost = 0.0
                continue

            price = line.product_id.uom_id._compute_price(
                line.product_id.with_company(company).standard_price,
                line.product_uom_id,
            ) * line.product_qty
            line.hosny_bom_line_cost = currency.round(price)
