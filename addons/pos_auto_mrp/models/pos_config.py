from odoo import api, fields, models


class PosConfig(models.Model):
    _inherit = "pos.config"

    auto_create_mrp_from_pos = fields.Boolean(
        string="Auto Create Manufacturing Orders",
        default=True,
        help="Automatically create Manufacturing Orders from POS sales for products that have a BoM.",
    )

    auto_done_mrp_from_pos = fields.Boolean(
        string="Auto Mark Manufacturing Orders as Done",
        default=True,
        help="Manufacturing Orders are always confirmed automatically when all components are available. If this option is enabled, they are also marked as done automatically.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        configs = super().create(vals_list)
        self.env["pos.mrp.source.profile"]._recompute_ready_for_all_pos()
        return configs

    def write(self, vals):
        result = super().write(vals)
        if {"active", "auto_create_mrp_from_pos"} & set(vals):
            self.env["pos.mrp.source.profile"]._recompute_ready_for_all_pos()
        return result

    def unlink(self):
        result = super().unlink()
        self.env["pos.mrp.source.profile"]._recompute_ready_for_all_pos()
        return result
