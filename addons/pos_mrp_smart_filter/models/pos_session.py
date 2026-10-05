from odoo import models


class PosSession(models.Model):
    _inherit = "pos.session"

    def _loader_params_product_product(self):
        result = super()._loader_params_product_product()
        fields = result["search_params"]["fields"]

        extra_fields = [
            "type",
            "qty_available",
            "pos_can_be_sold_or_manufactured",
        ]
        for field in extra_fields:
            if field not in fields:
                fields.append(field)

        return result

    def _pos_ui_models_to_load(self):
        result = super()._pos_ui_models_to_load()
        if "stock.location" not in result:
            result.append("stock.location")
        return result

    def _loader_params_stock_location(self):
        config = self.config_id
        location_ids = []

        if config.picking_type_id and config.picking_type_id.default_location_src_id:
            location_ids.append(config.picking_type_id.default_location_src_id.id)

        return {
            "search_params": {
                "domain": [("id", "in", location_ids)] if location_ids else [],
                "fields": ["id", "name", "complete_name"],
            },
        }

    def _get_pos_ui_stock_location(self, params):
        return self.env["stock.location"].search_read(**params["search_params"])