from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ProductTemplate(models.Model):
    _inherit = "product.template"

    pos_mrp_source_profile_id = fields.Many2one(
        "pos.mrp.source.profile",
        string="POS Component Source",
        ondelete="restrict",
        domain="[('active', '=', True), ('ready_for_all_pos', '=', True)]",
        help=(
            "Choose one logical component location. The physical stock location is selected "
            "automatically from the Point of Sale that creates the order."
        ),
    )

    def _get_pos_mrp_source_location(self, pos_config):
        """Resolve this product's logical source to one physical POS location."""
        self.ensure_one()
        profile = self.pos_mrp_source_profile_id
        if not profile:
            return self.env["stock.location"]
        return profile._get_location_for_pos_config(pos_config)

    @api.constrains("pos_mrp_source_profile_id")
    def _validate_pos_mrp_source_profile(self):
        for product in self.filtered("pos_mrp_source_profile_id"):
            profile = product.pos_mrp_source_profile_id
            missing = profile._get_missing_pos_configs()
            if missing:
                raise ValidationError(
                    _(
                        "The component source '%(profile)s' is not configured for: %(points_of_sale)s.",
                        profile=profile.display_name,
                        points_of_sale=", ".join(missing.mapped("display_name")),
                    )
                )
