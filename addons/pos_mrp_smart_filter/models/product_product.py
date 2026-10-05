from odoo import api, fields, models
from odoo.tools.float_utils import float_compare


class ProductProduct(models.Model):
    _inherit = "product.product"

    pos_can_be_sold_or_manufactured = fields.Boolean(
        string="POS Can Be Sold Or Manufactured",
        compute="_compute_pos_can_be_sold_or_manufactured",
    )

    @api.depends(
        "type",
        "qty_available",
        "bom_ids",
        "bom_ids.bom_line_ids",
        "bom_ids.bom_line_ids.product_qty",
        "bom_ids.bom_line_ids.product_id",
        "product_tmpl_id.bom_ids",
        "product_tmpl_id.bom_ids.bom_line_ids",
        "product_tmpl_id.bom_ids.bom_line_ids.product_qty",
        "product_tmpl_id.bom_ids.bom_line_ids.product_id",
    )
    def _compute_pos_can_be_sold_or_manufactured(self):
        for product in self:
            product.pos_can_be_sold_or_manufactured = product._pos_can_fulfill_qty(
                qty=1.0,
                location=False,
                visited=None,
            )

    def _get_pos_available_qty(self, location=False):
        self.ensure_one()

        if self.type not in ("product", "consu"):
            return 999999999.0

        if location:
            return self.with_context(location=location.id).qty_available

        return self.qty_available

    def _get_matching_bom(self):
        self.ensure_one()
        Bom = self.env["mrp.bom"]

        bom_map = Bom._bom_find(
            products=self,
            company_id=self.company_id.id if self.company_id else self.env.company.id,
        )
        return bom_map.get(self)

    def _pos_can_fulfill_qty(self, qty=1.0, location=False, visited=None):
        self.ensure_one()

        visited = visited or set()
        visit_key = ("product", self.id, round(qty, 6), location.id if location else 0)
        if visit_key in visited:
            return False
        visited.add(visit_key)

        if qty <= 0:
            return True

        if self.type == "service":
            return True

        if self.type == "consu":
            return True

        rounding = self.uom_id.rounding or 0.01
        available_qty = self._get_pos_available_qty(location=location)

        if float_compare(available_qty, qty, precision_rounding=rounding) >= 0:
            return True

        missing_qty = max(qty - available_qty, 0.0)

        bom = self._get_matching_bom()
        if not bom or bom.product_qty <= 0:
            return False

        factor = missing_qty / bom.product_qty

        for line in bom.bom_line_ids:
            component = line.product_id
            if not component:
                return False

            required_qty = line.product_qty * factor
            if required_qty <= 0:
                continue

            if component.type in ("service", "consu"):
                continue

            component_available = component._get_pos_available_qty(location=location)
            comp_rounding = component.uom_id.rounding or 0.01

            if float_compare(component_available, required_qty, precision_rounding=comp_rounding) >= 0:
                continue

            component_missing = max(required_qty - component_available, 0.0)

            if not component._pos_can_fulfill_qty(
                qty=component_missing,
                location=location,
                visited=visited,
            ):
                return False

        return True