from odoo import api, models


class PosSession(models.Model):
    _inherit = "pos.session"

    @api.model
    def _load_pos_data_models(self, config):
        models_to_load = super()._load_pos_data_models(config)
        if "product.meal.component.line" not in models_to_load:
            product_index = models_to_load.index("product.product") + 1
            models_to_load.insert(product_index, "product.meal.component.line")
        if "product.additional.final.line" not in models_to_load:
            product_index = models_to_load.index("product.product") + 1
            models_to_load.insert(product_index, "product.additional.final.line")
        return models_to_load
