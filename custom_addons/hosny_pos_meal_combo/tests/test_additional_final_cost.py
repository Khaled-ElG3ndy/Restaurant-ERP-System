from uuid import uuid4

from odoo import Command
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "hosny_pos_meal_combo")
class TestAdditionalFinalManufacturingCost(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.warehouse = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.company.id)], limit=1
        )
        cls.stock = cls.warehouse.lot_stock_id
        cls.mrp_picking_type = cls.env["stock.picking.type"].search(
            [("code", "=", "mrp_operation"), ("company_id", "=", cls.company.id)],
            limit=1,
        )
        analytic_account = cls.env["account.analytic.account"].search(
            [
                "|",
                ("company_id", "=", False),
                ("company_id", "=", cls.company.id),
            ],
            limit=1,
        )
        if not analytic_account:
            analytic_plan = cls.env["account.analytic.plan"].search([], limit=1)
            analytic_account = cls.env["account.analytic.account"].create({
                "name": "Additional Final Cost Test",
                "plan_id": analytic_plan.id,
                "company_id": cls.company.id,
            })
        cls.config = cls.env["pos.config"].create({
            "name": "Additional Final Cost Test",
            "company_id": cls.company.id,
            "analytic_account_id": analytic_account.id,
        })
        cls.session = cls.env["pos.session"].create({
            "config_id": cls.config.id,
            "user_id": cls.env.user.id,
        })
        cls.session.action_pos_session_open()

    def _make_manufactured_product(self, name, manufacturing_cost):
        component = self.env["product.product"].create({
            "name": "%s component" % name,
            "is_storable": True,
            "standard_price": manufacturing_cost,
        })
        finished = self.env["product.product"].create({
            "name": name,
            "is_storable": True,
            "sale_ok": True,
            "available_in_pos": True,
            # This is fixture data only.  The implementation reads the MO
            # finished-move valuation and never writes this field.
            "standard_price": manufacturing_cost,
        })
        self.env["stock.quant"]._update_available_quantity(component, self.stock, 10)
        bom = self.env["mrp.bom"].create({
            "product_tmpl_id": finished.product_tmpl_id.id,
            "product_id": finished.id,
            "product_qty": 1,
            "product_uom_id": finished.uom_id.id,
            "type": "normal",
            "bom_line_ids": [Command.create({
                "product_id": component.id,
                "product_qty": 1,
                "product_uom_id": component.uom_id.id,
            })],
        })
        return finished, bom

    def _make_pos_order(self, lines, is_refund=False):
        total = sum(line["price_subtotal"] for line in lines)
        return self.env["pos.order"].create({
            "session_id": self.session.id,
            "company_id": self.company.id,
            "amount_paid": -total if is_refund else total,
            "amount_total": -total if is_refund else total,
            "amount_tax": 0.0,
            "amount_return": 0.0,
            "state": "paid",
            "is_refund": is_refund,
            "lines": [Command.create(line) for line in lines],
        })

    def _make_pos_mo(self, line, product, bom, quantity=None):
        production = self.env["mrp.production"].create({
            "product_id": product.id,
            "product_qty": quantity or abs(line.qty),
            "product_uom_id": product.uom_id.id,
            "bom_id": bom.id,
            "company_id": self.company.id,
            "picking_type_id": self.mrp_picking_type.id,
            "location_src_id": self.stock.id,
            "location_dest_id": self.stock.id,
            "pos_order_id": line.order_id.id,
            "pos_order_line_id": line.id,
            "pos_order_line_ids": [Command.set(line.ids)],
            "pos_auto_mrp_generated": True,
        })
        line.write({
            "mrp_production_id": production.id,
            "mrp_production_ids": [Command.link(production.id)],
        })
        return production

    def _finish_pos_mo(self, line, product, bom, quantity=None):
        production = self._make_pos_mo(
            line,
            product,
            bom,
            quantity=quantity,
        )
        production.action_confirm()
        production.action_assign()
        production.qty_producing = production.product_qty
        production.move_raw_ids.write({"quantity": production.product_qty, "picked": True})
        production.button_mark_done()
        self.assertEqual(production.state, "done")
        return production

    def test_sale_and_refund_allocate_all_secondary_mo_costs_once(self):
        """The visible parent gets 12 + 5; the hidden child never duplicates it."""
        parent_product, parent_bom = self._make_manufactured_product(
            "Shrimp Molokhia", 12.0
        )
        extra_product, extra_bom = self._make_manufactured_product(
            "Plain Molokhia", 5.0
        )
        extra_rule = self.env["product.additional.final.line"].create({
            "parent_product_tmpl_id": parent_product.product_tmpl_id.id,
            "product_id": extra_product.id,
            "quantity": 1.0,
            "uom_id": extra_product.uom_id.id,
            "price_unit": 2.0,
        })
        self.assertAlmostEqual(
            parent_product.product_tmpl_id.final_cost_with_additional_products,
            17.0,
        )
        product_action = (
            parent_product.product_tmpl_id.action_open_additional_cost_breakdown()
        )
        self.assertEqual(
            product_action["views"],
            [(product_action["view_id"], "form")],
        )
        product_wizard = self.env[product_action["res_model"]].browse(
            product_action["res_id"]
        )
        self.assertTrue(product_wizard.is_product_configuration)
        self.assertTrue(product_wizard.breakdown_complete)
        self.assertFalse(product_wizard.order_reference)
        self.assertEqual(product_wizard.parent_product_name, parent_product.display_name)
        self.assertAlmostEqual(product_wizard.base_product_cost, 12.0)
        self.assertAlmostEqual(product_wizard.final_product_cost, 17.0)
        self.assertEqual(len(product_wizard.line_ids), 1)
        self.assertEqual(product_wizard.line_ids.product_id, extra_product)
        self.assertAlmostEqual(product_wizard.line_ids.quantity, 1.0)
        self.assertAlmostEqual(product_wizard.line_ids.unit_cost, 5.0)
        self.assertAlmostEqual(product_wizard.line_ids.total_cost, 5.0)
        self.assertAlmostEqual(
            sum(product_wizard.line_ids.mapped("total_cost")),
            product_wizard.total_additional_cost,
        )
        self.assertAlmostEqual(
            product_wizard.base_product_cost
            + product_wizard.total_additional_cost,
            product_wizard.final_product_cost,
        )
        parent_uuid = str(uuid4())
        sale = self._make_pos_order([
            {
                "name": "Shrimp Molokhia",
                "product_id": parent_product.id,
                "qty": 1.0,
                "price_unit": 30.0,
                "price_subtotal": 30.0,
                "price_subtotal_incl": 30.0,
                "uuid": parent_uuid,
                "is_additional_final_parent": True,
            },
            {
                "name": "Plain Molokhia",
                "product_id": extra_product.id,
                "qty": 1.0,
                "price_unit": 2.0,
                "price_subtotal": 2.0,
                "price_subtotal_incl": 2.0,
                "uuid": str(uuid4()),
                "is_additional_final_product": True,
                "additional_final_parent_uuid": parent_uuid,
                "additional_final_line_id": extra_rule.id,
            },
        ])
        parent_line = sale.lines.filtered(lambda line: line.product_id == parent_product)
        extra_line = sale.lines.filtered(lambda line: line.product_id == extra_product)
        parent_mo = self._finish_pos_mo(parent_line, parent_product, parent_bom)
        extra_mo = self._finish_pos_mo(extra_line, extra_product, extra_bom)
        sale._compute_total_cost_in_real_time()

        parent_line.invalidate_recordset()
        extra_line.invalidate_recordset()
        self.assertAlmostEqual(sum(parent_mo.move_finished_ids.mapped("value")), 12.0)
        self.assertAlmostEqual(sum(extra_mo.move_finished_ids.mapped("value")), 5.0)
        self.assertAlmostEqual(parent_line.mrp_direct_cost, 12.0)
        self.assertAlmostEqual(parent_line.additional_final_products_cost, 5.0)
        self.assertAlmostEqual(parent_line.total_cost, 17.0)
        self.assertAlmostEqual(extra_line.mrp_direct_cost, 5.0)
        self.assertAlmostEqual(extra_line.total_cost, 0.0)
        self.assertAlmostEqual(parent_line.margin, 15.0)
        self.assertAlmostEqual(extra_line.margin, 0.0)
        self.assertAlmostEqual(sale.margin, 15.0)
        self.assertEqual(extra_line.ui_cost_role, "Additional Product")
        self.assertFalse(extra_line.ui_product_cost)
        self.assertFalse(extra_line.ui_total_cost)
        self.assertFalse(extra_line.ui_margin)

        action = parent_line.action_open_additional_cost_breakdown()
        self.assertEqual(action["views"], [(action["view_id"], "form")])
        sale_wizard = self.env[action["res_model"]].browse(action["res_id"])
        self.assertTrue(sale_wizard.breakdown_complete)
        self.assertEqual(len(sale_wizard.line_ids), 1)
        self.assertEqual(sale_wizard.line_ids.product_id, extra_product)
        self.assertEqual(sale_wizard.line_ids.production_name, extra_mo.name)
        self.assertEqual(sale_wizard.line_ids.production_state, "done")
        self.assertAlmostEqual(sale_wizard.line_ids.quantity, 1.0)
        self.assertAlmostEqual(sale_wizard.line_ids.unit_cost, 5.0)
        self.assertAlmostEqual(sale_wizard.line_ids.total_cost, 5.0)
        self.assertAlmostEqual(
            sum(sale_wizard.line_ids.mapped("total_cost")),
            parent_line.additional_final_products_cost,
        )

        refund = self._make_pos_order([
            {
                "name": "Shrimp Molokhia refund",
                "product_id": parent_product.id,
                "qty": -1.0,
                "price_unit": 30.0,
                "price_subtotal": 30.0,
                "price_subtotal_incl": 30.0,
                "uuid": str(uuid4()),
                "is_additional_final_parent": True,
                "refunded_orderline_id": parent_line.id,
            },
            {
                "name": "Plain Molokhia refund",
                "product_id": extra_product.id,
                "qty": -1.0,
                "price_unit": 2.0,
                "price_subtotal": 2.0,
                "price_subtotal_incl": 2.0,
                "uuid": str(uuid4()),
                "is_additional_final_product": True,
                "additional_final_parent_uuid": parent_uuid,
                "additional_final_line_id": extra_rule.id,
                "refunded_orderline_id": extra_line.id,
            },
        ], is_refund=True)
        refund._compute_total_cost_in_real_time()
        refund.lines._additional_final_refresh_bundle_costs()
        refund_parent = refund.lines.filtered(lambda line: line.product_id == parent_product)
        refund_extra = refund.lines.filtered(lambda line: line.product_id == extra_product)

        self.assertAlmostEqual(refund_parent.mrp_direct_cost, -12.0)
        self.assertAlmostEqual(refund_parent.additional_final_products_cost, -5.0)
        self.assertAlmostEqual(refund_parent.total_cost, -17.0)
        self.assertAlmostEqual(refund_extra.mrp_direct_cost, -5.0)
        self.assertAlmostEqual(refund_extra.total_cost, 0.0)
        self.assertAlmostEqual(refund_parent.margin, -15.0)
        self.assertAlmostEqual(refund_extra.margin, 0.0)
        self.assertAlmostEqual(refund.margin, -15.0)

        refund_action = refund_parent.action_open_additional_cost_breakdown()
        refund_wizard = self.env[refund_action["res_model"]].browse(
            refund_action["res_id"]
        )
        self.assertTrue(refund_wizard.breakdown_complete)
        self.assertEqual(len(refund_wizard.line_ids), 1)
        self.assertEqual(refund_wizard.line_ids.production_name, extra_mo.name)
        self.assertAlmostEqual(refund_wizard.line_ids.quantity, -1.0)
        self.assertAlmostEqual(refund_wizard.line_ids.unit_cost, 5.0)
        self.assertAlmostEqual(refund_wizard.line_ids.total_cost, -5.0)
        self.assertAlmostEqual(
            sum(refund_wizard.line_ids.mapped("total_cost")),
            refund_parent.additional_final_products_cost,
        )

        self.env.flush_all()
        self.env["report.pos.order"].init()
        sale_report = self.env["report.pos.order"].search(
            [("order_id", "=", sale.id)], order="id"
        )
        refund_report = self.env["report.pos.order"].search(
            [("order_id", "=", refund.id)], order="id"
        )
        self.assertAlmostEqual(
            sale_report.filtered(lambda row: row.product_id == parent_product).margin,
            15.0,
        )
        self.assertAlmostEqual(
            sale_report.filtered(lambda row: row.product_id == extra_product).margin,
            0.0,
        )
        self.assertAlmostEqual(
            refund_report.filtered(lambda row: row.product_id == parent_product).margin,
            -15.0,
        )
        self.assertAlmostEqual(
            refund_report.filtered(lambda row: row.product_id == extra_product).margin,
            0.0,
        )
        self.assertEqual(parent_product.standard_price, 12.0)
        self.assertEqual(extra_product.standard_price, 5.0)

    def test_multiple_secondary_products_and_partial_refund_are_prorated(self):
        """Any number of secondary MOs is allocated once and by returned qty."""
        parent_product, parent_bom = self._make_manufactured_product("Bundle", 12.0)
        first_extra, first_bom = self._make_manufactured_product("First extra", 5.0)
        second_extra, second_bom = self._make_manufactured_product("Second extra", 3.0)
        parent_uuid = str(uuid4())
        sale = self._make_pos_order([
            {
                "name": "Bundle",
                "product_id": parent_product.id,
                "qty": 2.0,
                "price_unit": 40.0,
                "price_subtotal": 80.0,
                "price_subtotal_incl": 80.0,
                "uuid": parent_uuid,
                "is_additional_final_parent": True,
            },
            {
                "name": "First extra",
                "product_id": first_extra.id,
                "qty": 4.0,
                "price_unit": 0.0,
                "price_subtotal": 0.0,
                "price_subtotal_incl": 0.0,
                "uuid": str(uuid4()),
                "is_additional_final_product": True,
                "additional_final_parent_uuid": parent_uuid,
            },
            {
                "name": "Second extra",
                "product_id": second_extra.id,
                "qty": 4.0,
                "price_unit": 0.0,
                "price_subtotal": 0.0,
                "price_subtotal_incl": 0.0,
                "uuid": str(uuid4()),
                "is_additional_final_product": True,
                "additional_final_parent_uuid": parent_uuid,
            },
        ])
        parent_line = sale.lines.filtered(lambda line: line.product_id == parent_product)
        first_line = sale.lines.filtered(lambda line: line.product_id == first_extra)
        second_line = sale.lines.filtered(lambda line: line.product_id == second_extra)
        self._finish_pos_mo(parent_line, parent_product, parent_bom)
        first_mos = self._finish_pos_mo(
            first_line, first_extra, first_bom, quantity=2.0
        )
        first_mos |= self._finish_pos_mo(
            first_line, first_extra, first_bom, quantity=2.0
        )
        self._finish_pos_mo(second_line, second_extra, second_bom)
        sale._compute_total_cost_in_real_time()

        self.assertAlmostEqual(parent_line.mrp_direct_cost, 24.0)
        self.assertAlmostEqual(parent_line.additional_final_products_cost, 32.0)
        self.assertAlmostEqual(parent_line.total_cost, 56.0)
        self.assertAlmostEqual(first_line.total_cost, 0.0)
        self.assertAlmostEqual(second_line.total_cost, 0.0)

        refund = self._make_pos_order([
            {
                "name": "Bundle partial refund",
                "product_id": parent_product.id,
                "qty": -1.0,
                "price_unit": 40.0,
                "price_subtotal": 40.0,
                "price_subtotal_incl": 40.0,
                "uuid": str(uuid4()),
                "is_additional_final_parent": True,
                "refunded_orderline_id": parent_line.id,
            },
            {
                "name": "First extra partial refund",
                "product_id": first_extra.id,
                "qty": -2.0,
                "price_unit": 0.0,
                "price_subtotal": 0.0,
                "price_subtotal_incl": 0.0,
                "uuid": str(uuid4()),
                "is_additional_final_product": True,
                "additional_final_parent_uuid": parent_uuid,
                "refunded_orderline_id": first_line.id,
            },
            {
                "name": "Second extra partial refund",
                "product_id": second_extra.id,
                "qty": -2.0,
                "price_unit": 0.0,
                "price_subtotal": 0.0,
                "price_subtotal_incl": 0.0,
                "uuid": str(uuid4()),
                "is_additional_final_product": True,
                "additional_final_parent_uuid": parent_uuid,
                "refunded_orderline_id": second_line.id,
            },
        ], is_refund=True)
        refund._compute_total_cost_in_real_time()
        refund.lines._additional_final_refresh_bundle_costs()
        refund_parent = refund.lines.filtered(lambda line: line.product_id == parent_product)

        # Half of every independently-valued MO is reflected on the refund
        # parent: -12 + (-10) + (-6) = -28.
        self.assertAlmostEqual(refund_parent.mrp_direct_cost, -12.0)
        self.assertAlmostEqual(refund_parent.additional_final_products_cost, -16.0)
        self.assertAlmostEqual(refund_parent.total_cost, -28.0)
        self.assertTrue(all(
            line.total_cost == 0.0
            for line in refund.lines.filtered("is_additional_final_product")
        ))

        sale_action = parent_line.action_open_additional_cost_breakdown()
        sale_wizard = self.env[sale_action["res_model"]].browse(
            sale_action["res_id"]
        )
        self.assertTrue(sale_wizard.breakdown_complete)
        self.assertEqual(len(sale_wizard.line_ids), 3)
        self.assertEqual(
            set(sale_wizard.line_ids.mapped("product_id")),
            {first_extra, second_extra},
        )
        first_rows = sale_wizard.line_ids.filtered(
            lambda row: row.product_id == first_extra
        )
        self.assertEqual(len(first_rows), 2)
        self.assertEqual(set(first_rows.mapped("production_name")), set(first_mos.mapped("name")))
        self.assertAlmostEqual(
            sum(sale_wizard.line_ids.mapped("total_cost")),
            parent_line.additional_final_products_cost,
        )

        refund_action = refund_parent.action_open_additional_cost_breakdown()
        refund_wizard = self.env[refund_action["res_model"]].browse(
            refund_action["res_id"]
        )
        self.assertEqual(len(refund_wizard.line_ids), 3)
        self.assertAlmostEqual(
            sum(refund_wizard.line_ids.mapped("total_cost")),
            refund_parent.additional_final_products_cost,
        )

    def test_display_without_additional_products_and_with_pending_mo(self):
        """Ordinary lines show a dash; pending extra MOs never look cost-free."""
        ordinary_product = self.env["product.product"].create({
            "name": "Ordinary POS product",
            "sale_ok": True,
            "available_in_pos": True,
        })
        ordinary_order = self._make_pos_order([{
            "name": ordinary_product.name,
            "product_id": ordinary_product.id,
            "qty": 1.0,
            "price_unit": 10.0,
            "price_subtotal": 10.0,
            "price_subtotal_incl": 10.0,
            "uuid": str(uuid4()),
            "total_cost": 4.0,
            "is_total_cost_computed": True,
        }])
        ordinary_line = ordinary_order.lines
        self.assertEqual(ordinary_line.ui_additional_products_cost, "—")
        self.assertFalse(ordinary_line.ui_has_additional_products)
        self.assertTrue(ordinary_line.ui_product_cost)
        self.assertTrue(ordinary_line.ui_total_cost)

        parent_product, parent_bom = self._make_manufactured_product(
            "Pending bundle", 12.0
        )
        extra_product, extra_bom = self._make_manufactured_product(
            "Pending extra", 5.0
        )
        parent_uuid = str(uuid4())
        pending_order = self._make_pos_order([
            {
                "name": parent_product.name,
                "product_id": parent_product.id,
                "qty": 1.0,
                "price_unit": 30.0,
                "price_subtotal": 30.0,
                "price_subtotal_incl": 30.0,
                "uuid": parent_uuid,
                "is_additional_final_parent": True,
            },
            {
                "name": extra_product.name,
                "product_id": extra_product.id,
                "qty": 1.0,
                "price_unit": 0.0,
                "price_subtotal": 0.0,
                "price_subtotal_incl": 0.0,
                "uuid": str(uuid4()),
                "is_additional_final_product": True,
                "additional_final_parent_uuid": parent_uuid,
            },
        ])
        pending_parent = pending_order.lines.filtered(
            lambda line: line.product_id == parent_product
        )
        pending_child = pending_order.lines.filtered(
            lambda line: line.product_id == extra_product
        )
        pending_mo = self._make_pos_mo(pending_child, extra_product, extra_bom)
        self._finish_pos_mo(pending_parent, parent_product, parent_bom)
        pending_order._compute_total_cost_in_real_time()

        self.assertEqual(pending_mo.state, "draft")
        self.assertTrue(pending_parent.ui_has_additional_products)
        self.assertEqual(
            pending_parent.ui_additional_products_cost,
            "Not Computed Yet",
        )
        self.assertEqual(pending_parent.ui_total_cost, "Not Computed Yet")
        self.assertEqual(pending_child.ui_cost_role, "Additional Product")
        self.assertFalse(pending_child.ui_total_cost)
        self.assertFalse(pending_child.ui_margin)

        action = pending_parent.action_open_additional_cost_breakdown()
        wizard = self.env[action["res_model"]].browse(action["res_id"])
        self.assertFalse(wizard.breakdown_complete)
        self.assertEqual(len(wizard.line_ids), 1)
        self.assertEqual(wizard.line_ids.production_name, pending_mo.name)
        self.assertEqual(wizard.line_ids.production_state, "pending")
        self.assertFalse(wizard.line_ids.cost_computed)
        self.assertEqual(wizard.line_ids.unit_cost_display, "Not Computed Yet")
        self.assertEqual(wizard.total_additional_cost_display, "Not Computed Yet")
