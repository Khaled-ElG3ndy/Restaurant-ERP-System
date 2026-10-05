from odoo import api, fields, models

from .utils import boolean_search_domain


class StockLocation(models.Model):
    _inherit = "stock.location"

    pos_mrp_is_leaf = fields.Boolean(
        string="POS Manufacturing Leaf Location",
        compute="_compute_pos_mrp_is_leaf",
        search="_search_pos_mrp_is_leaf",
        help="Technical field used to exclude parent locations from POS source mappings.",
    )

    @api.model
    def _get_pos_mrp_leaf_location_ids(self):
        locations = self.with_context(active_test=False).search([("usage", "=", "internal")])
        parent_ids = set(locations.mapped("location_id").ids)

        # Some imported deployments store a complete path in `name` instead of
        # building a real parent/child hierarchy. Treat those prefixes as parents too.
        paths = {}
        for location in locations:
            raw_path = (location.complete_name or location.name or "").strip().rstrip("/")
            paths[location.id] = raw_path
        ordered_paths = sorted((path, location_id) for location_id, path in paths.items() if path)
        for path, location_id in ordered_paths:
            prefix = f"{path}/"
            if any(other_path.startswith(prefix) for other_path, other_id in ordered_paths if other_id != location_id):
                parent_ids.add(location_id)

        return locations.filtered(lambda location: location.id not in parent_ids).ids

    def _compute_pos_mrp_is_leaf(self):
        leaf_ids = set(self._get_pos_mrp_leaf_location_ids())
        for location in self:
            location.pos_mrp_is_leaf = location.id in leaf_ids

    @api.model
    def _search_pos_mrp_is_leaf(self, operator, value):
        leaf_ids = self._get_pos_mrp_leaf_location_ids()
        return boolean_search_domain(leaf_ids, operator, value)
