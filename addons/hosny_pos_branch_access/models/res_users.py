from odoo import fields, models


class ResUsers(models.Model):
    _inherit = "res.users"

    pos_config_ids = fields.Many2many(
        "pos.config",
        "res_users_pos_config_rel",
        "user_id",
        "config_id",
        string="Allowed Points of Sale",
        help=(
            "Points of sale this user is allowed to work on. Leave empty to give "
            "access to every point of sale, which is how managers are set up."
        ),
    )

    @property
    def SELF_READABLE_FIELDS(self):
        # The record rules below read this field on the connected user. Declaring
        # it self-readable lets that read happen without depending on the access
        # rights the user happens to have on res.users.
        return super().SELF_READABLE_FIELDS + ["pos_config_ids"]

    def _hosny_is_branch_cashier(self):
        self.ensure_one()
        user = self.sudo()
        return bool(user.pos_config_ids) and not (
            user._has_group("base.group_system")
            or user._has_group("point_of_sale.group_pos_manager")
        )

    def _has_group(self, group_ext_id):
        result = super()._has_group(group_ext_id)
        if result and group_ext_id == "base.group_no_one" and self._hosny_is_branch_cashier():
            return False
        return result
