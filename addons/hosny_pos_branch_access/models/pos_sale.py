from odoo import api, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    @api.model
    def _load_pos_data_search_read(self, data, config):
        if self.env.user._hosny_is_branch_cashier():
            return []
        return super()._load_pos_data_search_read(data, config)

    @api.model
    def _load_pos_data_read(self, records, config):
        if self.env.user._hosny_is_branch_cashier():
            return []
        return super()._load_pos_data_read(records, config)


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    @api.model
    def _load_pos_data_search_read(self, data, config):
        if self.env.user._hosny_is_branch_cashier():
            return []
        return super()._load_pos_data_search_read(data, config)

    @api.model
    def _load_pos_data_read(self, records, config):
        if self.env.user._hosny_is_branch_cashier():
            return []
        return super()._load_pos_data_read(records, config)
