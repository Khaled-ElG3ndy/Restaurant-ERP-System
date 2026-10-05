from odoo import api, fields, models


class StockMove(models.Model):
    _inherit = "stock.move"

    hosny_line_packaging_summary = fields.Char(
        string="ملخص تعبئة الشراء",
        related="purchase_line_id.hosny_line_packaging_summary",
        readonly=True,
    )

    @api.depends(
        "purchase_line_id",
        "purchase_line_id.product_uom_id",
        "purchase_line_id.hosny_purchase_packaging_id",
    )
    def _compute_packaging_uom_id(self):
        super()._compute_packaging_uom_id()
        for move in self.filtered("purchase_line_id"):
            packaging = (
                move.purchase_line_id.hosny_purchase_packaging_id
                if not move.purchase_line_id.hosny_line_packaging_enabled
                else self.env["hosny.purchase.packaging"]
            )
            move.packaging_uom_id = packaging.uom_id if packaging else False


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def _hosny_validate_branch_location_ids(self):
        """Keep receipt branch guards, but do not apply them to a supplier return.

        The branch-location addon deliberately restricts incoming receipts. A standard
        return of such a receipt uses the return operation type and a supplier
        destination, so treating it as another receipt makes every valid purchase
        return fail the operation-type branch check.
        """
        supplier_returns = self.filtered(
            lambda picking: picking.return_id
            and picking.location_dest_id.usage == "supplier"
        )
        regular_pickings = self - supplier_returns
        return super(StockPicking, regular_pickings)._hosny_validate_branch_location_ids()
