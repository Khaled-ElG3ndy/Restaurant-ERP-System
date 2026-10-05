from odoo import models


class MrpProduction(models.Model):
    _inherit = "mrp.production"

    def button_mark_done(self):
        """Refresh POS bundle COGS after the MO has its final stock valuation."""
        result = super().button_mark_done()
        completed = self.filtered(
            lambda production: production.pos_auto_mrp_generated
            and production.state == "done"
            and (production.pos_order_line_ids or production.pos_order_line_id)
        )
        if completed:
            (
                completed.mapped("pos_order_line_ids")
                | completed.mapped("pos_order_line_id")
            )._additional_final_refresh_bundle_costs()
        return result
