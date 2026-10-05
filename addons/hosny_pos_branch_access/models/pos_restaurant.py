from odoo import api, models


class RestaurantFloor(models.Model):
    _inherit = "restaurant.floor"

    @api.model
    def _load_pos_data_read(self, records, config):
        fields = self._load_pos_data_fields(config)
        read_fields = [field for field in fields if field != "pos_config_ids"]
        readable_records = records._filtered_access("read")
        result = readable_records.sudo().read(read_fields, load=False)

        if "pos_config_ids" in fields:
            allowed_config_ids = set(self.env.user.sudo().pos_config_ids.ids)
            current_config_id = config.id
            for record in result:
                record["pos_config_ids"] = (
                    [current_config_id]
                    if not allowed_config_ids or current_config_id in allowed_config_ids
                    else []
                )

        return result or []
