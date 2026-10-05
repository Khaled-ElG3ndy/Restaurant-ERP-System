from odoo import models


class IrHttp(models.AbstractModel):
    _inherit = "ir.http"

    def session_info(self):
        result = super().session_info()
        result["hosny_is_branch_cashier"] = self.env.user._hosny_is_branch_cashier()
        return result
