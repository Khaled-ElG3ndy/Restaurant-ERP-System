from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class PosHospitalityConfig(models.Model):
    _name = "pos.hospitality.config"
    _description = "POS Hospitality Configuration"
    _inherit = ["pos.load.mixin"]
    _order = "name, id"

    name = fields.Char(required=True, translate=True)
    pos_config_ids = fields.Many2many(
        "pos.config",
        "pos_hospitality_config_pos_config_rel",
        "hospitality_config_id",
        "pos_config_id",
        string="Point of Sales",
        required=True,
    )
    product_ids = fields.Many2many(
        "product.product",
        "pos_hospitality_config_product_rel",
        "hospitality_config_id",
        "product_id",
        string="Hospitality Products",
        domain="[('available_in_pos', '=', True), ('sale_ok', '=', True), ('active', '=', True)]",
        required=True,
    )
    active = fields.Boolean(default=True)

    @api.constrains("product_ids")
    def _check_products_available_in_pos(self):
        unavailable = self.product_ids.filtered(
            lambda product: not product.available_in_pos or not product.sale_ok or not product.active
        )
        if unavailable:
            raise ValidationError(
                _(
                    "Hospitality products must be active, saleable, and available in Point of Sale: %s",
                    ", ".join(unavailable.mapped("display_name")),
                )
            )

    @api.model
    def _load_pos_data_domain(self, data, config):
        return [("active", "=", True), ("pos_config_ids", "in", config.id)]

    @api.model
    def _load_pos_data_fields(self, config):
        return ["name", "pos_config_ids", "product_ids", "active", "write_date"]


class PosSession(models.Model):
    _inherit = "pos.session"

    @api.model
    def _load_pos_data_models(self, config):
        models_to_load = super()._load_pos_data_models(config)
        return [*models_to_load, "pos.hospitality.config"]


class PosOrderLine(models.Model):
    _inherit = "pos.order.line"

    is_hospitality = fields.Boolean(string="Hospitality", default=False, index=True)
    hospitality_original_price = fields.Float(
        string="Hospitality Original Price",
        digits="Product Price",
        help="Original unit price retained for control and reporting before the line was made complimentary.",
    )

    @api.model
    def _load_pos_data_fields(self, config):
        return super()._load_pos_data_fields(config) + [
            "is_hospitality",
            "hospitality_original_price",
        ]
