from datetime import timedelta

from odoo import Command, fields
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged
from odoo.tools.float_utils import float_compare


@tagged("post_install", "-at_install", "pos_auto_mrp_return")
class TestAutomaticReturnUnbuild(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.warehouse = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.company.id)], limit=1
        )
        cls.stock = cls.warehouse.lot_stock_id
        cls.partner = cls.env["res.partner"].create({"name": "Automatic Return Customer"})

    def _products_and_bom(self, tracking="none", component_qty=2, bom_type="normal"):
        component = self.env["product.product"].create({
            "name": "Automatic Return Component",
            "type": "consu",
            "is_storable": True,
        })
        finished = self.env["product.product"].create({
            "name": "Automatic Return Finished",
            "type": "consu",
            "is_storable": True,
            "tracking": tracking,
            "sale_ok": True,
            "list_price": 10,
        })
        self.env["stock.quant"]._update_available_quantity(component, self.stock, 100)
        bom = self.env["mrp.bom"].create({
            "product_tmpl_id": finished.product_tmpl_id.id,
            "product_id": finished.id,
            "product_qty": 1,
            "product_uom_id": finished.uom_id.id,
            "type": bom_type,
            "bom_line_ids": [Command.create({
                "product_id": component.id,
                "product_qty": component_qty,
                "product_uom_id": component.uom_id.id,
            })],
        })
        return component, finished, bom

    def _sale(self, product, qty):
        order = self.env["sale.order"].create({
            "partner_id": self.partner.id,
            "order_line": [Command.create({
                "product_id": product.id,
                "product_uom_qty": qty,
                "product_uom_id": product.uom_id.id,
                "price_unit": 10,
            })],
        })
        order.action_confirm()
        return order

    def _finish_mo(self, production, lot=False):
        if production.state == "done":
            self.assertEqual(production.state, "done")
            return
        production.action_assign()
        if lot:
            production.lot_producing_ids = lot
        production.qty_producing = production.product_qty
        production.move_raw_ids.picked = True
        production.button_mark_done()
        self.assertEqual(production.state, "done")

    def _complete_picking(self, picking, qty=False, lot=False):
        picking.action_assign()
        for move in picking.move_ids:
            if qty is not False:
                move.quantity = qty
            if lot and move.move_line_ids:
                move.move_line_ids.lot_id = lot
            move.picked = True
        picking._action_done()
        return picking

    def _delivery(self, order, qty, lot=False):
        picking = order.picking_ids.filtered(lambda item: item.picking_type_code == "outgoing")[:1]
        return self._complete_picking(picking, qty, lot=lot)

    def _return(self, delivery, qty, done_qty=False, lot=False):
        wizard = self.env["stock.return.picking"].with_context(
            active_id=delivery.id,
            active_ids=delivery.ids,
            active_model="stock.picking",
        ).create({})
        wizard.product_return_moves.quantity = qty
        action = wizard.action_create_returns()
        picking = self.env["stock.picking"].browse(action["res_id"])
        return self._complete_picking(
            picking,
            done_qty if done_qty is not False else qty,
            lot=lot,
        )

    def assertQty(self, actual, expected, uom):
        self.assertEqual(
            float_compare(actual, expected, precision_rounding=uom.rounding),
            0,
            "%s != %s" % (actual, expected),
        )

    def assertStock(self, product, location, on_hand, reserved=0):
        quants = self.env["stock.quant"].search([
            ("product_id", "=", product.id),
            ("location_id", "=", location.id),
        ])
        actual_on_hand = sum(quants.mapped("quantity"))
        actual_reserved = sum(quants.mapped("reserved_quantity"))
        self.assertQty(actual_on_hand, on_hand, product.uom_id)
        self.assertQty(actual_reserved, reserved, product.uom_id)
        self.assertQty(
            actual_on_hand - actual_reserved,
            on_hand - reserved,
            product.uom_id,
        )

    def test_sales_creation_full_return_and_actual_components(self):
        component, finished, _bom = self._products_and_bom()
        order = self._sale(finished, 10)
        production = order.order_line.mrp_production_ids
        self.assertEqual(len(production), 1)
        self.assertTrue(production.pos_auto_mrp_generated)
        self.assertEqual(production.state, "done")
        self.assertQty(production.qty_produced, 10, finished.uom_id)
        self.assertQty(
            self.env["stock.quant"]._get_available_quantity(component, self.stock),
            80,
            component.uom_id,
        )
        delivery = self._delivery(order, 10)

        returned = self._return(delivery, 10)
        allocations = order.order_line.pos_auto_mrp_allocation_ids
        self.assertEqual(len(allocations), 1)
        self.assertEqual(allocations.return_move_id.picking_id, returned)
        self.assertEqual(allocations.unbuild_id.state, "done")
        self.assertQty(allocations.quantity, 10, finished.uom_id)
        self.assertQty(
            self.env["stock.quant"]._get_available_quantity(component, self.stock),
            100,
            component.uom_id,
        )
        self.assertQty(
            self.env["stock.quant"]._get_available_quantity(finished, self.stock),
            0,
            finished.uom_id,
        )

    def test_sales_multiple_partial_returns_are_idempotent(self):
        _component, finished, _bom = self._products_and_bom()
        order = self._sale(finished, 10)
        self._finish_mo(order.order_line.mrp_production_ids)
        delivery = self._delivery(order, 10)
        first_return = self._return(delivery, 3)
        self._return(delivery, 2)

        allocations = order.order_line.pos_auto_mrp_allocation_ids.sorted("id")
        self.assertEqual(len(allocations), 2)
        self.assertEqual(sum(allocations.mapped("quantity")), 5)
        self.assertQty(order.order_line.remaining_returnable_qty, 5, finished.uom_id)
        first_return._action_done()
        order.order_line.invalidate_recordset()
        self.assertEqual(len(order.order_line.pos_auto_mrp_allocation_ids), 2)
        moves = allocations.mapped("unbuild_id.consume_line_ids") | allocations.mapped(
            "unbuild_id.produce_line_ids"
        )
        self.assertTrue(all(move.quantity >= 0 for move in moves))

    def test_return_is_split_fifo_across_multiple_manufacturing_orders(self):
        component, finished, _bom = self._products_and_bom()
        self.env["stock.quant"]._update_available_quantity(
            component, self.stock, -100
        )
        order = self._sale(finished, 10)
        generated = order.order_line.mrp_production_ids
        self.assertEqual(generated.state, "draft")
        production_vals = {
            "product_id": finished.id,
            "product_uom_id": finished.uom_id.id,
            "bom_id": generated.bom_id.id,
            "origin": order.name,
            "sale_order_id": order.id,
            "sale_order_line_id": order.order_line.id,
            "pos_auto_mrp_generated": True,
            "company_id": order.company_id.id,
            "picking_type_id": generated.picking_type_id.id,
            "location_src_id": generated.location_src_id.id,
            "location_dest_id": generated.location_dest_id.id,
        }
        generated.action_cancel()
        generated.unlink()
        self.env["stock.quant"]._update_available_quantity(
            component, self.stock, 100
        )
        first = self.env["mrp.production"].create({**production_vals, "product_qty": 4})
        second = self.env["mrp.production"].create({
            **production_vals,
            "product_qty": 6,
        })
        first.action_confirm()
        second.action_confirm()
        self._finish_mo(first)
        self._finish_mo(second)
        first.date_finished = fields.Datetime.now() - timedelta(days=1)
        second.date_finished = fields.Datetime.now()
        delivery = self._delivery(order, 10)

        self._return(delivery, 7)
        allocations = order.order_line.pos_auto_mrp_allocation_ids.sorted("id")
        self.assertEqual(allocations.mapped("production_id"), first | second)
        self.assertEqual(allocations.mapped("quantity"), [4, 3])

    def test_backorder_unbuilds_only_completed_quantity(self):
        _component, finished, _bom = self._products_and_bom()
        order = self._sale(finished, 5)
        self._finish_mo(order.order_line.mrp_production_ids)
        delivery = self._delivery(order, 5)

        self._return(delivery, 5, done_qty=2)
        allocations = order.order_line.pos_auto_mrp_allocation_ids
        self.assertEqual(len(allocations), 1)
        self.assertQty(allocations.quantity, 2, finished.uom_id)

    def test_over_return_is_blocked_with_user_error(self):
        _component, finished, _bom = self._products_and_bom()
        order = self._sale(finished, 3)
        self._finish_mo(order.order_line.mrp_production_ids)
        delivery = self._delivery(order, 3)
        wizard = self.env["stock.return.picking"].with_context(
            active_id=delivery.id,
            active_ids=delivery.ids,
            active_model="stock.picking",
        ).create({})
        wizard.product_return_moves.quantity = 4
        picking = self.env["stock.picking"].browse(wizard.action_create_returns()["res_id"])
        picking.move_ids.quantity = 4
        picking.move_ids.picked = True
        with self.assertRaises(UserError):
            picking._action_done()
        self.assertFalse(order.order_line.pos_auto_mrp_allocation_ids)

    def test_products_without_real_automatic_mo_keep_standard_return(self):
        product = self.env["product.product"].create({
            "name": "No BOM Product",
            "type": "consu",
            "is_storable": True,
            "sale_ok": True,
        })
        self.env["stock.quant"]._update_available_quantity(product, self.stock, 1)
        order = self._sale(product, 1)
        self.assertFalse(order.order_line.mrp_production_ids)
        delivery = self._delivery(order, 1)
        returned = self._return(delivery, 1)
        self.assertEqual(returned.state, "done")
        self.assertFalse(order.order_line.pos_auto_mrp_allocation_ids)

        _component, kit, _bom = self._products_and_bom(bom_type="phantom")
        kit_order = self._sale(kit, 1)
        self.assertFalse(kit_order.order_line.mrp_production_ids)

    def test_lot_is_preserved_on_automatic_unbuild(self):
        _component, finished, _bom = self._products_and_bom(tracking="lot")
        lot = self.env["stock.lot"].create({
            "name": "AUTO-RETURN-LOT",
            "product_id": finished.id,
            "company_id": self.company.id,
        })
        order = self._sale(finished, 2)
        production = order.order_line.mrp_production_ids
        self._finish_mo(production, lot=lot)
        delivery = self._delivery(order, 2, lot=lot)
        self._return(delivery, 1, lot=lot)
        allocation = order.order_line.pos_auto_mrp_allocation_ids
        self.assertEqual(allocation.lot_id, lot)
        self.assertEqual(allocation.unbuild_id.lot_id, lot)

    def test_serial_is_preserved_on_automatic_unbuild(self):
        _component, finished, _bom = self._products_and_bom(tracking="serial")
        serial = self.env["stock.lot"].create({
            "name": "AUTO-RETURN-SERIAL",
            "product_id": finished.id,
            "company_id": self.company.id,
        })
        order = self._sale(finished, 1)
        self._finish_mo(order.order_line.mrp_production_ids, lot=serial)
        delivery = self._delivery(order, 1, lot=serial)
        self._return(delivery, 1, lot=serial)
        allocation = order.order_line.pos_auto_mrp_allocation_ids
        self.assertEqual(allocation.quantity, 1)
        self.assertEqual(allocation.unbuild_id.lot_id, serial)

    def test_company_is_preserved_through_return_and_unbuild(self):
        company = self.env["res.company"].create({"name": "Automatic Return Company"})
        company_env = self.env(
            context=dict(
                self.env.context,
                allowed_company_ids=[company.id, self.company.id],
            )
        )
        warehouse = company_env["stock.warehouse"].create({
            "name": "Automatic Return Warehouse",
            "code": "ART",
            "company_id": company.id,
        })
        component = company_env["product.product"].create({
            "name": "Company Return Component",
            "type": "consu",
            "is_storable": True,
        })
        finished = company_env["product.product"].create({
            "name": "Company Return Finished",
            "type": "consu",
            "is_storable": True,
            "sale_ok": True,
            "taxes_id": [Command.clear()],
        })
        company_env["stock.quant"]._update_available_quantity(
            component, warehouse.lot_stock_id, 10
        )
        company_env["mrp.bom"].create({
            "product_tmpl_id": finished.product_tmpl_id.id,
            "product_id": finished.id,
            "product_qty": 1,
            "product_uom_id": finished.uom_id.id,
            "type": "normal",
            "company_id": company.id,
            "bom_line_ids": [Command.create({
                "product_id": component.id,
                "product_qty": 1,
                "product_uom_id": component.uom_id.id,
            })],
        })
        order = company_env["sale.order"].create({
            "partner_id": self.partner.id,
            "company_id": company.id,
            "warehouse_id": warehouse.id,
            "order_line": [Command.create({
                "product_id": finished.id,
                "product_uom_qty": 1,
                "product_uom_id": finished.uom_id.id,
                "price_unit": 10,
            })],
        })
        order.with_context(hosny_allow_negative_stock=True).action_confirm()
        production = order.order_line.mrp_production_ids
        company_env["stock.quant"]._update_available_quantity(
            component, production.move_raw_ids.location_id, 10
        )
        production.action_assign()
        production.qty_producing = 1
        production.move_raw_ids.picked = True
        production.button_mark_done()
        delivery = order.picking_ids.filtered(lambda item: item.picking_type_code == "outgoing")
        delivery.action_assign()
        delivery.move_ids.quantity = 1
        delivery.move_ids.picked = True
        delivery._action_done()
        wizard = company_env["stock.return.picking"].with_context(
            active_id=delivery.id,
            active_ids=delivery.ids,
            active_model="stock.picking",
        ).create({})
        wizard.product_return_moves.quantity = 1
        returned = company_env["stock.picking"].browse(
            wizard.action_create_returns()["res_id"]
        )
        returned.move_ids.quantity = 1
        returned.move_ids.picked = True
        returned._action_done()
        allocation = order.order_line.pos_auto_mrp_allocation_ids
        self.assertEqual(allocation.company_id, company)
        self.assertEqual(allocation.production_id.company_id, company)
        self.assertEqual(allocation.unbuild_id.company_id, company)


@tagged("post_install", "-at_install", "pos_auto_mrp_return")
class TestPosAutomaticReturnUnbuild(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.config = cls.env["pos.config"].search(
            [("company_id", "=", cls.env.company.id)], limit=1
        )
        if not cls.config:
            cls.config = cls.env["pos.config"].create({
                "name": "POS Auto MRP Test",
                "module_pos_restaurant": False,
            })
        cls.config.write({
            "auto_create_mrp_from_pos": True,
            "auto_done_mrp_from_pos": True,
        })
        cls.session = cls.config.current_session_id
        if not cls.session:
            cls.session = cls.env["pos.session"].create({
                "config_id": cls.config.id,
                "user_id": cls.env.user.id,
            })
            cls.session.action_pos_session_open()
        cls.session.update_stock_at_closing = False
        cls.stock = cls.config.picking_type_id.default_location_src_id

    def assertQty(self, actual, expected, uom):
        self.assertEqual(
            float_compare(actual, expected, precision_rounding=uom.rounding),
            0,
            "%s != %s" % (actual, expected),
        )

    def assertStock(self, product, location, on_hand, reserved=0):
        quants = self.env["stock.quant"].search([
            ("product_id", "=", product.id),
            ("location_id", "=", location.id),
        ])
        actual_on_hand = sum(quants.mapped("quantity"))
        actual_reserved = sum(quants.mapped("reserved_quantity"))
        self.assertQty(actual_on_hand, on_hand, product.uom_id)
        self.assertQty(actual_reserved, reserved, product.uom_id)
        self.assertQty(
            actual_on_hand - actual_reserved,
            on_hand - reserved,
            product.uom_id,
        )

    def _create_routed_pos_product(self, prefix, component_stock=100):
        component = self.env["product.product"].create({
            "name": "%s Component" % prefix,
            "type": "consu",
            "is_storable": True,
        })
        finished = self.env["product.product"].create({
            "name": "%s Finished" % prefix,
            "type": "consu",
            "is_storable": True,
            "available_in_pos": True,
            "sale_ok": True,
            "list_price": 10,
        })
        component_source = self.env["stock.location"].create({
            "name": "%s Components" % prefix,
            "location_id": self.stock.id,
            "usage": "internal",
        })
        profile = self.env["pos.mrp.source.profile"].create({
            "name": "%s Source" % prefix,
            "route_ids": [Command.create({
                "pos_config_id": self.config.id,
                "location_id": component_source.id,
            })],
        })
        finished.product_tmpl_id.pos_mrp_source_profile_id = profile.id
        self.env["mrp.bom"].create({
            "product_tmpl_id": finished.product_tmpl_id.id,
            "product_id": finished.id,
            "product_qty": 1,
            "product_uom_id": finished.uom_id.id,
            "type": "normal",
            "bom_line_ids": [Command.create({
                "product_id": component.id,
                "product_qty": 2,
                "product_uom_id": component.uom_id.id,
            })],
        })
        self.env["stock.quant"]._update_available_quantity(
            component, component_source, component_stock
        )
        return component, finished, component_source

    def _create_pos_sale_for_auto_confirmation(self, component_stock):
        component = self.env["product.product"].create({
            "name": "POS Auto Confirm Component",
            "type": "consu",
            "is_storable": True,
        })
        finished = self.env["product.product"].create({
            "name": "POS Auto Confirm Finished",
            "type": "consu",
            "is_storable": True,
            "available_in_pos": True,
            "sale_ok": True,
            "list_price": 10,
        })
        self.env["mrp.bom"].create({
            "product_tmpl_id": finished.product_tmpl_id.id,
            "product_id": finished.id,
            "product_qty": 1,
            "product_uom_id": finished.uom_id.id,
            "type": "normal",
            "bom_line_ids": [Command.create({
                "product_id": component.id,
                "product_qty": 2,
                "product_uom_id": component.uom_id.id,
            })],
        })
        source_location = (
            finished.product_tmpl_id._get_pos_mrp_source_location(self.config)
            or self.stock
        )
        if component_stock:
            self.env["stock.quant"]._update_available_quantity(
                component, source_location, component_stock
            )
        sale = self.env["pos.order"].create({
            "session_id": self.session.id,
            "company_id": self.env.company.id,
            "amount_paid": 10,
            "amount_total": 10,
            "amount_tax": 0,
            "amount_return": 0,
            "state": "paid",
            "lines": [Command.create({
                "product_id": finished.id,
                "qty": 1,
                "price_unit": 10,
                "price_subtotal": 10,
                "price_subtotal_incl": 10,
            })],
        })
        sale._create_mrp_from_pos_if_needed()
        return sale, sale.lines.mrp_production_ids

    def test_available_components_confirm_mo_without_marking_done(self):
        self.config.auto_done_mrp_from_pos = False
        _sale, production = self._create_pos_sale_for_auto_confirmation(10)

        self.assertEqual(production.state, "confirmed")
        self.assertEqual(production.qty_produced, 0)

    def test_unavailable_components_leave_mo_in_draft(self):
        self.config.auto_done_mrp_from_pos = True
        _sale, production = self._create_pos_sale_for_auto_confirmation(0)

        self.assertEqual(production.state, "draft")

    def test_pos_sale_and_partial_refund_wait_for_stock_move(self):
        component, finished, source_location = self._create_routed_pos_product(
            "POS Return"
        )
        self.assertStock(component, source_location, 100)
        self.assertStock(finished, source_location, 0)
        self.assertStock(finished, self.stock, 0)
        sale = self.env["pos.order"].create({
            "session_id": self.session.id,
            "company_id": self.env.company.id,
            "amount_paid": 30,
            "amount_total": 30,
            "amount_tax": 0,
            "amount_return": 0,
            "state": "paid",
            "lines": [Command.create({
                "product_id": finished.id,
                "qty": 3,
                "price_unit": 10,
                "price_subtotal": 30,
                "price_subtotal_incl": 30,
            })],
        })
        sale._create_order_picking()
        sale._create_mrp_from_pos_if_needed()
        production = sale.lines.mrp_production_ids
        self.assertEqual(production.state, "done")
        self.assertEqual(production.location_dest_id, source_location)
        self.assertEqual(production.move_raw_ids.location_id, source_location)
        self.assertEqual(production.move_finished_ids.location_dest_id, source_location)
        self.assertEqual(sale.picking_ids.move_ids.location_id, source_location)
        self.assertStock(component, source_location, 94)
        self.assertStock(finished, source_location, 0)
        self.assertStock(finished, self.stock, 0)
        sale._create_mrp_from_pos_if_needed()
        self.assertEqual(len(sale.lines.mrp_production_ids), 1)

        refund = self.env["pos.order"].create({
            "session_id": self.session.id,
            "company_id": self.env.company.id,
            "amount_paid": -10,
            "amount_total": -10,
            "amount_tax": 0,
            "amount_return": 0,
            "state": "paid",
            "is_refund": True,
            "lines": [Command.create({
                "product_id": finished.id,
                "qty": -1,
                "price_unit": 10,
                "price_subtotal": -10,
                "price_subtotal_incl": -10,
                "refunded_orderline_id": sale.lines.id,
            })],
        })
        refund._create_mrp_unbuild_from_refund_if_needed()
        self.assertFalse(refund.lines.pos_auto_mrp_refund_allocation_ids)
        refund._create_order_picking()
        allocation = refund.lines.pos_auto_mrp_refund_allocation_ids
        self.assertEqual(len(allocation), 1)
        self.assertEqual(allocation.state, "done")
        self.assertEqual(allocation.unbuild_id.origin_source, "pos_refund")
        self.assertEqual(allocation.unbuild_id.location_id, source_location)
        self.assertEqual(allocation.unbuild_id.location_dest_id, source_location)
        self.assertEqual(allocation.pos_order_line_id, sale.lines)
        self.assertEqual(allocation.pos_refund_order_line_id, refund.lines)
        refund.picking_ids.move_ids._pos_auto_mrp_process_completed_returns()
        self.assertEqual(len(refund.lines.pos_auto_mrp_refund_allocation_ids), 1)
        self.assertEqual(refund.picking_ids.move_ids.location_dest_id, source_location)
        self.assertStock(component, source_location, 96)
        self.assertStock(finished, source_location, 0)
        self.assertStock(finished, self.stock, 0)

        final_refund = self.env["pos.order"].create({
            "session_id": self.session.id,
            "company_id": self.env.company.id,
            "amount_paid": -20,
            "amount_total": -20,
            "amount_tax": 0,
            "amount_return": 0,
            "state": "paid",
            "is_refund": True,
            "lines": [Command.create({
                "product_id": finished.id,
                "qty": -2,
                "price_unit": 10,
                "price_subtotal": -20,
                "price_subtotal_incl": -20,
                "refunded_orderline_id": sale.lines.id,
            })],
        })
        final_refund._create_order_picking()
        allocations = sale.lines.pos_auto_mrp_allocation_ids
        self.assertEqual(len(allocations), 2)
        self.assertEqual(sum(allocations.mapped("quantity")), 3)
        self.assertEqual(sum(allocations.mapped("unbuild_id.product_qty")), 3)
        self.assertTrue(all(allocation.unbuild_id.state == "done" for allocation in allocations))
        self.assertEqual(final_refund.picking_ids.move_ids.location_dest_id, source_location)
        self.assertStock(component, source_location, 100)
        self.assertStock(finished, source_location, 0)
        self.assertStock(finished, self.stock, 0)

    def test_backend_refund_payment_completes_picking_and_unbuild(self):
        component, finished, component_source = self._create_routed_pos_product(
            "POS Backend Refund"
        )
        sale = self.env["pos.order"].create({
            "session_id": self.session.id,
            "company_id": self.env.company.id,
            "amount_paid": 20,
            "amount_total": 20,
            "amount_tax": 0,
            "amount_return": 0,
            "state": "paid",
            "lines": [Command.create({
                "product_id": finished.id,
                "qty": 2,
                "price_unit": 10,
                "price_subtotal": 20,
                "price_subtotal_incl": 20,
            })],
        })
        sale._create_order_picking()
        sale._create_mrp_from_pos_if_needed()
        production = sale.lines.mrp_production_ids
        self.assertEqual(production.state, "done")
        self.assertEqual(production.location_dest_id, component_source)
        self.assertEqual(production.move_raw_ids.location_id, component_source)
        self.assertQty(
            self.env["stock.quant"]._get_available_quantity(
                component, component_source
            ),
            96,
            component.uom_id,
        )

        refund = sale._refund()
        self.assertEqual(refund.state, "draft")
        payment = self.env["pos.make.payment"].with_context(
            active_id=refund.id,
            active_ids=refund.ids,
            active_model="pos.order",
        ).create({})
        payment.check()

        self.assertEqual(refund.state, "paid")
        self.assertEqual(refund.picking_ids.state, "done")
        allocation = refund.lines.pos_auto_mrp_refund_allocation_ids
        self.assertEqual(allocation.state, "done")
        self.assertEqual(allocation.unbuild_id.state, "done")
        self.assertEqual(allocation.unbuild_id.location_id, component_source)
        self.assertEqual(allocation.unbuild_id.location_dest_id, component_source)
        self.assertQty(
            self.env["stock.quant"]._get_available_quantity(
                component, component_source
            ),
            100,
            component.uom_id,
        )

    def test_mixed_pos_sections_return_to_their_own_locations(self):
        fish_component, fish_finished, fish_location = self._create_routed_pos_product(
            "Fish Section"
        )
        meat_component, meat_finished, meat_location = self._create_routed_pos_product(
            "Meat Section"
        )
        for product, location in (
            (fish_component, fish_location),
            (meat_component, meat_location),
            (fish_finished, fish_location),
            (meat_finished, meat_location),
            (fish_finished, self.stock),
            (meat_finished, self.stock),
        ):
            self.assertStock(product, location, 100 if product in (fish_component, meat_component) else 0)

        sale = self.env["pos.order"].create({
            "session_id": self.session.id,
            "company_id": self.env.company.id,
            "amount_paid": 20,
            "amount_total": 20,
            "amount_tax": 0,
            "amount_return": 0,
            "state": "paid",
            "lines": [
                Command.create({
                    "product_id": fish_finished.id,
                    "qty": 1,
                    "price_unit": 10,
                    "price_subtotal": 10,
                    "price_subtotal_incl": 10,
                }),
                Command.create({
                    "product_id": meat_finished.id,
                    "qty": 1,
                    "price_unit": 10,
                    "price_subtotal": 10,
                    "price_subtotal_incl": 10,
                }),
            ],
        })
        sale._create_order_picking()
        fish_line = sale.lines.filtered(lambda line: line.product_id == fish_finished)
        meat_line = sale.lines.filtered(lambda line: line.product_id == meat_finished)
        self.assertEqual(fish_line.mrp_production_ids.location_dest_id, fish_location)
        self.assertEqual(meat_line.mrp_production_ids.location_dest_id, meat_location)
        self.assertEqual(
            sale.picking_ids.move_ids.filtered(lambda move: move.product_id == fish_finished).location_id,
            fish_location,
        )
        self.assertEqual(
            sale.picking_ids.move_ids.filtered(lambda move: move.product_id == meat_finished).location_id,
            meat_location,
        )
        self.assertStock(fish_component, fish_location, 98)
        self.assertStock(meat_component, meat_location, 98)
        self.assertStock(fish_finished, fish_location, 0)
        self.assertStock(meat_finished, meat_location, 0)
        self.assertStock(fish_finished, self.stock, 0)
        self.assertStock(meat_finished, self.stock, 0)

        refund = self.env["pos.order"].create({
            "session_id": self.session.id,
            "company_id": self.env.company.id,
            "amount_paid": -20,
            "amount_total": -20,
            "amount_tax": 0,
            "amount_return": 0,
            "state": "paid",
            "is_refund": True,
            "lines": [
                Command.create({
                    "product_id": fish_finished.id,
                    "qty": -1,
                    "price_unit": 10,
                    "price_subtotal": -10,
                    "price_subtotal_incl": -10,
                    "refunded_orderline_id": fish_line.id,
                }),
                Command.create({
                    "product_id": meat_finished.id,
                    "qty": -1,
                    "price_unit": 10,
                    "price_subtotal": -10,
                    "price_subtotal_incl": -10,
                    "refunded_orderline_id": meat_line.id,
                }),
            ],
        })
        refund._create_order_picking()
        return_moves = refund.picking_ids.move_ids
        self.assertEqual(
            return_moves.filtered(lambda move: move.product_id == fish_finished).location_dest_id,
            fish_location,
        )
        self.assertEqual(
            return_moves.filtered(lambda move: move.product_id == meat_finished).location_dest_id,
            meat_location,
        )
        self.assertEqual(fish_line.pos_auto_mrp_allocation_ids.unbuild_id.location_id, fish_location)
        self.assertEqual(meat_line.pos_auto_mrp_allocation_ids.unbuild_id.location_id, meat_location)
        self.assertStock(fish_component, fish_location, 100)
        self.assertStock(meat_component, meat_location, 100)
        self.assertStock(fish_finished, fish_location, 0)
        self.assertStock(meat_finished, meat_location, 0)
        self.assertStock(fish_finished, self.stock, 0)
        self.assertStock(meat_finished, self.stock, 0)

    def test_pos_refund_uses_recorded_legacy_finished_move_location(self):
        component, finished, section_location = self._create_routed_pos_product(
            "Historical Section"
        )
        self.config.auto_create_mrp_from_pos = False
        sale = self.env["pos.order"].create({
            "session_id": self.session.id,
            "company_id": self.env.company.id,
            "amount_paid": 10,
            "amount_total": 10,
            "amount_tax": 0,
            "amount_return": 0,
            "state": "paid",
            "lines": [Command.create({
                "product_id": finished.id,
                "qty": 1,
                "price_unit": 10,
                "price_subtotal": 10,
                "price_subtotal_incl": 10,
            })],
        })
        bom = sale._find_manufacturing_bom(finished, sale.company_id)
        production = self.env["mrp.production"].create({
            "product_id": finished.id,
            "product_qty": 1,
            "product_uom_id": finished.uom_id.id,
            "bom_id": bom.id,
            "company_id": sale.company_id.id,
            "picking_type_id": sale._get_mrp_picking_type(bom, sale.company_id).id,
            "location_src_id": section_location.id,
            "location_dest_id": self.stock.id,
            "pos_order_id": sale.id,
            "pos_order_line_id": sale.lines.id,
            "pos_order_line_ids": [Command.set(sale.lines.ids)],
            "pos_auto_mrp_generated": True,
        })
        sale.lines.write({
            "mrp_production_id": production.id,
            "mrp_production_ids": [Command.link(production.id)],
        })
        production.action_confirm()
        production.action_assign()
        production.qty_producing = 1
        production.move_raw_ids.picked = True
        production.button_mark_done()
        self.assertEqual(production.move_finished_ids.location_dest_id, self.stock)
        self.assertStock(component, section_location, 98)
        self.assertStock(finished, self.stock, 1)
        sale._create_order_picking()
        self.assertEqual(sale.picking_ids.move_ids.location_id, self.stock)
        self.assertStock(finished, self.stock, 0)

        self.config.auto_create_mrp_from_pos = True
        refund = self.env["pos.order"].create({
            "session_id": self.session.id,
            "company_id": self.env.company.id,
            "amount_paid": -10,
            "amount_total": -10,
            "amount_tax": 0,
            "amount_return": 0,
            "state": "paid",
            "is_refund": True,
            "lines": [Command.create({
                "product_id": finished.id,
                "qty": -1,
                "price_unit": 10,
                "price_subtotal": -10,
                "price_subtotal_incl": -10,
                "refunded_orderline_id": sale.lines.id,
            })],
        })
        refund._create_order_picking()
        allocation = refund.lines.pos_auto_mrp_refund_allocation_ids
        self.assertEqual(refund.picking_ids.move_ids.location_dest_id, self.stock)
        self.assertEqual(allocation.unbuild_id.location_id, self.stock)
        self.assertEqual(allocation.unbuild_id.location_dest_id, section_location)
        self.assertStock(component, section_location, 100)
        self.assertStock(finished, section_location, 0)
        self.assertStock(finished, self.stock, 0)
