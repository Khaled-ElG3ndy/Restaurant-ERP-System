from odoo.tests import TransactionCase


class TestStockReportQuantSync(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.view_location = cls.env["stock.location"].create({
            "name": "Sync View",
            "usage": "view",
            "company_id": cls.company.id,
        })
        cls.stock_location = cls.env["stock.location"].create({
            "name": "Detached Stock",
            "usage": "internal",
            "company_id": cls.company.id,
        })
        cls.warehouse = cls.env["stock.warehouse"].create({
            "name": "Sync Warehouse",
            "code": "SYN",
            "company_id": cls.company.id,
            "view_location_id": cls.view_location.id,
            "lot_stock_id": cls.stock_location.id,
            "reception_steps": "one_step",
            "delivery_steps": "ship_only",
        })
        cls.warehouse.lot_stock_id = cls.stock_location
        cls.product = cls.env["product.product"].create({
            "name": "Synced Quantity Product",
            "type": "consu",
            "is_storable": True,
        })
        cls.env["stock.quant"]._update_available_quantity(
            cls.product,
            cls.stock_location,
            7.0,
        )

        cls.jeddah_view_location = cls.env["stock.location"].create({
            "name": "Jeddah View",
            "usage": "view",
            "company_id": cls.company.id,
        })
        cls.jeddah_stock_location = cls.env["stock.location"].create({
            "name": "Jeddah Stock",
            "usage": "internal",
            "company_id": cls.company.id,
            "location_id": cls.jeddah_view_location.id,
        })
        cls.madinah_view_location = cls.env["stock.location"].create({
            "name": "Madinah View",
            "usage": "view",
            "company_id": cls.company.id,
        })
        cls.madinah_stock_location = cls.env["stock.location"].create({
            "name": "Madinah Stock",
            "usage": "internal",
            "company_id": cls.company.id,
        })
        cls.madinah_main_location = cls.env["stock.location"].create({
            "name": "Madinah Main",
            "usage": "internal",
            "company_id": cls.company.id,
            "location_id": cls.madinah_stock_location.id,
        })
        cls.jeddah_warehouse = cls.env["stock.warehouse"].create({
            "name": "Jeddah Report Warehouse",
            "code": "JRW",
            "company_id": cls.company.id,
            "view_location_id": cls.jeddah_view_location.id,
            "lot_stock_id": cls.madinah_main_location.id,
            "reception_steps": "one_step",
            "delivery_steps": "ship_only",
        })
        cls.jeddah_warehouse.write({
            "view_location_id": cls.jeddah_view_location.id,
            "lot_stock_id": cls.madinah_main_location.id,
        })
        (cls.jeddah_view_location | cls.jeddah_stock_location).write({
            "warehouse_id": cls.jeddah_warehouse.id,
        })
        cls.madinah_warehouse = cls.env["stock.warehouse"].create({
            "name": "Madinah Report Warehouse",
            "code": "MRW",
            "company_id": cls.company.id,
            "view_location_id": cls.madinah_view_location.id,
            "lot_stock_id": cls.madinah_stock_location.id,
            "reception_steps": "one_step",
            "delivery_steps": "ship_only",
        })
        cls.madinah_warehouse.write({
            "view_location_id": cls.madinah_view_location.id,
            "lot_stock_id": cls.madinah_stock_location.id,
        })
        cls.madinah_view_location.write({"warehouse_id": cls.madinah_warehouse.id})
        cls.branch_product = cls.env["product.product"].create({
            "name": "Branch Quantity Product",
            "type": "consu",
            "is_storable": True,
        })
        cls.env["stock.quant"]._update_available_quantity(
            cls.branch_product,
            cls.jeddah_stock_location,
            5.0,
        )
        cls.env["stock.quant"]._update_available_quantity(
            cls.branch_product,
            cls.madinah_main_location,
            11.0,
        )
        cls.env.invalidate_all()

    def test_warehouse_quantity_includes_detached_lot_stock_location(self):
        product = self.product.with_context(warehouse_id=self.warehouse.id)
        self.assertEqual(product.qty_available, 7.0)
        self.assertEqual(product.free_qty, 7.0)

    def test_global_quantity_includes_detached_lot_stock_location(self):
        self.assertGreaterEqual(self.product.qty_available, 7.0)

    def test_warehouse_quantity_ignores_detached_lot_from_another_warehouse(self):
        product = self.branch_product.with_context(warehouse_id=self.jeddah_warehouse.id)
        self.assertEqual(product.qty_available, 5.0)
        self.assertEqual(product.free_qty, 5.0)

    def test_other_warehouse_still_includes_its_detached_lot_stock_location(self):
        product = self.branch_product.with_context(warehouse_id=self.madinah_warehouse.id)
        self.assertEqual(product.qty_available, 11.0)
        self.assertEqual(product.free_qty, 11.0)
