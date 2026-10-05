from odoo import api, fields, models
from odoo.fields import Domain


class ProductProduct(models.Model):
    _inherit = "product.product"

    hosny_stock_report_unit_cost = fields.Float(
        string="Unit Cost",
        compute="_compute_hosny_stock_report_unit_cost",
        digits=(16, 6),
        compute_sudo=True,
        help="Exact stock report unit cost. Uses Total Value / On Hand when stock exists.",
    )

    @api.depends_context("to_date", "company", "warehouse_id", "location")
    @api.depends("avg_cost", "total_value", "qty_available")
    def _compute_hosny_stock_report_unit_cost(self):
        for product in self:
            if product.uom_id.is_zero(product.qty_available):
                product.hosny_stock_report_unit_cost = product.avg_cost
            else:
                product.hosny_stock_report_unit_cost = product.total_value / product.qty_available

    def _hosny_search_context_ids(self, model_name, values):
        ids = set()
        domains = []
        for item in values:
            if isinstance(item, int):
                ids.add(item)
            else:
                domains.append(Domain(self.env[model_name]._rec_name, "ilike", item))
        if domains:
            ids |= set(self.env[model_name].search(Domain.OR(domains)).ids)
        return ids

    def _hosny_location_is_under_any_path(self, location, parent_paths):
        if not location.parent_path:
            return False
        return any(location.parent_path.startswith(parent_path) for parent_path in parent_paths)

    def _hosny_get_valid_detached_lot_locations(self, warehouses):
        """Return detached lot_stock_id locations that are not owned by another WH.

        Some production warehouses have a lot_stock_id outside their
        view_location_id tree. We still need to include those detached roots, but
        not when the detached location is under another warehouse's stock root.
        In that case adding it makes one selected warehouse show another
        warehouse's quantities.
        """
        Warehouse = self.env["stock.warehouse"]
        detached_lots = self.env["stock.location"]
        company_ids = warehouses.mapped("company_id").ids or self.env.companies.ids
        other_warehouses = Warehouse.search([
            ("company_id", "in", company_ids),
            ("id", "not in", warehouses.ids),
        ])
        other_lot_paths = [
            path for path in other_warehouses.mapped("lot_stock_id.parent_path") if path
        ]

        for warehouse in warehouses:
            lot_location = warehouse.lot_stock_id
            view_location = warehouse.view_location_id
            if not lot_location:
                continue
            if (
                view_location.parent_path
                and lot_location.parent_path
                and lot_location.parent_path.startswith(view_location.parent_path)
            ):
                continue
            if self._hosny_location_is_under_any_path(lot_location, other_lot_paths):
                continue
            detached_lots |= lot_location
        return detached_lots

    def _hosny_get_warehouse_location_ids(self, warehouses):
        Location = self.env["stock.location"]
        view_locations = warehouses.mapped("view_location_id")
        locations = Location

        if view_locations:
            locations |= Location.search([
                ("id", "child_of", view_locations.ids),
                ("warehouse_id", "in", warehouses.ids),
            ])

        detached_lots = self._hosny_get_valid_detached_lot_locations(warehouses)
        if detached_lots:
            locations |= Location.search([("id", "child_of", detached_lots.ids)])

        return set(locations.ids)

    def _get_domain_locations(self):
        """Include each warehouse's real stock location in stock report quantities.

        Odoo computes quantities for a warehouse from its view location tree. In this
        database some warehouses have a valid lot_stock_id that is no longer a child
        of view_location_id, so the stock report excludes real quants and displays 0.
        Including lot_stock_id keeps computed product quantities aligned with quants.
        """
        Location = self.env["stock.location"]
        Warehouse = self.env["stock.warehouse"]

        location = self.env.context.get("location") or self.env.context.get("search_location")
        if location and not isinstance(location, list):
            location = [location]
        warehouse = self.env.context.get("warehouse_id") or self.env.context.get("search_warehouse")
        if warehouse and not isinstance(warehouse, list):
            warehouse = [warehouse]

        if warehouse:
            warehouses = Warehouse.browse(
                self._hosny_search_context_ids("stock.warehouse", warehouse)
            )
            warehouse_location_ids = self._hosny_get_warehouse_location_ids(warehouses)
            if location:
                requested_locations = Location.browse(
                    self._hosny_search_context_ids("stock.location", location)
                )
                requested_location_ids = set(Location.search([
                    ("id", "child_of", requested_locations.ids),
                ]).ids)
                location_ids = warehouse_location_ids & requested_location_ids
            else:
                location_ids = warehouse_location_ids

            return self.with_context(strict=True)._get_domain_locations_new(location_ids)
        elif location:
            location_ids = self._hosny_search_context_ids("stock.location", location)
        else:
            warehouses = Warehouse.search([("company_id", "in", self.env.companies.ids)])
            location_ids = set(
                (warehouses.mapped("view_location_id") | warehouses.mapped("lot_stock_id")).ids
            )

        return self._get_domain_locations_new(location_ids)
