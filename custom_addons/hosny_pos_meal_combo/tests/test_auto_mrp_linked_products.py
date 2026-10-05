from uuid import uuid4

from odoo import Command
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "hosny_pos_meal_combo")
class TestAutoMrpLinkedProducts(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.warehouse = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.company.id)], limit=1
        )
        cls.stock = cls.warehouse.lot_stock_id
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
                "name": "Auto MRP Linked Products Test",
                "plan_id": analytic_plan.id,
                "company_id": cls.company.id,
            })
        cls.config = cls.env["pos.config"].create({
            "name": "Auto MRP Linked Products Test",
            "company_id": cls.company.id,
            "analytic_account_id": analytic_account.id,
            "auto_create_mrp_from_pos": True,
            "auto_done_mrp_from_pos": True,
        })
        cls.session = cls.env["pos.session"].create({
            "config_id": cls.config.id,
            "user_id": cls.env.user.id,
        })
        cls.session.action_pos_session_open()
        cls.partner = cls.env["res.partner"].create({
            "name": "Auto MRP Linked Products Customer",
        })

    def _make_manufactured_product(self, name, cost, storable_finished=True):
        component = self.env["product.product"].create({
            "name": "%s component" % name,
            "is_storable": True,
            "standard_price": cost,
        })
        finished = self.env["product.product"].create({
            "name": name,
            "type": "consu",
            "is_storable": storable_finished,
            "sale_ok": True,
            "available_in_pos": True,
            "standard_price": cost,
            "list_price": cost * 3,
        })
        self.env["stock.quant"]._update_available_quantity(component, self.stock, 100)
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

    def _link_additional_product(self, parent, linked, quantity=1.0):
        return self.env["product.additional.final.line"].create({
            "parent_product_tmpl_id": parent.product_tmpl_id.id,
            "product_id": linked.id,
            "quantity": quantity,
            "uom_id": linked.uom_id.id,
            "price_unit": 0.0,
        })

    def _assert_line_has_single_mo_for(self, line, product, qty):
        productions = (line.mrp_production_id | line.mrp_production_ids).filtered(
            lambda production: production.product_id == product
            and production.pos_auto_mrp_generated
        )
        self.assertEqual(len(productions), 1)
        self.assertEqual(productions.product_id, product)
        self.assertAlmostEqual(productions.product_qty, qty)
        return productions

    def test_pos_creates_mo_for_consumable_parent_and_linked_products(self):
        parent, _parent_bom = self._make_manufactured_product(
            "Consumable POS parent with BOM",
            7.0,
            storable_finished=False,
        )
        linked, _linked_bom = self._make_manufactured_product(
            "Linked POS product with BOM",
            3.0,
        )
        rule = self._link_additional_product(parent, linked, quantity=2.0)
        parent_uuid = str(uuid4())
        order = self.env["pos.order"].create({
            "session_id": self.session.id,
            "company_id": self.company.id,
            "amount_paid": 21.0,
            "amount_total": 21.0,
            "amount_tax": 0.0,
            "amount_return": 0.0,
            "state": "paid",
            "lines": [
                Command.create({
                    "name": parent.name,
                    "product_id": parent.id,
                    "qty": 1.0,
                    "price_unit": 21.0,
                    "price_subtotal": 21.0,
                    "price_subtotal_incl": 21.0,
                    "uuid": parent_uuid,
                    "is_additional_final_parent": True,
                }),
                Command.create({
                    "name": linked.name,
                    "product_id": linked.id,
                    "qty": 2.0,
                    "price_unit": 0.0,
                    "price_subtotal": 0.0,
                    "price_subtotal_incl": 0.0,
                    "uuid": str(uuid4()),
                    "is_additional_final_product": True,
                    "additional_final_parent_uuid": parent_uuid,
                    "additional_final_line_id": rule.id,
                }),
            ],
        })

        order._create_order_picking()

        parent_line = order.lines.filtered(lambda line: line.product_id == parent)
        linked_line = order.lines.filtered(lambda line: line.product_id == linked)
        self._assert_line_has_single_mo_for(parent_line, parent, 1.0)
        self._assert_line_has_single_mo_for(linked_line, linked, 2.0)
        self.assertEqual(
            set(order.lines.mapped("mrp_production_ids").mapped("product_id")),
            {parent, linked},
        )

    def test_sales_creates_mo_for_parent_line_and_configured_linked_products(self):
        parent, _parent_bom = self._make_manufactured_product(
            "Consumable Sales parent with BOM",
            8.0,
            storable_finished=False,
        )
        linked, _linked_bom = self._make_manufactured_product(
            "Linked Sales product with BOM",
            4.0,
        )
        self._link_additional_product(parent, linked, quantity=1.0)
        self._link_additional_product(parent, linked, quantity=2.0)
        sale = self.env["sale.order"].create({
            "partner_id": self.partner.id,
            "order_line": [Command.create({
                "product_id": parent.id,
                "product_uom_qty": 2.0,
                "product_uom_id": parent.uom_id.id,
                "price_unit": 24.0,
            })],
        })

        sale.action_confirm()

        productions = sale.order_line.mrp_production_ids.sorted("product_id")
        self.assertEqual(len(productions), 2)
        self.assertEqual(set(productions.mapped("product_id")), {parent, linked})
        self.assertAlmostEqual(
            productions.filtered(lambda production: production.product_id == parent).product_qty,
            2.0,
        )
        self.assertAlmostEqual(
            productions.filtered(lambda production: production.product_id == linked).product_qty,
            6.0,
        )
